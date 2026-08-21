"""The photo desk: every image queues, only editors see the queue."""

from app.extensions import db
from app.models import (
    ImageReview,
    ImageReviewStatus,
    Notification,
    NotificationKind,
    User,
    UserRole,
)


def _user(email):
    return db.session.query(User).filter_by(email=email).one()


def _admin_headers(client, make_user):
    make_user(email="editor@example.com", role=UserRole.ADMIN)
    token = client.post(
        "/api/v1/auth/login",
        json={"email": "editor@example.com", "password": "correct-horse-battery"},
    ).get_json()["data"]["access_token"]
    return {"Authorization": f"Bearer {token}"}


def _upload_avatar(client, stub_r2, headers, email):
    me = _user(email)
    ticket = client.post(
        "/api/v1/uploads",
        json={
            "purpose": "user_avatar",
            "target_id": str(me.id),
            "content_type": "image/jpeg",
            "size_bytes": 1024,
        },
        headers=headers,
    ).get_json()["data"]
    stub_r2["put"](ticket["key"], size_bytes=1024, content_type="image/jpeg")
    completed = client.post(
        f"/api/v1/uploads/{ticket['upload_id']}/complete", headers=headers
    )
    assert completed.status_code == 201
    return ticket["key"]


def test_completed_image_uploads_queue_for_review(client, auth, stub_r2):
    headers = auth(email="ada@example.com")
    key = _upload_avatar(client, stub_r2, headers, "ada@example.com")

    review = db.session.query(ImageReview).one()
    assert review.status is ImageReviewStatus.PENDING
    assert review.object_key == key
    assert review.uploader_user_id == _user("ada@example.com").id
    assert review.purpose.value == "user_avatar"


def test_audio_uploads_do_not_queue(client, auth, stub_r2):
    headers = auth(email="band@example.com")
    band = client.post(
        "/api/v1/me/artists", json={"name": "Bloodroot Choir"}, headers=headers
    ).get_json()["data"]["artist"]
    ticket = client.post(
        "/api/v1/uploads",
        json={
            "purpose": "artist_audio",
            "target_id": band["id"],
            "content_type": "audio/mpeg",
            "size_bytes": 1024,
        },
        headers=headers,
    ).get_json()["data"]
    stub_r2["put"](ticket["key"], size_bytes=1024, content_type="audio/mpeg")
    assert (
        client.post(
            f"/api/v1/uploads/{ticket['upload_id']}/complete", headers=headers
        ).status_code
        == 201
    )
    assert db.session.query(ImageReview).count() == 0


def test_queue_is_invisible_to_readers(client, auth):
    headers = auth()
    assert client.get("/api/v1/admin/image-reviews", headers=headers).status_code == 404
    assert client.get("/api/v1/admin/image-reviews").status_code == 401


def test_editor_reads_the_queue_with_image_urls(client, auth, make_user, stub_r2):
    headers = auth(email="ada@example.com")
    _upload_avatar(client, stub_r2, headers, "ada@example.com")

    admin = _admin_headers(client, make_user)
    listing = client.get("/api/v1/admin/image-reviews", headers=admin)
    assert listing.status_code == 200
    data = listing.get_json()["data"]
    assert data["total"] == 1
    review = data["reviews"][0]
    assert review["status"] == "pending"
    assert review["image_url"] is not None
    assert review["uploader"]["handle"] == _user("ada@example.com").handle


def test_approve_keeps_the_photo(client, auth, make_user, stub_r2):
    headers = auth(email="ada@example.com")
    key = _upload_avatar(client, stub_r2, headers, "ada@example.com")

    admin = _admin_headers(client, make_user)
    review_id = client.get("/api/v1/admin/image-reviews", headers=admin).get_json()[
        "data"
    ]["reviews"][0]["id"]
    resolved = client.post(
        f"/api/v1/admin/image-reviews/{review_id}/resolve",
        json={"action": "approve"},
        headers=admin,
    )
    assert resolved.status_code == 200
    assert resolved.get_json()["data"]["status"] == "approved"

    me = _user("ada@example.com")
    db.session.refresh(me)
    assert me.avatar_key == key
    assert key not in stub_r2["deleted"]

    # The pending queue is now empty; the approved list holds it.
    assert client.get(
        "/api/v1/admin/image-reviews", headers=admin
    ).get_json()["data"]["total"] == 0
    assert client.get(
        "/api/v1/admin/image-reviews?status=approved", headers=admin
    ).get_json()["data"]["total"] == 1


def test_remove_strips_deletes_and_notifies(client, auth, make_user, stub_r2):
    headers = auth(email="ada@example.com")
    key = _upload_avatar(client, stub_r2, headers, "ada@example.com")

    admin = _admin_headers(client, make_user)
    review_id = client.get("/api/v1/admin/image-reviews", headers=admin).get_json()[
        "data"
    ]["reviews"][0]["id"]
    resolved = client.post(
        f"/api/v1/admin/image-reviews/{review_id}/resolve",
        json={"action": "remove"},
        headers=admin,
    )
    assert resolved.status_code == 200
    assert resolved.get_json()["data"]["status"] == "removed"

    me = _user("ada@example.com")
    db.session.refresh(me)
    assert me.avatar_key is None
    assert key in stub_r2["deleted"]

    removal_notes = (
        db.session.query(Notification)
        .filter(
            Notification.user_id == me.id,
            Notification.kind == NotificationKind.IMAGE_REMOVED,
        )
        .all()
    )
    assert len(removal_notes) == 1


def test_removal_notice_is_a_system_notification(client, auth, make_user, stub_r2):
    """The notice names no editor and survives the uploader having blocked
    the editor's account — a block must not mute moderation."""
    headers = auth(email="ada@example.com")
    _upload_avatar(client, stub_r2, headers, "ada@example.com")

    admin = _admin_headers(client, make_user)
    # Ada blocks the editor's account before the desk acts.
    editor_handle = _user("editor@example.com").handle
    assert (
        client.post(f"/api/v1/users/{editor_handle}/block", headers=headers).status_code
        == 200
    )

    review_id = client.get("/api/v1/admin/image-reviews", headers=admin).get_json()[
        "data"
    ]["reviews"][0]["id"]
    client.post(
        f"/api/v1/admin/image-reviews/{review_id}/resolve",
        json={"action": "remove"},
        headers=admin,
    )

    inbox = client.get("/api/v1/me/notifications", headers=headers).get_json()["data"]
    lines = [n for n in inbox["notifications"] if n["kind"] == "image_removed"]
    assert len(lines) == 1
    assert lines[0]["line"] == "An editor removed one of your photos"
    # No actor rides along — the desk speaks as the paper.
    assert lines[0]["actor"] is None


def test_removing_a_stale_key_leaves_the_replacement_alone(
    client, auth, make_user, stub_r2
):
    """Owner replaced the photo before the desk got to the first one — the
    stale object is still deleted, the new photo survives."""
    headers = auth(email="ada@example.com")
    first_key = _upload_avatar(client, stub_r2, headers, "ada@example.com")
    second_key = _upload_avatar(client, stub_r2, headers, "ada@example.com")

    admin = _admin_headers(client, make_user)
    reviews = client.get("/api/v1/admin/image-reviews", headers=admin).get_json()[
        "data"
    ]["reviews"]
    first_review = next(r for r in reviews if r["image_url"].count(first_key))
    client.post(
        f"/api/v1/admin/image-reviews/{first_review['id']}/resolve",
        json={"action": "remove"},
        headers=admin,
    )

    me = _user("ada@example.com")
    db.session.refresh(me)
    assert me.avatar_key == second_key


def test_resolving_twice_is_refused(client, auth, make_user, stub_r2):
    headers = auth(email="ada@example.com")
    _upload_avatar(client, stub_r2, headers, "ada@example.com")

    admin = _admin_headers(client, make_user)
    review_id = client.get("/api/v1/admin/image-reviews", headers=admin).get_json()[
        "data"
    ]["reviews"][0]["id"]
    client.post(
        f"/api/v1/admin/image-reviews/{review_id}/resolve",
        json={"action": "approve"},
        headers=admin,
    )
    again = client.post(
        f"/api/v1/admin/image-reviews/{review_id}/resolve",
        json={"action": "remove"},
        headers=admin,
    )
    assert again.status_code == 409

    bad_action = client.post(
        f"/api/v1/admin/image-reviews/{review_id}/resolve",
        json={"action": "shred"},
        headers=admin,
    )
    assert bad_action.status_code in (400, 409)
