"""The classifieds board: gigs, applications, and who may decide what."""

from app.extensions import db
from app.models import (
    GigApplication,
    Notification,
    NotificationKind,
    User,
    UserRole,
)


def _user(email):
    return db.session.query(User).filter_by(email=email).one()


def _band(client, headers, name="Bloodroot Choir"):
    response = client.post("/api/v1/me/artists", json={"name": name}, headers=headers)
    assert response.status_code == 201
    return response.get_json()["data"]["artist"]


def _gig(client, headers, **extra):
    body = {
        "title": "Jazz trio wanted for Friday residency",
        "description": "Standards and originals, two sets, house PA.",
        "city": "New York",
        **extra,
    }
    response = client.post("/api/v1/gigs", json=body, headers=headers)
    assert response.status_code == 201, response.get_json()
    return response.get_json()["data"]["gig"]


def _apply(client, headers, gig, artist, message="We're free Fridays."):
    return client.post(
        f"/api/v1/gigs/{gig['id']}/applications",
        json={"artist_id": artist["id"], "message": message},
        headers=headers,
    )


# ── Posting and browsing ───────────────────────────────────────────────────


def test_post_and_browse_gigs(client, auth):
    poster = auth(email="venue@example.com")
    _gig(client, poster, pay_cents=30000, genre="jazz")

    board = client.get("/api/v1/gigs")
    assert board.status_code == 200
    data = board.get_json()["data"]
    assert data["total"] == 1
    gig = data["gigs"][0]
    assert gig["pay_label"] == "$300"
    assert gig["genre_label"] == "Jazz"
    assert gig["status"] == "open"


def test_posting_requires_auth_and_fields(client, auth):
    assert (
        client.post("/api/v1/gigs", json={"title": "x"}).status_code == 401
    )
    headers = auth()
    for body in (
        {},
        {"title": "Only a title"},
        {"title": "T", "description": "D"},  # city missing
        {"title": "T", "description": "D", "city": "NYC", "timezone": "Mars/Olympus"},
        {"title": "T", "description": "D", "city": "NYC", "pay_cents": -5},
    ):
        response = client.post("/api/v1/gigs", json=body, headers=headers)
        assert response.status_code == 400, body


def test_board_filters(client, auth):
    poster = auth(email="venue@example.com")
    _gig(client, poster, title="Jazz night", genre="jazz", city="New York")
    _gig(client, poster, title="Metal opener", genre="metal", city="Providence")

    by_genre = client.get("/api/v1/gigs?genre=metal").get_json()["data"]
    assert by_genre["total"] == 1
    assert by_genre["gigs"][0]["title"] == "Metal opener"

    by_city = client.get("/api/v1/gigs?city=providence").get_json()["data"]
    assert by_city["total"] == 1

    by_text = client.get("/api/v1/gigs?q=opener").get_json()["data"]
    assert by_text["total"] == 1


def test_closed_gigs_leave_the_board_but_keep_their_page(client, auth):
    poster = auth(email="venue@example.com")
    gig = _gig(client, poster)
    client.patch(f"/api/v1/gigs/{gig['id']}", json={"status": "closed"}, headers=poster)

    assert client.get("/api/v1/gigs").get_json()["data"]["total"] == 0
    assert client.get(f"/api/v1/gigs/{gig['id']}").status_code == 200


def test_editing_a_foreign_gig_is_a_404(client, auth):
    poster = auth(email="venue@example.com")
    gig = _gig(client, poster)

    intruder = auth(email="intruder@example.com")
    assert (
        client.patch(
            f"/api/v1/gigs/{gig['id']}", json={"title": "Mine"}, headers=intruder
        ).status_code
        == 404
    )
    assert client.delete(f"/api/v1/gigs/{gig['id']}", headers=intruder).status_code == 404


# ── Applying ───────────────────────────────────────────────────────────────


def test_apply_with_your_band(client, auth):
    poster = auth(email="venue@example.com")
    gig = _gig(client, poster)

    musician = auth(email="band@example.com")
    band = _band(client, musician)
    response = _apply(client, musician, gig, band)
    assert response.status_code == 201
    application = response.get_json()["data"]["application"]
    assert application["status"] == "pending"

    # The poster hears about it.
    rows = (
        db.session.query(Notification)
        .filter(
            Notification.user_id == _user("venue@example.com").id,
            Notification.kind == NotificationKind.GIG_APPLICATION,
        )
        .all()
    )
    assert len(rows) == 1


def test_cannot_apply_with_someone_elses_band(client, auth):
    poster = auth(email="venue@example.com")
    gig = _gig(client, poster)

    owner = auth(email="owner@example.com")
    band = _band(client, owner)

    impostor = auth(email="impostor@example.com")
    response = _apply(client, impostor, gig, band)
    assert response.status_code == 404  # same as a band that does not exist


def test_admins_get_no_application_bypass(client, auth, make_user):
    """Editors moderate the board; they do not audition other people's bands."""
    poster = auth(email="venue@example.com")
    gig = _gig(client, poster)
    band = _band(client, auth(email="owner@example.com"))

    make_user(email="editor@example.com", role=UserRole.ADMIN)
    token = client.post(
        "/api/v1/auth/login",
        json={"email": "editor@example.com", "password": "correct-horse-battery"},
    ).get_json()["data"]["access_token"]

    response = _apply(client, {"Authorization": f"Bearer {token}"}, gig, band)
    assert response.status_code == 404


def test_cannot_apply_to_your_own_gig(client, auth):
    poster = auth(email="venue@example.com")
    gig = _gig(client, poster)
    band = _band(client, poster)
    response = _apply(client, poster, gig, band)
    assert response.status_code == 400
    assert response.get_json()["error"]["code"] == "OWN_GIG"


def test_one_application_per_band(client, auth):
    poster = auth(email="venue@example.com")
    gig = _gig(client, poster)
    musician = auth(email="band@example.com")
    band = _band(client, musician)

    assert _apply(client, musician, gig, band).status_code == 201
    duplicate = _apply(client, musician, gig, band)
    assert duplicate.status_code == 409
    assert duplicate.get_json()["error"]["code"] == "ALREADY_APPLIED"

    # A second band of the same owner is a different hand.
    second = _band(client, musician, name="Side Project")
    assert _apply(client, musician, gig, second).status_code == 201


def test_closed_gigs_take_no_applications(client, auth):
    poster = auth(email="venue@example.com")
    gig = _gig(client, poster)
    client.patch(f"/api/v1/gigs/{gig['id']}", json={"status": "closed"}, headers=poster)

    musician = auth(email="band@example.com")
    band = _band(client, musician)
    response = _apply(client, musician, gig, band)
    assert response.status_code == 409
    assert response.get_json()["error"]["code"] == "GIG_CLOSED"


# ── Reading and deciding ───────────────────────────────────────────────────


def test_only_the_poster_reads_applications(client, auth):
    poster = auth(email="venue@example.com")
    gig = _gig(client, poster)
    musician = auth(email="band@example.com")
    band = _band(client, musician)
    _apply(client, musician, gig, band)

    allowed = client.get(f"/api/v1/gigs/{gig['id']}/applications", headers=poster)
    assert allowed.status_code == 200
    assert len(allowed.get_json()["data"]["applications"]) == 1

    # The applicant sees their own hand on the gig page, not the whole pile.
    assert (
        client.get(f"/api/v1/gigs/{gig['id']}/applications", headers=musician).status_code
        == 404
    )
    detail = client.get(f"/api/v1/gigs/{gig['id']}", headers=musician).get_json()[
        "data"
    ]["gig"]
    assert len(detail["my_applications"]) == 1
    assert "application_count" not in detail

    poster_detail = client.get(f"/api/v1/gigs/{gig['id']}", headers=poster).get_json()[
        "data"
    ]["gig"]
    assert poster_detail["application_count"] == 1


def test_decide_notifies_the_band(client, auth):
    poster = auth(email="venue@example.com")
    gig = _gig(client, poster)
    musician = auth(email="band@example.com")
    band = _band(client, musician)
    application = _apply(client, musician, gig, band).get_json()["data"]["application"]

    decided = client.patch(
        f"/api/v1/gigs/{gig['id']}/applications/{application['id']}",
        json={"status": "accepted"},
        headers=poster,
    )
    assert decided.status_code == 200
    assert decided.get_json()["data"]["application"]["status"] == "accepted"

    rows = (
        db.session.query(Notification)
        .filter(
            Notification.user_id == _user("band@example.com").id,
            Notification.kind == NotificationKind.GIG_ACCEPTED,
        )
        .all()
    )
    assert len(rows) == 1


def test_deciding_requires_owning_the_gig(client, auth):
    poster = auth(email="venue@example.com")
    gig = _gig(client, poster)
    musician = auth(email="band@example.com")
    band = _band(client, musician)
    application = _apply(client, musician, gig, band).get_json()["data"]["application"]

    # The applicant cannot accept themselves.
    response = client.patch(
        f"/api/v1/gigs/{gig['id']}/applications/{application['id']}",
        json={"status": "accepted"},
        headers=musician,
    )
    assert response.status_code == 404

    # And "pending" is not a decision.
    undecided = client.patch(
        f"/api/v1/gigs/{gig['id']}/applications/{application['id']}",
        json={"status": "pending"},
        headers=poster,
    )
    assert undecided.status_code == 400


def test_application_ids_are_scoped_to_their_gig(client, auth):
    poster = auth(email="venue@example.com")
    gig_a = _gig(client, poster, title="Gig A")
    gig_b = _gig(client, poster, title="Gig B")
    musician = auth(email="band@example.com")
    band = _band(client, musician)
    application = _apply(client, musician, gig_a, band).get_json()["data"]["application"]

    # Right application, wrong gig in the path.
    response = client.patch(
        f"/api/v1/gigs/{gig_b['id']}/applications/{application['id']}",
        json={"status": "accepted"},
        headers=poster,
    )
    assert response.status_code == 404


def test_withdraw_your_application(client, auth):
    poster = auth(email="venue@example.com")
    gig = _gig(client, poster)
    musician = auth(email="band@example.com")
    band = _band(client, musician)
    application = _apply(client, musician, gig, band).get_json()["data"]["application"]

    intruder = auth(email="intruder@example.com")
    assert (
        client.delete(
            f"/api/v1/gigs/{gig['id']}/applications/{application['id']}",
            headers=intruder,
        ).status_code
        == 404
    )

    withdrawn = client.delete(
        f"/api/v1/gigs/{gig['id']}/applications/{application['id']}", headers=musician
    )
    assert withdrawn.status_code == 200
    assert db.session.query(GigApplication).count() == 0


def test_deleting_a_gig_takes_its_applications(client, auth):
    poster = auth(email="venue@example.com")
    gig = _gig(client, poster)
    musician = auth(email="band@example.com")
    band = _band(client, musician)
    _apply(client, musician, gig, band)

    client.delete(f"/api/v1/gigs/{gig['id']}", headers=poster)
    assert db.session.query(GigApplication).count() == 0


def test_my_gigs_and_my_applications(client, auth):
    poster = auth(email="venue@example.com")
    gig = _gig(client, poster)
    musician = auth(email="band@example.com")
    band = _band(client, musician)
    _apply(client, musician, gig, band)

    mine = client.get("/api/v1/me/gigs", headers=poster).get_json()["data"]["gigs"]
    assert len(mine) == 1
    assert mine[0]["application_count"] == 1

    applications = client.get("/api/v1/me/applications", headers=musician).get_json()[
        "data"
    ]["applications"]
    assert len(applications) == 1
    assert applications[0]["gig"]["title"] == gig["title"]


# ── The hire directory ─────────────────────────────────────────────────────


def test_for_hire_directory_lists_only_flagged_bands(client, auth):
    musician = auth(email="band@example.com")
    listed = _band(client, musician, name="Available Band")
    _band(client, musician, name="Private Band")
    client.patch(
        f"/api/v1/artists/{listed['id']}",
        json={"available_for_hire": True},
        headers=musician,
    )

    directory = client.get("/api/v1/artists/for-hire").get_json()["data"]
    assert directory["total"] == 1
    assert directory["artists"][0]["name"] == "Available Band"


def test_for_hire_directory_filters(client, auth):
    musician = auth(email="band@example.com")
    jazz = _band(client, musician, name="Cool Trio")
    client.patch(
        f"/api/v1/artists/{jazz['id']}",
        json={"available_for_hire": True, "city": "New York",
              "style_tags": ["Hard bop"]},
        headers=musician,
    )

    assert client.get("/api/v1/artists/for-hire?city=new%20york").get_json()["data"][
        "total"
    ] == 1
    assert client.get("/api/v1/artists/for-hire?q=hard%20bop").get_json()["data"][
        "total"
    ] == 1
    assert client.get("/api/v1/artists/for-hire?q=zydeco").get_json()["data"][
        "total"
    ] == 0
