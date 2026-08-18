"""The social graph: who follows whom, who has shut whom out.

Two invariants live here and nowhere else:

1. **A block and a follow cannot coexist.** ``block_user`` deletes the follow
   edges in both directions inside the same transaction that writes the block
   row, and both follow paths re-check the block table before inserting.
2. **Mutual invisibility is symmetric.** The exclusion clause used to filter
   comments and reviews hides the blocked from the blocker *and* the blocker
   from the blocked — one rule, one place, so no read path can drift into
   showing one side of a conversation.
"""

import sqlalchemy as sa

from ..models import User, UserBlock, UserFollow


def get_user_by_handle(session, handle: str) -> User | None:
    if not handle:
        return None
    return (
        session.query(User)
        .filter(User.handle == handle.strip().lower(), User.is_active.is_(True))
        .one_or_none()
    )


def is_following(session, follower_id, followee_id) -> bool:
    return (
        session.get(UserFollow, {"follower_id": follower_id, "followee_id": followee_id})
        is not None
    )


def blocked_either_way(session, a_id, b_id) -> bool:
    """True if either party has blocked the other."""
    if a_id is None or b_id is None or a_id == b_id:
        return False
    return (
        session.query(UserBlock.blocker_id)
        .filter(
            sa.or_(
                sa.and_(UserBlock.blocker_id == a_id, UserBlock.blocked_id == b_id),
                sa.and_(UserBlock.blocker_id == b_id, UserBlock.blocked_id == a_id),
            )
        )
        .first()
        is not None
    )


def visible_author_clause(viewer_id, author_column):
    """SQL filter: rows whose author is mutually visible to ``viewer_id``.

    Applied to comment and review reads. For an anonymous viewer there is
    nothing to hide — profiles and their output are public.
    """
    if viewer_id is None:
        return sa.true()
    blocked = sa.exists().where(
        sa.or_(
            sa.and_(UserBlock.blocker_id == viewer_id, UserBlock.blocked_id == author_column),
            sa.and_(UserBlock.blocker_id == author_column, UserBlock.blocked_id == viewer_id),
        )
    )
    return sa.not_(blocked)


def block_user(session, blocker: User, blocked: User) -> None:
    """Write the block and sever the follow edges, one transaction.

    Leaving either follow standing would keep the blocked party's activity
    flowing into the blocker's feed — the exact thing the button promises to
    stop. Caller commits.
    """
    existing = session.get(
        UserBlock, {"blocker_id": blocker.id, "blocked_id": blocked.id}
    )
    if existing is None:
        session.add(UserBlock(blocker_id=blocker.id, blocked_id=blocked.id))

    session.query(UserFollow).filter(
        sa.or_(
            sa.and_(
                UserFollow.follower_id == blocker.id,
                UserFollow.followee_id == blocked.id,
            ),
            sa.and_(
                UserFollow.follower_id == blocked.id,
                UserFollow.followee_id == blocker.id,
            ),
        )
    ).delete(synchronize_session=False)


def unblock_user(session, blocker: User, blocked_id) -> None:
    session.query(UserBlock).filter(
        UserBlock.blocker_id == blocker.id, UserBlock.blocked_id == blocked_id
    ).delete(synchronize_session=False)


def follower_count(session, user_id) -> int:
    return int(
        session.query(sa.func.count(UserFollow.follower_id))
        .filter(UserFollow.followee_id == user_id)
        .scalar()
        or 0
    )


def following_count(session, user_id) -> int:
    return int(
        session.query(sa.func.count(UserFollow.followee_id))
        .filter(UserFollow.follower_id == user_id)
        .scalar()
        or 0
    )


def following_flags(session, viewer, users) -> dict:
    """Batch ``viewer follows u`` for a page of users — one query, no N+1."""
    if viewer is None or not users:
        return {}
    rows = (
        session.query(UserFollow.followee_id)
        .filter(
            UserFollow.follower_id == viewer.id,
            UserFollow.followee_id.in_([u.id for u in users]),
        )
        .all()
    )
    return {row[0]: True for row in rows}


def search_users(session, query: str, *, limit: int, offset: int):
    """Find people by handle or name. Escapes LIKE metacharacters — a query
    of ``%`` must not become a full-table wildcard."""
    from . import events as event_service

    needle = f"%{event_service._escape_like(query.lower())}%"
    base = session.query(User).filter(
        User.is_active.is_(True),
        sa.or_(
            User.handle.like(needle, escape="\\"),
            sa.func.lower(User.display_name).like(needle, escape="\\"),
        ),
    )
    total = int(base.with_entities(sa.func.count(User.id)).scalar() or 0)
    rows = base.order_by(User.handle.asc()).limit(limit).offset(offset).all()
    return rows, total
