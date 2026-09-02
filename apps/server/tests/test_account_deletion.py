"""Closing an account — Guideline 5.1.1(v), and the blast radius of doing it.

Written to break the route, not to confirm it: the interesting cases are the
ones where a delete leaves something behind, takes something it should not
have, or lets the wrong caller fire it.
"""

from datetime import timedelta

import pytest

from app.extensions import db as _db
from app.models import (
    Artist,
    AudioSample,
    Comment,
    Event,
    EventInterest,
    EventStatus,
    RefreshToken,
    User,
    UserBlock,
    UserFollow,
    utcnow,
)

PASSWORD = "correct-horse-battery"


@pytest.fixture()
def account(client):
    """A registered account, with its bearer header and its user row."""

    def _make(email="closer@example.com", password=PASSWORD, display_name="Closer"):
        response = client.post(
            "/api/v1/auth/register",
            json={"email": email, "password": password, "display_name": display_name},
        )
        assert response.status_code == 201, response.get_json()
        token = response.get_json()["data"]["access_token"]
        user = _db.session.query(User).filter(User.email == email.lower()).one()
        return user, {"Authorization": f"Bearer {token}"}

    return _make


# ── The guard ──────────────────────────────────────────────────────────────


def test_requires_authentication(client):
    response = client.post("/api/v1/me/delete", json={"password": PASSWORD})
    assert response.status_code == 401


def test_requires_the_current_password(client, account):
    user, headers = account()
    response = client.post(
        "/api/v1/me/delete", json={"password": "not-the-password"}, headers=headers
    )
    assert response.status_code == 403
    assert response.get_json()["error"]["code"] == "INVALID_CREDENTIALS"
    # Still there.
    assert _db.session.get(User, user.id) is not None


def test_rejects_a_malformed_body(client, account):
    _user, headers = account()
    response = client.post("/api/v1/me/delete", json={}, headers=headers)
    assert response.status_code == 400
    assert response.get_json()["error"]["code"] == "VALIDATION_ERROR"


def test_another_users_password_does_not_work(client, account):
    """The password is checked against the *caller*, not looked up globally."""
    victim, victim_headers = account(email="victim@example.com")
    account(email="attacker@example.com", password="a-totally-other-passphrase")

    response = client.post(
        "/api/v1/me/delete",
        json={"password": "a-totally-other-passphrase"},
        headers=victim_headers,
    )
    assert response.status_code == 403
    assert _db.session.get(User, victim.id) is not None


# ── The delete itself ──────────────────────────────────────────────────────


def test_deletes_the_row_and_ends_the_session(client, account):
    user, headers = account()
    user_id = user.id

    response = client.post(
        "/api/v1/me/delete", json={"password": PASSWORD}, headers=headers
    )
    assert response.status_code == 200
    assert response.get_json()["data"] == {"deleted": True}

    assert _db.session.get(User, user_id) is None
    # Not a soft delete hiding behind is_active.
    assert _db.session.query(User).filter(User.id == user_id).count() == 0
    # The access token is now worthless even though it has not expired.
    assert client.get("/api/v1/me", headers=headers).status_code == 401


def test_refresh_tokens_go_with_the_account(client, account):
    user, headers = account()
    user_id = user.id
    assert _db.session.query(RefreshToken).filter(
        RefreshToken.user_id == user_id
    ).count() >= 1

    client.post("/api/v1/me/delete", json={"password": PASSWORD}, headers=headers)

    assert _db.session.query(RefreshToken).filter(
        RefreshToken.user_id == user_id
    ).count() == 0


def test_personal_rows_cascade_away(client, account, make_event, make_artist):
    user, headers = account()
    other, _ = account(email="other@example.com")
    event = make_event()

    _db.session.add_all(
        [
            EventInterest(user_id=user.id, event_id=event.id, going=True),
            UserFollow(follower_id=user.id, followee_id=other.id),
            UserBlock(blocker_id=user.id, blocked_id=other.id),
            Comment(event_id=event.id, author_user_id=user.id, body="See you there."),
        ]
    )
    _db.session.commit()
    user_id = user.id
    make_artist(user, name="Bloodroot Choir")

    client.post("/api/v1/me/delete", json={"password": PASSWORD}, headers=headers)

    assert _db.session.query(EventInterest).filter(
        EventInterest.user_id == user_id
    ).count() == 0
    assert _db.session.query(UserFollow).filter(
        UserFollow.follower_id == user_id
    ).count() == 0
    assert _db.session.query(UserBlock).filter(
        UserBlock.blocker_id == user_id
    ).count() == 0
    assert _db.session.query(Comment).filter(
        Comment.author_user_id == user_id
    ).count() == 0
    assert _db.session.query(Artist).filter(
        Artist.owner_user_id == user_id
    ).count() == 0
    # The other account is untouched.
    assert _db.session.get(User, other.id) is not None


def test_someone_elses_follow_of_me_also_goes(client, account):
    """The cascade has to cover both sides of an edge, not just the one keyed
    on the deleted id first."""
    user, headers = account()
    other, _ = account(email="fan@example.com")
    _db.session.add(UserFollow(follower_id=other.id, followee_id=user.id))
    _db.session.commit()
    user_id = user.id

    client.post("/api/v1/me/delete", json={"password": PASSWORD}, headers=headers)

    assert _db.session.query(UserFollow).filter(
        UserFollow.followee_id == user_id
    ).count() == 0


# ── What survives, and in what shape ───────────────────────────────────────


def test_upcoming_listings_are_cancelled_not_deleted(client, account, make_event):
    user, headers = account()
    upcoming = make_event(created_by=user, hours_ahead=48, headline="Still Ahead")
    upcoming_id = upcoming.id

    client.post("/api/v1/me/delete", json={"password": PASSWORD}, headers=headers)
    _db.session.expire_all()

    survivor = _db.session.get(Event, upcoming_id)
    assert survivor is not None, "a listing readers have on their list must not vanish"
    assert survivor.status is EventStatus.CANCELLED
    assert survivor.cancelled_at is not None
    assert survivor.created_by_user_id is None


def test_past_listings_stay_published(client, account, make_event):
    """A night that already happened is a record, not a promise. Cancelling it
    retroactively would rewrite history in everyone's list."""
    user, headers = account()
    past = make_event(created_by=user, hours_ahead=-72, headline="Last Month")
    past_id = past.id

    client.post("/api/v1/me/delete", json={"password": PASSWORD}, headers=headers)
    _db.session.expire_all()

    survivor = _db.session.get(Event, past_id)
    assert survivor.status is EventStatus.PUBLISHED
    assert survivor.created_by_user_id is None


def test_the_accounts_own_poster_is_stripped_and_purged(
    client, account, make_event, stub_r2
):
    user, headers = account()
    event = make_event(created_by=user, poster_key="events/poster/mine.jpg")
    event_id = event.id
    stub_r2["put"]("events/poster/mine.jpg", content_type="image/jpeg")

    client.post("/api/v1/me/delete", json={"password": PASSWORD}, headers=headers)
    _db.session.expire_all()

    assert _db.session.get(Event, event_id).poster_key is None
    assert "events/poster/mine.jpg" in stub_r2["deleted"]


def test_a_stock_poster_is_left_alone(client, account, make_event, stub_r2):
    """`poster_credit` marks an image this app attached from a Commons source.
    It was never the account's file, and other listings may share it."""
    user, headers = account()
    event = make_event(
        created_by=user,
        poster_key="stock/jazz.jpg",
        poster_credit="Photo by Someone, CC BY-SA 2.0",
    )
    event_id = event.id

    client.post("/api/v1/me/delete", json={"password": PASSWORD}, headers=headers)
    _db.session.expire_all()

    assert _db.session.get(Event, event_id).poster_key == "stock/jazz.jpg"
    assert "stock/jazz.jpg" not in stub_r2["deleted"]


def test_avatar_and_band_media_are_purged_from_storage(
    client, account, make_artist, stub_r2
):
    user, headers = account()
    user.avatar_key = "users/avatar/me.jpg"
    artist = make_artist(user, name="Bloodroot Choir")
    artist.photo_key = "artists/photo/band.jpg"
    _db.session.add(
        AudioSample(
            artist_id=artist.id,
            title="Demo",
            object_key="artists/audio/demo.mp3",
            content_type="audio/mpeg",
            size_bytes=1024,
        )
    )
    _db.session.commit()

    client.post("/api/v1/me/delete", json={"password": PASSWORD}, headers=headers)

    for key in (
        "users/avatar/me.jpg",
        "artists/photo/band.jpg",
        "artists/audio/demo.mp3",
    ):
        assert key in stub_r2["deleted"], f"{key} was left in the bucket"


def test_another_accounts_listing_is_not_touched(client, account, make_event):
    """Only the caller's own listings are cancelled — not every listing at the
    same venue, and not one merely marked as going."""
    user, headers = account()
    other, _ = account(email="promoter@example.com")
    theirs = make_event(created_by=other, hours_ahead=48, headline="Not Mine")
    theirs_id = theirs.id
    _db.session.add(EventInterest(user_id=user.id, event_id=theirs_id, going=True))
    _db.session.commit()

    client.post("/api/v1/me/delete", json={"password": PASSWORD}, headers=headers)
    _db.session.expire_all()

    survivor = _db.session.get(Event, theirs_id)
    assert survivor.status is EventStatus.PUBLISHED
    assert survivor.created_by_user_id == other.id


def test_a_storage_failure_still_reports_success(client, account, monkeypatch):
    """The purge runs after the commit, and must not be able to fail the call.

    By the time a key is being deleted the account is already gone. Letting the
    exception out would answer 500 to a request that succeeded, and send the
    caller back to retry a deletion that has already happened. An orphaned
    object is cheaper than that, and the sweeper will find it.
    """
    from app.services import r2_storage

    user, headers = account()
    user.avatar_key = "users/avatar/me.jpg"
    _db.session.commit()
    user_id = user.id

    def _boom(key):  # noqa: ARG001
        raise RuntimeError("R2 is down")

    monkeypatch.setattr(r2_storage.R2Storage, "delete_object", staticmethod(_boom))

    response = client.post(
        "/api/v1/me/delete", json={"password": PASSWORD}, headers=headers
    )
    assert response.status_code == 200
    assert response.get_json()["data"] == {"deleted": True}

    _db.session.expire_all()
    assert _db.session.get(User, user_id) is None


def test_the_email_is_free_to_register_again(client, account):
    """A deleted account must not leave its address permanently claimed."""
    _user, headers = account(email="again@example.com")
    client.post("/api/v1/me/delete", json={"password": PASSWORD}, headers=headers)

    response = client.post(
        "/api/v1/auth/register",
        json={
            "email": "again@example.com",
            "password": PASSWORD,
            "display_name": "Second Time",
        },
    )
    assert response.status_code == 201


def test_deletion_clears_the_browser_cookies(client):
    """A web caller keeps its refresh cookie unless the response clears it."""
    registered = client.post(
        "/api/v1/auth/register",
        json={
            "email": "web@example.com",
            "password": PASSWORD,
            "display_name": "Web",
        },
    )
    token = registered.get_json()["data"]["access_token"]
    assert client.get_cookie("live_msc_refresh", path="/api/v1/auth") is not None

    response = client.post(
        "/api/v1/me/delete",
        json={"password": PASSWORD},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert response.status_code == 200
    assert client.get_cookie("live_msc_refresh", path="/api/v1/auth") is None
