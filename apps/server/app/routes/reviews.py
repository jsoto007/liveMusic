"""Reviews: read them on the event, write your own once the doors open."""

from flask import Blueprint, request
from sqlalchemy.orm import joinedload

from ..auth_helpers import load_current_user, require_auth
from ..extensions import db, limiter
from ..models import Event, EventStatus, Review, UserRole
from ..services import reviews as review_service
from ..services import social
from ..services.reviews import ReviewRefused
from .response import error, ok
from .serializers import serialize_review
from .validators import get_json, parse_int, parse_pagination, parse_string

reviews_bp = Blueprint("reviews", __name__)

MAX_REVIEW_LENGTH = 2000


def _reviewable_event(event_id):
    event = db.session.get(Event, event_id)
    if event is None or event.status is EventStatus.DRAFT:
        return None
    return event


@reviews_bp.get("/events/<uuid:event_id>/reviews")
def list_reviews(event_id):
    event = _reviewable_event(event_id)
    if event is None:
        return error("NOT_FOUND", "That show could not be found.", status=404)

    limit, offset, err = parse_pagination(request.args, default_limit=20, max_limit=50)
    if err:
        return err

    viewer = load_current_user()
    viewer_id = viewer.id if viewer else None

    base = (
        db.session.query(Review)
        .options(joinedload(Review.author))
        .filter(
            Review.event_id == event.id,
            social.visible_author_clause(viewer_id, Review.author_user_id),
        )
    )
    total = int(base.with_entities(db.func.count(Review.id)).scalar() or 0)
    rows = base.order_by(Review.created_at.desc()).limit(limit).offset(offset).all()

    mine = None
    if viewer is not None:
        mine_row = (
            db.session.query(Review)
            .options(joinedload(Review.author))
            .filter(Review.event_id == event.id, Review.author_user_id == viewer.id)
            .one_or_none()
        )
        if mine_row is not None:
            mine = serialize_review(mine_row, can_edit=True)

    return ok(
        {
            "reviews": [
                serialize_review(
                    row,
                    can_edit=viewer is not None and row.author_user_id == viewer.id,
                )
                for row in rows
            ],
            "total": total,
            "has_more": offset + limit < total,
            "my_review": mine,
            **review_service.aggregate(db.session, event.id),
        }
    )


@reviews_bp.post("/events/<uuid:event_id>/reviews")
@require_auth
@limiter.limit("20 per hour")
def create_review(event_id):
    author = load_current_user()
    event = _reviewable_event(event_id)
    if event is None:
        return error("NOT_FOUND", "That show could not be found.", status=404)

    body, err = get_json(request)
    if err:
        return err
    rating, err = parse_int(body.get("rating"), "rating", minimum=1, maximum=5)
    if err:
        return err
    text, err = parse_string(
        body.get("body"), "body", required=False, max_length=MAX_REVIEW_LENGTH
    )
    if err:
        return err

    existing = (
        db.session.query(Review.id)
        .filter(Review.event_id == event.id, Review.author_user_id == author.id)
        .first()
    )
    if existing is not None:
        return error(
            "ALREADY_REVIEWED",
            "You have already reviewed this show — edit your review instead.",
            status=409,
        )

    try:
        review = review_service.create_review(
            db.session, author, event, rating=rating, body=text
        )
        db.session.commit()
    except ReviewRefused as refusal:
        db.session.rollback()
        return error(refusal.code, refusal.message, status=refusal.status)
    except Exception:
        # Two submissions raced the friendly check; the unique constraint on
        # (event, author) is the real rule. Tell the loser what happened.
        db.session.rollback()
        return error(
            "ALREADY_REVIEWED",
            "You have already reviewed this show — edit your review instead.",
            status=409,
        )

    return ok({"review": serialize_review(review, can_edit=True)}, status=201)


@reviews_bp.patch("/reviews/<uuid:review_id>")
@require_auth
def update_review(review_id):
    user = load_current_user()
    review = db.session.get(Review, review_id)
    if review is None or review.author_user_id != user.id:
        return error("NOT_FOUND", "That review could not be found.", status=404)

    body, err = get_json(request)
    if err:
        return err

    if "rating" in body:
        rating, err = parse_int(body.get("rating"), "rating", minimum=1, maximum=5)
        if err:
            return err
        review.rating = rating

    if "body" in body:
        text, err = parse_string(
            body.get("body"), "body", required=False, max_length=MAX_REVIEW_LENGTH
        )
        if err:
            return err
        review.body = text

    db.session.commit()
    return ok({"review": serialize_review(review, can_edit=True)})


@reviews_bp.delete("/reviews/<uuid:review_id>")
@require_auth
def delete_review(review_id):
    user = load_current_user()
    review = db.session.get(Review, review_id)
    if review is None or (
        review.author_user_id != user.id and user.role is not UserRole.ADMIN
    ):
        return error("NOT_FOUND", "That review could not be found.", status=404)

    db.session.delete(review)
    db.session.commit()
    return ok({"deleted": True})
