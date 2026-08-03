"""Venue lookup for the post-a-show flow."""

from flask import Blueprint, request

from ..extensions import db, limiter
from ..models import Venue
from ..services.events import _escape_like
from .response import ok
from .serializers import serialize_venue
from .validators import parse_pagination, parse_string

venues_bp = Blueprint("venues", __name__)


@venues_bp.get("/venues")
@limiter.limit("120 per minute")
def list_venues():
    limit, offset, err = parse_pagination(request.args, default_limit=20, max_limit=50)
    if err:
        return err

    query, err = parse_string(request.args.get("q"), "q", required=False, max_length=80)
    if err:
        return err
    city, err = parse_string(request.args.get("city"), "city", required=False, max_length=120)
    if err:
        return err

    stmt = db.session.query(Venue)
    if city:
        stmt = stmt.filter(db.func.lower(Venue.city) == city.lower())
    if query:
        pattern = f"%{_escape_like(query)}%"
        stmt = stmt.filter(
            db.or_(
                Venue.name.ilike(pattern, escape="\\"),
                Venue.neighborhood.ilike(pattern, escape="\\"),
            )
        )

    rows = stmt.order_by(Venue.name.asc()).limit(limit).offset(offset).all()
    return ok({"venues": [serialize_venue(venue) for venue in rows]})
