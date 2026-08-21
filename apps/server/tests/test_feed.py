"""The Following feed: only what you follow, never what was kept private."""

from app.extensions import db
from app.models import User


def _user(email):
    return db.session.query(User).filter_by(email=email).one()


def _follow_user(client, follower, followee_email):
    handle = _user(followee_email).handle
    assert (
        client.post(f"/api/v1/users/{handle}/follow", headers=follower).status_code
        == 200
    )


def _feed(client, headers):
    response = client.get("/api/v1/me/feed", headers=headers)
    assert response.status_code == 200
    return response.get_json()["data"]


def test_feed_requires_auth(client):
    assert client.get("/api/v1/me/feed").status_code == 401


def test_feed_is_empty_without_follows(client, auth):
    assert _feed(client, auth())["items"] == []


def test_reviews_by_followed_readers_appear(client, auth, make_event):
    event = make_event(hours_ahead=-2, headline="Night Shift")
    ada = auth(email="ada@example.com", display_name="Ada Fournier")
    client.post(
        f"/api/v1/events/{event.id}/reviews",
        json={"rating": 5, "body": "Transcendent."},
        headers=ada,
    )

    ben = auth(email="ben@example.com")
    _follow_user(client, ben, "ada@example.com")

    items = _feed(client, ben)["items"]
    assert len(items) == 1
    assert items[0]["type"] == "review"
    assert items[0]["line"] == "Ada Fournier reviewed Night Shift"
    assert items[0]["review"]["rating"] == 5


def test_public_list_additions_appear_private_ones_never(client, auth, make_event):
    event = make_event(headline="Night Shift")
    ada = auth(email="ada@example.com", display_name="Ada Fournier")

    public = client.post(
        "/api/v1/me/lists", json={"name": "Open shelf", "is_public": True}, headers=ada
    ).get_json()["data"]["list"]
    private = client.post(
        "/api/v1/me/lists", json={"name": "Secret shelf"}, headers=ada
    ).get_json()["data"]["list"]
    client.put(f"/api/v1/me/lists/{public['id']}/events/{event.id}", headers=ada)
    client.put(f"/api/v1/me/lists/{private['id']}/events/{event.id}", headers=ada)

    ben = auth(email="ben@example.com")
    _follow_user(client, ben, "ada@example.com")

    items = _feed(client, ben)["items"]
    assert len(items) == 1
    assert items[0]["type"] == "list_add"
    assert items[0]["list"]["name"] == "Open shelf"


def test_shows_from_followed_artists_appear(client, auth, make_event):
    musician = auth(email="band@example.com")
    band = client.post(
        "/api/v1/me/artists", json={"name": "Bloodroot Choir"}, headers=musician
    ).get_json()["data"]["artist"]

    import uuid

    from app.models import Artist

    artist = db.session.get(Artist, uuid.UUID(band["id"]))
    make_event(artist=artist, headline="Album release")

    fan = auth(email="fan@example.com")
    client.post(f"/api/v1/artists/{band['id']}/follow", headers=fan)

    items = _feed(client, fan)["items"]
    assert len(items) == 1
    assert items[0]["type"] == "new_show"
    assert items[0]["line"] == "Bloodroot Choir posted a show"


def test_shows_posted_by_followed_readers_appear(client, auth, make_event):
    ada = auth(email="ada@example.com")
    make_event(created_by=_user("ada@example.com"), headline="Ada's night")
    assert ada is not None

    ben = auth(email="ben@example.com")
    _follow_user(client, ben, "ada@example.com")

    items = _feed(client, ben)["items"]
    assert [item["event"]["headline"] for item in items] == ["Ada's night"]


def test_blocking_empties_their_column(client, auth, make_event):
    event = make_event(hours_ahead=-2)
    ada = auth(email="ada@example.com")
    client.post(
        f"/api/v1/events/{event.id}/reviews", json={"rating": 4}, headers=ada
    )

    ben = auth(email="ben@example.com")
    _follow_user(client, ben, "ada@example.com")
    assert len(_feed(client, ben)["items"]) == 1

    client.post(f"/api/v1/users/{_user('ada@example.com').handle}/block", headers=ben)
    assert _feed(client, ben)["items"] == []


def test_feed_pages_newest_first(client, auth, make_event):
    ada = auth(email="ada@example.com")
    for index in range(3):
        event = make_event(hours_ahead=-2 - index, headline=f"Show {index}")
        client.post(
            f"/api/v1/events/{event.id}/reviews", json={"rating": 3}, headers=ada
        )

    ben = auth(email="ben@example.com")
    _follow_user(client, ben, "ada@example.com")

    page = client.get("/api/v1/me/feed?limit=2", headers=ben).get_json()["data"]
    assert len(page["items"]) == 2
    assert page["total"] == 3
    assert page["has_more"] is True

    stamps = [item["at"] for item in page["items"]]
    assert stamps == sorted(stamps, reverse=True)
