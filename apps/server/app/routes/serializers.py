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


def user_card(user) -> dict:
    """The byline form of a person — everything a comment, a follower row or
    a notification needs, and nothing more."""
    return {
        "id": str(user.id),
        "handle": user.handle,
        "display_name": user.display_name,
        "avatar_url": R2Storage.access_url(user.avatar_key),
    }


def serialize_user(user, *, include_email: bool = False) -> dict:
    """Safe by default: the email is opt-IN.

    It defaulted to ``True``, which meant the rule at the top of this module
    held only as long as every future call site remembered to opt out. The day
    someone adds a "posted by" block to an event payload, the address leaks by
    omission. Now the leak requires an explicit argument.
    """
    payload = {
        "id": str(user.id),
        "handle": user.handle,
        "display_name": user.display_name,
        "avatar_url": R2Storage.access_url(user.avatar_key),
        "bio": user.bio,
        "role": user.role.value,
        "home_city": user.home_city,
        "email_verified": user.email_verified_at is not None,
        "created_at": _iso(user.created_at),
    }
    if include_email:
        payload["email"] = user.email
    return payload


def serialize_public_profile(
    user,
    *,
    followers: int,
    following: int,
    public_list_count: int,
    review_count: int,
    artists: list | None = None,
    is_following: bool | None = None,
    is_blocked: bool | None = None,
    is_self: bool = False,
) -> dict:
    """A profile page. Never the email, never preferences — this is the
    public record, whoever asks."""
    payload = user_card(user)
    payload.update(
        {
            "bio": user.bio,
            "home_city": user.home_city,
            "role": user.role.value,
            "member_since": _iso(user.created_at),
            "follower_count": followers,
            "following_count": following,
            "public_list_count": public_list_count,
            "review_count": review_count,
            "artists": [serialize_artist(artist) for artist in (artists or [])],
            "is_self": is_self,
        }
    )
    if is_following is not None:
        payload["is_following"] = is_following
    if is_blocked is not None:
        # Only the viewer's own verdict ships. Whether the *other* party has
        # blocked the viewer is never serialized — surfacing it would turn
        # every profile read into a "who blocked me" oracle.
        payload["is_blocked"] = is_blocked
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


def serialize_event(
    event, *, detail: bool = False, interest=None, now=None, can_manage: bool = False,
    comment_count: int | None = None, rating: dict | None = None,
) -> dict:
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
        "poster_credit": event.poster_credit,
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

    # Engagement counts ride along only where the route computed them (detail
    # pages, batch-annotated lists) — absent keys, not zeroes, so a client can
    # tell "none" from "not counted here".
    if comment_count is not None:
        payload["comment_count"] = comment_count
    if rating is not None:
        payload.update(rating)

    if detail:
        payload.update(
            {
                "blurb": event.blurb,
                "ticket_url": event.ticket_url,
                "published_at": _iso(event.published_at),
                "cancelled": event.status is EventStatus.CANCELLED,
                # Whether to offer this reader the poster control. Decided by
                # the route from the authenticated user (see
                # ``auth_helpers.may_manage_event_media``) — never inferred
                # client-side from the artist id, which the client also holds
                # and could not check anyway. Defaults False: a caller that
                # forgets to pass it hides a button, rather than showing one
                # that will be refused.
                "can_manage": can_manage,
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


# ── Lists ──────────────────────────────────────────────────────────────────


def serialize_event_list(event_list, *, item_count: int | None = None,
                         include_owner: bool = False) -> dict:
    payload = {
        "id": str(event_list.id),
        "name": event_list.name,
        "description": event_list.description,
        "is_public": event_list.is_public,
        "created_at": _iso(event_list.created_at),
        "updated_at": _iso(event_list.updated_at),
    }
    if item_count is not None:
        payload["item_count"] = item_count
        payload["count_label"] = "1 show" if item_count == 1 else f"{item_count} shows"
    if include_owner:
        payload["owner"] = user_card(event_list.owner)
    return payload


def serialize_list_entry(item, event_payload: dict) -> dict:
    """One shelf line: the show plus the note the owner pinned to it."""
    return {
        "event": event_payload,
        "note": item.note,
        "added_at": _iso(item.created_at),
    }


# ── Comments and reviews ───────────────────────────────────────────────────


def serialize_comment(comment, *, like_count: int = 0, viewer_liked: bool = False,
                      can_delete: bool = False) -> dict:
    return {
        "id": str(comment.id),
        "event_id": str(comment.event_id),
        "author": user_card(comment.author),
        "body": comment.body,
        "like_count": like_count,
        "viewer_liked": viewer_liked,
        "can_delete": can_delete,
        "created_at": _iso(comment.created_at),
    }


def serialize_review(review, *, can_edit: bool = False, include_event: bool = False,
                     now=None) -> dict:
    payload = {
        "id": str(review.id),
        "event_id": str(review.event_id),
        "author": user_card(review.author),
        "rating": review.rating,
        "rating_label": "★" * review.rating + "☆" * (5 - review.rating),
        "body": review.body,
        "can_edit": can_edit,
        "created_at": _iso(review.created_at),
        "edited": as_utc(review.updated_at) > as_utc(review.created_at),
    }
    if include_event and review.event is not None:
        payload["event"] = serialize_event(review.event, now=now)
    return payload


# ── Gigs ───────────────────────────────────────────────────────────────────


def serialize_gig(gig, *, detail: bool = False, can_manage: bool = False,
                  application_count: int | None = None,
                  my_applications: list | None = None) -> dict:
    payload = {
        "id": str(gig.id),
        "title": gig.title,
        "city": gig.city,
        "neighborhood": gig.neighborhood,
        "venue_name": gig.venue_name,
        "starts_at": _iso(gig.starts_at),
        "date_label": date_long(gig.starts_at, gig.timezone_name) if gig.starts_at else None,
        "time_label": time_label(gig.starts_at, gig.timezone_name),
        "pay_cents": gig.pay_cents,
        # Door prices and gig pay read the same way: None = "not stated".
        "pay_label": price_label(gig.pay_cents),
        "pay_note": gig.pay_note,
        "genre": gig.genre.value if gig.genre else None,
        "genre_label": GENRE_LABELS.get(gig.genre) if gig.genre else None,
        "status": gig.status.value,
        "posted_by": user_card(gig.posted_by),
        "created_at": _iso(gig.created_at),
    }
    if detail:
        payload["description"] = gig.description
        payload["can_manage"] = can_manage
    if application_count is not None:
        payload["application_count"] = application_count
    if my_applications is not None:
        payload["my_applications"] = my_applications
    return payload


def serialize_gig_application(application, *, include_artist: bool = True,
                              include_gig: bool = False) -> dict:
    payload = {
        "id": str(application.id),
        "gig_id": str(application.gig_id),
        "artist_id": str(application.artist_id),
        "message": application.message,
        "status": application.status.value,
        "created_at": _iso(application.created_at),
    }
    if include_artist and application.artist is not None:
        payload["artist"] = serialize_artist(application.artist)
    if include_gig and application.gig is not None:
        payload["gig"] = serialize_gig(application.gig)
    return payload


# ── Notifications ──────────────────────────────────────────────────────────


def _excerpt(text: str | None, limit: int = 90) -> str | None:
    if not text:
        return None
    flat = " ".join(text.split())
    return flat if len(flat) <= limit else flat[: limit - 1].rstrip() + "…"


def serialize_notification(notification) -> dict:
    """One inbox line, with the sentence built server-side so both clients
    print the same paper."""
    actor = notification.actor
    event = notification.event
    gig = notification.gig
    comment = notification.comment

    actor_name = actor.display_name if actor else "Someone"
    kind = notification.kind.value
    subject = event.headline if event else (gig.title if gig else "")

    lines = {
        "new_follower": f"{actor_name} started following you",
        "event_comment": f"{actor_name} commented on {subject}",
        "comment_like": f"{actor_name} liked your comment on {subject}",
        "mention": f"{actor_name} mentioned you on {subject}",
        "event_review": f"{actor_name} reviewed {subject}",
        "gig_application": f"{actor_name} applied to “{subject}”",
        "gig_accepted": f"Your application for “{subject}” was accepted",
        "gig_declined": f"Your application for “{subject}” was declined",
        # The editor stays unnamed on purpose — the desk speaks as the paper.
        "image_removed": "An editor removed one of your photos",
    }

    return {
        "id": str(notification.id),
        "kind": kind,
        "line": lines.get(kind, f"{actor_name} did something"),
        "actor": user_card(actor) if actor else None,
        "event_id": str(notification.event_id) if notification.event_id else None,
        "event_headline": event.headline if event else None,
        "gig_id": str(notification.gig_id) if notification.gig_id else None,
        "gig_title": gig.title if gig else None,
        "comment_excerpt": _excerpt(comment.body) if comment else None,
        "read": notification.read_at is not None,
        "created_at": _iso(notification.created_at),
    }


# ── Reports ────────────────────────────────────────────────────────────────


def serialize_report(report, *, comment=None, review=None, reported_user=None,
                     reporter=None) -> dict:
    subject_type = (
        "comment"
        if report.comment_id
        else "review"
        if report.review_id
        else "user"
        if report.reported_user_id
        # Every pointer nulled — the content was deleted out from under the
        # report (author delete, or an earlier resolution).
        else "removed"
    )
    payload = {
        "id": str(report.id),
        "subject_type": subject_type,
        "reason": report.reason.value,
        "detail": report.detail,
        "status": report.status.value,
        "created_at": _iso(report.created_at),
        "resolved_at": _iso(report.resolved_at),
    }
    if reporter is not None:
        payload["reporter"] = user_card(reporter)
    if comment is not None:
        payload["comment"] = serialize_comment(comment)
    if review is not None:
        payload["review"] = serialize_review(review)
    if reported_user is not None:
        payload["reported_user"] = user_card(reported_user)
    return payload


# ── Messages ───────────────────────────────────────────────────────────────


def serialize_message(message) -> dict:
    return {
        "id": str(message.id),
        "conversation_id": str(message.conversation_id),
        "sender": user_card(message.sender),
        "body": message.body,
        "created_at": _iso(message.created_at),
    }


def serialize_conversation(conversation, *, viewer, unread: bool,
                           last_message=None) -> dict:
    """One line of the mailbox, from the viewer's side of it."""
    other = conversation.other_user(viewer.id)
    subject = None
    if conversation.artist is not None:
        subject = f"About {conversation.artist.name}"
    elif conversation.gig is not None:
        subject = f"About “{conversation.gig.title}”"

    payload = {
        "id": str(conversation.id),
        "with": user_card(other),
        "subject": subject,
        "artist_id": str(conversation.artist_id) if conversation.artist_id else None,
        "gig_id": str(conversation.gig_id) if conversation.gig_id else None,
        "unread": unread,
        "last_message_at": _iso(conversation.last_message_at),
        "created_at": _iso(conversation.created_at),
    }
    if last_message is not None:
        payload["last_line"] = _excerpt(last_message.body, 80)
        payload["last_from_me"] = last_message.sender_user_id == viewer.id
    return payload


# ── The photo desk ─────────────────────────────────────────────────────────


def serialize_image_review(review, *, uploader=None) -> dict:
    return {
        "id": str(review.id),
        "purpose": review.purpose.value,
        # Presigned per request, exactly like every other object URL.
        "image_url": R2Storage.access_url(review.object_key),
        "status": review.status.value,
        "uploader": user_card(uploader) if uploader is not None else None,
        "created_at": _iso(review.created_at),
        "reviewed_at": _iso(review.reviewed_at),
    }


# ── The Following feed ─────────────────────────────────────────────────────


def serialize_feed_item(entry, *, interest=None, now=None) -> dict:
    """One brief in the Following column."""
    kind = entry["type"]
    event_payload = serialize_event(entry["event"], interest=interest, now=now)
    actor_user = entry.get("actor_user")

    if kind == "new_show":
        artist = entry.get("artist")
        who = artist.name if artist else event_payload["headline"]
        line = f"{who} posted a show"
    elif kind == "review":
        line = f"{actor_user.display_name} reviewed {event_payload['headline']}"
    else:  # list_add
        line = (
            f"{actor_user.display_name} added {event_payload['headline']}"
            f" to “{entry['list'].name}”"
        )

    payload = {
        "type": kind,
        "at": _iso(entry["at"]),
        "line": line,
        "event": event_payload,
        "actor": user_card(actor_user) if actor_user else None,
    }
    if kind == "review":
        payload["review"] = serialize_review(entry["review"])
    if kind == "list_add":
        payload["list"] = serialize_event_list(entry["list"], include_owner=True)
    return payload
