"""Public profiles and the reader-to-reader graph.

Profiles are public by design (the privacy model lives on lists), so the
reads here take an *optional* viewer — they only use it to answer "do I
follow this person" and "have I blocked them". Everything that writes an
edge requires auth and re-checks the block table.
"""

from flask import Blueprint, request

from ..auth_helpers import load_current_user, require_auth
from ..extensions import db, limiter
from ..models import (
    Artist,
    EventList,
    NotificationKind,
    Review,
    User,
    UserBlock,
    UserFollow,
)
from ..services import inbox, social
from ..services import lists as list_service
from .response import error, ok
from .serializers import (
    serialize_event_list,
    serialize_public_profile,
    serialize_review,
    user_card,
)
from .validators import parse_pagination, parse_string

users_bp = Blueprint("users", __name__)

_NOT_FOUND = ("NOT_FOUND", "That person could not be found.")


def _lookup(handle: str) -> User | None:
    return social.get_user_by_handle(db.session, handle)


@users_bp.get("/users/search")
@limiter.limit("60 per minute")
def search_users():
    query, err = parse_string(
        request.args.get("q"), "q", max_length=60, min_length=2
    )
    if err:
        return err
    limit, offset, err = parse_pagination(request.args, default_limit=20, max_limit=50)
    if err:
        return err

    rows, total = social.search_users(db.session, query, limit=limit, offset=offset)
    viewer = load_current_user()
    follows = social.following_flags(db.session, viewer, rows)

    people = []
    for user in rows:
        card = user_card(user)
        card["bio"] = user.bio
        if viewer is not None:
            card["is_following"] = bool(follows.get(user.id))
            card["is_self"] = user.id == viewer.id
        people.append(card)

    return ok(
        {"people": people, "total": total, "has_more": offset + limit < total}
    )


@users_bp.get("/users/<handle>")
def get_profile(handle):
    user = _lookup(handle)
    if user is None:
        return error(*_NOT_FOUND, status=404)

    viewer = load_current_user()
    is_self = viewer is not None and viewer.id == user.id

    public_lists = int(
        db.session.query(db.func.count(EventList.id))
        .filter(EventList.owner_user_id == user.id, EventList.is_public.is_(True))
        .scalar()
        or 0
    )
    review_count = int(
        db.session.query(db.func.count(Review.id))
        .filter(Review.author_user_id == user.id)
        .scalar()
        or 0
    )
    artists = (
        db.session.query(Artist)
        .filter(Artist.owner_user_id == user.id)
        .order_by(Artist.name.asc())
        .all()
    )

    is_following = None
    is_blocked = None
    if viewer is not None and not is_self:
        is_following = social.is_following(db.session, viewer.id, user.id)
        is_blocked = (
            db.session.get(
                UserBlock, {"blocker_id": viewer.id, "blocked_id": user.id}
            )
            is not None
        )

    return ok(
        {
            "profile": serialize_public_profile(
                user,
                followers=social.follower_count(db.session, user.id),
                following=social.following_count(db.session, user.id),
                public_list_count=public_lists,
                review_count=review_count,
                artists=artists,
                is_following=is_following,
                is_blocked=is_blocked,
                is_self=is_self,
            )
        }
    )


def _people_page(query, *, viewer, limit, offset, total):
    rows = query.limit(limit).offset(offset).all()
    follows = social.following_flags(db.session, viewer, rows)
    people = []
    for person in rows:
        card = user_card(person)
        if viewer is not None:
            card["is_following"] = bool(follows.get(person.id))
            card["is_self"] = person.id == viewer.id
        people.append(card)
    return ok({"people": people, "total": total, "has_more": offset + limit < total})


@users_bp.get("/users/<handle>/followers")
def list_followers(handle):
    user = _lookup(handle)
    if user is None:
        return error(*_NOT_FOUND, status=404)
    limit, offset, err = parse_pagination(request.args, default_limit=50, max_limit=100)
    if err:
        return err

    base = (
        db.session.query(User)
        .join(UserFollow, UserFollow.follower_id == User.id)
        .filter(UserFollow.followee_id == user.id, User.is_active.is_(True))
        .order_by(UserFollow.created_at.desc())
    )
    total = social.follower_count(db.session, user.id)
    return _people_page(
        base, viewer=load_current_user(), limit=limit, offset=offset, total=total
    )


@users_bp.get("/users/<handle>/following")
def list_following(handle):
    user = _lookup(handle)
    if user is None:
        return error(*_NOT_FOUND, status=404)
    limit, offset, err = parse_pagination(request.args, default_limit=50, max_limit=100)
    if err:
        return err

    base = (
        db.session.query(User)
        .join(UserFollow, UserFollow.followee_id == User.id)
        .filter(UserFollow.follower_id == user.id, User.is_active.is_(True))
        .order_by(UserFollow.created_at.desc())
    )
    total = social.following_count(db.session, user.id)
    return _people_page(
        base, viewer=load_current_user(), limit=limit, offset=offset, total=total
    )


@users_bp.get("/users/<handle>/lists")
def list_user_lists(handle):
    user = _lookup(handle)
    if user is None:
        return error(*_NOT_FOUND, status=404)

    viewer = load_current_user()
    query = db.session.query(EventList).filter(EventList.owner_user_id == user.id)
    # The owner sees their whole shelf here; everyone else sees only what was
    # made public. Filtered in SQL, not after the fact.
    if viewer is None or viewer.id != user.id:
        query = query.filter(EventList.is_public.is_(True))

    rows = query.order_by(EventList.updated_at.desc()).limit(100).all()
    counts = list_service.item_counts(db.session, [row.id for row in rows])
    return ok(
        {
            "lists": [
                serialize_event_list(row, item_count=counts.get(row.id, 0))
                for row in rows
            ]
        }
    )


@users_bp.get("/users/<handle>/reviews")
def list_user_reviews(handle):
    user = _lookup(handle)
    if user is None:
        return error(*_NOT_FOUND, status=404)
    limit, offset, err = parse_pagination(request.args, default_limit=20, max_limit=50)
    if err:
        return err

    base = db.session.query(Review).filter(Review.author_user_id == user.id)
    total = int(base.with_entities(db.func.count(Review.id)).scalar() or 0)
    rows = base.order_by(Review.created_at.desc()).limit(limit).offset(offset).all()

    viewer = load_current_user()
    return ok(
        {
            "reviews": [
                serialize_review(
                    review,
                    can_edit=viewer is not None and viewer.id == review.author_user_id,
                    include_event=True,
                )
                for review in rows
            ],
            "total": total,
            "has_more": offset + limit < total,
        }
    )


# ── Follows ────────────────────────────────────────────────────────────────


@users_bp.post("/users/<handle>/follow")
@require_auth
@limiter.limit("120 per hour")
def follow_user(handle):
    viewer = load_current_user()
    target = _lookup(handle)
    if target is None:
        return error(*_NOT_FOUND, status=404)
    if target.id == viewer.id:
        return error(
            "VALIDATION_ERROR", "You cannot follow yourself.", {"handle": "self"}
        )
    if social.blocked_either_way(db.session, viewer.id, target.id):
        return error("BLOCKED", "You can’t follow this account.", status=403)

    existing = db.session.get(
        UserFollow, {"follower_id": viewer.id, "followee_id": target.id}
    )
    if existing is None:
        db.session.add(UserFollow(follower_id=viewer.id, followee_id=target.id))
        # Re-following after an unfollow should not re-ring the bell — dedupe
        # holds one follower line per (recipient, actor) for all time.
        inbox.notify(
            db.session,
            target.id,
            NotificationKind.NEW_FOLLOWER,
            actor=viewer,
            dedupe=True,
        )
        try:
            db.session.commit()
        except Exception:
            # Two taps raced; the composite PK kept one row, which is what the
            # user meant. Same shape as artist follows.
            db.session.rollback()

    return ok(
        {
            "handle": target.handle,
            "is_following": True,
            "follower_count": social.follower_count(db.session, target.id),
        }
    )


@users_bp.delete("/users/<handle>/follow")
@require_auth
def unfollow_user(handle):
    viewer = load_current_user()
    target = _lookup(handle)
    if target is None:
        return error(*_NOT_FOUND, status=404)

    existing = db.session.get(
        UserFollow, {"follower_id": viewer.id, "followee_id": target.id}
    )
    if existing is not None:
        db.session.delete(existing)
        db.session.commit()

    return ok(
        {
            "handle": target.handle,
            "is_following": False,
            "follower_count": social.follower_count(db.session, target.id),
        }
    )


# ── Blocks ─────────────────────────────────────────────────────────────────


@users_bp.post("/users/<handle>/block")
@require_auth
@limiter.limit("60 per hour")
def block_user(handle):
    viewer = load_current_user()
    target = _lookup(handle)
    if target is None:
        return error(*_NOT_FOUND, status=404)
    if target.id == viewer.id:
        return error(
            "VALIDATION_ERROR", "You cannot block yourself.", {"handle": "self"}
        )

    social.block_user(db.session, viewer, target)
    db.session.commit()
    return ok({"handle": target.handle, "is_blocked": True})


@users_bp.delete("/users/<handle>/block")
@require_auth
def unblock_user(handle):
    viewer = load_current_user()
    target = _lookup(handle)
    if target is None:
        return error(*_NOT_FOUND, status=404)

    social.unblock_user(db.session, viewer, target.id)
    db.session.commit()
    return ok({"handle": target.handle, "is_blocked": False})


@users_bp.get("/me/blocks")
@require_auth
def my_blocks():
    viewer = load_current_user()
    rows = (
        db.session.query(User)
        .join(UserBlock, UserBlock.blocked_id == User.id)
        .filter(UserBlock.blocker_id == viewer.id)
        .order_by(UserBlock.created_at.desc())
        .limit(500)
        .all()
    )
    return ok({"people": [user_card(person) for person in rows]})
