"""The caller's notification inbox. Nothing here takes a user id from the
request — every query is scoped to the authenticated reader, so there is no
id to forge."""

from flask import Blueprint, request
from sqlalchemy.orm import joinedload

from ..auth_helpers import load_current_user, require_auth
from ..extensions import db
from ..models import Notification
from ..services import inbox as inbox_service
from .response import error, ok
from .serializers import serialize_notification
from .validators import get_json, parse_bool, parse_pagination, parse_uuid

inbox_bp = Blueprint("inbox", __name__)


@inbox_bp.get("/me/notifications")
@require_auth
def list_notifications():
    user = load_current_user()
    limit, offset, err = parse_pagination(request.args, default_limit=50, max_limit=100)
    if err:
        return err

    unread_only = request.args.get("unread") in ("1", "true")

    base = (
        db.session.query(Notification)
        .options(
            joinedload(Notification.actor),
            joinedload(Notification.event),
            joinedload(Notification.comment),
            joinedload(Notification.gig),
        )
        .filter(Notification.user_id == user.id)
    )
    if unread_only:
        base = base.filter(Notification.read_at.is_(None))

    total = int(base.with_entities(db.func.count(Notification.id)).scalar() or 0)
    rows = (
        base.order_by(Notification.created_at.desc())
        .limit(limit)
        .offset(offset)
        .all()
    )

    return ok(
        {
            "notifications": [serialize_notification(row) for row in rows],
            "total": total,
            "has_more": offset + limit < total,
            "unread_count": inbox_service.unread_count(db.session, user.id),
        }
    )


@inbox_bp.get("/me/notifications/unread-count")
@require_auth
def unread_count():
    user = load_current_user()
    return ok({"unread_count": inbox_service.unread_count(db.session, user.id)})


@inbox_bp.post("/me/notifications/read")
@require_auth
def mark_read():
    user = load_current_user()
    body, err = get_json(request)
    if err:
        return err

    mark_all, err = parse_bool(body.get("all"), "all", required=False)
    if err:
        return err

    ids = None
    if not mark_all:
        raw_ids = body.get("ids")
        if not isinstance(raw_ids, list) or not raw_ids:
            return error(
                "VALIDATION_ERROR",
                "Pass ids to mark, or all: true.",
                {"ids": "required"},
            )
        if len(raw_ids) > 200:
            return error(
                "VALIDATION_ERROR", "At most 200 ids per call.", {"ids": "too_many"}
            )
        ids = []
        for raw in raw_ids:
            parsed, err = parse_uuid(raw, "ids")
            if err:
                return err
            ids.append(parsed)

    marked = inbox_service.mark_read(db.session, user.id, ids=ids)
    db.session.commit()
    return ok(
        {
            "marked": marked,
            "unread_count": inbox_service.unread_count(db.session, user.id),
        }
    )
