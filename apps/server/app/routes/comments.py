"""Comments and their likes.

Visibility rules enforced here:

* Drafts have no comment section — 404, same as the event read itself.
* A block between commenter and the listing's owners bars new comments (403).
* Reads are mutually filtered: neither side of a block sees the other.
"""

from flask import Blueprint, request
from sqlalchemy.orm import joinedload

from ..auth_helpers import load_current_user, require_auth
from ..extensions import db, limiter
from ..models import (
    Comment,
    CommentLike,
    Event,
    EventStatus,
    NotificationKind,
    UserRole,
)
from ..services import comments as comment_service
from ..services import inbox, social
from .response import error, ok
from .serializers import serialize_comment
from .validators import get_json, parse_pagination, parse_string

comments_bp = Blueprint("comments", __name__)

MAX_COMMENT_LENGTH = 2000


def _commentable_event(event_id):
    """The event, if its comment section exists for the public. Drafts and
    missing ids are the same 404."""
    event = db.session.get(Event, event_id)
    if event is None or event.status is EventStatus.DRAFT:
        return None
    return event


@comments_bp.get("/events/<uuid:event_id>/comments")
def list_comments(event_id):
    event = _commentable_event(event_id)
    if event is None:
        return error("NOT_FOUND", "That show could not be found.", status=404)

    limit, offset, err = parse_pagination(request.args, default_limit=50, max_limit=100)
    if err:
        return err

    viewer = load_current_user()
    viewer_id = viewer.id if viewer else None

    base = (
        db.session.query(Comment)
        .options(joinedload(Comment.author))
        .filter(
            Comment.event_id == event.id,
            social.visible_author_clause(viewer_id, Comment.author_user_id),
        )
    )
    total = int(base.with_entities(db.func.count(Comment.id)).scalar() or 0)
    rows = (
        base.order_by(Comment.created_at.desc()).limit(limit).offset(offset).all()
    )

    ids = [row.id for row in rows]
    likes = comment_service.like_counts(db.session, ids)
    liked = comment_service.liked_flags(db.session, viewer, ids)
    is_admin = viewer is not None and viewer.role is UserRole.ADMIN

    return ok(
        {
            "comments": [
                serialize_comment(
                    row,
                    like_count=likes.get(row.id, 0),
                    viewer_liked=bool(liked.get(row.id)),
                    can_delete=is_admin
                    or (viewer is not None and row.author_user_id == viewer.id),
                )
                for row in rows
            ],
            "total": total,
            "has_more": offset + limit < total,
        }
    )


@comments_bp.post("/events/<uuid:event_id>/comments")
@require_auth
@limiter.limit("30 per hour")
def create_comment(event_id):
    author = load_current_user()
    event = _commentable_event(event_id)
    if event is None:
        return error("NOT_FOUND", "That show could not be found.", status=404)

    body, err = get_json(request)
    if err:
        return err
    text, err = parse_string(body.get("body"), "body", max_length=MAX_COMMENT_LENGTH)
    if err:
        return err

    if comment_service.author_barred(db.session, author, event):
        return error("BLOCKED", "You can’t comment on this listing.", status=403)

    comment = comment_service.create_comment(db.session, author, event, text)
    db.session.commit()

    return ok(
        {
            "comment": serialize_comment(
                comment, like_count=0, viewer_liked=False, can_delete=True
            )
        },
        status=201,
    )


@comments_bp.delete("/comments/<uuid:comment_id>")
@require_auth
def delete_comment(comment_id):
    user = load_current_user()
    comment = db.session.get(Comment, comment_id)
    # Author and editor may remove; everyone else learns nothing about
    # whether the id was ever real.
    if comment is None or (
        comment.author_user_id != user.id and user.role is not UserRole.ADMIN
    ):
        return error("NOT_FOUND", "That comment could not be found.", status=404)

    db.session.delete(comment)
    db.session.commit()
    return ok({"deleted": True})


@comments_bp.post("/comments/<uuid:comment_id>/like")
@require_auth
@limiter.limit("240 per hour")
def like_comment(comment_id):
    user = load_current_user()
    comment = db.session.get(Comment, comment_id)
    if comment is None:
        return error("NOT_FOUND", "That comment could not be found.", status=404)
    if social.blocked_either_way(db.session, user.id, comment.author_user_id):
        return error("BLOCKED", "You can’t like this comment.", status=403)

    existing = db.session.get(
        CommentLike, {"comment_id": comment.id, "user_id": user.id}
    )
    if existing is None:
        db.session.add(CommentLike(comment_id=comment.id, user_id=user.id))
        # One bell per (liker, comment) for all time — an unlike/relike loop
        # must not become a doorbell.
        inbox.notify(
            db.session,
            comment.author_user_id,
            NotificationKind.COMMENT_LIKE,
            actor=user,
            event_id=comment.event_id,
            comment_id=comment.id,
            dedupe=True,
        )
        try:
            db.session.commit()
        except Exception:
            db.session.rollback()

    return ok(
        {
            "comment_id": str(comment.id),
            "viewer_liked": True,
            "like_count": comment_service.like_counts(db.session, [comment.id]).get(
                comment.id, 0
            ),
        }
    )


@comments_bp.delete("/comments/<uuid:comment_id>/like")
@require_auth
def unlike_comment(comment_id):
    user = load_current_user()
    existing = db.session.get(
        CommentLike, {"comment_id": comment_id, "user_id": user.id}
    )
    if existing is not None:
        db.session.delete(existing)
        db.session.commit()

    return ok(
        {
            "comment_id": str(comment_id),
            "viewer_liked": False,
            "like_count": comment_service.like_counts(db.session, [comment_id]).get(
                comment_id, 0
            ),
        }
    )
