"""The Following feed — the reader's personal edition of the paper."""

from flask import Blueprint, request

from ..auth_helpers import load_current_user, require_auth
from ..extensions import db, limiter
from ..models import utcnow
from ..services import events as event_service
from ..services import feed as feed_service
from .response import ok
from .serializers import serialize_feed_item
from .validators import parse_pagination

feed_bp = Blueprint("feed", __name__)


@feed_bp.get("/me/feed")
@require_auth
@limiter.limit("120 per minute")
def my_feed():
    user = load_current_user()
    limit, offset, err = parse_pagination(request.args, default_limit=30, max_limit=100)
    if err:
        return err

    result = feed_service.build_feed(db.session, user, limit=limit, offset=offset)

    events = [entry["event"] for entry in result["items"]]
    interests = event_service.interests_for(db.session, user, events)
    now = utcnow()

    return ok(
        {
            "items": [
                serialize_feed_item(
                    entry, interest=interests.get(entry["event"].id), now=now
                )
                for entry in result["items"]
            ],
            "total": result["total"],
            "has_more": result["has_more"],
            "window_days": result["window_days"],
            "window_truncated": result["window_truncated"],
        }
    )
