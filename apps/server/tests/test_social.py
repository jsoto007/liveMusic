"""Profiles, handles, follows and blocks — the reader-to-reader graph."""

from app.extensions import db
from app.models import Notification, NotificationKind, User, UserFollow


def _user(email):
    return db.session.query(User).filter_by(email=email).one()


def _handle(email):
    return _user(email).handle


# ── Handles ────────────────────────────────────────────────────────────────


def test_registration_issues_a_handle(client, auth):
    headers = auth(email="ada@example.com", display_name="Ada Fournier")
    me = client.get("/api/v1/me", headers=headers)
    assert me.status_code == 200
    assert me.get_json()["data"]["user"]["handle"] == "ada_fournier"


def test_handle_collisions_get_suffixes(client, auth):
    auth(email="one@example.com", display_name="Ada Fournier")
    auth(email="two@example.com", display_name="Ada Fournier")
    first = _handle("one@example.com")
    second = _handle("two@example.com")
    assert first == "ada_fournier"
    assert second != first
    assert second.startswith("ada_fournier")


def test_handle_can_be_changed(client, auth):
    headers = auth(email="ada@example.com")
    response = client.patch("/api/v1/me", json={"handle": "AdaLive"}, headers=headers)
    assert response.status_code == 200
    assert response.get_json()["data"]["user"]["handle"] == "adalive"


def test_handle_rejects_bad_grammar_and_reserved_names(client, auth):
    headers = auth(email="ada@example.com")
    for bad in ("ab", "has space", "has-hyphen", "admin", "me", "x" * 31):
        response = client.patch("/api/v1/me", json={"handle": bad}, headers=headers)
        assert response.status_code == 400, bad
        assert response.get_json()["error"]["code"] == "VALIDATION_ERROR"


def test_handle_conflict_is_a_409(client, auth):
    auth(email="one@example.com", display_name="Taken Name")
    headers = auth(email="two@example.com")
    response = client.patch(
        "/api/v1/me", json={"handle": "taken_name"}, headers=headers
    )
    assert response.status_code == 409
    assert response.get_json()["error"]["code"] == "HANDLE_TAKEN"


def test_bio_is_editable_and_capped(client, auth):
    headers = auth(email="ada@example.com")
    ok = client.patch("/api/v1/me", json={"bio": "Plays the saw."}, headers=headers)
    assert ok.status_code == 200
    too_long = client.patch("/api/v1/me", json={"bio": "x" * 501}, headers=headers)
    assert too_long.status_code == 400


# ── Profiles ───────────────────────────────────────────────────────────────


def test_profile_is_public(client, auth):
    auth(email="ada@example.com", display_name="Ada Fournier")
    response = client.get(f"/api/v1/users/{_handle('ada@example.com')}")
    assert response.status_code == 200
    profile = response.get_json()["data"]["profile"]
    assert profile["display_name"] == "Ada Fournier"
    assert profile["follower_count"] == 0
    assert "email" not in profile


def test_unknown_profile_is_a_404(client):
    response = client.get("/api/v1/users/nobody_here")
    assert response.status_code == 404


def test_profile_shows_viewer_relationship(client, auth):
    auth(email="ada@example.com")
    viewer = auth(email="ben@example.com")
    handle = _handle("ada@example.com")

    client.post(f"/api/v1/users/{handle}/follow", headers=viewer)
    response = client.get(f"/api/v1/users/{handle}", headers=viewer)
    profile = response.get_json()["data"]["profile"]
    assert profile["is_following"] is True
    assert profile["is_blocked"] is False
    assert profile["follower_count"] == 1


# ── Follows ────────────────────────────────────────────────────────────────


def test_follow_requires_auth(client, auth):
    auth(email="ada@example.com")
    response = client.post(f"/api/v1/users/{_handle('ada@example.com')}/follow")
    assert response.status_code == 401


def test_follow_and_unfollow(client, auth):
    auth(email="ada@example.com")
    ben = auth(email="ben@example.com")
    handle = _handle("ada@example.com")

    followed = client.post(f"/api/v1/users/{handle}/follow", headers=ben)
    assert followed.status_code == 200
    assert followed.get_json()["data"]["follower_count"] == 1

    # Idempotent re-follow.
    again = client.post(f"/api/v1/users/{handle}/follow", headers=ben)
    assert again.get_json()["data"]["follower_count"] == 1

    unfollowed = client.delete(f"/api/v1/users/{handle}/follow", headers=ben)
    assert unfollowed.get_json()["data"]["follower_count"] == 0


def test_cannot_follow_yourself(client, auth):
    headers = auth(email="ada@example.com")
    response = client.post(
        f"/api/v1/users/{_handle('ada@example.com')}/follow", headers=headers
    )
    assert response.status_code == 400


def test_follow_notifies_once_across_refollows(client, auth):
    auth(email="ada@example.com")
    ben = auth(email="ben@example.com")
    handle = _handle("ada@example.com")

    client.post(f"/api/v1/users/{handle}/follow", headers=ben)
    client.delete(f"/api/v1/users/{handle}/follow", headers=ben)
    client.post(f"/api/v1/users/{handle}/follow", headers=ben)

    rows = (
        db.session.query(Notification)
        .filter(
            Notification.user_id == _user("ada@example.com").id,
            Notification.kind == NotificationKind.NEW_FOLLOWER,
        )
        .all()
    )
    assert len(rows) == 1


def test_follower_and_following_pages(client, auth):
    auth(email="ada@example.com")
    ben = auth(email="ben@example.com")
    handle = _handle("ada@example.com")
    client.post(f"/api/v1/users/{handle}/follow", headers=ben)

    followers = client.get(f"/api/v1/users/{handle}/followers")
    assert followers.status_code == 200
    assert followers.get_json()["data"]["total"] == 1
    assert followers.get_json()["data"]["people"][0]["handle"] == _handle(
        "ben@example.com"
    )

    following = client.get(f"/api/v1/users/{_handle('ben@example.com')}/following")
    assert following.get_json()["data"]["people"][0]["handle"] == handle


# ── Blocks ─────────────────────────────────────────────────────────────────


def test_block_severs_follows_both_ways(client, auth):
    ada = auth(email="ada@example.com")
    ben = auth(email="ben@example.com")
    ada_handle = _handle("ada@example.com")
    ben_handle = _handle("ben@example.com")

    client.post(f"/api/v1/users/{ada_handle}/follow", headers=ben)
    client.post(f"/api/v1/users/{ben_handle}/follow", headers=ada)

    blocked = client.post(f"/api/v1/users/{ben_handle}/block", headers=ada)
    assert blocked.status_code == 200

    assert db.session.query(UserFollow).count() == 0


def test_block_prevents_new_follows_in_both_directions(client, auth):
    ada = auth(email="ada@example.com")
    ben = auth(email="ben@example.com")
    ada_handle = _handle("ada@example.com")
    ben_handle = _handle("ben@example.com")

    client.post(f"/api/v1/users/{ben_handle}/block", headers=ada)

    as_blocker = client.post(f"/api/v1/users/{ben_handle}/follow", headers=ada)
    assert as_blocker.status_code == 403
    assert as_blocker.get_json()["error"]["code"] == "BLOCKED"

    as_blocked = client.post(f"/api/v1/users/{ada_handle}/follow", headers=ben)
    assert as_blocked.status_code == 403


def test_unblock_restores_the_ability_to_follow(client, auth):
    ada = auth(email="ada@example.com")
    auth(email="ben@example.com")
    ben_handle = _handle("ben@example.com")

    client.post(f"/api/v1/users/{ben_handle}/block", headers=ada)
    client.delete(f"/api/v1/users/{ben_handle}/block", headers=ada)

    response = client.post(f"/api/v1/users/{ben_handle}/follow", headers=ada)
    assert response.status_code == 200


def test_blocks_are_listed_for_their_owner_only(client, auth):
    ada = auth(email="ada@example.com")
    auth(email="ben@example.com")
    client.post(f"/api/v1/users/{_handle('ben@example.com')}/block", headers=ada)

    mine = client.get("/api/v1/me/blocks", headers=ada)
    assert [p["handle"] for p in mine.get_json()["data"]["people"]] == [
        _handle("ben@example.com")
    ]

    anonymous = client.get("/api/v1/me/blocks")
    assert anonymous.status_code == 401


def test_profile_never_reveals_being_blocked(client, auth):
    """The blocked party's profile read must not disclose the block."""
    ada = auth(email="ada@example.com")
    ben = auth(email="ben@example.com")
    client.post(f"/api/v1/users/{_handle('ben@example.com')}/block", headers=ada)

    seen_by_ben = client.get(
        f"/api/v1/users/{_handle('ada@example.com')}", headers=ben
    )
    profile = seen_by_ben.get_json()["data"]["profile"]
    assert profile["is_blocked"] is False  # ben has not blocked ada
    assert "has_blocked_viewer" not in profile


# ── Search ─────────────────────────────────────────────────────────────────


def test_search_finds_people_by_handle_and_name(client, auth):
    auth(email="ada@example.com", display_name="Ada Fournier")
    auth(email="ben@example.com", display_name="Ben Okafor")

    by_handle = client.get("/api/v1/users/search?q=ada_f")
    assert by_handle.get_json()["data"]["total"] == 1

    by_name = client.get("/api/v1/users/search?q=okafor")
    assert by_name.get_json()["data"]["people"][0]["display_name"] == "Ben Okafor"


def test_search_escapes_like_wildcards(client, auth):
    auth(email="ada@example.com", display_name="Ada Fournier")
    # "%%" URL-encoded — if the LIKE escape were missing this would match
    # every user instead of none.
    response = client.get("/api/v1/users/search?q=%25%25")
    assert response.status_code == 200
    assert response.get_json()["data"]["total"] == 0


def test_search_requires_two_characters(client):
    response = client.get("/api/v1/users/search?q=a")
    assert response.status_code == 400
