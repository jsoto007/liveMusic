"""Registration, login, refresh rotation, and the ways each can be abused."""

from app.extensions import db
from app.models import RefreshToken, User, utcnow
from app.utils.tokens import hash_refresh_token


def register(client, **overrides):
    payload = {
        "email": "reader@example.com",
        "password": "correct-horse-battery",
        "display_name": "Reader",
    }
    payload.update(overrides)
    return client.post("/api/v1/auth/register", json=payload)


def test_register_returns_access_token_and_sets_refresh_cookie(client):
    response = register(client)
    assert response.status_code == 201

    body = response.get_json()["data"]
    assert body["access_token"]
    assert body["user"]["email"] == "reader@example.com"
    # The refresh token must NOT be in the body for a browser client.
    assert "refresh_token" not in body

    cookies = response.headers.getlist("Set-Cookie")
    refresh_cookie = next(c for c in cookies if c.startswith("live_msc_refresh="))
    assert "HttpOnly" in refresh_cookie
    assert "Path=/api/v1/auth" in refresh_cookie
    # The CSRF cookie is deliberately readable — the client echoes it back.
    csrf_cookie = next(c for c in cookies if c.startswith("csrf_token="))
    assert "HttpOnly" not in csrf_cookie


def test_register_normalizes_email_case(client):
    assert register(client, email="Reader@Example.COM").status_code == 201
    # A second attempt differing only in case must collide, not create a twin.
    assert register(client, email="reader@example.com").status_code == 409


def test_register_rejects_weak_password(client):
    response = register(client, password="short")
    assert response.status_code == 400
    assert response.get_json()["error"]["code"] == "VALIDATION_ERROR"


def test_register_rejects_password_containing_email(client):
    response = register(client, email="bloodroot@example.com", password="bloodroot-choir-x")
    assert response.status_code == 400


def test_native_client_receives_refresh_token_in_body(client):
    response = client.post(
        "/api/v1/auth/register?client=native",
        json={"email": "a@example.com", "password": "correct-horse-battery",
              "display_name": "A"},
    )
    assert response.status_code == 201
    body = response.get_json()["data"]
    assert body["refresh_token"]
    assert not response.headers.getlist("Set-Cookie")


def test_login_success(client):
    register(client)
    response = client.post(
        "/api/v1/auth/login",
        json={"email": "reader@example.com", "password": "correct-horse-battery"},
    )
    assert response.status_code == 200
    assert response.get_json()["data"]["access_token"]


def test_login_is_identical_for_unknown_user_and_wrong_password(client):
    register(client)

    wrong_password = client.post(
        "/api/v1/auth/login",
        json={"email": "reader@example.com", "password": "not-the-password-x"},
    )
    unknown_user = client.post(
        "/api/v1/auth/login",
        json={"email": "nobody@example.com", "password": "not-the-password-x"},
    )

    # Identical status AND identical body — either difference enumerates the
    # user table.
    assert wrong_password.status_code == unknown_user.status_code == 401
    assert wrong_password.get_json() == unknown_user.get_json()


def test_repeated_failures_lock_the_account(client):
    register(client)
    for _ in range(8):
        client.post(
            "/api/v1/auth/login",
            json={"email": "reader@example.com", "password": "wrong-password-here"},
        )

    response = client.post(
        "/api/v1/auth/login",
        json={"email": "reader@example.com", "password": "correct-horse-battery"},
    )
    # Even the *correct* password is refused while the lock holds. The response
    # is deliberately the ordinary INVALID_CREDENTIALS one rather than a
    # distinct 423 — see test_auth_hardening.py, where a separate status was
    # shown to be an account-existence oracle.
    assert response.status_code == 401
    assert response.get_json()["error"]["code"] == "INVALID_CREDENTIALS"


def test_refresh_rotates_the_token(client):
    register(client)
    csrf = client.get_cookie("csrf_token").value
    first = client.get_cookie("live_msc_refresh", path="/api/v1/auth").value

    response = client.post("/api/v1/auth/refresh", headers={"X-CSRF-Token": csrf})
    assert response.status_code == 200

    second = client.get_cookie("live_msc_refresh", path="/api/v1/auth").value
    assert second != first, "the refresh token must rotate on every use"


def test_refresh_without_csrf_header_is_rejected(client):
    register(client)
    response = client.post("/api/v1/auth/refresh")
    assert response.status_code == 403
    assert response.get_json()["error"]["code"] == "CSRF_REQUIRED"


def test_refresh_with_mismatched_csrf_header_is_rejected(client):
    register(client)
    response = client.post("/api/v1/auth/refresh", headers={"X-CSRF-Token": "not-the-cookie"})
    assert response.status_code == 403
    assert response.get_json()["error"]["code"] == "CSRF_INVALID"


def test_reusing_a_rotated_refresh_token_kills_the_whole_family(client, app):
    """Theft detection: a token that has already been exchanged reappearing
    means a copy is in someone else's hands, so every sibling is revoked."""
    register(client)
    csrf = client.get_cookie("csrf_token").value
    stolen = client.get_cookie("live_msc_refresh", path="/api/v1/auth").value

    # Legitimate rotation.
    assert client.post("/api/v1/auth/refresh", headers={"X-CSRF-Token": csrf}).status_code == 200
    live_token = client.get_cookie("live_msc_refresh", path="/api/v1/auth").value

    # The attacker replays the old one. Note the CSRF token rotated with the
    # refresh, so read the current one — this test is about token reuse, not
    # about CSRF.
    client.set_cookie("live_msc_refresh", stolen, path="/api/v1/auth")
    replay = client.post(
        "/api/v1/auth/refresh",
        headers={"X-CSRF-Token": client.get_cookie("csrf_token").value},
    )
    assert replay.status_code == 401

    with app.app_context():
        row = (
            db.session.query(RefreshToken)
            .filter(RefreshToken.token_hash == hash_refresh_token(live_token))
            .one()
        )
        assert row.revoked_at is not None, (
            "the victim's live token must be revoked too, not just the replayed one"
        )


def test_logout_revokes_the_session(client):
    register(client)
    csrf = client.get_cookie("csrf_token").value

    assert client.post("/api/v1/auth/logout", headers={"X-CSRF-Token": csrf}).status_code == 200

    # The cookie was cleared, so refresh has nothing to present.
    response = client.post("/api/v1/auth/refresh", headers={"X-CSRF-Token": csrf})
    assert response.status_code in (401, 403)


def test_logout_all_revokes_every_session(client, app, make_user):
    register(client)
    token = client.post(
        "/api/v1/auth/login",
        json={"email": "reader@example.com", "password": "correct-horse-battery"},
    ).get_json()["data"]["access_token"]

    response = client.post(
        "/api/v1/auth/logout-all", headers={"Authorization": f"Bearer {token}"}
    )
    assert response.status_code == 200
    assert response.get_json()["data"]["sessions_revoked"] >= 2

    with app.app_context():
        live = (
            db.session.query(RefreshToken)
            .filter(RefreshToken.revoked_at.is_(None))
            .count()
        )
        assert live == 0


def test_expired_access_token_is_refused(client, app, make_user):
    import jwt

    user = make_user()
    with app.app_context():
        stale = jwt.encode(
            {
                "sub": str(user.id),
                "typ": "access",
                "iat": int(utcnow().timestamp()) - 7200,
                "exp": int(utcnow().timestamp()) - 3600,
            },
            app.config["JWT_SECRET"],
            algorithm="HS256",
        )
    response = client.get("/api/v1/me", headers={"Authorization": f"Bearer {stale}"})
    assert response.status_code == 401


def test_alg_none_token_is_refused(client, app, make_user):
    """A classic JWT downgrade: an unsigned token claiming to be an admin."""
    import jwt

    user = make_user()
    forged = jwt.encode(
        {"sub": str(user.id), "typ": "access", "role": "admin",
         "iat": int(utcnow().timestamp()), "exp": int(utcnow().timestamp()) + 3600},
        key="",
        algorithm="none",
    )
    response = client.get("/api/v1/me", headers={"Authorization": f"Bearer {forged}"})
    assert response.status_code == 401


def test_refresh_token_cannot_be_used_as_a_bearer_token(client):
    """The refresh secret is not a JWT at all, so it must not authenticate."""
    register(client)
    raw_refresh = client.get_cookie("live_msc_refresh", path="/api/v1/auth").value
    response = client.get("/api/v1/me", headers={"Authorization": f"Bearer {raw_refresh}"})
    assert response.status_code == 401


def test_deactivated_user_cannot_authenticate(client, app):
    headers_response = register(client)
    token = headers_response.get_json()["data"]["access_token"]

    with app.app_context():
        user = db.session.query(User).one()
        user.is_active = False
        db.session.commit()

    response = client.get("/api/v1/me", headers={"Authorization": f"Bearer {token}"})
    assert response.status_code == 401


def test_refresh_tokens_are_never_stored_in_the_clear(client, app):
    register(client)
    raw = client.get_cookie("live_msc_refresh", path="/api/v1/auth").value
    with app.app_context():
        rows = db.session.query(RefreshToken).all()
        assert rows
        for row in rows:
            assert row.token_hash != raw
            assert len(row.token_hash) == 64
