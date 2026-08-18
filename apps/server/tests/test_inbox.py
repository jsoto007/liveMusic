"""The notification inbox: strictly yours, and only yours."""

from app.extensions import db
from app.models import User


def _user(email):
    return db.session.query(User).filter_by(email=email).one()


def _follow(client, follower_headers, followee_email):
    handle = _user(followee_email).handle
    response = client.post(f"/api/v1/users/{handle}/follow", headers=follower_headers)
    assert response.status_code == 200


def test_inbox_requires_auth(client):
    assert client.get("/api/v1/me/notifications").status_code == 401
    assert client.get("/api/v1/me/notifications/unread-count").status_code == 401


def test_only_the_recipient_sees_a_notification(client, auth):
    ada = auth(email="ada@example.com", display_name="Ada Fournier")
    ben = auth(email="ben@example.com", display_name="Ben Okafor")
    _follow(client, ben, "ada@example.com")

    ada_inbox = client.get("/api/v1/me/notifications", headers=ada).get_json()["data"]
    assert ada_inbox["total"] == 1
    assert ada_inbox["notifications"][0]["kind"] == "new_follower"
    assert ada_inbox["notifications"][0]["line"] == "Ben Okafor started following you"
    assert ada_inbox["notifications"][0]["actor"]["handle"] == "ben_okafor"

    ben_inbox = client.get("/api/v1/me/notifications", headers=ben).get_json()["data"]
    assert ben_inbox["total"] == 0


def test_unread_count_and_mark_all(client, auth):
    ada = auth(email="ada@example.com")
    ben = auth(email="ben@example.com")
    _follow(client, ben, "ada@example.com")

    count = client.get("/api/v1/me/notifications/unread-count", headers=ada)
    assert count.get_json()["data"]["unread_count"] == 1

    marked = client.post(
        "/api/v1/me/notifications/read", json={"all": True}, headers=ada
    )
    assert marked.get_json()["data"]["unread_count"] == 0

    listed = client.get("/api/v1/me/notifications", headers=ada).get_json()["data"]
    assert listed["notifications"][0]["read"] is True


def test_marking_specific_ids(client, auth):
    ada = auth(email="ada@example.com")
    ben = auth(email="ben@example.com")
    carol = auth(email="carol@example.com")
    _follow(client, ben, "ada@example.com")
    _follow(client, carol, "ada@example.com")

    inbox = client.get("/api/v1/me/notifications", headers=ada).get_json()["data"]
    first_id = inbox["notifications"][0]["id"]

    response = client.post(
        "/api/v1/me/notifications/read", json={"ids": [first_id]}, headers=ada
    )
    assert response.get_json()["data"]["marked"] == 1
    assert response.get_json()["data"]["unread_count"] == 1


def test_marking_someone_elses_notification_marks_nothing(client, auth):
    ada = auth(email="ada@example.com")
    ben = auth(email="ben@example.com")
    _follow(client, ben, "ada@example.com")

    ada_inbox = client.get("/api/v1/me/notifications", headers=ada).get_json()["data"]
    target_id = ada_inbox["notifications"][0]["id"]

    # Ben forges Ada's notification id into his own mark-read call.
    response = client.post(
        "/api/v1/me/notifications/read", json={"ids": [target_id]}, headers=ben
    )
    assert response.get_json()["data"]["marked"] == 0

    # Ada's line is still unread.
    count = client.get("/api/v1/me/notifications/unread-count", headers=ada)
    assert count.get_json()["data"]["unread_count"] == 1


def test_mark_read_validates_its_body(client, auth):
    headers = auth()
    assert (
        client.post("/api/v1/me/notifications/read", json={}, headers=headers).status_code
        == 400
    )
    assert (
        client.post(
            "/api/v1/me/notifications/read", json={"ids": "everything"}, headers=headers
        ).status_code
        == 400
    )
    assert (
        client.post(
            "/api/v1/me/notifications/read",
            json={"ids": ["not-a-uuid"]},
            headers=headers,
        ).status_code
        == 400
    )


def test_unread_filter(client, auth):
    ada = auth(email="ada@example.com")
    ben = auth(email="ben@example.com")
    carol = auth(email="carol@example.com")
    _follow(client, ben, "ada@example.com")
    _follow(client, carol, "ada@example.com")

    inbox = client.get("/api/v1/me/notifications", headers=ada).get_json()["data"]
    client.post(
        "/api/v1/me/notifications/read",
        json={"ids": [inbox["notifications"][0]["id"]]},
        headers=ada,
    )

    unread_only = client.get(
        "/api/v1/me/notifications?unread=1", headers=ada
    ).get_json()["data"]
    assert unread_only["total"] == 1
    assert all(not n["read"] for n in unread_only["notifications"])
