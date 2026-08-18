"""Avatar uploads: the same R2 ticket flow, aimed strictly at yourself."""

from app.extensions import db
from app.models import User


def _user(email):
    return db.session.query(User).filter_by(email=email).one()


def _ticket(client, headers, target_id, content_type="image/jpeg"):
    return client.post(
        "/api/v1/uploads",
        json={
            "purpose": "user_avatar",
            "target_id": str(target_id),
            "content_type": content_type,
            "size_bytes": 1024,
        },
        headers=headers,
    )


def test_avatar_upload_end_to_end(client, auth, stub_r2):
    headers = auth(email="ada@example.com")
    me = _user("ada@example.com")

    issued = _ticket(client, headers, me.id)
    assert issued.status_code == 201, issued.get_json()
    ticket = issued.get_json()["data"]
    assert ticket["key"].startswith("users/avatar/")

    stub_r2["put"](ticket["key"], size_bytes=2048, content_type="image/jpeg")
    completed = client.post(
        f"/api/v1/uploads/{ticket['upload_id']}/complete", headers=headers
    )
    assert completed.status_code == 201, completed.get_json()
    assert completed.get_json()["data"]["user"]["avatar_url"] is not None

    db.session.refresh(me)
    assert me.avatar_key == ticket["key"]


def test_avatar_cannot_target_someone_else(client, auth):
    auth(email="victim@example.com")
    attacker = auth(email="attacker@example.com")
    victim = _user("victim@example.com")

    response = _ticket(client, attacker, victim.id)
    assert response.status_code == 404


def test_avatar_rejects_non_image_types(client, auth):
    headers = auth(email="ada@example.com")
    response = _ticket(client, headers, _user("ada@example.com").id,
                       content_type="audio/mpeg")
    assert response.status_code == 415


def test_replacing_an_avatar_deletes_the_old_object(client, auth, stub_r2):
    headers = auth(email="ada@example.com")
    me = _user("ada@example.com")

    first = _ticket(client, headers, me.id).get_json()["data"]
    stub_r2["put"](first["key"], size_bytes=100, content_type="image/jpeg")
    client.post(f"/api/v1/uploads/{first['upload_id']}/complete", headers=headers)

    second = _ticket(client, headers, me.id).get_json()["data"]
    stub_r2["put"](second["key"], size_bytes=100, content_type="image/jpeg")
    client.post(f"/api/v1/uploads/{second['upload_id']}/complete", headers=headers)

    assert first["key"] in stub_r2["deleted"]
    db.session.refresh(me)
    assert me.avatar_key == second["key"]


def test_oversized_avatar_is_bounced_at_completion(client, auth, stub_r2, app):
    headers = auth(email="ada@example.com")
    me = _user("ada@example.com")

    ticket = _ticket(client, headers, me.id).get_json()["data"]
    stub_r2["put"](
        ticket["key"],
        size_bytes=app.config["IMAGE_MAX_BYTES"] + 1,
        content_type="image/jpeg",
    )
    response = client.post(
        f"/api/v1/uploads/{ticket['upload_id']}/complete", headers=headers
    )
    assert response.status_code == 413
    assert ticket["key"] in stub_r2["deleted"]
    db.session.refresh(me)
    assert me.avatar_key is None
