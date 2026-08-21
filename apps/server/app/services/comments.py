"""Comments under a listing: creation, the mention sweep, and teardown.

Creation is a multi-step write — the row, the owner's notification, one per
mention — so it is coordinated here rather than in the route.
"""

import re

import sqlalchemy as sa

from ..models import Comment, CommentLike, NotificationKind, User
from ..utils.handles import HANDLE_RE  # noqa: F401 - the mention grammar IS the handle grammar
from . import inbox, social

#: ``@name`` tokens, same alphabet as handles. Case-insensitive so ``@Ada``
#: finds ``ada``; the handle store is lowercase.
MENTION_RE = re.compile(r"@([a-z0-9_]{3,30})", re.IGNORECASE)

#: A comment can name half the room; only the first few get an inbox line.
MAX_MENTIONS_NOTIFIED = 10


def event_owner_ids(event) -> set:
    """The people who answer for a listing: whoever posted it, and the owner
    of the band account it is billed under."""
    owners = set()
    if event.created_by_user_id is not None:
        owners.add(event.created_by_user_id)
    if event.artist is not None:
        owners.add(event.artist.owner_user_id)
    return owners


def author_barred(session, author: User, event) -> bool:
    """Whether a block between the author and any owner bars this comment.

    Symmetric on purpose — mutual invisibility means you also do not get to
    keep writing under the listings of someone you have blocked.
    """
    return any(
        social.blocked_either_way(session, author.id, owner_id)
        for owner_id in event_owner_ids(event)
        if owner_id != author.id
    )


def create_comment(session, author: User, event, body: str) -> Comment:
    """Insert the comment and queue every notification it owes. Caller commits."""
    comment = Comment(event_id=event.id, author_user_id=author.id, body=body)
    session.add(comment)
    session.flush()  # the notifications need comment.id

    for owner_id in event_owner_ids(event):
        inbox.notify(
            session,
            owner_id,
            NotificationKind.EVENT_COMMENT,
            actor=author,
            event_id=event.id,
            comment_id=comment.id,
        )

    mentioned = resolve_mentions(session, body)
    already_owed = event_owner_ids(event) | {author.id}
    for user in mentioned:
        if user.id in already_owed:
            # The owner is already getting the comment notification; a second
            # line for the same sentence reads like a stutter.
            continue
        inbox.notify(
            session,
            user.id,
            NotificationKind.MENTION,
            actor=author,
            event_id=event.id,
            comment_id=comment.id,
        )
    return comment


def resolve_mentions(session, body: str) -> list[User]:
    """The real accounts a body names, capped, order of first appearance."""
    seen: list[str] = []
    for raw in MENTION_RE.findall(body or ""):
        handle = raw.lower()
        if handle not in seen:
            seen.append(handle)
        if len(seen) >= MAX_MENTIONS_NOTIFIED:
            break
    if not seen:
        return []
    rows = (
        session.query(User)
        .filter(User.handle.in_(seen), User.is_active.is_(True))
        .all()
    )
    by_handle = {user.handle: user for user in rows}
    return [by_handle[h] for h in seen if h in by_handle]


def like_counts(session, comment_ids) -> dict:
    """comment_id → like count for a page of comments, one query."""
    if not comment_ids:
        return {}
    rows = (
        session.query(CommentLike.comment_id, sa.func.count(CommentLike.user_id))
        .filter(CommentLike.comment_id.in_(comment_ids))
        .group_by(CommentLike.comment_id)
        .all()
    )
    return {comment_id: int(count) for comment_id, count in rows}


def liked_flags(session, viewer, comment_ids) -> dict:
    if viewer is None or not comment_ids:
        return {}
    rows = (
        session.query(CommentLike.comment_id)
        .filter(
            CommentLike.user_id == viewer.id,
            CommentLike.comment_id.in_(comment_ids),
        )
        .all()
    )
    return {row[0]: True for row in rows}
