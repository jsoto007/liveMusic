"""The in-app inbox. ``notify`` is the only writer.

Every rule about who may be notified sits in the one function every caller
goes through: never yourself, never across a block, and (opt-in per call)
never twice for the same fact. The dedupe is a read-then-insert and therefore
best-effort under concurrency — a duplicate inbox line is an annoyance, not a
breached invariant, so it does not rate the locking a quota does.
"""

import sqlalchemy as sa

from ..models import Notification, NotificationKind, utcnow
from . import social


def notify(
    session,
    recipient_id,
    kind: NotificationKind,
    *,
    actor=None,
    event_id=None,
    comment_id=None,
    gig_id=None,
    dedupe: bool = False,
) -> Notification | None:
    """Queue one inbox line inside the caller's transaction (caller commits)."""
    if recipient_id is None:
        return None
    actor_id = actor.id if actor is not None else None
    if actor_id is not None and actor_id == recipient_id:
        return None
    if social.blocked_either_way(session, recipient_id, actor_id):
        return None

    if dedupe and _already_told(
        session, recipient_id, kind, actor_id, event_id=event_id,
        comment_id=comment_id, gig_id=gig_id,
    ):
        return None

    row = Notification(
        user_id=recipient_id,
        kind=kind,
        actor_user_id=actor_id,
        event_id=event_id,
        comment_id=comment_id,
        gig_id=gig_id,
    )
    session.add(row)
    return row


def _already_told(session, recipient_id, kind, actor_id, *, event_id, comment_id, gig_id):
    return (
        session.query(Notification.id)
        .filter(
            Notification.user_id == recipient_id,
            Notification.kind == kind,
            Notification.actor_user_id == actor_id,
            Notification.event_id == event_id,
            Notification.comment_id == comment_id,
            Notification.gig_id == gig_id,
        )
        .first()
        is not None
    )


def unread_count(session, user_id) -> int:
    return int(
        session.query(sa.func.count(Notification.id))
        .filter(Notification.user_id == user_id, Notification.read_at.is_(None))
        .scalar()
        or 0
    )


def mark_read(session, user_id, *, ids=None) -> int:
    """Mark the caller's notifications read. Scoped to ``user_id`` in the
    UPDATE itself — ids belonging to anyone else are simply unmatched rows,
    so a forged id cannot touch another inbox."""
    query = session.query(Notification).filter(
        Notification.user_id == user_id, Notification.read_at.is_(None)
    )
    if ids is not None:
        if not ids:
            return 0
        query = query.filter(Notification.id.in_(ids))
    return int(query.update({"read_at": utcnow()}, synchronize_session=False))
