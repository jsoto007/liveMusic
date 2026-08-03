"""Band accounts: the public page, edits, follows."""

from app.extensions import db
from app.models import Artist, ArtistFollow, UserRole


def create_band(client, headers, name="Bloodroot Choir", **extra):
    response = client.post("/api/v1/me/artists", json={"name": name, **extra}, headers=headers)
    assert response.status_code == 201, response.get_json()
    return response.get_json()["data"]["artist"]


def test_creating_a_band_promotes_the_user_to_artist(client, auth):
    from app.models import User

    headers = auth(email="ada@example.com")
    create_band(client, headers)

    user = db.session.query(User).filter_by(email="ada@example.com").one()
    assert user.role is UserRole.ARTIST


def test_creating_a_band_does_not_downgrade_an_admin(client, auth, make_user):
    """A role change on an unrelated action is how privileges get lost."""
    admin = make_user(email="admin@example.com", role=UserRole.ADMIN)
    token = client.post(
        "/api/v1/auth/login",
        json={"email": "admin@example.com", "password": "correct-horse-battery"},
    ).get_json()["data"]["access_token"]

    create_band(client, {"Authorization": f"Bearer {token}"}, name="Admin's band")
    db.session.refresh(admin)
    assert admin.role is UserRole.ADMIN


def test_band_page_is_public_and_resolvable_by_slug(client, auth):
    headers = auth()
    band = create_band(client, headers)

    by_id = client.get(f"/api/v1/artists/{band['id']}")
    by_slug = client.get(f"/api/v1/artists/{band['slug']}")

    assert by_id.status_code == 200
    assert by_slug.status_code == 200
    assert by_slug.get_json()["data"]["artist"]["name"] == "Bloodroot Choir"


def test_slugs_are_unique_across_bands_of_the_same_name(client, auth):
    first = create_band(client, auth(email="one@example.com"))
    second = create_band(client, auth(email="two@example.com"))
    assert first["slug"] != second["slug"]


def test_owner_can_edit_the_profile(client, auth):
    headers = auth()
    band = create_band(client, headers)

    response = client.patch(
        f"/api/v1/artists/{band['id']}",
        json={
            "one_liner": "Post-punk quartet",
            "style_tags": ["Post-punk", "No wave"],
            "available_for_hire": True,
            "members": [{"name": "Ada Fournier", "instrument": "guitar, voice"}],
        },
        headers=headers,
    )
    assert response.status_code == 200

    artist = response.get_json()["data"]["artist"]
    assert artist["style_tags"] == ["Post-punk", "No wave"]
    assert artist["available_for_hire"] is True
    assert artist["members"][0]["name"] == "Ada Fournier"


def test_a_stranger_cannot_edit_your_band(client, auth):
    band = create_band(client, auth(email="owner@example.com"))
    intruder = auth(email="intruder@example.com")

    response = client.patch(
        f"/api/v1/artists/{band['id']}", json={"name": "Hijacked"}, headers=intruder
    )
    assert response.status_code == 404


def test_editing_a_band_cannot_change_its_owner(client, auth, make_user):
    """Mass-assignment check: an unexpected field must not be honoured."""
    import uuid

    headers = auth(email="owner@example.com")
    band = create_band(client, headers)
    stranger = make_user(email="stranger@example.com")

    client.patch(
        f"/api/v1/artists/{band['id']}",
        json={"owner_user_id": str(stranger.id), "verified_at": "2020-01-01T00:00:00Z"},
        headers=headers,
    )

    row = db.session.get(Artist, uuid.UUID(band["id"]))
    assert row.owner_user_id != stranger.id
    assert row.verified_at is None


def test_style_tags_are_capped(client, auth):
    headers = auth()
    band = create_band(client, headers)
    response = client.patch(
        f"/api/v1/artists/{band['id']}",
        json={"style_tags": [f"tag{i}" for i in range(40)]},
        headers=headers,
    )
    assert response.status_code == 400


def test_follow_and_unfollow(client, auth):
    band = create_band(client, auth(email="owner@example.com"))
    fan = auth(email="fan@example.com")

    followed = client.post(f"/api/v1/artists/{band['id']}/follow", headers=fan)
    assert followed.status_code == 200
    assert followed.get_json()["data"]["follower_count"] == 1

    unfollowed = client.delete(f"/api/v1/artists/{band['id']}/follow", headers=fan)
    assert unfollowed.get_json()["data"]["follower_count"] == 0


def test_following_twice_does_not_double_count(client, auth):
    band = create_band(client, auth(email="owner@example.com"))
    fan = auth(email="fan@example.com")

    client.post(f"/api/v1/artists/{band['id']}/follow", headers=fan)
    response = client.post(f"/api/v1/artists/{band['id']}/follow", headers=fan)

    assert response.get_json()["data"]["follower_count"] == 1
    assert db.session.query(ArtistFollow).count() == 1


def test_following_requires_authentication(client, auth):
    band = create_band(client, auth())
    assert client.post(f"/api/v1/artists/{band['id']}/follow").status_code == 401


def test_band_account_limit(client, auth):
    headers = auth()
    for index in range(5):
        create_band(client, headers, name=f"Band {index}")

    response = client.post("/api/v1/me/artists", json={"name": "One too many"},
                           headers=headers)
    assert response.status_code == 409
    assert response.get_json()["error"]["code"] == "LIMIT_REACHED"


def test_me_does_not_leak_another_users_email(client, auth):
    """An email only ever appears on the caller's own record."""
    band = create_band(client, auth(email="owner@example.com"))
    public = client.get(f"/api/v1/artists/{band['id']}").get_json()["data"]["artist"]
    assert "email" not in str(public)


def test_my_artist_events_include_drafts_but_only_mine(client, auth):
    from datetime import timedelta

    from app.models import utcnow

    headers = auth(email="owner@example.com")
    band = create_band(client, headers)

    client.post(
        "/api/v1/events",
        json={
            "headline": "Unannounced",
            "artist_id": band["id"],
            "starts_at": (utcnow() + timedelta(days=2)).isoformat(),
            "venue": {"name": "Dusk", "city": "Providence"},
            "publish": False,
        },
        headers=headers,
    )

    mine = client.get(f"/api/v1/me/artists/{band['id']}/events", headers=headers)
    assert [event["status"] for event in mine.get_json()["data"]["events"]] == ["draft"]

    intruder = auth(email="intruder@example.com")
    assert client.get(
        f"/api/v1/me/artists/{band['id']}/events", headers=intruder
    ).status_code == 404
