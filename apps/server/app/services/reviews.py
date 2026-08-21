"""Reviews: the after-the-show verdicts and their aggregates."""

import sqlalchemy as sa

from ..models import EventStatus, NotificationKind, Review, as_utc, utcnow
from . import comments as comment_service
from . import inbox


class ReviewRefused(Exception):
    """Raised with a stable code the route can hand straight to ``error()``."""

    def __init__(self, code: str, message: str, status: int = 409):
        super().__init__(message)
        self.code = code
        self.message = message
        self.status = status


def check_reviewable(event) -> None:
    """A review needs a show that was published and has actually begun."""
    if event.status is EventStatus.CANCELLED:
        raise ReviewRefused(
            "EVENT_CANCELLED", "That show was cancelled — there is nothing to review."
        )
    if as_utc(event.starts_at) > utcnow():
        raise ReviewRefused(
            "NOT_STARTED", "Reviews open once the show has started.", status=409
        )


def create_review(session, author, event, *, rating: int, body: str | None) -> Review:
    """Insert and queue the owner notification. Caller commits.

    The unique constraint on (event, author) is the real one-review-per-reader
    guarantee; the friendly pre-check in the route only shapes the error.
    """
    check_reviewable(event)
    review = Review(
        event_id=event.id, author_user_id=author.id, rating=rating, body=body
    )
    session.add(review)
    session.flush()

    for owner_id in comment_service.event_owner_ids(event):
        inbox.notify(
            session,
            owner_id,
            NotificationKind.EVENT_REVIEW,
            actor=author,
            event_id=event.id,
        )
    return review


def aggregate(session, event_id) -> dict:
    row = (
        session.query(
            sa.func.count(Review.id), sa.func.avg(Review.rating)
        )
        .filter(Review.event_id == event_id)
        .one()
    )
    count = int(row[0] or 0)
    average = round(float(row[1]), 1) if row[1] is not None else None
    return {
        "review_count": count,
        "avg_rating": average,
        "rating_label": f"{average:g} of 5 · {count} review{'s' if count != 1 else ''}"
        if average is not None
        else None,
    }


def aggregates_for(session, event_ids) -> dict:
    """event_id → aggregate dict for a page of events, one query."""
    if not event_ids:
        return {}
    rows = (
        session.query(
            Review.event_id, sa.func.count(Review.id), sa.func.avg(Review.rating)
        )
        .filter(Review.event_id.in_(event_ids))
        .group_by(Review.event_id)
        .all()
    )
    out = {}
    for event_id, count, average in rows:
        avg = round(float(average), 1) if average is not None else None
        out[event_id] = {
            "review_count": int(count),
            "avg_rating": avg,
            "rating_label": f"{avg:g} of 5 · {int(count)} review{'s' if int(count) != 1 else ''}"
            if avg is not None
            else None,
        }
    return out
