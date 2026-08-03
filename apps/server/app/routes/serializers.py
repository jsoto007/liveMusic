"""Wire shapes.

Two rules hold everywhere here:

1. **Raw values and display labels both ship.** Clients get ``price_cents`` and
   ``price_label``, ``starts_at`` and ``time_label``. The raw value is what a
   client sorts and computes on; the label is what it prints, and it is built
   once on the server so the web and mobile listings read identically.
2. **Nothing is serialized that the caller is not entitled to.** An email
   address only ever appears on the caller's own record.
"""

from datetime import date, timedelta
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from ..models import (
    AGE_LABELS,
    GENRE_LABELS,
    AgeRestriction,
    EventStatus,
    Genre,
    as_utc,
    utcnow,
)
from ..services.r2_storage import R2Storage


def _zone(name: str | None) -> ZoneInfo:
    try:
        return ZoneInfo(name or "UTC")
    except (ZoneInfoNotFoundError, ValueError):
        return ZoneInfo("UTC")


def _iso(value):
    """ISO-8601, always with an offset.

    Stored timestamps come back naive on SQLite, and an ISO string without an
    offset is ambiguous to a client — it would be read as local time and the
    listing would print hours out.
    """
    value = as_utc(value)
    return value.isoformat() if value else None


def price_label(price_cents: int | None) -> str | None:
    """``None`` means the price was never stated; ``0`` means free. They are
    different facts and the paper prints them differently."""
    if price_cents is None:
        return None
    if price_cents == 0:
        return "Free"
    if price_cents % 100 == 0:
        return f"${price_cents // 100}"
    return f"${price_cents / 100:.2f}"


def time_label(moment, zone_name: str | None) -> str | None:
    """Wall-clock time in the venue's zone, e.g. ``9:00 PM``."""
    if moment is None:
        return None
    local = as_utc(moment).astimezone(_zone(zone_name))
    return local.strftime("%-I:%M %p")


def day_bucket(moment, zone_name: str | None, *, now=None) -> str:
    """Which section of the paper a listing sets into.

    ``tonight`` / ``tomorrow`` / ``weekend`` / ``later``, decided in the
    *venue's* local calendar — a show at 11pm Friday belongs to Friday's page
    for the people standing outside it, whatever the server's clock says.
    """
    zone = _zone(zone_name)
    local = as_utc(moment).astimezone(zone)
    today: date = (now or utcnow()).astimezone(zone).date()
    delta = (local.date() - today).days

    if delta <= 0:
        return "tonight"
    if delta == 1:
        return "tomorrow"
    if _weekend_window(today)[0] <= local.date() <= _weekend_window(today)[1]:
        return "weekend"
    return "later"


def _weekend_window(today: date) -> tuple[date, date]:
    """The Fri–Sun of the weekend we are in or heading towards.

    The obvious test — "a Fri/Sat/Sun within the next seven days" — is wrong
    twice over. On a Saturday it reached *next* weekend's Friday and Saturday
    while dropping that weekend's Sunday into "Later on", so the section headed
    "This weekend" listed shows eight days out. On a Friday it caught both this
    Sunday and next Friday, putting two different weekends in one section and
    printing a listing eight days away above one three days away. Anchoring to
    a concrete Fri–Sun window removes both.
    """
    weekday = today.weekday()  # Monday is 0
    if weekday in (5, 6):  # already Sat/Sun — this weekend began on Friday
        friday = today - timedelta(days=weekday - 4)
    else:
        friday = today + timedelta(days=(4 - weekday) % 7)
    return friday, friday + timedelta(days=2)


def day_label(moment, zone_name: str | None, *, now=None) -> str:
    zone = _zone(zone_name)
    local = as_utc(moment).astimezone(zone)
    today = (now or utcnow()).astimezone(zone).date()
    delta = (local.date() - today).days
    if delta <= 0:
        return "Tonight"
    if delta == 1:
        return "Tomorrow"
    if delta <= 6:
        return local.strftime("%A")
    # Past six days a bare weekday name is ambiguous — "Saturday" could be
    # tomorrow week. Print the date.
    return local.strftime("%-d %B")


def date_long(moment, zone_name: str | None) -> str:
    local = as_utc(moment).astimezone(_zone(zone_name))
    return local.strftime("%a, %-d %B")


# ── Users ──────────────────────────────────────────────────────────────────


def serialize_user(user, *, include_email: bool = False) -> dict:
    """Safe by default: the email is opt-IN.

    It defaulted to ``True``, which meant the rule at the top of this module
    held only as long as every future call site remembered to opt out. The day
    someone adds a "posted by" block to an event payload, the address leaks by
    omission. Now the leak requires an explicit argument.
    """
    payload = {
        "id": str(user.id),
        "display_name": user.display_name,
        "role": user.role.value,
        "home_city": user.home_city,
        "email_verified": user.email_verified_at is not None,
        "created_at": _iso(user.created_at),
    }
    if include_email:
        payload["email"] = user.email
    return payload


# ── Venues ─────────────────────────────────────────────────────────────────


def serialize_venue(venue) -> dict:
    return {
        "id": str(venue.id),
        "name": venue.name,
        "slug": venue.slug,
        "address": venue.address,
        "neighborhood": venue.neighborhood,
        "city": venue.city,
        "latitude": venue.latitude,
        "longitude": venue.longitude,
        "timezone": venue.timezone_name,
    }


# ── Artists ────────────────────────────────────────────────────────────────


def serialize_sample(sample) -> dict:
    return {
        "id": str(sample.id),
        "title": sample.title,
        "duration_seconds": sample.duration_seconds,
        "duration_label": _duration_label(sample.duration_seconds),
        "content_type": sample.content_type,
        # Minted per request. Never persisted — a stored signed URL becomes a
        # dead link the moment its signature ages out.
        "stream_url": R2Storage.access_url(sample.object_key),
        "created_at": _iso(sample.created_at),
    }


def _duration_label(seconds: int | None) -> str | None:
    if seconds is None or seconds < 0:
        return None
    return f"{seconds // 60}:{seconds % 60:02d}"


def serialize_artist(artist, *, detail: bool = False, follower_count: int | None = None,
                     is_following: bool | None = None) -> dict:
    payload = {
        "id": str(artist.id),
        "name": artist.name,
        "slug": artist.slug,
        "city": artist.city,
        "neighborhood": artist.neighborhood,
        "one_liner": artist.one_liner,
        "style_tags": list(artist.style_tags or []),
        "available_for_hire": artist.available_for_hire,
        "verified": artist.verified_at is not None,
        "photo_url": R2Storage.access_url(artist.photo_key),
    }
    if follower_count is not None:
        payload["follower_count"] = follower_count
    if is_following is not None:
        payload["is_following"] = is_following
    if detail:
        payload.update(
            {
                "bio": artist.bio,
                "sounds_like": artist.sounds_like,
                "members": [
                    {"name": m.name, "instrument": m.instrument} for m in artist.members
                ],
                "samples": [serialize_sample(s) for s in artist.samples],
            }
        )
    return payload


# ── Events ─────────────────────────────────────────────────────────────────


def serialize_event(event, *, detail: bool = False, interest=None, now=None) -> dict:
    venue = event.venue
    zone_name = venue.timezone_name if venue else "UTC"

    payload = {
        "id": str(event.id),
        "headline": event.headline,
        "support_line": event.support_line,
        "genre": event.genre.value,
        "genre_label": GENRE_LABELS.get(event.genre, GENRE_LABELS[Genre.OTHER]),
        "status": event.status.value,
        "starts_at": _iso(event.starts_at),
        "doors_at": _iso(event.doors_at),
        "time_label": time_label(event.starts_at, zone_name),
        "doors_label": time_label(event.doors_at, zone_name),
        "day_bucket": day_bucket(event.starts_at, zone_name, now=now),
        "day_label": day_label(event.starts_at, zone_name, now=now),
        "date_long": date_long(event.starts_at, zone_name),
        "price_cents": event.price_cents,
        "price_label": price_label(event.price_cents),
        "age_restriction": event.age_restriction.value,
        "age_label": AGE_LABELS.get(event.age_restriction, AGE_LABELS[AgeRestriction.ALL_AGES]),
        "short_line": event.short_line,
        "poster_url": R2Storage.access_url(event.poster_key),
        "venue": serialize_venue(venue) if venue else None,
        "artist": (
            {"id": str(event.artist.id), "name": event.artist.name, "slug": event.artist.slug}
            if event.artist
            else None
        ),
        "saved": bool(interest and interest.saved),
        "going": bool(interest and interest.going),
        # Listings linger for a few hours after they start (see services.events
        # GRACE) — this says whether the doors are already behind you.
        "already_started": as_utc(event.starts_at) <= (now or utcnow()),
    }

    if detail:
        payload.update(
            {
                "blurb": event.blurb,
                "ticket_url": event.ticket_url,
                "published_at": _iso(event.published_at),
                "cancelled": event.status is EventStatus.CANCELLED,
                "lineup": [
                    {
                        "name": slot.name,
                        "note": slot.note,
                        "starts_at": _iso(slot.starts_at),
                        "time_label": time_label(slot.starts_at, zone_name),
                    }
                    for slot in event.lineup
                ],
            }
        )
    return payload


def group_events_by_day(events: list[dict]) -> list[dict]:
    """Fold a flat, chronologically sorted list into the paper's sections."""
    order = ["tonight", "tomorrow", "weekend", "later"]
    labels = {
        "tonight": "Tonight",
        "tomorrow": "Tomorrow",
        "weekend": "This weekend",
        "later": "Later on",
    }
    grouped: dict[str, list[dict]] = {key: [] for key in order}
    for event in events:
        grouped.setdefault(event["day_bucket"], []).append(event)

    sections = []
    for key in order:
        rows = grouped.get(key) or []
        if not rows:
            continue
        # "Tonight — Tue 28 July": the section header carries the date so the
        # page still makes sense when it is read the next morning.
        heading = labels[key]
        if key in ("tonight", "tomorrow") and rows:
            # Prefer the date of the first show still to come. Listings stay on
            # the page for a few hours after they start, so just after midnight
            # `rows[0]` is last night's show and the header would date
            # Saturday's bill as Friday.
            upcoming = next((row for row in rows if not row.get("already_started")), rows[-1])
            heading = f"{labels[key]} — {upcoming['date_long']}"
        sections.append(
            {
                "key": key,
                "label": heading,
                "count_label": "1 show" if len(rows) == 1 else f"{len(rows)} shows",
                "events": rows,
            }
        )
    return sections


def relative_window(days: int) -> tuple:
    """The UTC window a listings query covers: now → now + ``days``."""
    now = utcnow()
    return now - timedelta(hours=6), now + timedelta(days=days)
