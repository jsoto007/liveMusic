"""Email verification, password reset, preferences, unsubscribe, notifications.

The transport is stubbed throughout — a test that reaches the network is a
flaky test, and none of these are about SMTP working.
"""

from datetime import timedelta

import pytest

from app.extensions import db
from app.models import (
    ArtistFollow,
    EmailDelivery,
    EmailKind,
    EmailToken,
    Event,
    EventInterest,
    EventStatus,
    Genre,
    RefreshToken,
    User,
    utcnow,
)


@pytest.fixture()
def outbox(monkeypatch):
    """Capture every message instead of sending it."""
    from app.services import email_service

    sent = []

    def _send(message):
        sent.append(message)
        return True

    monkeypatch.setattr(email_service, "send_email", _send)
    # notifications.py imported `deliver`, which closes over send_email in its
    # own module namespace — patch there too.
    monkeypatch.setattr("app.services.email_service.send_email", _send)
    return sent


def register(client, email="reader@example.com", password="correct-horse-battery"):
    return client.post(
        "/api/v1/auth/register",
        json={"email": email, "password": password, "display_name": "Reader"},
    )


# ── Verification ───────────────────────────────────────────────────────────


def test_registering_sends_a_confirmation_email(client, outbox):
    assert register(client).status_code == 201

    assert len(outbox) == 1
    message = outbox[0]
    assert message.to == "reader@example.com"
    assert "Confirm" in message.subject
    # Both halves always ship: some clients refuse HTML outright, and a
    # message with no text alternative scores worse with spam filters.
    assert message.html and message.text
    assert "/verify-email?token=" in message.html
    assert "/verify-email?token=" in message.text


def test_a_failed_email_does_not_fail_registration(client, monkeypatch):
    """An account whose welcome mail bounced is still an account."""
    from app.services import email_service

    def _explode(message):
        raise RuntimeError("smtp is on fire")

    monkeypatch.setattr(email_service, "send_email", _explode)
    monkeypatch.setattr("app.services.email_service.send_email", _explode)

    assert register(client).status_code == 201
    assert db.session.query(User).count() == 1


def test_the_verification_link_marks_the_address_confirmed(client, outbox):
    register(client)
    token = _token_from(outbox[0].text, "/verify-email?token=")

    response = client.post("/api/v1/auth/verify-email", json={"token": token})
    assert response.status_code == 200
    assert response.get_json()["data"]["verified"] is True

    user = db.session.query(User).one()
    assert user.email_verified_at is not None


def test_a_verification_link_works_only_once(client, outbox):
    """Mail clients prefetch links; a second click must not resurrect it."""
    register(client)
    token = _token_from(outbox[0].text, "/verify-email?token=")

    assert client.post("/api/v1/auth/verify-email", json={"token": token}).status_code == 200
    second = client.post("/api/v1/auth/verify-email", json={"token": token})
    assert second.status_code == 400
    assert second.get_json()["error"]["code"] == "INVALID_TOKEN"


def test_an_expired_verification_link_is_refused(client, outbox):
    register(client)
    token = _token_from(outbox[0].text, "/verify-email?token=")

    row = db.session.query(EmailToken).one()
    row.expires_at = utcnow() - timedelta(minutes=1)
    db.session.commit()

    assert client.post("/api/v1/auth/verify-email", json={"token": token}).status_code == 400


def test_tokens_are_never_stored_in_the_clear(client, outbox):
    register(client)
    token = _token_from(outbox[0].text, "/verify-email?token=")

    rows = db.session.query(EmailToken).all()
    assert rows
    for row in rows:
        assert row.token_hash != token
        assert len(row.token_hash) == 64


def test_resend_verification_does_not_reveal_whether_an_account_exists(client, outbox):
    register(client, email="known@example.com")
    outbox.clear()

    known = client.post(
        "/api/v1/auth/verify-email/resend", json={"email": "known@example.com"}
    )
    unknown = client.post(
        "/api/v1/auth/verify-email/resend", json={"email": "nobody@example.com"}
    )

    assert known.status_code == unknown.status_code == 200
    assert known.get_json() == unknown.get_json()
    # Only the real one actually sent anything.
    assert len(outbox) == 1


# ── Password reset ─────────────────────────────────────────────────────────


def test_forgot_password_does_not_reveal_whether_an_account_exists(client, outbox):
    register(client, email="known@example.com")
    outbox.clear()

    known = client.post("/api/v1/auth/forgot-password", json={"email": "known@example.com"})
    unknown = client.post("/api/v1/auth/forgot-password", json={"email": "nobody@example.com"})

    assert known.status_code == unknown.status_code == 200
    assert known.get_json() == unknown.get_json()
    assert len(outbox) == 1


def test_a_reset_link_sets_a_new_password_and_ends_every_session(client, outbox):
    """A reset is a security event. If it was prompted by a compromise,
    leaving the attacker's session alive defeats the whole exercise."""
    access = register(client, email="reader@example.com").get_json()["data"]["access_token"]
    headers = {"Authorization": f"Bearer {access}"}
    assert client.get("/api/v1/me", headers=headers).status_code == 200

    outbox.clear()
    client.post("/api/v1/auth/forgot-password", json={"email": "reader@example.com"})
    token = _token_from(outbox[0].text, "/reset-password?token=")

    response = client.post(
        "/api/v1/auth/reset-password",
        json={"token": token, "password": "a-brand-new-passphrase"},
    )
    assert response.status_code == 200

    # The old access token is dead immediately, not in fifteen minutes.
    assert client.get("/api/v1/me", headers=headers).status_code == 401
    live_refresh = (
        db.session.query(RefreshToken).filter(RefreshToken.revoked_at.is_(None)).count()
    )
    assert live_refresh == 0

    # And the new password works.
    assert client.post(
        "/api/v1/auth/login",
        json={"email": "reader@example.com", "password": "a-brand-new-passphrase"},
    ).status_code == 200


def test_a_reset_link_works_only_once(client, outbox):
    register(client)
    outbox.clear()
    client.post("/api/v1/auth/forgot-password", json={"email": "reader@example.com"})
    token = _token_from(outbox[0].text, "/reset-password?token=")

    first = client.post(
        "/api/v1/auth/reset-password", json={"token": token, "password": "first-new-passphrase"}
    )
    second = client.post(
        "/api/v1/auth/reset-password", json={"token": token, "password": "second-new-passphrase"}
    )
    assert first.status_code == 200
    assert second.status_code == 400


def test_requesting_a_new_reset_link_retires_the_previous_one(client, outbox):
    """Otherwise an older stolen email stays usable after the victim reacts."""
    register(client)
    outbox.clear()

    client.post("/api/v1/auth/forgot-password", json={"email": "reader@example.com"})
    first_token = _token_from(outbox[0].text, "/reset-password?token=")
    client.post("/api/v1/auth/forgot-password", json={"email": "reader@example.com"})
    second_token = _token_from(outbox[1].text, "/reset-password?token=")

    assert first_token != second_token
    stale = client.post(
        "/api/v1/auth/reset-password",
        json={"token": first_token, "password": "a-brand-new-passphrase"},
    )
    assert stale.status_code == 400


def test_a_weak_password_is_refused_at_reset(client, outbox):
    register(client)
    outbox.clear()
    client.post("/api/v1/auth/forgot-password", json={"email": "reader@example.com"})
    token = _token_from(outbox[0].text, "/reset-password?token=")

    assert client.post(
        "/api/v1/auth/reset-password", json={"token": token, "password": "short"}
    ).status_code == 400


def test_reset_marks_the_address_verified(client, outbox):
    """Reaching the mailbox proves control of the address."""
    register(client)
    outbox.clear()
    client.post("/api/v1/auth/forgot-password", json={"email": "reader@example.com"})
    token = _token_from(outbox[0].text, "/reset-password?token=")
    client.post(
        "/api/v1/auth/reset-password",
        json={"token": token, "password": "a-brand-new-passphrase"},
    )
    assert db.session.query(User).one().email_verified_at is not None


# ── Preferences and unsubscribe ────────────────────────────────────────────


def test_preferences_default_to_on(client, auth, outbox):
    headers = auth()
    prefs = client.get("/api/v1/me/email-preferences", headers=headers).get_json()["data"][
        "preferences"
    ]
    assert prefs == {
        "notify_new_shows": True,
        "notify_show_reminders": True,
        "unsubscribed_all": False,
    }


def test_a_preference_can_be_turned_off(client, auth, outbox):
    headers = auth()
    response = client.patch(
        "/api/v1/me/email-preferences", json={"notify_new_shows": False}, headers=headers
    )
    assert response.get_json()["data"]["preferences"]["notify_new_shows"] is False


def test_turning_a_category_back_on_lifts_the_master_switch(client, auth, outbox):
    """Otherwise the toggle appears to work and silently changes nothing."""
    headers = auth()
    client.patch(
        "/api/v1/me/email-preferences", json={"unsubscribed_all": True}, headers=headers
    )
    response = client.patch(
        "/api/v1/me/email-preferences", json={"notify_new_shows": True}, headers=headers
    )
    prefs = response.get_json()["data"]["preferences"]
    assert prefs["unsubscribed_all"] is False
    assert prefs["notify_new_shows"] is True


def test_one_click_unsubscribe_works_without_signing_in(client, outbox):
    """A mail provider POSTs this with no browser and no session."""
    from app.utils.email_tokens import sign_unsubscribe

    register(client)
    user = db.session.query(User).one()
    signature = sign_unsubscribe(user.id)

    response = client.post(
        f"/api/v1/email/unsubscribe?user={user.id}&sig={signature}"
    )
    assert response.status_code == 200

    db.session.refresh(user)
    assert user.unsubscribed_all_at is not None


def test_a_plain_click_asks_for_confirmation_and_changes_nothing(client, outbox):
    """GET must not mutate. Defender Safe Links, Proofpoint, Gmail's scanner
    and iOS Mail link preview all fetch URLs found in message bodies — with GET
    mutating, the reader's own mail security silently unsubscribed them."""
    from app.utils.email_tokens import sign_unsubscribe

    register(client)
    user = db.session.query(User).one()
    response = client.get(
        f"/api/v1/email/unsubscribe?user={user.id}&sig={sign_unsubscribe(user.id)}"
    )

    assert response.status_code == 200
    assert b"<form" in response.data
    db.session.refresh(user)
    assert user.unsubscribed_all_at is None, "a GET must not unsubscribe anyone"


def test_a_head_request_does_not_unsubscribe(client, outbox):
    """Flask routes HEAD alongside GET, so a bare HEAD did it too."""
    from app.utils.email_tokens import sign_unsubscribe

    register(client)
    user = db.session.query(User).one()
    client.head(f"/api/v1/email/unsubscribe?user={user.id}&sig={sign_unsubscribe(user.id)}")

    db.session.refresh(user)
    assert user.unsubscribed_all_at is None


def test_unsubscribe_requires_a_valid_signature(client, outbox):
    """Without it this is a way to unsubscribe anyone whose id you can guess."""
    register(client)
    user = db.session.query(User).one()

    response = client.get(f"/api/v1/email/unsubscribe?user={user.id}&sig=not-the-signature")
    assert response.status_code == 400

    db.session.refresh(user)
    assert user.unsubscribed_all_at is None


def test_one_users_signature_does_not_unsubscribe_another(client, outbox):
    from app.utils.email_tokens import sign_unsubscribe

    register(client, email="victim@example.com")
    register(client, email="attacker@example.com")
    victim = db.session.query(User).filter_by(email="victim@example.com").one()
    attacker = db.session.query(User).filter_by(email="attacker@example.com").one()

    response = client.get(
        f"/api/v1/email/unsubscribe?user={victim.id}&sig={sign_unsubscribe(attacker.id)}"
    )
    assert response.status_code == 400

    db.session.refresh(victim)
    assert victim.unsubscribed_all_at is None


# ── Notifications ──────────────────────────────────────────────────────────


@pytest.fixture()
def band_with_follower(client, auth, db, make_user, make_venue):
    """A band, a follower, and a signed-in owner able to post."""
    owner_headers = auth(email="band@example.com")
    artist = client.post(
        "/api/v1/me/artists", json={"name": "Bloodroot Choir"}, headers=owner_headers
    ).get_json()["data"]["artist"]

    import uuid

    artist_uuid = uuid.UUID(artist["id"])
    follower = make_user(email="fan@example.com")
    db.session.add(ArtistFollow(user_id=follower.id, artist_id=artist_uuid))
    db.session.commit()
    return owner_headers, artist, follower


def test_publishing_a_show_emails_the_bands_followers(client, band_with_follower, outbox):
    headers, artist, follower = band_with_follower
    outbox.clear()

    response = client.post(
        "/api/v1/events",
        json={
            "headline": "Bloodroot Choir",
            "artist_id": artist["id"],
            "starts_at": (utcnow() + timedelta(days=2)).isoformat(),
            "venue": {"name": "Dusk", "city": "Providence", "timezone": "America/New_York"},
            "publish": True,
        },
        headers=headers,
    )
    assert response.status_code == 201

    assert len(outbox) == 1
    assert outbox[0].to == "fan@example.com"
    assert "Bloodroot Choir" in outbox[0].html
    # Bulk mail must carry a one-click unsubscribe or providers deprioritise it.
    assert outbox[0].list_unsubscribe


def test_a_draft_does_not_email_anyone(client, band_with_follower, outbox):
    headers, artist, _follower = band_with_follower
    outbox.clear()

    client.post(
        "/api/v1/events",
        json={
            "headline": "Not ready",
            "artist_id": artist["id"],
            "starts_at": (utcnow() + timedelta(days=2)).isoformat(),
            "venue": {"name": "Dusk", "city": "Providence"},
            "publish": False,
        },
        headers=headers,
    )
    assert outbox == []


def test_a_follower_is_emailed_once_however_often_it_is_republished(
    client, band_with_follower, outbox
):
    """Publish → cancel → publish must not re-mail the list."""
    headers, artist, _follower = band_with_follower
    outbox.clear()

    event_id = client.post(
        "/api/v1/events",
        json={
            "headline": "Bloodroot Choir",
            "artist_id": artist["id"],
            "starts_at": (utcnow() + timedelta(days=2)).isoformat(),
            "venue": {"name": "Dusk", "city": "Providence"},
            "publish": False,
        },
        headers=headers,
    ).get_json()["data"]["event"]["id"]

    client.post(f"/api/v1/events/{event_id}/publish", headers=headers)
    client.post(f"/api/v1/events/{event_id}/cancel", headers=headers)
    client.post(f"/api/v1/events/{event_id}/publish", headers=headers)

    assert len(outbox) == 1


def test_an_unsubscribed_follower_is_not_emailed(client, band_with_follower, outbox, db):
    headers, artist, follower = band_with_follower
    follower.unsubscribed_all_at = utcnow()
    db.session.commit()
    outbox.clear()

    client.post(
        "/api/v1/events",
        json={
            "headline": "Bloodroot Choir",
            "artist_id": artist["id"],
            "starts_at": (utcnow() + timedelta(days=2)).isoformat(),
            "venue": {"name": "Dusk", "city": "Providence"},
            "publish": True,
        },
        headers=headers,
    )
    assert outbox == []


def test_a_follower_who_turned_off_new_shows_is_not_emailed(
    client, band_with_follower, outbox, db
):
    headers, artist, follower = band_with_follower
    follower.notify_new_shows = False
    db.session.commit()
    outbox.clear()

    client.post(
        "/api/v1/events",
        json={
            "headline": "Bloodroot Choir",
            "artist_id": artist["id"],
            "starts_at": (utcnow() + timedelta(days=2)).isoformat(),
            "venue": {"name": "Dusk", "city": "Providence"},
            "publish": True,
        },
        headers=headers,
    )
    assert outbox == []


def test_the_band_is_not_emailed_about_its_own_show(client, band_with_follower, outbox, db):
    headers, artist, _follower = band_with_follower
    import uuid

    owner = db.session.query(User).filter_by(email="band@example.com").one()
    db.session.add(ArtistFollow(user_id=owner.id, artist_id=uuid.UUID(artist["id"])))
    db.session.commit()
    outbox.clear()

    client.post(
        "/api/v1/events",
        json={
            "headline": "Bloodroot Choir",
            "artist_id": artist["id"],
            "starts_at": (utcnow() + timedelta(days=2)).isoformat(),
            "venue": {"name": "Dusk", "city": "Providence"},
            "publish": True,
        },
        headers=headers,
    )
    assert [message.to for message in outbox] == ["fan@example.com"]


# ── Reminders ──────────────────────────────────────────────────────────────


def test_reminders_go_to_people_going_tomorrow(db, make_user, make_venue, outbox):
    from app.services.notifications import send_due_show_reminders

    user = make_user(email="going@example.com")
    venue = make_venue()
    event = Event(
        venue_id=venue.id,
        headline="Bloodroot Choir",
        genre=Genre.ROCK_PUNK,
        starts_at=utcnow() + timedelta(hours=23),
        status=EventStatus.PUBLISHED,
        published_at=utcnow(),
    )
    db.session.add(event)
    db.session.flush()
    db.session.add(EventInterest(user_id=user.id, event_id=event.id, going=True))
    db.session.commit()

    result = send_due_show_reminders()
    assert result["sent"] == 1
    assert outbox[0].to == "going@example.com"


def test_a_reminder_is_sent_only_once_however_often_the_job_runs(
    db, make_user, make_venue, outbox
):
    """The scheduler window overlaps deliberately; idempotency is what makes
    that safe."""
    from app.services.notifications import send_due_show_reminders

    user = make_user(email="going@example.com")
    venue = make_venue()
    event = Event(
        venue_id=venue.id,
        headline="Bloodroot Choir",
        genre=Genre.ROCK_PUNK,
        starts_at=utcnow() + timedelta(hours=23),
        status=EventStatus.PUBLISHED,
        published_at=utcnow(),
    )
    db.session.add(event)
    db.session.flush()
    db.session.add(EventInterest(user_id=user.id, event_id=event.id, going=True))
    db.session.commit()

    send_due_show_reminders()
    send_due_show_reminders()
    send_due_show_reminders()

    assert len(outbox) == 1
    assert db.session.query(EmailDelivery).filter_by(kind=EmailKind.SHOW_REMINDER).count() == 1


def test_only_going_gets_a_reminder_not_merely_saved(db, make_user, make_venue, outbox):
    from app.services.notifications import send_due_show_reminders

    user = make_user(email="saver@example.com")
    venue = make_venue()
    event = Event(
        venue_id=venue.id,
        headline="Bloodroot Choir",
        genre=Genre.ROCK_PUNK,
        starts_at=utcnow() + timedelta(hours=23),
        status=EventStatus.PUBLISHED,
        published_at=utcnow(),
    )
    db.session.add(event)
    db.session.flush()
    db.session.add(EventInterest(user_id=user.id, event_id=event.id, saved=True, going=False))
    db.session.commit()

    assert send_due_show_reminders()["sent"] == 0


def test_a_show_far_out_gets_no_reminder_yet(db, make_user, make_venue, outbox):
    from app.services.notifications import send_due_show_reminders

    user = make_user(email="going@example.com")
    venue = make_venue()
    event = Event(
        venue_id=venue.id,
        headline="Next month",
        genre=Genre.ROCK_PUNK,
        starts_at=utcnow() + timedelta(days=20),
        status=EventStatus.PUBLISHED,
        published_at=utcnow(),
    )
    db.session.add(event)
    db.session.flush()
    db.session.add(EventInterest(user_id=user.id, event_id=event.id, going=True))
    db.session.commit()

    assert send_due_show_reminders()["sent"] == 0


def test_a_transport_failure_leaves_the_reminder_retryable(
    db, make_user, make_venue, monkeypatch
):
    """A blip must not cost the reader that notification forever."""
    from app.services.notifications import send_due_show_reminders

    user = make_user(email="going@example.com")
    venue = make_venue()
    event = Event(
        venue_id=venue.id,
        headline="Bloodroot Choir",
        genre=Genre.ROCK_PUNK,
        starts_at=utcnow() + timedelta(hours=23),
        status=EventStatus.PUBLISHED,
        published_at=utcnow(),
    )
    db.session.add(event)
    db.session.flush()
    db.session.add(EventInterest(user_id=user.id, event_id=event.id, going=True))
    db.session.commit()

    monkeypatch.setattr("app.services.email_service.send_email", lambda message: False)
    assert send_due_show_reminders()["sent"] == 0
    assert db.session.query(EmailDelivery).count() == 0, "the claim must be released"

    sent = []
    monkeypatch.setattr(
        "app.services.email_service.send_email", lambda message: sent.append(message) or True
    )
    assert send_due_show_reminders()["sent"] == 1


# ── Rendering ──────────────────────────────────────────────────────────────


@pytest.mark.parametrize(
    "template",
    ["verify_email", "reset_password", "new_show_from_followed", "show_reminder"],
)
def test_every_template_renders_both_halves(app, template):
    from app.services.email_preview import render_preview
    from app.services.email_service import render_email

    with app.test_request_context():
        html = render_preview(template)
        assert "<html" in html.lower()
        assert "Live" in html

    from app.services.email_preview import _SAMPLE_ARTIST, _SAMPLE_EVENT, _SAMPLE_USER

    with app.test_request_context():
        html, text = render_email(
            template,
            user=_SAMPLE_USER,
            artist=_SAMPLE_ARTIST,
            event=_SAMPLE_EVENT,
            site_url="https://example.test",
            unsubscribe_url="https://example.test/u",
            verify_url="https://example.test/v",
            reset_url="https://example.test/r",
            event_url="https://example.test/e",
            artist_url="https://example.test/a",
            ttl_hours=48,
            ttl_minutes=30,
        )
        assert html.strip() and text.strip()
        # The text half must not be markup.
        assert "<td" not in text


def test_links_come_from_configuration_not_the_host_header(client, outbox, app):
    """Trusting the inbound Host is how reset links end up pointing at an
    attacker's domain."""
    register(client, email="reader@example.com")
    outbox.clear()

    client.post(
        "/api/v1/auth/forgot-password",
        json={"email": "reader@example.com"},
        headers={"Host": "evil.example"},
    )

    assert outbox
    assert "evil.example" not in outbox[0].html
    assert "evil.example" not in outbox[0].text


def _token_from(text: str, marker: str) -> str:
    """Pull a token out of a rendered message body."""
    index = text.index(marker) + len(marker)
    token = text[index:]
    for terminator in ("\n", " ", '"', "&"):
        token = token.split(terminator)[0]
    return token.strip()


# ── Hardening (2026-08-03 review) ──────────────────────────────────────────


def test_a_non_ascii_signature_is_rejected_not_a_500(client, outbox):
    """`hmac.compare_digest` refuses non-ASCII `str` and raised TypeError —
    an unauthenticated 500 with a traceback, one request, no auth."""
    register(client)
    user = db.session.query(User).one()

    response = client.get(f"/api/v1/email/unsubscribe?user={user.id}&sig=%C3%A9")
    assert response.status_code == 400


def test_a_recipient_cannot_be_mail_bombed(client, outbox, app):
    """Every route limit is keyed by source IP, so a rotating-IP caller had
    unbounded volume at one inbox — from our own sending domain."""
    app.config["EMAIL_PER_RECIPIENT_HOURLY"] = 3
    register(client, email="victim@example.com")
    outbox.clear()

    for _ in range(10):
        client.post("/api/v1/auth/forgot-password", json={"email": "victim@example.com"})

    assert len(outbox) <= 3


def test_a_newline_in_a_headline_cannot_break_the_subject(client, auth, outbox, db):
    """It used to raise inside EmailMessage, get swallowed as a transport
    failure, release the delivery claim, and then fail identically forever —
    so nobody was ever emailed about that show."""
    import uuid as _uuid

    from app.models import ArtistFollow

    headers = auth(email="band@example.com")
    artist = client.post(
        "/api/v1/me/artists", json={"name": "Bloodroot Choir"}, headers=headers
    ).get_json()["data"]["artist"]

    follower = db.session.query(User).filter_by(email="band@example.com").one()
    other = client.post(
        "/api/v1/auth/register",
        json={"email": "fan@example.com", "password": "correct-horse-battery",
              "display_name": "Fan"},
    )
    assert other.status_code == 201
    fan = db.session.query(User).filter_by(email="fan@example.com").one()
    db.session.add(ArtistFollow(user_id=fan.id, artist_id=_uuid.UUID(artist["id"])))
    db.session.commit()
    assert follower is not None
    outbox.clear()

    created = client.post(
        "/api/v1/events",
        json={
            "headline": "Gig\nSecond line\rThird",
            "artist_id": artist["id"],
            "starts_at": (utcnow() + timedelta(days=2)).isoformat(),
            "venue": {"name": "Dusk", "city": "Providence"},
            "publish": True,
        },
        headers=headers,
    )
    assert created.status_code == 201

    assert len(outbox) == 1
    assert "\n" not in outbox[0].subject
    assert "\r" not in outbox[0].subject


def test_control_characters_are_stripped_from_text_fields(client, auth):
    created = client.post(
        "/api/v1/events",
        json={
            "headline": "Gig\nSecond line",
            "starts_at": (utcnow() + timedelta(days=2)).isoformat(),
            "venue": {"name": "Dusk", "city": "Providence"},
        },
        headers=auth(),
    )
    assert created.status_code == 201
    assert "\n" not in created.get_json()["data"]["event"]["headline"]


def test_a_rescheduled_show_reminds_again_for_the_new_date(
    db, make_user, make_venue, outbox
):
    """Keyed on the event id alone, the row from the first date suppressed the
    reminder for the date that actually happens."""
    from app.services.notifications import send_due_show_reminders

    user = make_user(email="going@example.com")
    venue = make_venue()
    event = Event(
        venue_id=venue.id,
        headline="Bloodroot Choir",
        genre=Genre.ROCK_PUNK,
        starts_at=utcnow() + timedelta(hours=23),
        status=EventStatus.PUBLISHED,
        published_at=utcnow(),
    )
    db.session.add(event)
    db.session.flush()
    db.session.add(EventInterest(user_id=user.id, event_id=event.id, going=True))
    db.session.commit()

    assert send_due_show_reminders()["sent"] == 1
    assert send_due_show_reminders()["sent"] == 0, "still idempotent for one date"

    # The band moves it a week out; the window catches it again.
    event.starts_at = utcnow() + timedelta(days=7, hours=23)
    db.session.commit()
    assert send_due_show_reminders()["sent"] == 0, "not due yet"

    event.starts_at = utcnow() + timedelta(hours=22)
    db.session.commit()
    assert send_due_show_reminders()["sent"] == 1, "the new date gets its own reminder"


def test_a_database_failure_in_the_mail_path_does_not_500_the_request(
    client, monkeypatch
):
    """The ledger write and the token mint both sat outside the guard, so a
    transient DB error 500'd a registration whose user row had already
    committed — the client was told it failed, retried, and got EMAIL_IN_USE
    forever. Breaking the token mint stands in for any of them."""
    from app.services import notifications

    def _explode(*args, **kwargs):
        raise RuntimeError("connection reset")

    monkeypatch.setattr(notifications, "issue_token", _explode)

    response = register(client, email="resilient@example.com")
    assert response.status_code == 201
    assert db.session.query(User).filter_by(email="resilient@example.com").count() == 1


def test_a_database_failure_recording_a_delivery_does_not_raise(client, auth, monkeypatch):
    """The other half: the delivery ledger insert."""
    from app.models import EmailKind
    from app.services import email_service

    register(client, email="ledger@example.com")
    user = db.session.query(User).filter_by(email="ledger@example.com").one()

    def _explode(*args, **kwargs):
        raise RuntimeError("deadlock detected")

    monkeypatch.setattr(email_service, "_claim_delivery", _explode)

    # Must return False, not raise.
    assert email_service.deliver(
        user, EmailKind.SHOW_REMINDER, "show_reminder", "Subject",
        subject_id=user.id, once=True, event={}, event_url="https://example.test",
    ) is False
