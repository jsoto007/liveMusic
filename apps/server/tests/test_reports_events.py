"""Reporting a listing — Guideline 1.2's missing surface.

A listing carries a headline, a support line, a note and an uploaded poster,
and until now it was the one user-written thing in the paper with no flag on
it. These are written against the ways that flag can go wrong: reporting a
draft nobody could have seen, reporting your own listing instead of cancelling
it, an editor removing a listing and taking the audit line with it, and an
editor's removal deleting a stock image that was never the poster's to lose.
"""

import pytest

from app.extensions import db as _db
from app.models import (
    ContentReport,
    Event,
    EventStatus,
    ReportStatus,
    User,
    UserRole,
)


@pytest.fixture()
def reporter(client):
    response = client.post(
        "/api/v1/auth/register",
        json={
            "email": "reader@example.com",
            "password": "correct-horse-battery",
            "display_name": "Reader",
        },
    )
    assert response.status_code == 201
    token = response.get_json()["data"]["access_token"]
    return {"Authorization": f"Bearer {token}"}


@pytest.fixture()
def editor(client, db):
    response = client.post(
        "/api/v1/auth/register",
        json={
            "email": "editor@example.com",
            "password": "correct-horse-battery",
            "display_name": "Editor",
        },
    )
    user = db.session.query(User).filter(User.email == "editor@example.com").one()
    user.role = UserRole.ADMIN
    db.session.commit()
    token = response.get_json()["data"]["access_token"]
    return {"Authorization": f"Bearer {token}"}


# ── Filing ─────────────────────────────────────────────────────────────────


def test_a_reader_can_report_a_published_listing(client, reporter, make_event):
    event = make_event(headline="Something Objectionable")

    response = client.post(
        "/api/v1/reports",
        json={"event_id": str(event.id), "reason": "inappropriate"},
        headers=reporter,
    )
    assert response.status_code == 201
    assert response.get_json()["data"] == {"reported": True}

    report = _db.session.query(ContentReport).one()
    assert report.event_id == event.id
    assert report.status is ReportStatus.OPEN


def test_reporting_requires_authentication(client, make_event):
    event = make_event()
    response = client.post(
        "/api/v1/reports",
        json={"event_id": str(event.id), "reason": "spam"},
    )
    assert response.status_code == 401


def test_a_draft_cannot_be_reported(client, reporter, make_event):
    """A draft was never published, so a reader could not have seen it. A 404
    also keeps the route from confirming that an unpublished listing exists."""
    event = make_event(status=EventStatus.DRAFT)
    response = client.post(
        "/api/v1/reports",
        json={"event_id": str(event.id), "reason": "spam"},
        headers=reporter,
    )
    assert response.status_code == 404


def test_you_cannot_report_your_own_listing(client, db, make_event):
    registered = client.post(
        "/api/v1/auth/register",
        json={
            "email": "poster@example.com",
            "password": "correct-horse-battery",
            "display_name": "Poster",
        },
    )
    token = registered.get_json()["data"]["access_token"]
    poster = db.session.query(User).filter(User.email == "poster@example.com").one()
    event = make_event(created_by=poster)

    response = client.post(
        "/api/v1/reports",
        json={"event_id": str(event.id), "reason": "spam"},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert response.status_code == 400
    assert response.get_json()["error"]["details"]["subject"] == "own_content"


def test_two_subjects_at_once_is_refused(client, reporter, make_event):
    """The schema allows at most one subject; the route must require exactly
    one, or a caller could file an ambiguous report the desk cannot render."""
    event = make_event()
    response = client.post(
        "/api/v1/reports",
        json={
            "event_id": str(event.id),
            "reported_user_id": str(event.id),
            "reason": "spam",
        },
        headers=reporter,
    )
    assert response.status_code == 400
    assert response.get_json()["error"]["details"]["subject"] == "exactly_one"


def test_a_malformed_event_id_is_a_validation_error_not_a_500(client, reporter):
    response = client.post(
        "/api/v1/reports",
        json={"event_id": "not-a-uuid", "reason": "spam"},
        headers=reporter,
    )
    assert response.status_code == 400
    assert response.get_json()["error"]["code"] == "VALIDATION_ERROR"


def test_an_unknown_listing_is_not_found(client, reporter):
    response = client.post(
        "/api/v1/reports",
        json={
            "event_id": "00000000-0000-4000-8000-000000000000",
            "reason": "spam",
        },
        headers=reporter,
    )
    assert response.status_code == 404


# ── The desk ───────────────────────────────────────────────────────────────


def test_the_desk_shows_the_reported_listing(client, reporter, editor, make_event):
    event = make_event(headline="Something Objectionable")
    client.post(
        "/api/v1/reports",
        json={"event_id": str(event.id), "reason": "inappropriate"},
        headers=reporter,
    )

    response = client.get("/api/v1/admin/reports", headers=editor)
    assert response.status_code == 200
    row = response.get_json()["data"]["reports"][0]
    assert row["subject_type"] == "event"
    assert row["event"]["headline"] == "Something Objectionable"


def test_a_non_editor_cannot_see_the_desk(client, reporter, make_event):
    event = make_event()
    client.post(
        "/api/v1/reports",
        json={"event_id": str(event.id), "reason": "spam"},
        headers=reporter,
    )
    assert client.get("/api/v1/admin/reports", headers=reporter).status_code == 404


def test_removing_a_listing_cancels_it_and_destroys_its_poster(
    client, reporter, editor, make_event, stub_r2
):
    event = make_event(poster_key="events/poster/bad.jpg")
    event_id = event.id
    stub_r2["put"]("events/poster/bad.jpg", content_type="image/jpeg")
    client.post(
        "/api/v1/reports",
        json={"event_id": str(event_id), "reason": "inappropriate"},
        headers=reporter,
    )
    report_id = _db.session.query(ContentReport).one().id

    response = client.post(
        f"/api/v1/admin/reports/{report_id}/resolve",
        json={"action": "remove_content"},
        headers=editor,
    )
    assert response.status_code == 200
    _db.session.expire_all()

    listing = _db.session.get(Event, event_id)
    assert listing is not None, "a listing readers hold on a list is cancelled, not deleted"
    assert listing.status is EventStatus.CANCELLED
    assert listing.cancelled_at is not None
    assert listing.poster_key is None
    assert "events/poster/bad.jpg" in stub_r2["deleted"]


def test_removing_a_listing_keeps_the_audit_line(
    client, reporter, editor, make_event
):
    """The report row is the record that moderation happened. Cancelling the
    listing must not take it with it."""
    event = make_event()
    client.post(
        "/api/v1/reports",
        json={"event_id": str(event.id), "reason": "spam"},
        headers=reporter,
    )
    report_id = _db.session.query(ContentReport).one().id

    client.post(
        f"/api/v1/admin/reports/{report_id}/resolve",
        json={"action": "remove_content"},
        headers=editor,
    )
    _db.session.expire_all()

    report = _db.session.get(ContentReport, report_id)
    assert report is not None
    assert report.status is ReportStatus.RESOLVED
    assert report.resolved_at is not None


def test_dismissing_leaves_the_listing_on_the_bill(
    client, reporter, editor, make_event
):
    event = make_event(poster_key="events/poster/fine.jpg")
    event_id = event.id
    client.post(
        "/api/v1/reports",
        json={"event_id": str(event_id), "reason": "spam"},
        headers=reporter,
    )
    report_id = _db.session.query(ContentReport).one().id

    client.post(
        f"/api/v1/admin/reports/{report_id}/resolve",
        json={"action": "dismiss"},
        headers=editor,
    )
    _db.session.expire_all()

    listing = _db.session.get(Event, event_id)
    assert listing.status is EventStatus.PUBLISHED
    assert listing.poster_key == "events/poster/fine.jpg"


def test_deleting_the_listing_nulls_the_pointer_not_the_report(
    client, reporter, make_event
):
    """`ON DELETE SET NULL`, like every other subject column: the report
    survives its subject and reads as 'content already removed'."""
    event = make_event(status=EventStatus.DRAFT)
    event.status = EventStatus.PUBLISHED
    _db.session.commit()
    client.post(
        "/api/v1/reports",
        json={"event_id": str(event.id), "reason": "spam"},
        headers=reporter,
    )
    report_id = _db.session.query(ContentReport).one().id

    _db.session.delete(event)
    _db.session.commit()
    _db.session.expire_all()

    report = _db.session.get(ContentReport, report_id)
    assert report is not None
    assert report.event_id is None
