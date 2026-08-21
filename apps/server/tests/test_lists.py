"""Named lists: shelves, their privacy, and their caps."""

from app.extensions import db
from app.models import EventList, EventListItem, EventStatus, User
from app.services.lists import MAX_ITEMS_PER_LIST, MAX_LISTS_PER_USER


def _user(email):
    return db.session.query(User).filter_by(email=email).one()


def _create_list(client, headers, name="Jazz to catch", **extra):
    response = client.post(
        "/api/v1/me/lists", json={"name": name, **extra}, headers=headers
    )
    assert response.status_code == 201, response.get_json()
    return response.get_json()["data"]["list"]


# ── CRUD ───────────────────────────────────────────────────────────────────


def test_create_and_list_lists(client, auth):
    headers = auth()
    created = _create_list(client, headers, description="For October")

    mine = client.get("/api/v1/me/lists", headers=headers)
    assert mine.status_code == 200
    lists = mine.get_json()["data"]["lists"]
    assert len(lists) == 1
    assert lists[0]["id"] == created["id"]
    assert lists[0]["is_public"] is False  # private is the default
    assert lists[0]["item_count"] == 0


def test_lists_require_auth(client):
    assert client.get("/api/v1/me/lists").status_code == 401
    assert client.post("/api/v1/me/lists", json={"name": "x"}).status_code == 401


def test_malformed_list_body(client, auth):
    headers = auth()
    assert client.post("/api/v1/me/lists", json={}, headers=headers).status_code == 400
    assert (
        client.post(
            "/api/v1/me/lists", json={"name": "x" * 81}, headers=headers
        ).status_code
        == 400
    )
    assert (
        client.post(
            "/api/v1/me/lists",
            json={"name": "ok", "is_public": "yes"},
            headers=headers,
        ).status_code
        == 400
    )


def test_duplicate_list_name_is_a_409(client, auth):
    headers = auth()
    _create_list(client, headers, name="Jazz")
    response = client.post("/api/v1/me/lists", json={"name": "jazz"}, headers=headers)
    assert response.status_code == 409
    assert response.get_json()["error"]["code"] == "NAME_TAKEN"


def test_list_cap_is_enforced(client, auth):
    headers = auth(email="ada@example.com")
    owner = _user("ada@example.com")
    for index in range(MAX_LISTS_PER_USER):
        db.session.add(EventList(owner_user_id=owner.id, name=f"Shelf {index}"))
    db.session.commit()

    response = client.post("/api/v1/me/lists", json={"name": "One more"}, headers=headers)
    assert response.status_code == 409
    assert response.get_json()["error"]["code"] == "LIMIT_REACHED"


def test_rename_and_visibility_toggle(client, auth):
    headers = auth()
    created = _create_list(client, headers)

    response = client.patch(
        f"/api/v1/me/lists/{created['id']}",
        json={"name": "October", "is_public": True},
        headers=headers,
    )
    assert response.status_code == 200
    updated = response.get_json()["data"]["list"]
    assert updated["name"] == "October"
    assert updated["is_public"] is True


def test_touching_a_foreign_list_is_a_404(client, auth):
    owner = auth(email="owner@example.com")
    created = _create_list(client, owner)

    intruder = auth(email="intruder@example.com")
    for method, kwargs in (
        (client.patch, {"json": {"name": "Mine now"}}),
        (client.delete, {}),
    ):
        response = method(
            f"/api/v1/me/lists/{created['id']}", headers=intruder, **kwargs
        )
        assert response.status_code == 404


def test_delete_list_removes_items(client, auth, make_event):
    headers = auth()
    created = _create_list(client, headers)
    event = make_event()
    client.put(
        f"/api/v1/me/lists/{created['id']}/events/{event.id}", headers=headers
    )

    response = client.delete(f"/api/v1/me/lists/{created['id']}", headers=headers)
    assert response.status_code == 200
    assert db.session.query(EventListItem).count() == 0


# ── Items ──────────────────────────────────────────────────────────────────


def test_add_and_remove_event(client, auth, make_event):
    headers = auth()
    created = _create_list(client, headers)
    event = make_event()

    added = client.put(
        f"/api/v1/me/lists/{created['id']}/events/{event.id}",
        json={"note": "Front row"},
        headers=headers,
    )
    assert added.status_code == 200
    assert added.get_json()["data"]["item_count"] == 1

    # Idempotent — a second PUT is a note update, not a duplicate.
    again = client.put(
        f"/api/v1/me/lists/{created['id']}/events/{event.id}", headers=headers
    )
    assert again.get_json()["data"]["item_count"] == 1

    removed = client.delete(
        f"/api/v1/me/lists/{created['id']}/events/{event.id}", headers=headers
    )
    assert removed.get_json()["data"]["item_count"] == 0


def test_draft_events_cannot_be_shelved(client, auth, make_event):
    headers = auth()
    created = _create_list(client, headers)
    draft = make_event(status=EventStatus.DRAFT)

    response = client.put(
        f"/api/v1/me/lists/{created['id']}/events/{draft.id}", headers=headers
    )
    assert response.status_code == 404


def test_item_cap_is_enforced(client, auth, make_event):
    headers = auth(email="ada@example.com")
    created = _create_list(client, headers)
    event = make_event()

    import uuid

    # Fill the shelf directly; the API path would be 200 slow round-trips.
    list_id = uuid.UUID(created["id"])
    for index in range(MAX_ITEMS_PER_LIST):
        extra = make_event(headline=f"Filler {index}")
        db.session.add(EventListItem(list_id=list_id, event_id=extra.id))
    db.session.commit()

    response = client.put(
        f"/api/v1/me/lists/{list_id}/events/{event.id}", headers=headers
    )
    assert response.status_code == 409
    assert response.get_json()["error"]["code"] == "LIMIT_REACHED"


def test_adding_to_a_foreign_list_is_a_404(client, auth, make_event):
    owner = auth(email="owner@example.com")
    created = _create_list(client, owner)
    event = make_event()

    intruder = auth(email="intruder@example.com")
    response = client.put(
        f"/api/v1/me/lists/{created['id']}/events/{event.id}", headers=intruder
    )
    assert response.status_code == 404


# ── The public read ────────────────────────────────────────────────────────


def test_public_list_is_readable_by_anyone(client, auth, make_event):
    headers = auth(email="ada@example.com", display_name="Ada Fournier")
    created = _create_list(client, headers, is_public=True)
    event = make_event(headline="Night Shift")
    client.put(
        f"/api/v1/me/lists/{created['id']}/events/{event.id}", headers=headers
    )

    response = client.get(f"/api/v1/lists/{created['id']}")
    assert response.status_code == 200
    data = response.get_json()["data"]
    assert data["list"]["owner"]["handle"] == "ada_fournier"
    assert data["entries"][0]["event"]["headline"] == "Night Shift"
    assert data["can_manage"] is False


def test_private_list_is_invisible_to_everyone_but_its_owner(client, auth):
    headers = auth(email="ada@example.com")
    created = _create_list(client, headers)  # private by default

    anonymous = client.get(f"/api/v1/lists/{created['id']}")
    assert anonymous.status_code == 404

    stranger = client.get(
        f"/api/v1/lists/{created['id']}", headers=auth(email="ben@example.com")
    )
    assert stranger.status_code == 404

    owner = client.get(f"/api/v1/lists/{created['id']}", headers=headers)
    assert owner.status_code == 200
    assert owner.get_json()["data"]["can_manage"] is True


def test_profile_lists_show_only_public_to_strangers(client, auth):
    headers = auth(email="ada@example.com")
    _create_list(client, headers, name="Public shelf", is_public=True)
    _create_list(client, headers, name="Private shelf")
    handle = _user("ada@example.com").handle

    stranger = client.get(f"/api/v1/users/{handle}/lists")
    names = [row["name"] for row in stranger.get_json()["data"]["lists"]]
    assert names == ["Public shelf"]

    owner = client.get(f"/api/v1/users/{handle}/lists", headers=headers)
    assert len(owner.get_json()["data"]["lists"]) == 2
