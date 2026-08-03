"""Regressions for the listings defects found in the 2026-08-03 review.

Each of these was a user-visible wrong answer, not a theoretical concern.
"""

from datetime import date, datetime, time, timedelta, timezone
from zoneinfo import ZoneInfo

import pytest

from app.models import AgeRestriction, Event, EventStatus, Genre, utcnow
from app.routes.serializers import day_bucket, day_label, group_events_by_day, serialize_event

ZONE = "America/New_York"


@pytest.fixture()
def make_event(db, make_venue):
    def _make(venue=None, starts_at=None, headline="A show", **kwargs):
        venue = venue or make_venue(timezone_name=ZONE)
        event = Event(
            venue_id=venue.id,
            headline=headline,
            genre=Genre.ROCK_PUNK,
            starts_at=starts_at or (utcnow() + timedelta(hours=3)),
            age_restriction=AgeRestriction.ALL_AGES,
            status=EventStatus.PUBLISHED,
            published_at=utcnow(),
            **kwargs,
        )
        db.session.add(event)
        db.session.commit()
        return event

    return _make


def at(local_date: date, hour: int = 20, zone: str = ZONE):
    """A UTC instant for a wall-clock time in the venue's zone."""
    return datetime.combine(local_date, time(hour), tzinfo=ZoneInfo(zone)).astimezone(timezone.utc)


def now_at(local_date: date, hour: int = 12, zone: str = ZONE):
    return at(local_date, hour, zone)


# ── The weekend bucket was off by a week ───────────────────────────────────


def test_on_a_saturday_this_weekend_means_today_not_next_week():
    """`delta <= 7 and weekday in (4,5,6)` reached NEXT weekend's Fri and Sat
    while dropping this weekend's Sunday into 'Later on' — a section headed
    'This weekend' listing shows eight days out."""
    saturday = date(2026, 9, 5)
    now = now_at(saturday)

    assert day_bucket(at(saturday, 21), ZONE, now=now) == "tonight"
    assert day_bucket(at(date(2026, 9, 6)), ZONE, now=now) == "tomorrow"
    # Next weekend must NOT be "this weekend".
    assert day_bucket(at(date(2026, 9, 11)), ZONE, now=now) == "later"
    assert day_bucket(at(date(2026, 9, 12)), ZONE, now=now) == "later"


def test_on_a_friday_the_weekend_does_not_span_two_weekends():
    """It used to hold both this Sunday and next Friday, so the page printed a
    listing eight days out above one three days out."""
    friday = date(2026, 9, 4)
    now = now_at(friday)

    assert day_bucket(at(date(2026, 9, 6)), ZONE, now=now) == "weekend"  # this Sunday
    assert day_bucket(at(date(2026, 9, 11)), ZONE, now=now) == "later"  # next Friday


def test_on_a_wednesday_the_coming_weekend_is_friday_to_sunday():
    wednesday = date(2026, 9, 2)
    now = now_at(wednesday)

    for day in (4, 5, 6):  # Fri 4th, Sat 5th, Sun 6th
        assert day_bucket(at(date(2026, 9, day)), ZONE, now=now) == "weekend"
    assert day_bucket(at(date(2026, 9, 7)), ZONE, now=now) == "later"


def test_a_weekday_name_is_not_used_for_a_date_a_week_out():
    """'Saturday' a week away read identically to today's Saturday."""
    saturday = date(2026, 9, 5)
    now = now_at(saturday)
    assert day_label(at(date(2026, 9, 12)), ZONE, now=now) == "12 September"


# ── The "Tonight" heading carried yesterday's date ─────────────────────────


def test_the_tonight_heading_uses_the_next_show_not_one_already_over():
    """Listings linger a few hours after they start, so just after midnight the
    first row is last night's show and the heading dated Saturday's bill
    Friday."""
    rows = [
        {"day_bucket": "tonight", "date_long": "Fri, 4 September", "already_started": True},
        {"day_bucket": "tonight", "date_long": "Sat, 5 September", "already_started": False},
    ]
    sections = group_events_by_day(rows)
    assert sections[0]["label"] == "Tonight — Sat, 5 September"


# ── The day filter ran after pagination ────────────────────────────────────


def test_asking_for_the_weekend_does_not_return_an_empty_page(client, make_event, make_venue):
    """The killer case: buckets are chronological, so a SQL LIMIT returned the
    soonest rows — all 'tonight' — and the weekend filter then emptied the
    page while the weekend's shows sat just past the cut."""
    venue = make_venue(timezone_name=ZONE)
    today = utcnow().astimezone(ZoneInfo(ZONE)).date()
    friday = today + timedelta(days=(4 - today.weekday()) % 7)
    if friday <= today + timedelta(days=1):
        friday += timedelta(days=7)

    # More tonight-shows than a page holds, plus one at the weekend.
    for index in range(60):
        make_event(venue=venue, headline=f"Tonight {index}",
                   starts_at=utcnow() + timedelta(hours=2, minutes=index))
    make_event(venue=venue, headline="Weekend show", starts_at=at(friday, 21))

    data = client.get("/api/v1/events?day=weekend&limit=50").get_json()["data"]

    assert data["count"] == 1, "the weekend show must survive pagination"
    assert data["events"][0]["headline"] == "Weekend show"
    assert data["total"] == 1


def test_pagination_reports_whether_more_remains(client, make_event, make_venue):
    venue = make_venue(timezone_name=ZONE)
    for index in range(12):
        make_event(venue=venue, headline=f"Show {index}",
                   starts_at=utcnow() + timedelta(hours=2, minutes=index))

    first = client.get("/api/v1/events?limit=5&offset=0").get_json()["data"]
    assert first["count"] == 5
    assert first["total"] == 12
    assert first["has_more"] is True

    last = client.get("/api/v1/events?limit=5&offset=10").get_json()["data"]
    assert last["count"] == 2
    assert last["has_more"] is False


# ── The bounding box dropped venues across the antimeridian ────────────────


def test_a_venue_across_the_antimeridian_is_not_dropped(client, make_event, make_venue):
    """A plain BETWEEN on a box spanning ±180 excluded a venue 1.3 miles away."""
    venue = make_venue(name="Across the line", latitude=-17.75, longitude=-179.99,
                       timezone_name="Pacific/Fiji")
    make_event(venue=venue, headline="Just over the line")

    data = client.get(
        "/api/v1/events/nearby?latitude=-17.75&longitude=179.99&radius_miles=10"
    ).get_json()["data"]

    assert data["count"] == 1
    assert data["events"][0]["headline"] == "Just over the line"
    assert data["events"][0]["distance_miles"] < 2


def test_the_ordinary_bounding_box_still_excludes_the_far_away(client, make_event, make_venue):
    make_event(venue=make_venue(name="Boston", latitude=42.3601, longitude=-71.0589))
    data = client.get(
        "/api/v1/events/nearby?latitude=41.8180&longitude=-71.4460&radius_miles=5"
    ).get_json()["data"]
    assert data["count"] == 0


# ── Nearby ranked by distance, not by start time ───────────────────────────


def test_nearby_prefers_the_nearest_not_the_soonest(client, make_event, make_venue):
    """The 300-row pre-filter was ordered chronologically, so a venue across
    the street with a show next week lost its place to a farther one tonight."""
    near = make_venue(name="Round the corner", latitude=41.8180, longitude=-71.4460)
    far = make_venue(name="Across town", latitude=41.8600, longitude=-71.4800)

    make_event(venue=far, headline="Farther, sooner", starts_at=utcnow() + timedelta(hours=2))
    make_event(venue=near, headline="Nearer, later", starts_at=utcnow() + timedelta(days=9))

    data = client.get(
        "/api/v1/events/nearby?latitude=41.8180&longitude=-71.4460&radius_miles=10"
    ).get_json()["data"]

    assert [event["headline"] for event in data["events"]] == ["Nearer, later", "Farther, sooner"]


# ── A listing's start time is bounded on edit, not only on create ──────────


def test_a_listing_cannot_be_edited_into_the_distant_past(client, auth):
    headers = auth()
    created = client.post(
        "/api/v1/events",
        json={
            "headline": "Bloodroot Choir",
            "starts_at": (utcnow() + timedelta(days=1)).isoformat(),
            "venue": {"name": "Dusk", "city": "Providence", "timezone": ZONE},
            "publish": True,
        },
        headers=headers,
    ).get_json()["data"]["event"]

    response = client.patch(
        f"/api/v1/events/{created['id']}",
        json={"starts_at": "1900-01-01T20:00:00+00:00"},
        headers=headers,
    )
    assert response.status_code == 400


def test_an_already_started_show_is_flagged(client, make_event, make_venue):
    venue = make_venue(timezone_name=ZONE)
    make_event(venue=venue, headline="Started an hour ago",
               starts_at=utcnow() - timedelta(hours=1))
    event = client.get("/api/v1/events").get_json()["data"]["events"][0]
    assert event["already_started"] is True


def test_serialize_event_marks_a_future_show_as_not_started(make_event):
    event = make_event(starts_at=utcnow() + timedelta(hours=4))
    assert serialize_event(event)["already_started"] is False
