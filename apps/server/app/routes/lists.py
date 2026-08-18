"""Named event lists: your shelves, and the public view of anyone's.

Ownership is re-derived on every write (``get_owned_list`` — a foreign or
missing list are the same 404), and the public read path never branches on a
client-supplied "is this mine" flag: it derives visibility from the row.
"""

from flask import Blueprint, request
from sqlalchemy.orm import joinedload

from ..auth_helpers import load_current_user, require_auth
from ..extensions import db, limiter
from ..models import Event, EventList, EventListItem, utcnow
from ..services import events as event_service
from ..services import lists as list_service
from ..services.lists import ListRefused
from .response import error, ok
from .serializers import serialize_event, serialize_event_list, serialize_list_entry
from .validators import get_json, parse_bool, parse_pagination, parse_string

lists_bp = Blueprint("lists", __name__)


@lists_bp.get("/me/lists")
@require_auth
def my_lists():
    user = load_current_user()
    rows = (
        db.session.query(EventList)
        .filter(EventList.owner_user_id == user.id)
        .order_by(EventList.updated_at.desc())
        .all()
    )
    counts = list_service.item_counts(db.session, [row.id for row in rows])
    return ok(
        {
            "lists": [
                serialize_event_list(row, item_count=counts.get(row.id, 0))
                for row in rows
            ],
            "max_lists": list_service.MAX_LISTS_PER_USER,
        }
    )


@lists_bp.post("/me/lists")
@require_auth
@limiter.limit("20 per hour")
def create_list():
    user = load_current_user()
    body, err = get_json(request)
    if err:
        return err

    name, err = parse_string(body.get("name"), "name", max_length=80)
    if err:
        return err
    description, err = parse_string(
        body.get("description"), "description", required=False, max_length=300
    )
    if err:
        return err
    is_public, err = parse_bool(body.get("is_public"), "is_public", required=False)
    if err:
        return err

    try:
        event_list = list_service.create_list(
            db.session,
            user,
            name=name,
            description=description,
            is_public=bool(is_public),
        )
    except ListRefused as refusal:
        db.session.rollback()
        return error(refusal.code, refusal.message, status=refusal.status)

    db.session.commit()
    return ok({"list": serialize_event_list(event_list, item_count=0)}, status=201)


@lists_bp.patch("/me/lists/<uuid:list_id>")
@require_auth
def update_list(list_id):
    user = load_current_user()
    event_list = list_service.get_owned_list(db.session, user, list_id)
    if event_list is None:
        return error("NOT_FOUND", "That list could not be found.", status=404)

    body, err = get_json(request)
    if err:
        return err

    if "name" in body:
        name, err = parse_string(body.get("name"), "name", max_length=80)
        if err:
            return err
        try:
            list_service.rename_guard(db.session, event_list, name)
        except ListRefused as refusal:
            return error(refusal.code, refusal.message, status=refusal.status)
        event_list.name = name

    if "description" in body:
        description, err = parse_string(
            body.get("description"), "description", required=False, max_length=300
        )
        if err:
            return err
        event_list.description = description

    if "is_public" in body:
        is_public, err = parse_bool(body.get("is_public"), "is_public")
        if err:
            return err
        event_list.is_public = is_public

    db.session.commit()
    item_count = list_service.item_counts(db.session, [event_list.id]).get(
        event_list.id, 0
    )
    return ok({"list": serialize_event_list(event_list, item_count=item_count)})


@lists_bp.delete("/me/lists/<uuid:list_id>")
@require_auth
def delete_list(list_id):
    user = load_current_user()
    event_list = list_service.get_owned_list(db.session, user, list_id)
    if event_list is None:
        return error("NOT_FOUND", "That list could not be found.", status=404)

    db.session.delete(event_list)
    db.session.commit()
    return ok({"deleted": True})


@lists_bp.put("/me/lists/<uuid:list_id>/events/<uuid:event_id>")
@require_auth
@limiter.limit("120 per hour")
def add_to_list(list_id, event_id):
    user = load_current_user()
    event_list = list_service.get_owned_list(db.session, user, list_id)
    if event_list is None:
        return error("NOT_FOUND", "That list could not be found.", status=404)

    event = db.session.get(Event, event_id)
    if event is None:
        return error("NOT_FOUND", "That show could not be found.", status=404)

    note = None
    if request.is_json:
        body = request.get_json(silent=True) or {}
        if isinstance(body, dict) and "note" in body:
            note, err = parse_string(
                body.get("note"), "note", required=False, max_length=200
            )
            if err:
                return err

    try:
        list_service.add_item(db.session, event_list, event, note=note)
    except ListRefused as refusal:
        db.session.rollback()
        return error(refusal.code, refusal.message, status=refusal.status)

    event_list.updated_at = utcnow()
    db.session.commit()
    item_count = list_service.item_counts(db.session, [event_list.id]).get(
        event_list.id, 0
    )
    return ok({"list_id": str(event_list.id), "event_id": str(event.id),
               "item_count": item_count})


@lists_bp.delete("/me/lists/<uuid:list_id>/events/<uuid:event_id>")
@require_auth
def remove_from_list(list_id, event_id):
    user = load_current_user()
    event_list = list_service.get_owned_list(db.session, user, list_id)
    if event_list is None:
        return error("NOT_FOUND", "That list could not be found.", status=404)

    item = db.session.get(
        EventListItem, {"list_id": event_list.id, "event_id": event_id}
    )
    if item is not None:
        db.session.delete(item)
        event_list.updated_at = utcnow()
        db.session.commit()

    item_count = list_service.item_counts(db.session, [event_list.id]).get(
        event_list.id, 0
    )
    return ok({"list_id": str(event_list.id), "event_id": str(event_id),
               "item_count": item_count})


@lists_bp.get("/lists/<uuid:list_id>")
def view_list(list_id):
    """The shareable read: a public list for anyone, a private one for its
    owner, and a 404 that refuses to distinguish "private" from "gone"."""
    viewer = load_current_user()
    event_list = list_service.get_visible_list(db.session, viewer, list_id)
    if event_list is None:
        return error("NOT_FOUND", "That list could not be found.", status=404)

    limit, offset, err = parse_pagination(request.args, default_limit=50, max_limit=100)
    if err:
        return err

    base = (
        db.session.query(EventListItem)
        .options(
            joinedload(EventListItem.event).joinedload(Event.venue),
            joinedload(EventListItem.event).joinedload(Event.artist),
        )
        .filter(EventListItem.list_id == event_list.id)
    )
    total = int(
        base.with_entities(db.func.count(EventListItem.event_id)).scalar() or 0
    )
    rows = (
        base.order_by(EventListItem.created_at.desc())
        .limit(limit)
        .offset(offset)
        .all()
    )

    events = [row.event for row in rows if row.event is not None]
    interests = event_service.interests_for(db.session, viewer, events)
    now = utcnow()

    entries = []
    for row in rows:
        if row.event is None:
            continue
        entries.append(
            serialize_list_entry(
                row,
                serialize_event(
                    row.event, interest=interests.get(row.event.id), now=now
                ),
            )
        )

    is_owner = viewer is not None and viewer.id == event_list.owner_user_id
    return ok(
        {
            "list": serialize_event_list(
                event_list, item_count=total, include_owner=True
            ),
            "entries": entries,
            "total": total,
            "has_more": offset + limit < total,
            "can_manage": is_owner,
        }
    )
