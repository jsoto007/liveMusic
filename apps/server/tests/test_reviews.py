"""Reviews: stars after the show, never before."""

from app.extensions import db
from app.models import Notification, NotificationKind, User


def _user(email):
    return db.session.query(User).filter_by(email=email).one()


def _review(client, headers, event, rating=4, body="Tight set."):
    return client.post(
        f"/api/v1/events/{event.id}/reviews",
        json={"rating": rating, "body": body},
        headers=headers,
    )


def test_review_a_started_show(client, auth, make_event):
    event = make_event(hours_ahead=-2)
    response = _review(client, auth(email="ada@example.com"), event, rating=5)
    assert response.status_code == 201
    review = response.get_json()["data"]["review"]
    assert review["rating"] == 5
    assert review["can_edit"] is True


def test_reviews_open_at_showtime_not_before(client, auth, make_event):
    event = make_event(hours_ahead=3)
    response = _review(client, auth(), event)
    assert response.status_code == 409
    assert response.get_json()["error"]["code"] == "NOT_STARTED"


def test_cancelled_shows_cannot_be_reviewed(client, auth, make_event):
    from app.models import EventStatus

    event = make_event(hours_ahead=-2, status=EventStatus.CANCELLED)
    response = _review(client, auth(), event)
    assert response.status_code == 409
    assert response.get_json()["error"]["code"] == "EVENT_CANCELLED"


def test_review_requires_auth_and_a_sane_rating(client, auth, make_event):
    event = make_event(hours_ahead=-2)
    assert _review(client, None or {}, event).status_code == 401

    headers = auth()
    for bad in (0, 6, "five", None):
        response = client.post(
            f"/api/v1/events/{event.id}/reviews",
            json={"rating": bad},
            headers=headers,
        )
        assert response.status_code == 400, bad


def test_one_review_per_reader(client, auth, make_event):
    event = make_event(hours_ahead=-2)
    headers = auth()
    assert _review(client, headers, event).status_code == 201
    duplicate = _review(client, headers, event, rating=1)
    assert duplicate.status_code == 409
    assert duplicate.get_json()["error"]["code"] == "ALREADY_REVIEWED"


def test_edit_and_delete_own_review(client, auth, make_event):
    event = make_event(hours_ahead=-2)
    headers = auth()
    review = _review(client, headers, event).get_json()["data"]["review"]

    edited = client.patch(
        f"/api/v1/reviews/{review['id']}", json={"rating": 2}, headers=headers
    )
    assert edited.status_code == 200
    assert edited.get_json()["data"]["review"]["rating"] == 2

    deleted = client.delete(f"/api/v1/reviews/{review['id']}", headers=headers)
    assert deleted.status_code == 200


def test_foreign_review_is_untouchable(client, auth, make_event):
    event = make_event(hours_ahead=-2)
    review = _review(client, auth(email="author@example.com"), event).get_json()[
        "data"
    ]["review"]

    intruder = auth(email="intruder@example.com")
    assert (
        client.patch(
            f"/api/v1/reviews/{review['id']}", json={"rating": 1}, headers=intruder
        ).status_code
        == 404
    )
    assert (
        client.delete(f"/api/v1/reviews/{review['id']}", headers=intruder).status_code
        == 404
    )


def test_aggregates_ride_the_event_detail(client, auth, make_event):
    event = make_event(hours_ahead=-2)
    _review(client, auth(email="one@example.com"), event, rating=5)
    _review(client, auth(email="two@example.com"), event, rating=2)

    detail = client.get(f"/api/v1/events/{event.id}").get_json()["data"]["event"]
    assert detail["review_count"] == 2
    assert detail["avg_rating"] == 3.5

    listing = client.get(f"/api/v1/events/{event.id}/reviews").get_json()["data"]
    assert listing["review_count"] == 2
    assert listing["avg_rating"] == 3.5


def test_reviews_list_marks_mine(client, auth, make_event):
    event = make_event(hours_ahead=-2)
    headers = auth(email="ada@example.com")
    _review(client, headers, event, rating=4)

    response = client.get(f"/api/v1/events/{event.id}/reviews", headers=headers)
    data = response.get_json()["data"]
    assert data["my_review"]["rating"] == 4

    anonymous = client.get(f"/api/v1/events/{event.id}/reviews")
    assert anonymous.get_json()["data"]["my_review"] is None


def test_review_notifies_the_event_owner(client, auth, make_user, make_event):
    owner = make_user(email="owner@example.com")
    event = make_event(hours_ahead=-2, created_by=owner)
    _review(client, auth(email="fan@example.com"), event)

    rows = (
        db.session.query(Notification)
        .filter(
            Notification.user_id == owner.id,
            Notification.kind == NotificationKind.EVENT_REVIEW,
        )
        .all()
    )
    assert len(rows) == 1


def test_blocked_reviews_are_mutually_invisible(client, auth, make_event):
    event = make_event(hours_ahead=-2)
    ada = auth(email="ada@example.com")
    ben = auth(email="ben@example.com")
    _review(client, ben, event, rating=1, body="Ben's verdict")

    client.post(f"/api/v1/users/{_user('ben@example.com').handle}/block", headers=ada)

    seen_by_ada = client.get(f"/api/v1/events/{event.id}/reviews", headers=ada)
    assert seen_by_ada.get_json()["data"]["total"] == 0

    # The aggregate stays honest — hiding a voice does not un-count its vote.
    assert seen_by_ada.get_json()["data"]["review_count"] == 1


def test_profile_lists_a_readers_reviews(client, auth, make_event):
    event = make_event(hours_ahead=-2, headline="Night Shift")
    headers = auth(email="ada@example.com")
    _review(client, headers, event)

    handle = _user("ada@example.com").handle
    response = client.get(f"/api/v1/users/{handle}/reviews")
    data = response.get_json()["data"]
    assert data["total"] == 1
    assert data["reviews"][0]["event"]["headline"] == "Night Shift"
