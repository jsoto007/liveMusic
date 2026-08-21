"""The correspondence: threads between two readers, opened off a hire anchor.

Every read and write here is scoped to the authenticated party of the
thread. A conversation id belonging to other people is a 404 — thread ids
are not probeable, and neither are application ids (see the resolver).
"""

from flask import Blueprint, request
from sqlalchemy.orm import joinedload

from ..auth_helpers import load_current_user, require_auth
from ..extensions import db, limiter
from ..models import Conversation, Message
from ..services import messaging
from ..services.messaging import MessageRefused
from .response import error, ok
from .serializers import serialize_conversation, serialize_message
from .validators import get_json, parse_pagination, parse_string, parse_uuid

messages_bp = Blueprint("messages", __name__)

MAX_MESSAGE_LENGTH = 2000


@messages_bp.post("/conversations")
@require_auth
@limiter.limit("30 per hour")
def open_conversation():
    """Start (or continue) the thread with whoever the anchor points at."""
    sender = load_current_user()
    body, err = get_json(request)
    if err:
        return err

    text, err = parse_string(body.get("body"), "body", max_length=MAX_MESSAGE_LENGTH)
    if err:
        return err

    anchors = [key for key in ("to", "artist_id", "application_id") if body.get(key)]
    if len(anchors) != 1:
        return error(
            "VALIDATION_ERROR",
            "Address the message one way: a @handle, a band, or an application.",
            {"to": "exactly_one"},
        )

    to_handle = None
    artist_id = application_id = None
    if anchors[0] == "to":
        to_handle, err = parse_string(body.get("to"), "to", max_length=30)
        if err:
            return err
        to_handle = to_handle.lstrip("@").lower()
    elif anchors[0] == "artist_id":
        artist_id, err = parse_uuid(body.get("artist_id"), "artist_id")
        if err:
            return err
    else:
        application_id, err = parse_uuid(body.get("application_id"), "application_id")
        if err:
            return err

    try:
        recipient, artist, gig = messaging.resolve_recipient(
            db.session,
            sender,
            to_handle=to_handle,
            artist_id=artist_id,
            application_id=application_id,
        )
        conversation, message = messaging.send_message(
            db.session, sender, recipient, text, artist=artist, gig=gig
        )
        db.session.commit()
    except MessageRefused as refusal:
        db.session.rollback()
        return error(refusal.code, refusal.message, status=refusal.status)

    return ok(
        {
            "conversation": serialize_conversation(
                conversation, viewer=sender, unread=False
            ),
            "message": serialize_message(message),
        },
        status=201,
    )


@messages_bp.get("/me/conversations")
@require_auth
def my_conversations():
    user = load_current_user()
    limit, offset, err = parse_pagination(request.args, default_limit=50, max_limit=100)
    if err:
        return err

    base = (
        db.session.query(Conversation)
        .options(
            joinedload(Conversation.a_user),
            joinedload(Conversation.b_user),
            joinedload(Conversation.artist),
            joinedload(Conversation.gig),
        )
        .filter(
            db.or_(
                Conversation.a_user_id == user.id, Conversation.b_user_id == user.id
            )
        )
    )
    total = int(base.with_entities(db.func.count(Conversation.id)).scalar() or 0)
    rows = (
        base.order_by(Conversation.last_message_at.desc())
        .limit(limit)
        .offset(offset)
        .all()
    )

    # Each thread's last line in one query: messages stamp created_at with
    # the same instant they write to last_message_at, so the pair join finds
    # exactly the newest message per thread without scanning histories.
    ids = [row.id for row in rows]
    last_by_convo = {}
    if ids:
        latest = (
            db.session.query(Message)
            .join(
                Conversation,
                db.and_(
                    Message.conversation_id == Conversation.id,
                    Message.created_at == Conversation.last_message_at,
                ),
            )
            .filter(Message.conversation_id.in_(ids))
            .all()
        )
        for message in latest:
            last_by_convo.setdefault(message.conversation_id, message)

    return ok(
        {
            "conversations": [
                serialize_conversation(
                    row,
                    viewer=user,
                    unread=messaging.has_unread(db.session, row, user.id),
                    last_message=last_by_convo.get(row.id),
                )
                for row in rows
            ],
            "total": total,
            "has_more": offset + limit < total,
        }
    )


@messages_bp.get("/me/conversations/unread-count")
@require_auth
def unread_count():
    user = load_current_user()
    return ok(
        {
            "unread_count": messaging.unread_conversation_count(
                db.session, user.id
            )
        }
    )


@messages_bp.get("/conversations/<uuid:conversation_id>")
@require_auth
def get_conversation(conversation_id):
    user = load_current_user()
    conversation = messaging.get_conversation_for(db.session, user.id, conversation_id)
    if conversation is None:
        return error("NOT_FOUND", "That conversation could not be found.", status=404)
    return ok(
        {
            "conversation": serialize_conversation(
                conversation,
                viewer=user,
                unread=messaging.has_unread(db.session, conversation, user.id),
            )
        }
    )


@messages_bp.get("/conversations/<uuid:conversation_id>/messages")
@require_auth
def list_messages(conversation_id):
    user = load_current_user()
    conversation = messaging.get_conversation_for(db.session, user.id, conversation_id)
    if conversation is None:
        return error("NOT_FOUND", "That conversation could not be found.", status=404)

    limit, offset, err = parse_pagination(request.args, default_limit=50, max_limit=100)
    if err:
        return err

    base = db.session.query(Message).filter(
        Message.conversation_id == conversation.id
    )
    total = int(base.with_entities(db.func.count(Message.id)).scalar() or 0)
    rows = (
        base.options(joinedload(Message.sender))
        .order_by(Message.created_at.desc())
        .limit(limit)
        .offset(offset)
        .all()
    )

    return ok(
        {
            "messages": [serialize_message(row) for row in rows],
            "total": total,
            "has_more": offset + limit < total,
        }
    )


@messages_bp.post("/conversations/<uuid:conversation_id>/messages")
@require_auth
@limiter.limit("120 per hour")
def send_message(conversation_id):
    user = load_current_user()
    conversation = messaging.get_conversation_for(db.session, user.id, conversation_id)
    if conversation is None:
        return error("NOT_FOUND", "That conversation could not be found.", status=404)

    body, err = get_json(request)
    if err:
        return err
    text, err = parse_string(body.get("body"), "body", max_length=MAX_MESSAGE_LENGTH)
    if err:
        return err

    try:
        message = messaging.append_message(db.session, conversation, user, text)
        db.session.commit()
    except MessageRefused as refusal:
        db.session.rollback()
        return error(refusal.code, refusal.message, status=refusal.status)

    return ok({"message": serialize_message(message)}, status=201)


@messages_bp.post("/conversations/<uuid:conversation_id>/read")
@require_auth
def mark_conversation_read(conversation_id):
    user = load_current_user()
    conversation = messaging.get_conversation_for(db.session, user.id, conversation_id)
    if conversation is None:
        return error("NOT_FOUND", "That conversation could not be found.", status=404)

    messaging.mark_read(db.session, conversation, user.id)
    db.session.commit()
    return ok({"conversation_id": str(conversation.id), "read": True})
