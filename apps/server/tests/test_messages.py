"""The correspondence desk: who may write to whom, and who may read it."""

from app.extensions import db
from app.models import Conversation, User


def _user(email):
    return db.session.query(User).filter_by(email=email).one()


def _band(client, headers, name="Bloodroot Choir"):
    response = client.post("/api/v1/me/artists", json={"name": name}, headers=headers)
    assert response.status_code == 201
    return response.get_json()["data"]["artist"]


def _gig(client, headers, **extra):
    response = client.post(
        "/api/v1/gigs",
        json={
            "title": "Jazz trio wanted",
            "description": "Two sets.",
            "city": "Providence",
            **extra,
        },
        headers=headers,
    )
    assert response.status_code == 201
    return response.get_json()["data"]["gig"]


def _open(client, headers, **body):
    return client.post("/api/v1/conversations", json=body, headers=headers)


# ── Opening threads ────────────────────────────────────────────────────────


def test_message_by_handle(client, auth):
    auth(email="ada@example.com", display_name="Ada Fournier")
    ben = auth(email="ben@example.com")

    response = _open(client, ben, to="ada_fournier", body="Saw your set. Hello.")
    assert response.status_code == 201, response.get_json()
    conversation = response.get_json()["data"]["conversation"]
    assert conversation["with"]["handle"] == "ada_fournier"
    assert conversation["subject"] is None


def test_message_a_band_reaches_its_owner(client, auth):
    owner = auth(email="owner@example.com", display_name="Band Owner")
    band = _band(client, owner)

    venue = auth(email="venue@example.com")
    response = _open(
        client, venue, artist_id=band["id"], body="Are you free on the 4th?"
    )
    assert response.status_code == 201
    conversation = response.get_json()["data"]["conversation"]
    assert conversation["with"]["handle"] == _user("owner@example.com").handle
    assert conversation["subject"] == "About Bloodroot Choir"


def test_application_thread_connects_poster_and_applicant(client, auth):
    poster = auth(email="venue@example.com")
    gig = _gig(client, poster)
    musician = auth(email="band@example.com")
    band = _band(client, musician)
    application = client.post(
        f"/api/v1/gigs/{gig['id']}/applications",
        json={"artist_id": band["id"]},
        headers=musician,
    ).get_json()["data"]["application"]

    # Poster → applicant.
    from_poster = _open(
        client, poster, application_id=application["id"], body="Can you do 9pm?"
    )
    assert from_poster.status_code == 201
    assert (
        from_poster.get_json()["data"]["conversation"]["with"]["handle"]
        == _user("band@example.com").handle
    )

    # Applicant → poster lands in the same thread.
    from_band = _open(
        client, musician, application_id=application["id"], body="9 sharp works."
    )
    assert from_band.status_code == 201
    assert (
        from_band.get_json()["data"]["conversation"]["id"]
        == from_poster.get_json()["data"]["conversation"]["id"]
    )


def test_strangers_cannot_use_an_application_as_an_address_book(client, auth):
    poster = auth(email="venue@example.com")
    gig = _gig(client, poster)
    musician = auth(email="band@example.com")
    band = _band(client, musician)
    application = client.post(
        f"/api/v1/gigs/{gig['id']}/applications",
        json={"artist_id": band["id"]},
        headers=musician,
    ).get_json()["data"]["application"]

    stranger = auth(email="stranger@example.com")
    response = _open(
        client, stranger, application_id=application["id"], body="hello?"
    )
    assert response.status_code == 404


def test_one_thread_per_pair(client, auth):
    auth(email="ada@example.com")
    ben = auth(email="ben@example.com")
    handle = _user("ada@example.com").handle

    first = _open(client, ben, to=handle, body="one")
    second = _open(client, ben, to=handle, body="two")
    assert (
        first.get_json()["data"]["conversation"]["id"]
        == second.get_json()["data"]["conversation"]["id"]
    )
    assert db.session.query(Conversation).count() == 1


def test_opening_requires_exactly_one_anchor_and_a_body(client, auth):
    auth(email="ada@example.com")
    ben = auth(email="ben@example.com")
    handle = _user("ada@example.com").handle

    assert _open(client, ben, body="no anchor").status_code == 400
    assert (
        _open(client, ben, to=handle, artist_id=str(_user("ada@example.com").id),
              body="two anchors").status_code
        == 400
    )
    assert _open(client, ben, to=handle).status_code == 400
    assert _open(client, ben, to="nobody_here", body="hi").status_code == 404
    assert (
        client.post("/api/v1/conversations", json={"to": handle, "body": "hi"}).status_code
        == 401
    )


def test_cannot_message_yourself(client, auth):
    ada = auth(email="ada@example.com")
    response = _open(client, ada, to=_user("ada@example.com").handle, body="me")
    assert response.status_code == 400


def test_blocks_bar_new_mail_both_ways(client, auth):
    ada = auth(email="ada@example.com")
    ben = auth(email="ben@example.com")
    ada_handle = _user("ada@example.com").handle
    ben_handle = _user("ben@example.com").handle

    client.post(f"/api/v1/users/{ben_handle}/block", headers=ada)

    assert _open(client, ada, to=ben_handle, body="hi").status_code == 403
    blocked = _open(client, ben, to=ada_handle, body="hi")
    assert blocked.status_code == 403
    assert blocked.get_json()["error"]["code"] == "BLOCKED"


def test_block_after_thread_opens_stops_further_mail(client, auth):
    ada = auth(email="ada@example.com")
    ben = auth(email="ben@example.com")
    conversation = _open(
        client, ben, to=_user("ada@example.com").handle, body="hello"
    ).get_json()["data"]["conversation"]

    client.post(
        f"/api/v1/users/{_user('ben@example.com').handle}/block", headers=ada
    )
    response = client.post(
        f"/api/v1/conversations/{conversation['id']}/messages",
        json={"body": "still there?"},
        headers=ben,
    )
    assert response.status_code == 403


# ── Reading and writing threads ────────────────────────────────────────────


def test_thread_is_private_to_its_two_parties(client, auth):
    auth(email="ada@example.com")
    ben = auth(email="ben@example.com")
    conversation = _open(
        client, ben, to=_user("ada@example.com").handle, body="between us"
    ).get_json()["data"]["conversation"]

    intruder = auth(email="intruder@example.com")
    for path in (
        f"/api/v1/conversations/{conversation['id']}",
        f"/api/v1/conversations/{conversation['id']}/messages",
    ):
        assert client.get(path, headers=intruder).status_code == 404
    assert (
        client.post(
            f"/api/v1/conversations/{conversation['id']}/messages",
            json={"body": "let me in"},
            headers=intruder,
        ).status_code
        == 404
    )


def test_reply_and_read_back_newest_first(client, auth):
    ada = auth(email="ada@example.com")
    ben = auth(email="ben@example.com")
    conversation = _open(
        client, ben, to=_user("ada@example.com").handle, body="first"
    ).get_json()["data"]["conversation"]

    client.post(
        f"/api/v1/conversations/{conversation['id']}/messages",
        json={"body": "second"},
        headers=ada,
    )

    listing = client.get(
        f"/api/v1/conversations/{conversation['id']}/messages", headers=ben
    ).get_json()["data"]
    assert listing["total"] == 2
    assert [m["body"] for m in listing["messages"]] == ["second", "first"]
    assert listing["messages"][0]["sender"]["handle"] == _user("ada@example.com").handle


def test_unread_flags_and_read_stamp(client, auth):
    ada = auth(email="ada@example.com")
    ben = auth(email="ben@example.com")
    conversation = _open(
        client, ben, to=_user("ada@example.com").handle, body="ping"
    ).get_json()["data"]["conversation"]

    # Ada has unread mail; Ben (the sender) does not.
    assert client.get(
        "/api/v1/me/conversations/unread-count", headers=ada
    ).get_json()["data"]["unread_count"] == 1
    assert client.get(
        "/api/v1/me/conversations/unread-count", headers=ben
    ).get_json()["data"]["unread_count"] == 0

    ada_box = client.get("/api/v1/me/conversations", headers=ada).get_json()["data"]
    assert ada_box["conversations"][0]["unread"] is True
    assert ada_box["conversations"][0]["last_line"] == "ping"
    assert ada_box["conversations"][0]["last_from_me"] is False

    client.post(
        f"/api/v1/conversations/{conversation['id']}/read", headers=ada
    )
    assert client.get(
        "/api/v1/me/conversations/unread-count", headers=ada
    ).get_json()["data"]["unread_count"] == 0


def test_mailbox_lists_only_your_threads(client, auth):
    auth(email="ada@example.com")
    ben = auth(email="ben@example.com")
    carol = auth(email="carol@example.com")
    _open(client, ben, to=_user("ada@example.com").handle, body="a-b")
    _open(client, carol, to=_user("ada@example.com").handle, body="a-c")

    ben_box = client.get("/api/v1/me/conversations", headers=ben).get_json()["data"]
    assert ben_box["total"] == 1
    assert ben_box["conversations"][0]["with"]["handle"] == _user(
        "ada@example.com"
    ).handle
