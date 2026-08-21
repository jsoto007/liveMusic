"""Comments, likes and mentions — and the block rules that police them."""

from app.extensions import db
from app.models import Notification, NotificationKind, User


def _user(email):
    return db.session.query(User).filter_by(email=email).one()


def _comment(client, headers, event, body="What a night."):
    response = client.post(
        f"/api/v1/events/{event.id}/comments", json={"body": body}, headers=headers
    )
    assert response.status_code == 201, response.get_json()
    return response.get_json()["data"]["comment"]


def _notifications(email, kind):
    return (
        db.session.query(Notification)
        .filter(
            Notification.user_id == _user(email).id,
            Notification.kind == kind,
        )
        .all()
    )


# ── Writing and reading ────────────────────────────────────────────────────


def test_comment_and_read_back(client, auth, make_event):
    event = make_event()
    headers = auth(email="ada@example.com", display_name="Ada Fournier")
    _comment(client, headers, event, body="First!")
    _comment(client, headers, event, body="Second.")

    response = client.get(f"/api/v1/events/{event.id}/comments")
    assert response.status_code == 200
    data = response.get_json()["data"]
    assert data["total"] == 2
    # Newest first.
    assert [c["body"] for c in data["comments"]] == ["Second.", "First!"]
    assert data["comments"][0]["author"]["handle"] == "ada_fournier"


def test_comment_requires_auth_and_a_body(client, auth, make_event):
    event = make_event()
    assert (
        client.post(
            f"/api/v1/events/{event.id}/comments", json={"body": "hi"}
        ).status_code
        == 401
    )
    headers = auth()
    assert (
        client.post(
            f"/api/v1/events/{event.id}/comments", json={}, headers=headers
        ).status_code
        == 400
    )
    assert (
        client.post(
            f"/api/v1/events/{event.id}/comments",
            json={"body": "x" * 2001},
            headers=headers,
        ).status_code
        == 400
    )


def test_drafts_have_no_comment_section(client, auth, make_event):
    from app.models import EventStatus

    draft = make_event(status=EventStatus.DRAFT)
    headers = auth()
    assert client.get(f"/api/v1/events/{draft.id}/comments").status_code == 404
    assert (
        client.post(
            f"/api/v1/events/{draft.id}/comments", json={"body": "hi"}, headers=headers
        ).status_code
        == 404
    )


def test_event_detail_counts_comments(client, auth, make_event):
    event = make_event()
    _comment(client, auth(), event)

    response = client.get(f"/api/v1/events/{event.id}")
    assert response.get_json()["data"]["event"]["comment_count"] == 1


def test_author_can_delete_own_comment_others_cannot(client, auth, make_event):
    event = make_event()
    author = auth(email="author@example.com")
    comment = _comment(client, author, event)

    stranger = auth(email="stranger@example.com")
    denied = client.delete(f"/api/v1/comments/{comment['id']}", headers=stranger)
    assert denied.status_code == 404  # indistinguishable from a bad id

    deleted = client.delete(f"/api/v1/comments/{comment['id']}", headers=author)
    assert deleted.status_code == 200
    assert client.get(f"/api/v1/events/{event.id}/comments").get_json()["data"]["total"] == 0


def test_admin_can_remove_any_comment(client, auth, make_user, make_event):
    from app.models import UserRole

    event = make_event()
    comment = _comment(client, auth(email="author@example.com"), event)

    make_user(email="editor@example.com", role=UserRole.ADMIN)
    token = client.post(
        "/api/v1/auth/login",
        json={"email": "editor@example.com", "password": "correct-horse-battery"},
    ).get_json()["data"]["access_token"]

    response = client.delete(
        f"/api/v1/comments/{comment['id']}",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert response.status_code == 200


# ── Likes ──────────────────────────────────────────────────────────────────


def test_like_and_unlike(client, auth, make_event):
    event = make_event()
    comment = _comment(client, auth(email="author@example.com"), event)
    liker = auth(email="liker@example.com")

    liked = client.post(f"/api/v1/comments/{comment['id']}/like", headers=liker)
    assert liked.status_code == 200
    assert liked.get_json()["data"]["like_count"] == 1

    again = client.post(f"/api/v1/comments/{comment['id']}/like", headers=liker)
    assert again.get_json()["data"]["like_count"] == 1  # idempotent

    unliked = client.delete(f"/api/v1/comments/{comment['id']}/like", headers=liker)
    assert unliked.get_json()["data"]["like_count"] == 0


def test_like_notifies_author_once_ever(client, auth, make_event):
    event = make_event()
    comment = _comment(client, auth(email="author@example.com"), event)
    liker = auth(email="liker@example.com")

    client.post(f"/api/v1/comments/{comment['id']}/like", headers=liker)
    client.delete(f"/api/v1/comments/{comment['id']}/like", headers=liker)
    client.post(f"/api/v1/comments/{comment['id']}/like", headers=liker)

    assert len(_notifications("author@example.com", NotificationKind.COMMENT_LIKE)) == 1


def test_liking_your_own_comment_rings_no_bell(client, auth, make_event):
    event = make_event()
    author = auth(email="author@example.com")
    comment = _comment(client, author, event)
    client.post(f"/api/v1/comments/{comment['id']}/like", headers=author)
    assert _notifications("author@example.com", NotificationKind.COMMENT_LIKE) == []


# ── Notifications to the listing's owners ──────────────────────────────────


def test_comment_notifies_the_event_owner(client, auth, make_user, make_event):
    owner = make_user(email="owner@example.com")
    event = make_event(created_by=owner)

    _comment(client, auth(email="fan@example.com"), event)
    assert len(_notifications("owner@example.com", NotificationKind.EVENT_COMMENT)) == 1


def test_commenting_on_your_own_listing_rings_no_bell(client, auth, make_user, make_event):
    make_user(email="owner@example.com")
    owner_headers = auth(email="owner2@example.com")
    event = make_event(created_by=_user("owner2@example.com"))
    _comment(client, owner_headers, event)
    assert _notifications("owner2@example.com", NotificationKind.EVENT_COMMENT) == []


# ── Mentions ───────────────────────────────────────────────────────────────


def test_mention_notifies_the_named_reader(client, auth, make_event):
    event = make_event()
    auth(email="mentioned@example.com", display_name="Named Person")
    handle = _user("mentioned@example.com").handle

    _comment(client, auth(email="writer@example.com"), event, body=f"See you there @{handle}!")

    rows = _notifications("mentioned@example.com", NotificationKind.MENTION)
    assert len(rows) == 1


def test_unknown_mentions_are_ignored(client, auth, make_event):
    event = make_event()
    comment = _comment(
        client, auth(), event, body="@nobody_by_this_name are you going?"
    )
    assert comment["body"].startswith("@nobody_by_this_name")
    assert db.session.query(Notification).filter_by(
        kind=NotificationKind.MENTION
    ).count() == 0


def test_mentioning_yourself_rings_no_bell(client, auth, make_event):
    event = make_event()
    writer = auth(email="writer@example.com")
    handle = _user("writer@example.com").handle
    _comment(client, writer, event, body=f"Note to self @{handle}")
    assert _notifications("writer@example.com", NotificationKind.MENTION) == []


# ── Blocks ─────────────────────────────────────────────────────────────────


def test_blocked_reader_cannot_comment_on_blockers_listing(
    client, auth, make_user, make_event
):
    owner_headers = auth(email="owner@example.com")
    event = make_event(created_by=_user("owner@example.com"))
    troll = auth(email="troll@example.com")

    client.post(
        f"/api/v1/users/{_user('troll@example.com').handle}/block",
        headers=owner_headers,
    )

    response = client.post(
        f"/api/v1/events/{event.id}/comments", json={"body": "hi"}, headers=troll
    )
    assert response.status_code == 403
    assert response.get_json()["error"]["code"] == "BLOCKED"


def test_blocked_comments_vanish_from_both_sides(client, auth, make_event):
    event = make_event()
    ada = auth(email="ada@example.com")
    ben = auth(email="ben@example.com")
    _comment(client, ben, event, body="Ben was here.")

    client.post(f"/api/v1/users/{_user('ben@example.com').handle}/block", headers=ada)

    seen_by_ada = client.get(f"/api/v1/events/{event.id}/comments", headers=ada)
    assert seen_by_ada.get_json()["data"]["total"] == 0

    _comment(client, ada, event, body="Ada was here.")
    seen_by_ben = client.get(f"/api/v1/events/{event.id}/comments", headers=ben)
    assert [c["body"] for c in seen_by_ben.get_json()["data"]["comments"]] == [
        "Ben was here."
    ]

    # The room itself still sees everyone.
    seen_by_anon = client.get(f"/api/v1/events/{event.id}/comments")
    assert seen_by_anon.get_json()["data"]["total"] == 2


def test_blocked_reader_cannot_like_the_blockers_comment(client, auth, make_event):
    event = make_event()
    ada = auth(email="ada@example.com")
    ben = auth(email="ben@example.com")
    comment = _comment(client, ada, event)

    client.post(f"/api/v1/users/{_user('ben@example.com').handle}/block", headers=ada)

    response = client.post(f"/api/v1/comments/{comment['id']}/like", headers=ben)
    assert response.status_code == 403


def test_deleting_a_comment_takes_its_notifications(client, auth, make_user, make_event):
    owner = make_user(email="owner@example.com")
    event = make_event(created_by=owner)
    author = auth(email="author@example.com")
    comment = _comment(client, author, event)

    assert len(_notifications("owner@example.com", NotificationKind.EVENT_COMMENT)) == 1
    client.delete(f"/api/v1/comments/{comment['id']}", headers=author)
    assert _notifications("owner@example.com", NotificationKind.EVENT_COMMENT) == []
