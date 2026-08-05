"""Listings: the bill, the map, a show, and posting one."""

import math
from datetime import timedelta

from flask import Blueprint, current_app, g, request
from sqlalchemy.orm import joinedload

from ..auth_helpers import (
    get_owned_artist,
    load_current_user,
    may_manage_event_media,
    require_auth,
)
from ..extensions import db, limiter
from ..models import (
    AgeRestriction,
    Event,
    EventInterest,
    EventLineupSlot,
    EventStatus,
    Genre,
    Venue,
    as_utc,
    utcnow,
)
from ..services import events as event_service
from .response import error, ok
from .serializers import group_events_by_day, serialize_event
from .validators import (
    get_json,
    parse_bool,
    parse_cents,
    parse_datetime,
    parse_enum,
    parse_latitude,
    parse_longitude,
    parse_pagination,
    parse_string,
    parse_uuid,
)

events_bp = Blueprint("events", __name__)

MAX_LINEUP_SLOTS = 20
MAX_SEARCH_TERM = 80
# The most listings the feed will pull into memory to bucket before paginating.
# The query window is already bounded to 30 days, so this only bites in a city
# with an implausible density of shows — and when it does, the response says so
# rather than quietly looking like the end of the feed.
WINDOW_CAP = 500
# How far ahead a listing may be scheduled. Two years is generous for a
# festival announcement and stops a typo'd year from parking a row at the end
# of every query's range forever.
MAX_SCHEDULE_AHEAD = timedelta(days=730)


def _check_schedule_bounds(starts_at):
    """A start time has to be plausible. Returns an error response or ``None``.

    Shared by create and update: the bounds lived only in ``create_event``, so
    a PATCH could move a published listing to 1900 and be accepted. Any rule
    worth enforcing on the way in is worth enforcing on the way through.
    """
    now = utcnow()
    if starts_at < now - timedelta(hours=12):
        return error("VALIDATION_ERROR", "A show cannot start in the past.", {"starts_at": "past"})
    if starts_at > now + MAX_SCHEDULE_AHEAD:
        return error(
            "VALIDATION_ERROR",
            "A show cannot be scheduled more than two years ahead.",
            {"starts_at": "too_far"},
        )
    return None


def _parse_genres(args) -> tuple[list[Genre] | None, object | None]:
    raw_values = args.getlist("genre")
    if not raw_values:
        return None, None
    genres = []
    for raw in raw_values:
        genre, err = parse_enum(raw, Genre, "genre")
        if err:
            return None, err
        genres.append(genre)
    return genres, None


@events_bp.get("/events")
@limiter.limit("120 per minute")
def list_events():
    """The bill. Anonymous readers get the same listings; only the saved/going
    flags depend on who is asking."""
    limit, offset, err = parse_pagination(request.args, default_limit=50, max_limit=100)
    if err:
        return err

    genres, err = _parse_genres(request.args)
    if err:
        return err

    city, err = parse_string(
        request.args.get("city"), "city", required=False, max_length=120
    )
    if err:
        return err

    query, err = parse_string(
        request.args.get("q"), "q", required=False, max_length=MAX_SEARCH_TERM
    )
    if err:
        return err

    day = (request.args.get("day") or "all").strip().lower()
    if day not in {"all", "tonight", "tomorrow", "weekend"}:
        return error(
            "VALIDATION_ERROR",
            "day must be one of: all, tonight, tomorrow, weekend.",
            {"day": "invalid"},
        )

    stmt = event_service.visible_query(db.session)
    stmt = event_service.apply_filters(stmt, city=city, genres=genres, query=query)
    stmt = stmt.order_by(Event.starts_at.asc())

    # The day bucket is decided in the venue's local calendar, which SQL does
    # not know, so it has to be applied after serialization. That means the
    # page CANNOT be taken in SQL: the buckets are chronological, so `LIMIT 50`
    # returns the fifty soonest — all of them "tonight" — and a request for
    # "weekend" then filtered them all away and rendered "nothing on the bill"
    # while the weekend's shows sat just past the cut. The window is already
    # bounded to 30 days (and usually one city), so it is fetched whole,
    # bucketed, and only then paginated.
    #
    # WINDOW_CAP is the backstop against a pathologically dense city: it is far
    # above any real day's listings, and truncation is reported rather than
    # silently pretending the feed ended.
    rows = db.session.execute(stmt.limit(WINDOW_CAP + 1)).unique().scalars().all()
    truncated = len(rows) > WINDOW_CAP
    rows = rows[:WINDOW_CAP]

    user = load_current_user()
    interests = event_service.interests_for(db.session, user, rows)
    now = utcnow()
    payload = [
        serialize_event(event, interest=interests.get(event.id), now=now) for event in rows
    ]

    if day != "all":
        payload = [event for event in payload if event["day_bucket"] == day]

    total = len(payload)
    page = payload[offset : offset + limit]

    return ok(
        {
            "events": page,
            "sections": group_events_by_day(page),
            # `count` is this page; `total` is the whole filtered set. A client
            # paging through needs both — comparing len(events) to limit was
            # how the empty-page bug stayed invisible.
            "count": len(page),
            "total": total,
            "has_more": offset + len(page) < total,
            "window_truncated": truncated,
        }
    )


@events_bp.get("/events/nearby")
@limiter.limit("60 per minute")
def nearby_events():
    """The map: listings within a radius, nearest first."""
    latitude, err = parse_latitude(request.args.get("latitude"))
    if err:
        return err
    longitude, err = parse_longitude(request.args.get("longitude"))
    if err:
        return err

    try:
        radius = float(request.args.get("radius_miles", 5))
    except (TypeError, ValueError):
        return error(
            "VALIDATION_ERROR", "radius_miles must be a number.", {"radius_miles": "invalid"}
        )
    if not 0 < radius <= 50:
        return error(
            "VALIDATION_ERROR",
            "radius_miles must be between 0 and 50.",
            {"radius_miles": "out_of_range"},
        )

    genres, err = _parse_genres(request.args)
    if err:
        return err

    min_lat, max_lat, min_lon, max_lon = event_service.bounding_box(latitude, longitude, radius)

    stmt = event_service.visible_query(db.session, days=14)
    stmt = event_service.apply_filters(stmt, genres=genres)
    stmt = stmt.where(
        Venue.latitude.isnot(None),
        Venue.longitude.isnot(None),
        Venue.latitude.between(min_lat, max_lat),
        event_service.longitude_clause(Venue.longitude, min_lon, max_lon),
    )
    # Ordered by planar distance, NOT by start time. Truncating a chronological
    # order before computing distance meant the 60 "nearest" were really the 60
    # nearest *of the 300 soonest* — a venue across the street with a show next
    # week was dropped for a farther one tonight. The exact haversine pass below
    # still does the real ranking; this only has to stop under-selecting.
    _cos_lat = math.cos(math.radians(latitude))
    stmt = stmt.order_by(
        (
            (Venue.latitude - latitude) * (Venue.latitude - latitude)
            + (Venue.longitude - longitude) * (Venue.longitude - longitude) * (_cos_lat * _cos_lat)
        ).asc()
    ).limit(300)

    rows = db.session.execute(stmt).unique().scalars().all()

    user = load_current_user()
    interests = event_service.interests_for(db.session, user, rows)
    now = utcnow()

    within = []
    for event in rows:
        miles = event_service.haversine_miles(
            latitude, longitude, event.venue.latitude, event.venue.longitude
        )
        if miles > radius:
            continue
        payload = serialize_event(event, interest=interests.get(event.id), now=now)
        payload["distance_miles"] = round(miles, 2)
        payload["distance_label"] = event_service.distance_label(miles)
        within.append((miles, payload))

    within.sort(key=lambda pair: pair[0])
    ordered = [payload for _miles, payload in within[:60]]
    for index, payload in enumerate(ordered, start=1):
        payload["pin_number"] = index

    return ok({"events": ordered, "count": len(ordered), "radius_miles": radius})


@events_bp.get("/events/<uuid:event_id>")
def get_event(event_id):
    event = db.session.get(
        Event, event_id, options=[joinedload(Event.venue), joinedload(Event.artist)]
    )
    user = load_current_user()

    if event is None or not _may_view(event, user):
        # A draft is indistinguishable from a nonexistent id to anyone but its
        # owner — otherwise the endpoint enumerates unpublished shows.
        return error("NOT_FOUND", "That listing could not be found.", status=404)

    interest = None
    if user is not None:
        interest = db.session.get(EventInterest, {"user_id": user.id, "event_id": event.id})

    return ok(
        {
            "event": serialize_event(
                event,
                detail=True,
                interest=interest,
                can_manage=may_manage_event_media(event, user),
            )
        }
    )


def _announce(event: Event) -> None:
    """Tell the artist's followers, without letting mail break the response.

    Delivery is idempotent on (user, kind, event), so a listing that is
    published, unpublished and published again does not re-mail anybody.
    """
    from ..services.notifications import notify_followers_of_new_show

    try:
        notify_followers_of_new_show(event)
    except Exception:
        current_app.logger.exception("Follower notification failed after publish.")
        db.session.rollback()


def _may_view(event: Event, user) -> bool:
    if event.status is not EventStatus.DRAFT:
        return True
    if user is None:
        return False
    return get_owned_artist(event.artist_id) is not None or event.created_by_user_id == user.id


# ── Posting a show ─────────────────────────────────────────────────────────


def _resolve_venue(body):
    """Accept either an existing ``venue_id`` or a new venue by name+city.

    The prototype's post flow is three fields, so a band typing a room name
    that is not in the database yet must still be able to post.
    """
    venue_id, err = parse_uuid(body.get("venue_id"), "venue_id", required=False)
    if err:
        return None, err
    if venue_id:
        venue = db.session.get(Venue, venue_id)
        if venue is None:
            return None, error(
                "VALIDATION_ERROR", "That venue was not found.", {"venue_id": "invalid"}
            )
        return venue, None

    raw_venue = body.get("venue")
    if not isinstance(raw_venue, dict):
        return None, error(
            "VALIDATION_ERROR",
            "Provide venue_id, or a venue object with a name and city.",
            {"venue": "required"},
        )

    name, err = parse_string(raw_venue.get("name"), "venue.name", max_length=160)
    if err:
        return None, err
    city, err = parse_string(raw_venue.get("city"), "venue.city", max_length=120)
    if err:
        return None, err
    neighborhood, err = parse_string(
        raw_venue.get("neighborhood"), "venue.neighborhood", required=False, max_length=120
    )
    if err:
        return None, err
    address, err = parse_string(
        raw_venue.get("address"), "venue.address", required=False, max_length=300
    )
    if err:
        return None, err
    latitude, err = parse_latitude(raw_venue.get("latitude"), "venue.latitude", required=False)
    if err:
        return None, err
    longitude, err = parse_longitude(raw_venue.get("longitude"), "venue.longitude", required=False)
    if err:
        return None, err

    timezone_name, err = parse_string(
        raw_venue.get("timezone"), "venue.timezone", required=False, max_length=64
    )
    if err:
        return None, err
    if timezone_name:
        from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

        try:
            ZoneInfo(timezone_name)
        except (ZoneInfoNotFoundError, ValueError):
            return None, error(
                "VALIDATION_ERROR",
                "venue.timezone must be an IANA time zone name.",
                {"venue.timezone": "invalid"},
            )

    from ..utils.slugs import unique_slug

    existing = (
        db.session.query(Venue)
        .filter(
            db.func.lower(Venue.name) == name.lower(),
            db.func.lower(Venue.city) == city.lower(),
        )
        .one_or_none()
    )
    if existing is not None:
        return existing, None

    # No coordinates supplied — look them up so the room can appear on the map.
    # A client that used the address autocomplete will have sent them already;
    # this covers a plainly typed name. Failing soft is deliberate: a venue
    # without coordinates is still a venue, it just does not get a pin.
    if latitude is None or longitude is None:
        from ..services import geocoding

        match = geocoding.geocode_one(", ".join(filter(None, [address or name, city])))
        if match:
            latitude = match["latitude"]
            longitude = match["longitude"]
            neighborhood = neighborhood or match.get("neighborhood")

    venue = Venue(
        name=name,
        slug=unique_slug(db.session, Venue, f"{name}-{city}"),
        address=address,
        city=city,
        neighborhood=neighborhood,
        latitude=latitude,
        longitude=longitude,
        timezone_name=timezone_name or "UTC",
    )
    db.session.add(venue)
    db.session.flush()
    return venue, None


def _apply_lineup(event: Event, raw_lineup) -> object | None:
    if raw_lineup is None:
        return None
    if not isinstance(raw_lineup, list):
        return error("VALIDATION_ERROR", "lineup must be a list.", {"lineup": "invalid"})
    if len(raw_lineup) > MAX_LINEUP_SLOTS:
        return error(
            "VALIDATION_ERROR",
            f"A lineup allows at most {MAX_LINEUP_SLOTS} slots.",
            {"lineup": "too_many"},
        )

    event.lineup.clear()
    for position, raw in enumerate(raw_lineup):
        if not isinstance(raw, dict):
            return error(
                "VALIDATION_ERROR", "Each lineup slot must be an object.", {"lineup": "invalid"}
            )
        name, err = parse_string(raw.get("name"), "lineup.name", max_length=160)
        if err:
            return err
        note, err = parse_string(raw.get("note"), "lineup.note", required=False, max_length=200)
        if err:
            return err
        starts_at, err = parse_datetime(raw.get("starts_at"), "lineup.starts_at", required=False)
        if err:
            return err
        event.lineup.append(
            EventLineupSlot(name=name, note=note, starts_at=starts_at, position=position)
        )
    return None


@events_bp.post("/events")
@require_auth
@limiter.limit("30 per hour")
def create_event():
    body, err = get_json(request)
    if err:
        return err

    artist_id, err = parse_uuid(body.get("artist_id"), "artist_id", required=False)
    if err:
        return err

    artist = None
    if artist_id is not None:
        artist = get_owned_artist(artist_id)
        if artist is None:
            # Same 404 whether the artist is missing or owned by someone else.
            return error("NOT_FOUND", "Not found.", status=404)

    headline, err = parse_string(body.get("headline"), "headline", max_length=160)
    if err:
        return err

    starts_at, err = parse_datetime(body.get("starts_at"), "starts_at")
    if err:
        return err
    err = _check_schedule_bounds(starts_at)
    if err:
        return err
    now = utcnow()

    doors_at, err = parse_datetime(body.get("doors_at"), "doors_at", required=False)
    if err:
        return err
    if doors_at and doors_at > starts_at:
        return error(
            "VALIDATION_ERROR", "Doors cannot be after the first set.", {"doors_at": "after_start"}
        )

    venue, err = _resolve_venue(body)
    if err:
        return err

    genre, err = parse_enum(body.get("genre"), Genre, "genre", required=False)
    if err:
        return err
    age_restriction, err = parse_enum(
        body.get("age_restriction"), AgeRestriction, "age_restriction", required=False
    )
    if err:
        return err
    price_cents, err = parse_cents(body.get("price_cents"), "price_cents", required=False)
    if err:
        return err

    support_line, err = parse_string(
        body.get("support_line"), "support_line", required=False, max_length=300
    )
    if err:
        return err
    short_line, err = parse_string(
        body.get("short_line"), "short_line", required=False, max_length=300
    )
    if err:
        return err
    blurb, err = parse_string(body.get("blurb"), "blurb", required=False, max_length=4000)
    if err:
        return err

    ticket_url, err = _parse_http_url(body.get("ticket_url"), "ticket_url")
    if err:
        return err

    publish, err = parse_bool(body.get("publish"), "publish", required=False)
    if err:
        return err

    event = Event(
        artist_id=artist.id if artist else None,
        venue_id=venue.id,
        created_by_user_id=load_current_user().id,
        headline=headline,
        support_line=support_line,
        genre=genre or Genre.OTHER,
        starts_at=starts_at,
        doors_at=doors_at,
        price_cents=price_cents,
        age_restriction=age_restriction or AgeRestriction.ALL_AGES,
        ticket_url=ticket_url,
        short_line=short_line,
        blurb=blurb,
        status=EventStatus.PUBLISHED if publish else EventStatus.DRAFT,
        published_at=now if publish else None,
    )
    db.session.add(event)

    err = _apply_lineup(event, body.get("lineup"))
    if err:
        db.session.rollback()
        return err

    db.session.commit()

    if event.status is EventStatus.PUBLISHED:
        _announce(event)

    return ok({"event": serialize_event(event, detail=True, can_manage=True)}, status=201)


def _parse_http_url(value, field: str):
    """Only http(s). A ``javascript:`` or ``data:`` URL stored here would be
    rendered as a link and executed in whoever clicked it."""
    if value is None or value == "":
        return None, None
    parsed, err = parse_string(value, field, required=False, max_length=500)
    if err:
        return None, err
    if parsed is None:
        return None, None
    if not parsed.lower().startswith(("http://", "https://")):
        return None, error(
            "VALIDATION_ERROR", f"{field} must be an http or https link.", {field: "invalid"}
        )
    return parsed, None


def _load_editable_event(event_id):
    """The event, if the caller may edit it. Otherwise ``(None, response)``."""
    user = load_current_user()
    event = db.session.get(Event, event_id)
    if event is None:
        return None, error("NOT_FOUND", "That listing could not be found.", status=404)
    owns_artist = event.artist_id is not None and get_owned_artist(event.artist_id) is not None
    if not owns_artist and event.created_by_user_id != user.id:
        from ..models import UserRole

        if user.role is not UserRole.ADMIN:
            return None, error("NOT_FOUND", "That listing could not be found.", status=404)
    return event, None


@events_bp.patch("/events/<uuid:event_id>")
@require_auth
def update_event(event_id):
    event, err = _load_editable_event(event_id)
    if err:
        return err
    body, err = get_json(request)
    if err:
        return err

    if "headline" in body:
        value, err = parse_string(body.get("headline"), "headline", max_length=160)
        if err:
            return err
        event.headline = value

    for field, max_length in (
        ("support_line", 300),
        ("short_line", 300),
        ("blurb", 4000),
    ):
        if field in body:
            value, err = parse_string(
                body.get(field), field, required=False, max_length=max_length
            )
            if err:
                return err
            setattr(event, field, value)

    if "genre" in body:
        value, err = parse_enum(body.get("genre"), Genre, "genre")
        if err:
            return err
        event.genre = value

    if "age_restriction" in body:
        value, err = parse_enum(body.get("age_restriction"), AgeRestriction, "age_restriction")
        if err:
            return err
        event.age_restriction = value

    if "price_cents" in body:
        value, err = parse_cents(body.get("price_cents"), "price_cents", required=False)
        if err:
            return err
        event.price_cents = value

    if "ticket_url" in body:
        value, err = _parse_http_url(body.get("ticket_url"), "ticket_url")
        if err:
            return err
        event.ticket_url = value

    if "starts_at" in body:
        value, err = parse_datetime(body.get("starts_at"), "starts_at")
        if err:
            return err
        err = _check_schedule_bounds(value)
        if err:
            db.session.rollback()
            return err
        event.starts_at = value

    if "doors_at" in body:
        value, err = parse_datetime(body.get("doors_at"), "doors_at", required=False)
        if err:
            return err
        event.doors_at = value

    # Re-check the invariant after any combination of the two changed, not just
    # when both were supplied — editing only `starts_at` can invalidate a
    # `doors_at` that was fine before.
    if event.doors_at and as_utc(event.doors_at) > as_utc(event.starts_at):
        db.session.rollback()
        return error(
            "VALIDATION_ERROR", "Doors cannot be after the first set.", {"doors_at": "after_start"}
        )

    if "lineup" in body:
        err = _apply_lineup(event, body.get("lineup"))
        if err:
            db.session.rollback()
            return err

    db.session.commit()
    return ok({"event": serialize_event(event, detail=True, can_manage=True)})


@events_bp.post("/events/<uuid:event_id>/publish")
@require_auth
def publish_event(event_id):
    event, err = _load_editable_event(event_id)
    if err:
        return err
    if event.status is EventStatus.CANCELLED:
        return error(
            "INVALID_STATE", "A cancelled listing cannot be published again.", status=409
        )
    if event.status is not EventStatus.PUBLISHED:
        event.status = EventStatus.PUBLISHED
        event.published_at = utcnow()
        db.session.commit()
        _announce(event)
    return ok({"event": serialize_event(event, detail=True, can_manage=True)})


@events_bp.post("/events/<uuid:event_id>/cancel")
@require_auth
def cancel_event(event_id):
    event, err = _load_editable_event(event_id)
    if err:
        return err
    if event.status is not EventStatus.CANCELLED:
        event.status = EventStatus.CANCELLED
        event.cancelled_at = utcnow()
        db.session.commit()
    return ok({"event": serialize_event(event, detail=True, can_manage=True)})


@events_bp.delete("/events/<uuid:event_id>")
@require_auth
def delete_event(event_id):
    event, err = _load_editable_event(event_id)
    if err:
        return err
    if event.status is EventStatus.PUBLISHED:
        # Readers may already have it on their list; a published listing is
        # cancelled (and stays visible, marked) rather than vanishing.
        return error(
            "INVALID_STATE",
            "A published listing is cancelled, not deleted.",
            status=409,
        )
    db.session.delete(event)
    db.session.commit()
    return ok({"deleted": True})


# ── Saving and going ───────────────────────────────────────────────────────


@events_bp.put("/events/<uuid:event_id>/interest")
@require_auth
def set_interest(event_id):
    body, err = get_json(request)
    if err:
        return err

    user = load_current_user()
    event = db.session.get(Event, event_id)
    if event is None or event.status is EventStatus.DRAFT:
        return error("NOT_FOUND", "That listing could not be found.", status=404)

    saved, err = parse_bool(body.get("saved"), "saved", required=False)
    if err:
        return err
    going, err = parse_bool(body.get("going"), "going", required=False)
    if err:
        return err
    if saved is None and going is None:
        return error(
            "VALIDATION_ERROR", "Provide saved, going, or both.", {"saved": "required"}
        )

    interest = db.session.get(EventInterest, {"user_id": user.id, "event_id": event.id})
    if interest is None:
        interest = EventInterest(user_id=user.id, event_id=event.id)
        db.session.add(interest)
    if saved is not None:
        interest.saved = saved
    if going is not None:
        interest.going = going

    # A row with neither flag is noise; drop it so "your list" queries stay
    # over live rows only.
    if not interest.saved and not interest.going:
        db.session.delete(interest)
        db.session.commit()
        return ok({"event_id": str(event.id), "saved": False, "going": False})

    db.session.commit()
    return ok(
        {"event_id": str(event.id), "saved": interest.saved, "going": interest.going}
    )


@events_bp.get("/events/<uuid:event_id>/going-count")
def going_count(event_id):
    event = db.session.get(Event, event_id)
    if event is None or event.status is EventStatus.DRAFT:
        return error("NOT_FOUND", "That listing could not be found.", status=404)
    count = (
        db.session.query(db.func.count(EventInterest.user_id))
        .filter(EventInterest.event_id == event.id, EventInterest.going.is_(True))
        .scalar()
    )
    return ok({"event_id": str(event.id), "going_count": int(count or 0)})


__all__ = ["events_bp", "g"]
