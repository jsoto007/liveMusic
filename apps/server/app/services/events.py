"""Listings queries — the shape of the paper.

Every read here is filtered to ``PUBLISHED`` unless a caller explicitly asks
for their own drafts. A draft leaking into a public feed is the failure mode
this module exists to prevent, so the visibility filter lives in one place
rather than being repeated (and eventually forgotten) per route.
"""

import math
from datetime import timedelta

from sqlalchemy import func, or_, select
from sqlalchemy import true as sa_true
from sqlalchemy.orm import joinedload

from ..models import (
    Artist,
    Event,
    EventInterest,
    EventStatus,
    Venue,
    utcnow,
)

EARTH_RADIUS_MILES = 3958.8

# How far back a listing stays on the page after its start time. A show that
# started an hour ago is still the show you are walking to.
GRACE = timedelta(hours=6)


def base_query(session):
    return (
        select(Event)
        .join(Venue, Event.venue_id == Venue.id)
        .options(joinedload(Event.venue), joinedload(Event.artist))
    )


def visible_query(session, *, days: int = 30):
    now = utcnow()
    return base_query(session).where(
        Event.status == EventStatus.PUBLISHED,
        Event.starts_at >= now - GRACE,
        Event.starts_at <= now + timedelta(days=days),
    )


def apply_filters(stmt, *, city=None, genres=None, query=None, venue_id=None, artist_id=None):
    if city:
        stmt = stmt.where(func.lower(Venue.city) == city.strip().lower())
    if genres:
        stmt = stmt.where(Event.genre.in_(genres))
    if venue_id:
        stmt = stmt.where(Event.venue_id == venue_id)
    if artist_id:
        stmt = stmt.where(Event.artist_id == artist_id)
    if query:
        # ILIKE with a leading wildcard cannot use a btree index, which is why
        # the term is length-capped by the caller and the window is already
        # bounded to a month of listings. If this ever outgrows that, the
        # replacement is a Postgres tsvector column, not a wider LIKE.
        pattern = f"%{_escape_like(query.strip())}%"
        stmt = stmt.outerjoin(Artist, Event.artist_id == Artist.id).where(
            or_(
                Event.headline.ilike(pattern, escape="\\"),
                Event.support_line.ilike(pattern, escape="\\"),
                Venue.name.ilike(pattern, escape="\\"),
                Venue.neighborhood.ilike(pattern, escape="\\"),
                Artist.name.ilike(pattern, escape="\\"),
            )
        )
    return stmt


def _escape_like(term: str) -> str:
    """Neutralise LIKE metacharacters.

    Without this a search for ``%`` matches every listing and a search for
    ``_`` matches any single character — not injection, but a trivial way to
    make the database scan everything.
    """
    return term.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")


def haversine_miles(lat1, lon1, lat2, lon2) -> float:
    phi1, phi2 = math.radians(lat1), math.radians(lat2)
    d_phi = phi2 - phi1
    d_lambda = math.radians(lon2 - lon1)
    a = (
        math.sin(d_phi / 2) ** 2
        + math.cos(phi1) * math.cos(phi2) * math.sin(d_lambda / 2) ** 2
    )
    return 2 * EARTH_RADIUS_MILES * math.asin(math.sqrt(a))


def bounding_box(latitude: float, longitude: float, radius_miles: float):
    """A lat/lon box that contains the radius, for cheap pre-filtering in SQL.

    Distance is then computed exactly in Python over the (small) result set.
    The box is a superset, never a subset, so nothing inside the radius is
    dropped — and the longitude span widens with latitude, which a fixed-degree
    box would get wrong near the poles.
    """
    lat_delta = radius_miles / 69.0
    cos_lat = math.cos(math.radians(latitude))
    # Guard the degenerate case at the poles where a degree of longitude
    # collapses to nothing and the division blows up.
    lon_delta = 180.0 if abs(cos_lat) < 1e-6 else min(180.0, radius_miles / (69.0 * abs(cos_lat)))
    return (
        latitude - lat_delta,
        latitude + lat_delta,
        longitude - lon_delta,
        longitude + lon_delta,
    )


def longitude_clause(column, min_lon: float, max_lon: float):
    """A longitude predicate that survives the antimeridian.

    Stored longitudes are in [-180, 180], so a box straddling ±180 comes out
    as e.g. (179.84, 180.14) and a plain BETWEEN silently excludes a venue at
    -179.99 — 1.3 miles away and simply missing from the map. Near the poles
    the span can also exceed the whole circle, in which case there is nothing
    left to filter on.
    """
    if max_lon - min_lon >= 360.0:
        return sa_true()
    if min_lon < -180.0:
        # Wraps west: match the eastern remainder as well.
        return or_(column.between(-180.0, max_lon), column >= min_lon + 360.0)
    if max_lon > 180.0:
        # Wraps east: match the western remainder as well.
        return or_(column.between(min_lon, 180.0), column <= max_lon - 360.0)
    return column.between(min_lon, max_lon)


def interests_for(session, user, events) -> dict:
    """Map ``event_id -> EventInterest`` for the caller, in one query."""
    if user is None or not events:
        return {}
    event_ids = [event.id for event in events]
    rows = (
        session.query(EventInterest)
        .filter(EventInterest.user_id == user.id, EventInterest.event_id.in_(event_ids))
        .all()
    )
    return {row.event_id: row for row in rows}


def distance_label(miles: float) -> str:
    if miles < 0.1:
        return "here"
    return f"{miles:.1f} mi"
