"""Listings: the feed, the map, posting a show, and who may touch what."""

from datetime import timedelta

import pytest

from app.extensions import db
from app.models import (
    AgeRestriction,
    Event,
    EventStatus,
    Genre,
    utcnow,
)


@pytest.fixture()
def make_event(db, make_venue):
    def _make(artist=None, venue=None, hours_ahead=3, status=EventStatus.PUBLISHED,
              headline="Bloodroot Choir", genre=Genre.ROCK_PUNK, price_cents=1200,
              created_by=None, **kwargs):
        venue = venue or make_venue()
        event = Event(
            artist_id=artist.id if artist else None,
            venue_id=venue.id,
            created_by_user_id=created_by.id if created_by else None,
            headline=headline,
            genre=genre,
            starts_at=utcnow() + timedelta(hours=hours_ahead),
            price_cents=price_cents,
            age_restriction=AgeRestriction.TWENTY_ONE_PLUS,
            status=status,
            published_at=utcnow() if status is EventStatus.PUBLISHED else None,
            **kwargs,
        )
        db.session.add(event)
        db.session.commit()
        return event

    return _make


# ── The bill ───────────────────────────────────────────────────────────────


def test_listings_are_public(client, make_event):
    make_event()
    response = client.get("/api/v1/events")
    assert response.status_code == 200
    data = response.get_json()["data"]
    assert data["count"] == 1
    assert data["events"][0]["headline"] == "Bloodroot Choir"


def test_listings_group_into_sections(client, make_event):
    make_event(headline="Tonight's show", hours_ahead=3)
    make_event(headline="Next week", hours_ahead=24 * 9)

    sections = client.get("/api/v1/events").get_json()["data"]["sections"]
    keys = [section["key"] for section in sections]
    assert "tonight" in keys
    assert sections[0]["count_label"] == "1 show"


def test_drafts_never_appear_in_the_feed(client, make_event):
    make_event(headline="Not ready", status=EventStatus.DRAFT)
    data = client.get("/api/v1/events").get_json()["data"]
    assert data["count"] == 0


def test_finished_shows_drop_off_the_feed(client, make_event):
    make_event(headline="Last night", hours_ahead=-30)
    assert client.get("/api/v1/events").get_json()["data"]["count"] == 0


def test_genre_filter(client, make_event):
    make_event(headline="Punk show", genre=Genre.ROCK_PUNK)
    make_event(headline="Jazz show", genre=Genre.JAZZ)

    data = client.get("/api/v1/events?genre=jazz").get_json()["data"]
    assert [event["headline"] for event in data["events"]] == ["Jazz show"]


def test_invalid_genre_is_a_validation_error_not_a_crash(client):
    response = client.get("/api/v1/events?genre=polka-jazz-fusion")
    assert response.status_code == 400
    assert response.get_json()["error"]["code"] == "VALIDATION_ERROR"


def test_search_matches_headline_and_venue(client, make_event, make_venue):
    make_event(headline="Bloodroot Choir")
    make_event(headline="The Coleman Trio", venue=make_venue(name="Nick-a-Nee's"))

    by_artist = client.get("/api/v1/events?q=bloodroot").get_json()["data"]
    assert by_artist["count"] == 1

    by_venue = client.get("/api/v1/events?q=nick").get_json()["data"]
    assert by_venue["count"] == 1


def test_search_wildcards_are_escaped(client, make_event):
    """A bare `%` must match nothing, not every listing."""
    make_event(headline="Bloodroot Choir")
    data = client.get("/api/v1/events?q=%25").get_json()["data"]
    assert data["count"] == 0


def test_price_label_distinguishes_free_from_unstated(client, make_event):
    make_event(headline="Free show", price_cents=0)
    make_event(headline="Unknown price", price_cents=None)

    labels = {
        event["headline"]: event["price_label"]
        for event in client.get("/api/v1/events").get_json()["data"]["events"]
    }
    assert labels["Free show"] == "Free"
    assert labels["Unknown price"] is None


def test_times_are_rendered_in_the_venue_zone(client, make_event, make_venue):
    """A listing reads in the local wall clock of the room it happens in."""
    from datetime import datetime, timezone

    venue = make_venue(name="Dusk", timezone_name="America/New_York")
    event = make_event(venue=venue)
    event.starts_at = datetime(2026, 7, 28, 1, 0, tzinfo=timezone.utc)  # 9pm EDT the 27th
    db.session.commit()

    detail = client.get(f"/api/v1/events/{event.id}").get_json()["data"]["event"]
    assert detail["time_label"] == "9:00 PM"


def test_pagination_rejects_absurd_offsets(client):
    assert client.get("/api/v1/events?offset=999999").status_code == 400
    assert client.get("/api/v1/events?limit=0").status_code == 400


# ── The map ────────────────────────────────────────────────────────────────


def test_nearby_orders_by_distance_and_numbers_pins(client, make_event, make_venue):
    near = make_venue(name="Dusk", latitude=41.8180, longitude=-71.4460)
    far = make_venue(name="Fete", latitude=41.8600, longitude=-71.4800)
    make_event(headline="Close by", venue=near)
    make_event(headline="Further out", venue=far)

    data = client.get(
        "/api/v1/events/nearby?latitude=41.8180&longitude=-71.4460&radius_miles=10"
    ).get_json()["data"]

    assert [event["headline"] for event in data["events"]] == ["Close by", "Further out"]
    assert [event["pin_number"] for event in data["events"]] == [1, 2]
    assert data["events"][0]["distance_label"] == "here"


def test_nearby_excludes_beyond_the_radius(client, make_event, make_venue):
    make_event(venue=make_venue(name="Far", latitude=42.3601, longitude=-71.0589))  # Boston
    data = client.get(
        "/api/v1/events/nearby?latitude=41.8180&longitude=-71.4460&radius_miles=5"
    ).get_json()["data"]
    assert data["count"] == 0


def test_nearby_rejects_out_of_range_coordinates(client):
    assert client.get("/api/v1/events/nearby?latitude=95&longitude=0").status_code == 400
    assert client.get("/api/v1/events/nearby?latitude=41&longitude=999").status_code == 400


def test_nearby_rejects_nan_latitude(client):
    """NaN fails every comparison, so a naive range check would let it through
    and then poison the distance arithmetic."""
    assert client.get("/api/v1/events/nearby?latitude=nan&longitude=-71").status_code == 400


# ── Posting a show ─────────────────────────────────────────────────────────


def _post_payload(**overrides):
    payload = {
        "headline": "Bloodroot Choir",
        "starts_at": (utcnow() + timedelta(days=1)).isoformat(),
        "venue": {"name": "Dusk", "city": "Providence", "timezone": "America/New_York"},
        "genre": "rock_punk",
        "price_cents": 1200,
        "publish": True,
    }
    payload.update(overrides)
    return payload


def test_posting_a_show_requires_authentication(client):
    assert client.post("/api/v1/events", json=_post_payload()).status_code == 401


def test_post_a_show_creates_the_venue_when_it_is_new(client, auth):
    response = client.post("/api/v1/events", json=_post_payload(), headers=auth())
    assert response.status_code == 201
    event = response.get_json()["data"]["event"]
    assert event["venue"]["name"] == "Dusk"
    assert event["status"] == "published"


def test_post_a_show_reuses_an_existing_venue(client, auth, make_venue):
    make_venue(name="Dusk", city="Providence")
    headers = auth()
    client.post("/api/v1/events", json=_post_payload(), headers=headers)
    client.post("/api/v1/events", json=_post_payload(headline="Another"), headers=headers)

    from app.models import Venue

    assert db.session.query(Venue).filter(Venue.name == "Dusk").count() == 1


def test_unpublished_show_is_a_draft(client, auth):
    response = client.post("/api/v1/events", json=_post_payload(publish=False), headers=auth())
    assert response.get_json()["data"]["event"]["status"] == "draft"


def test_cannot_post_a_show_in_the_past(client, auth):
    payload = _post_payload(starts_at=(utcnow() - timedelta(days=3)).isoformat())
    response = client.post("/api/v1/events", json=payload, headers=auth())
    assert response.status_code == 400


def test_cannot_post_a_show_decades_ahead(client, auth):
    payload = _post_payload(starts_at=(utcnow() + timedelta(days=5000)).isoformat())
    assert client.post("/api/v1/events", json=payload, headers=auth()).status_code == 400


def test_doors_after_the_first_set_is_rejected(client, auth):
    start = utcnow() + timedelta(days=1)
    payload = _post_payload(
        starts_at=start.isoformat(), doors_at=(start + timedelta(hours=1)).isoformat()
    )
    assert client.post("/api/v1/events", json=payload, headers=auth()).status_code == 400


def test_javascript_ticket_url_is_rejected(client, auth):
    """A stored `javascript:` URL renders as a link and runs on click."""
    payload = _post_payload(ticket_url="javascript:alert(document.cookie)")
    response = client.post("/api/v1/events", json=payload, headers=auth())
    assert response.status_code == 400


def test_cannot_post_on_behalf_of_a_band_you_do_not_own(client, auth, make_user, make_artist):
    other_owner = make_user(email="other@example.com")
    someone_elses_band = make_artist(other_owner, name="Kestrel")

    payload = _post_payload(artist_id=str(someone_elses_band.id))
    response = client.post("/api/v1/events", json=payload, headers=auth())
    assert response.status_code == 404


def test_lineup_length_is_capped(client, auth):
    payload = _post_payload(lineup=[{"name": f"Band {i}"} for i in range(50)])
    assert client.post("/api/v1/events", json=payload, headers=auth()).status_code == 400


# ── Editing ────────────────────────────────────────────────────────────────


def test_creator_can_edit_their_listing(client, auth):
    headers = auth()
    event_id = client.post(
        "/api/v1/events", json=_post_payload(), headers=headers
    ).get_json()["data"]["event"]["id"]

    response = client.patch(
        f"/api/v1/events/{event_id}", json={"headline": "Renamed"}, headers=headers
    )
    assert response.status_code == 200
    assert response.get_json()["data"]["event"]["headline"] == "Renamed"


def test_a_stranger_cannot_edit_someone_elses_listing(client, auth, make_event):
    """The IDOR case: a valid session, someone else's object."""
    event = make_event()
    intruder = auth(email="intruder@example.com")

    response = client.patch(
        f"/api/v1/events/{event.id}", json={"headline": "Cancelled lol"}, headers=intruder
    )
    assert response.status_code == 404


def test_a_stranger_cannot_cancel_someone_elses_listing(client, auth, make_event):
    event = make_event()
    intruder = auth(email="intruder@example.com")
    assert client.post(f"/api/v1/events/{event.id}/cancel", headers=intruder).status_code == 404

    db.session.refresh(event)
    assert event.status is EventStatus.PUBLISHED


def test_editing_starts_at_revalidates_doors(client, auth):
    """Moving the set earlier can invalidate a doors time that was fine."""
    headers = auth()
    start = utcnow() + timedelta(days=2)
    created = client.post(
        "/api/v1/events",
        json=_post_payload(
            starts_at=start.isoformat(),
            doors_at=(start - timedelta(minutes=30)).isoformat(),
        ),
        headers=headers,
    ).get_json()["data"]["event"]

    response = client.patch(
        f"/api/v1/events/{created['id']}",
        json={"starts_at": (start - timedelta(hours=2)).isoformat()},
        headers=headers,
    )
    assert response.status_code == 400


def test_published_listing_cannot_be_deleted(client, auth):
    headers = auth()
    event_id = client.post(
        "/api/v1/events", json=_post_payload(), headers=headers
    ).get_json()["data"]["event"]["id"]

    response = client.delete(f"/api/v1/events/{event_id}", headers=headers)
    assert response.status_code == 409
    assert response.get_json()["error"]["code"] == "INVALID_STATE"


def test_draft_can_be_deleted(client, auth):
    headers = auth()
    event_id = client.post(
        "/api/v1/events", json=_post_payload(publish=False), headers=headers
    ).get_json()["data"]["event"]["id"]
    assert client.delete(f"/api/v1/events/{event_id}", headers=headers).status_code == 200


def test_a_draft_is_invisible_to_everyone_but_its_owner(client, auth, make_event):
    headers = auth()
    event_id = client.post(
        "/api/v1/events", json=_post_payload(publish=False), headers=headers
    ).get_json()["data"]["event"]["id"]

    assert client.get(f"/api/v1/events/{event_id}").status_code == 404
    assert client.get(f"/api/v1/events/{event_id}", headers=headers).status_code == 200

    intruder = auth(email="intruder@example.com")
    assert client.get(f"/api/v1/events/{event_id}", headers=intruder).status_code == 404


# ── Saving and going ───────────────────────────────────────────────────────


def test_save_and_going_are_independent(client, auth, make_event):
    event = make_event()
    headers = auth()

    client.put(f"/api/v1/events/{event.id}/interest", json={"saved": True}, headers=headers)
    response = client.put(
        f"/api/v1/events/{event.id}/interest", json={"going": True}, headers=headers
    )
    data = response.get_json()["data"]
    assert data["saved"] is True and data["going"] is True


def test_clearing_both_flags_removes_the_row(client, auth, make_event):
    from app.models import EventInterest

    event = make_event()
    headers = auth()
    client.put(f"/api/v1/events/{event.id}/interest", json={"saved": True}, headers=headers)
    client.put(f"/api/v1/events/{event.id}/interest", json={"saved": False}, headers=headers)

    assert db.session.query(EventInterest).count() == 0


def test_interest_requires_authentication(client, make_event):
    event = make_event()
    response = client.put(f"/api/v1/events/{event.id}/interest", json={"saved": True})
    assert response.status_code == 401


def test_cannot_mark_interest_in_a_draft(client, auth, make_event):
    event = make_event(status=EventStatus.DRAFT)
    response = client.put(
        f"/api/v1/events/{event.id}/interest", json={"saved": True}, headers=auth()
    )
    assert response.status_code == 404


def test_my_list_splits_going_from_kept(client, auth, make_event):
    going_event = make_event(headline="Going to this")
    saved_event = make_event(headline="Maybe later")
    headers = auth()

    client.put(f"/api/v1/events/{going_event.id}/interest", json={"going": True}, headers=headers)
    client.put(f"/api/v1/events/{saved_event.id}/interest", json={"saved": True}, headers=headers)

    data = client.get("/api/v1/me/list", headers=headers).get_json()["data"]
    assert [event["headline"] for event in data["going"]] == ["Going to this"]
    assert [event["headline"] for event in data["saved"]] == ["Maybe later"]
    assert data["summary"] == "1 going · 1 kept"


def test_my_list_is_scoped_to_the_caller(client, auth, make_event):
    event = make_event()
    mine = auth(email="mine@example.com")
    client.put(f"/api/v1/events/{event.id}/interest", json={"going": True}, headers=mine)

    theirs = auth(email="theirs@example.com")
    data = client.get("/api/v1/me/list", headers=theirs).get_json()["data"]
    assert data["going"] == [] and data["saved"] == []
