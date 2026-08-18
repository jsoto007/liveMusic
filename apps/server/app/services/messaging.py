"""The correspondence desk: who may write to whom, and where it files.

One thread per pair of readers, resolved from whichever anchor opened it —
a band's page ("message the band" goes to its current owner), a gig
application (poster and applicant can reach each other), or a plain
@handle. Blocks bar new mail in both directions; history already delivered
stays readable, exactly like a mailbox.
"""

import sqlalchemy as sa
from sqlalchemy.orm import joinedload

from ..models import Artist, Conversation, Gig, GigApplication, Message, User, utcnow
from . import social


class MessageRefused(Exception):
    def __init__(self, code: str, message: str, status: int = 403):
        super().__init__(message)
        self.code = code
        self.message = message
        self.status = status


def _ordered_pair(user_id, other_id):
    return (user_id, other_id) if user_id < other_id else (other_id, user_id)


def resolve_recipient(session, sender: User, *, to_handle=None, artist_id=None,
                      application_id=None):
    """Work out who the mail is for, and what subject line it carries.

    Returns ``(recipient, artist, gig)``. Raises with a stable code when the
    anchor does not resolve — a missing artist and a foreign application are
    both NOT_FOUND, indistinguishable on purpose.
    """
    if to_handle is not None:
        recipient = social.get_user_by_handle(session, to_handle)
        if recipient is None:
            raise MessageRefused("NOT_FOUND", "That person could not be found.", 404)
        return recipient, None, None

    if artist_id is not None:
        artist = session.get(Artist, artist_id)
        if artist is None:
            raise MessageRefused("NOT_FOUND", "That band could not be found.", 404)
        recipient = session.get(User, artist.owner_user_id)
        if recipient is None or not recipient.is_active:
            raise MessageRefused("NOT_FOUND", "That band could not be found.", 404)
        return recipient, artist, None

    if application_id is not None:
        application = (
            session.query(GigApplication)
            .options(
                joinedload(GigApplication.gig),
                joinedload(GigApplication.artist),
            )
            .filter(GigApplication.id == application_id)
            .one_or_none()
        )
        if application is None or application.gig is None:
            raise MessageRefused("NOT_FOUND", "That application could not be found.", 404)

        gig: Gig = application.gig
        applicant_owner_id = (
            application.artist.owner_user_id
            if application.artist is not None
            else application.applicant_user_id
        )
        # Only the two parties to the application may open its thread, and
        # each writes to the other. Anyone else gets the same 404 a bad id
        # would — an application id must not leak who applied where.
        if sender.id == gig.posted_by_user_id:
            recipient_id = applicant_owner_id
        elif sender.id == applicant_owner_id:
            recipient_id = gig.posted_by_user_id
        else:
            raise MessageRefused("NOT_FOUND", "That application could not be found.", 404)

        recipient = session.get(User, recipient_id)
        if recipient is None or not recipient.is_active:
            raise MessageRefused("NOT_FOUND", "That application could not be found.", 404)
        return recipient, application.artist, gig

    raise MessageRefused(
        "VALIDATION_ERROR", "Say who the message is for.", 400
    )


def send_message(session, sender: User, recipient: User, body: str, *,
                 artist=None, gig=None) -> tuple[Conversation, Message]:
    """Find-or-open the pair's thread and append. Caller commits."""
    if recipient.id == sender.id:
        raise MessageRefused(
            "VALIDATION_ERROR", "You cannot message yourself.", 400
        )
    if social.blocked_either_way(session, sender.id, recipient.id):
        raise MessageRefused("BLOCKED", "You can’t message this account.")

    a_id, b_id = _ordered_pair(sender.id, recipient.id)
    conversation = (
        session.query(Conversation)
        .filter(Conversation.a_user_id == a_id, Conversation.b_user_id == b_id)
        .one_or_none()
    )
    if conversation is None:
        try:
            # A savepoint, so a lost race throws away only this insert and
            # never the caller's wider transaction.
            with session.begin_nested():
                conversation = Conversation(
                    a_user_id=a_id,
                    b_user_id=b_id,
                    artist_id=artist.id if artist is not None else None,
                    gig_id=gig.id if gig is not None else None,
                )
                session.add(conversation)
        except sa.exc.IntegrityError:
            # Two first-messages raced; the pair constraint kept one thread.
            # Adopt it — both writers meant the same mailbox.
            conversation = (
                session.query(Conversation)
                .filter(
                    Conversation.a_user_id == a_id, Conversation.b_user_id == b_id
                )
                .one()
            )
    elif conversation.artist_id is None and conversation.gig_id is None:
        # A plain thread later anchored to a hire enquiry keeps the subject.
        if artist is not None:
            conversation.artist_id = artist.id
        if gig is not None:
            conversation.gig_id = gig.id

    message = append_message(session, conversation, sender, body)
    return conversation, message


def append_message(session, conversation: Conversation, sender: User,
                   body: str) -> Message:
    """Append to an existing thread. The sender has read everything up to
    their own message by definition."""
    other_id = (
        conversation.b_user_id
        if sender.id == conversation.a_user_id
        else conversation.a_user_id
    )
    if social.blocked_either_way(session, sender.id, other_id):
        raise MessageRefused("BLOCKED", "You can’t message this account.")

    # One clock read for the message and the thread's summary column — the
    # mailbox joins messages on (conversation_id, created_at ==
    # last_message_at) to find each thread's last line in one query, and that
    # only works if the two stamps are identical.
    now = utcnow()
    message = Message(
        conversation_id=conversation.id,
        sender_user_id=sender.id,
        body=body,
        created_at=now,
    )
    conversation.last_message_at = now
    if sender.id == conversation.a_user_id:
        conversation.a_last_read_at = now
    else:
        conversation.b_last_read_at = now
    session.add(message)
    session.flush()
    return message


def mark_read(session, conversation: Conversation, user_id) -> None:
    now = utcnow()
    if user_id == conversation.a_user_id:
        conversation.a_last_read_at = now
    else:
        conversation.b_last_read_at = now


def get_conversation_for(session, user_id, conversation_id) -> Conversation | None:
    """The thread, if the caller is one of its two parties — else None, and
    the route's 404 keeps thread ids unprobeable."""
    conversation = session.get(Conversation, conversation_id)
    if conversation is None or not conversation.involves(user_id):
        return None
    return conversation


def _unread_exists_clause(user_column_read, user_id):
    return sa.and_(
        Message.conversation_id == Conversation.id,
        Message.sender_user_id != user_id,
        sa.or_(
            user_column_read.is_(None), Message.created_at > user_column_read
        ),
    )


def unread_conversation_count(session, user_id) -> int:
    """Threads holding mail the caller has not seen — one number for the
    masthead badge."""
    a_side = (
        session.query(Conversation.id)
        .filter(
            Conversation.a_user_id == user_id,
            sa.exists().where(
                _unread_exists_clause(Conversation.a_last_read_at, user_id)
            ),
        )
    )
    b_side = (
        session.query(Conversation.id)
        .filter(
            Conversation.b_user_id == user_id,
            sa.exists().where(
                _unread_exists_clause(Conversation.b_last_read_at, user_id)
            ),
        )
    )
    return int(a_side.count() + b_side.count())


def has_unread(session, conversation: Conversation, user_id) -> bool:
    last_read = conversation.my_last_read(user_id)
    query = session.query(Message.id).filter(
        Message.conversation_id == conversation.id,
        Message.sender_user_id != user_id,
    )
    if last_read is not None:
        query = query.filter(Message.created_at > last_read)
    return query.first() is not None
