"""The Following feed: what the people and bands you follow have been up to.

Three sources, merged by time:

* shows newly published by artists you follow, or posted by people you follow
* reviews written by people you follow
* additions to *public* lists by people you follow

Computed on read, no fan-out table — at this paper's scale a bounded window
query per source is cheaper than maintaining write-time copies, and there is
no consistency debt to repay when a follow or a block changes.

The pagination rule from CLAUDE.md §5 applies: the merge happens in Python,
so each source is fetched over a bounded window and the page is sliced from
the merged whole. ``window_truncated`` tells the client when the window, not
the data, was the limit.
"""

from datetime import timedelta

import sqlalchemy as sa
from sqlalchemy.orm import joinedload

from ..models import (
    Artist,
    ArtistFollow,
    Event,
    EventList,
    EventListItem,
    EventStatus,
    Review,
    UserFollow,
    as_utc,
    utcnow,
)

WINDOW_DAYS = 30
PER_SOURCE_CAP = 200


def build_feed(session, viewer, *, limit: int, offset: int) -> dict:
    since = utcnow() - timedelta(days=WINDOW_DAYS)

    followed_user_ids = [
        row[0]
        for row in session.query(UserFollow.followee_id)
        .filter(UserFollow.follower_id == viewer.id)
        .all()
    ]
    followed_artist_ids = [
        row[0]
        for row in session.query(ArtistFollow.artist_id)
        .filter(ArtistFollow.user_id == viewer.id)
        .all()
    ]

    items: list[dict] = []
    truncated = False

    # ── New shows ──────────────────────────────────────────────────────────
    show_filters = []
    if followed_artist_ids:
        show_filters.append(Event.artist_id.in_(followed_artist_ids))
    if followed_user_ids:
        show_filters.append(Event.created_by_user_id.in_(followed_user_ids))
        show_filters.append(
            Event.artist_id.in_(
                sa.select(Artist.id).where(Artist.owner_user_id.in_(followed_user_ids))
            )
        )
    if show_filters:
        shows = (
            session.query(Event)
            .options(joinedload(Event.venue), joinedload(Event.artist))
            .filter(
                Event.status == EventStatus.PUBLISHED,
                Event.published_at.isnot(None),
                Event.published_at >= since,
                sa.or_(*show_filters),
            )
            .order_by(Event.published_at.desc())
            .limit(PER_SOURCE_CAP)
            .all()
        )
        truncated = truncated or len(shows) == PER_SOURCE_CAP
        for event in shows:
            items.append(
                {
                    "type": "new_show",
                    "at": as_utc(event.published_at),
                    "event": event,
                    "artist": event.artist,
                    "actor_user": None,
                }
            )

    # ── Reviews ────────────────────────────────────────────────────────────
    if followed_user_ids:
        reviews = (
            session.query(Review)
            .options(
                joinedload(Review.author),
                joinedload(Review.event).joinedload(Event.venue),
            )
            .filter(
                Review.author_user_id.in_(followed_user_ids),
                Review.created_at >= since,
            )
            .order_by(Review.created_at.desc())
            .limit(PER_SOURCE_CAP)
            .all()
        )
        truncated = truncated or len(reviews) == PER_SOURCE_CAP
        for review in reviews:
            items.append(
                {
                    "type": "review",
                    "at": as_utc(review.created_at),
                    "event": review.event,
                    "review": review,
                    "actor_user": review.author,
                }
            )

        # ── Public list additions ──────────────────────────────────────────
        adds = (
            session.query(EventListItem, EventList)
            .join(EventList, EventList.id == EventListItem.list_id)
            .options(
                joinedload(EventListItem.event).joinedload(Event.venue),
            )
            .filter(
                EventList.owner_user_id.in_(followed_user_ids),
                EventList.is_public.is_(True),
                EventListItem.created_at >= since,
            )
            .order_by(EventListItem.created_at.desc())
            .limit(PER_SOURCE_CAP)
            .all()
        )
        truncated = truncated or len(adds) == PER_SOURCE_CAP
        for item, event_list in adds:
            # A draft can never be list-added, but a later unpublish would
            # leave one reachable here; skip anything not currently visible.
            if item.event is None or item.event.status is EventStatus.DRAFT:
                continue
            items.append(
                {
                    "type": "list_add",
                    "at": as_utc(item.created_at),
                    "event": item.event,
                    "list": event_list,
                    "actor_user": event_list.owner,
                }
            )

    items.sort(key=lambda entry: entry["at"], reverse=True)
    total = len(items)
    page = items[offset : offset + limit]
    return {
        "items": page,
        "total": total,
        "has_more": offset + limit < total,
        "window_days": WINDOW_DAYS,
        "window_truncated": truncated,
    }
