"""Regressions for the findings of the 2026-08-03 adversarial review.

Each test here corresponds to a vulnerability that was live and is now closed.
None of them should ever be deleted without understanding what it was for.
"""

from datetime import timedelta

import pytest

from app.extensions import db
from app.models import RefreshToken, User, utcnow
from app.utils.tokens import hash_refresh_token


def register(client, email="reader@example.com", password="correct-horse-battery"):
    return client.post(
        "/api/v1/auth/register",
        json={"email": email, "password": password, "display_name": "Reader"},
    )


# ── 1. Lockout was an account-existence oracle ─────────────────────────────


def test_locked_account_is_indistinguishable_from_a_wrong_password(client):
    """A distinct 423 let nine wrong guesses prove whether an address exists,
    and was a large timing outlier because it returned before any hashing."""
    register(client)
    for _ in range(9):
        client.post(
            "/api/v1/auth/login",
            json={"email": "reader@example.com", "password": "wrong-password-here"},
        )

    locked = client.post(
        "/api/v1/auth/login",
        json={"email": "reader@example.com", "password": "correct-horse-battery"},
    )
    unknown = client.post(
        "/api/v1/auth/login",
        json={"email": "nobody@example.com", "password": "correct-horse-battery"},
    )

    assert locked.status_code == unknown.status_code == 401
    assert locked.get_json() == unknown.get_json()


# ── 2. ?client=native exfiltrated the httpOnly refresh cookie ──────────────


def test_client_native_cannot_convert_a_cookie_session_into_a_body_token(client):
    """Same-origin JS could append ?client=native to a refresh call and read the
    30-day refresh token out of the response — httpOnly bought nothing."""
    register(client)
    csrf = client.get_cookie("csrf_token").value

    response = client.post(
        "/api/v1/auth/refresh?client=native", headers={"X-CSRF-Token": csrf}
    )

    assert response.status_code == 200
    assert "refresh_token" not in response.get_json()["data"]
    # And the rotated token must still be delivered as a cookie, or the browser
    # would keep presenting the old (now revoked) one and trip theft detection.
    assert any(c.startswith("live_msc_refresh=") for c in response.headers.getlist("Set-Cookie"))


def test_a_real_native_client_still_gets_its_token_in_the_body(client):
    """The fix must not break native clients, which have no cookie jar."""
    response = client.post(
        "/api/v1/auth/register?client=native",
        json={"email": "native@example.com", "password": "correct-horse-battery",
              "display_name": "Native"},
    )
    assert response.status_code == 201
    assert response.get_json()["data"]["refresh_token"]


# ── 3. Refresh rotation had no atomic claim ────────────────────────────────


def test_the_second_rotation_of_one_token_is_treated_as_theft(app, client):
    """Read-then-write let two concurrent refreshes both succeed, so the family
    was never revoked. The claim is now a single conditional UPDATE."""
    from app.utils.tokens import TokenError, rotate_refresh_token

    register(client, email="race@example.com")
    raw = client.get_cookie("live_msc_refresh", path="/api/v1/auth").value

    user, _first = rotate_refresh_token(db.session, raw)
    db.session.commit()
    assert user is not None

    # A second claim on the same token — what the losing side of the race does.
    with pytest.raises(TokenError):
        rotate_refresh_token(db.session, raw)

    live = (
        db.session.query(RefreshToken)
        .join(User, User.id == RefreshToken.user_id)
        .filter(User.email == "race@example.com", RefreshToken.revoked_at.is_(None))
        .count()
    )
    assert live == 0, "the whole family must be revoked when a token is claimed twice"


def test_replaying_an_expired_token_also_revokes_the_family(app, client):
    """An expired token turning up is the same leak signal as a rotated one."""
    from app.utils.tokens import TokenError, rotate_refresh_token

    register(client, email="stale@example.com")
    raw = client.get_cookie("live_msc_refresh", path="/api/v1/auth").value

    row = (
        db.session.query(RefreshToken)
        .filter(RefreshToken.token_hash == hash_refresh_token(raw))
        .one()
    )
    row.expires_at = utcnow() - timedelta(minutes=1)
    db.session.commit()

    with pytest.raises(TokenError):
        rotate_refresh_token(db.session, raw)

    db.session.refresh(row)
    assert row.revoked_at is not None


# ── 4. Access tokens survived logout-all and lockout ───────────────────────


def test_sign_out_everywhere_kills_the_access_token_immediately(client):
    """This is the control someone uses when a device is stolen. Revoking only
    refresh tokens left the thief authenticated for the token's full life."""
    token = register(client, email="stolen@example.com").get_json()["data"]["access_token"]
    headers = {"Authorization": f"Bearer {token}"}

    assert client.get("/api/v1/me", headers=headers).status_code == 200
    assert client.post("/api/v1/auth/logout-all", headers=headers).status_code == 200
    assert client.get("/api/v1/me", headers=headers).status_code == 401


def test_lockout_also_ends_sessions_already_open(client):
    token = register(client, email="locked@example.com").get_json()["data"]["access_token"]
    headers = {"Authorization": f"Bearer {token}"}
    assert client.get("/api/v1/me", headers=headers).status_code == 200

    for _ in range(9):
        client.post(
            "/api/v1/auth/login",
            json={"email": "locked@example.com", "password": "wrong-password-here"},
        )

    assert client.get("/api/v1/me", headers=headers).status_code == 401


# ── 5. TESTING=true unlocked the dev secrets in production ─────────────────


def test_testing_flag_cannot_disable_the_production_guardrails():
    """`FLASK_ENV=production TESTING=true` used to boot with a JWT secret that
    is a literal in this repo — forgeable by anyone who can read it."""
    from app.config import Config

    class ProductionWithTesting(Config):
        TESTING = True
        IS_DEVELOPMENT = False
        SECRET_KEY = "x" * 40
        JWT_SECRET = "y" * 40
        SQLALCHEMY_DATABASE_URI = "postgresql+psycopg2:///live_msc"
        RATELIMIT_STORAGE_URI = "redis://localhost:6379"

    with pytest.raises(RuntimeError, match="TESTING"):
        ProductionWithTesting.validate()


def test_production_requires_a_real_jwt_secret():
    from app.config import Config

    class Production(Config):
        TESTING = False
        IS_DEVELOPMENT = False
        SECRET_KEY = "x" * 40
        JWT_SECRET = ""
        SQLALCHEMY_DATABASE_URI = "postgresql+psycopg2:///live_msc"
        RATELIMIT_STORAGE_URI = "redis://localhost:6379"

    with pytest.raises(RuntimeError, match="JWT_SECRET"):
        Production.validate()


def test_production_rejects_a_jwt_secret_equal_to_the_app_secret():
    from app.config import Config

    class Production(Config):
        TESTING = False
        IS_DEVELOPMENT = False
        SECRET_KEY = "z" * 40
        JWT_SECRET = "z" * 40
        SQLALCHEMY_DATABASE_URI = "postgresql+psycopg2:///live_msc"
        RATELIMIT_STORAGE_URI = "redis://localhost:6379"

    with pytest.raises(RuntimeError, match="must differ"):
        Production.validate()


def test_production_rejects_an_in_memory_rate_limiter():
    """Per-process limits multiply by the worker count, so every published
    limit would silently be N times looser than it reads."""
    from app.config import Config

    class Production(Config):
        TESTING = False
        IS_DEVELOPMENT = False
        SECRET_KEY = "x" * 40
        JWT_SECRET = "y" * 40
        SQLALCHEMY_DATABASE_URI = "postgresql+psycopg2:///live_msc"
        RATELIMIT_STORAGE_URI = "memory://"

    with pytest.raises(RuntimeError, match="RATELIMIT"):
        Production.validate()


# ── Serializer default ─────────────────────────────────────────────────────


def test_serialize_user_omits_the_email_unless_asked(make_user):
    """Safe by default: a future call site must opt in to leak an address."""
    from app.routes.serializers import serialize_user

    user = make_user(email="private@example.com")
    assert "email" not in serialize_user(user)
    assert serialize_user(user, include_email=True)["email"] == "private@example.com"
