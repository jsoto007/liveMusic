"""Artist profiles: the public page, the band's own edits, follows, samples."""

import uuid as uuid_module

from flask import Blueprint, g, request
from sqlalchemy.orm import joinedload

from ..auth_helpers import load_current_user, require_artist_owner, require_auth
from ..extensions import db, limiter
from ..models import Artist, ArtistFollow, ArtistMember, AudioSample, Event, EventStatus, utcnow
from ..services import events as event_service
from ..services.r2_storage import R2Storage
from .response import error, ok
from .serializers import serialize_artist, serialize_event, serialize_sample
from .validators import (
    get_json,
    parse_bool,
    parse_int,
    parse_pagination,
    parse_string,
    parse_string_list,
)

artists_bp = Blueprint("artists", __name__)

MAX_MEMBERS = 24


def _lookup_artist(handle: str) -> Artist | None:
    """Resolve by id or slug — the mobile app links by id, the web by slug."""
    query = db.session.query(Artist).options(
        joinedload(Artist.members), joinedload(Artist.samples)
    )
    try:
        artist_uuid = uuid_module.UUID(handle)
    except (ValueError, AttributeError, TypeError):
        return query.filter(Artist.slug == handle).one_or_none()
    return query.filter(Artist.id == artist_uuid).one_or_none()


def _follower_count(artist_id) -> int:
    return int(
        db.session.query(db.func.count(ArtistFollow.user_id))
        .filter(ArtistFollow.artist_id == artist_id)
        .scalar()
        or 0
    )


@artists_bp.get("/artists/for-hire")
@limiter.limit("120 per minute")
def for_hire_directory():
    """The hire desk: bands that flagged themselves available.

    Registered above the ``/artists/<handle>`` catch-all so the literal path
    wins the match.
    """
    limit, offset, err = parse_pagination(request.args, default_limit=30, max_limit=100)
    if err:
        return err

    base = db.session.query(Artist).filter(Artist.available_for_hire.is_(True))

    city = (request.args.get("city") or "").strip()
    if city:
        base = base.filter(
            db.func.lower(Artist.city).like(
                f"%{event_service._escape_like(city.lower())}%", escape="\\"
            )
        )

    query = (request.args.get("q") or "").strip()
    if query:
        needle = f"%{event_service._escape_like(query.lower())}%"
        base = base.filter(
            db.or_(
                db.func.lower(Artist.name).like(needle, escape="\\"),
                db.func.lower(db.func.coalesce(Artist.one_liner, "")).like(
                    needle, escape="\\"
                ),
                db.func.lower(db.func.coalesce(Artist.sounds_like, "")).like(
                    needle, escape="\\"
                ),
                # style_tags is a JSON list; matching its serialized text is a
                # LIKE-level filter, not a structured query — good enough for
                # a directory search box.
                db.func.lower(db.func.cast(Artist.style_tags, db.String)).like(
                    needle, escape="\\"
                ),
            )
        )

    total = int(base.with_entities(db.func.count(Artist.id)).scalar() or 0)
    rows = (
        base.order_by(Artist.verified_at.isnot(None).desc(), Artist.name.asc())
        .limit(limit)
        .offset(offset)
        .all()
    )

    return ok(
        {
            "artists": [serialize_artist(artist) for artist in rows],
            "total": total,
            "has_more": offset + limit < total,
        }
    )


@artists_bp.get("/artists/<handle>")
def get_artist(handle):
    artist = _lookup_artist(handle)
    if artist is None:
        return error("NOT_FOUND", "That band could not be found.", status=404)

    user = load_current_user()
    is_following = False
    if user is not None:
        is_following = (
            db.session.get(ArtistFollow, {"user_id": user.id, "artist_id": artist.id}) is not None
        )

    return ok(
        {
            "artist": serialize_artist(
                artist,
                detail=True,
                follower_count=_follower_count(artist.id),
                is_following=is_following,
            )
        }
    )


@artists_bp.get("/artists/<handle>/events")
def artist_events(handle):
    artist = _lookup_artist(handle)
    if artist is None:
        return error("NOT_FOUND", "That band could not be found.", status=404)

    limit, offset, err = parse_pagination(request.args, default_limit=20, max_limit=50)
    if err:
        return err

    stmt = (
        event_service.base_query(db.session)
        .where(Event.artist_id == artist.id, Event.status == EventStatus.PUBLISHED)
        .order_by(Event.starts_at.asc())
        .limit(limit)
        .offset(offset)
    )
    rows = db.session.execute(stmt).unique().scalars().all()

    user = load_current_user()
    interests = event_service.interests_for(db.session, user, rows)
    now = utcnow()
    return ok(
        {
            "events": [
                serialize_event(event, interest=interests.get(event.id), now=now)
                for event in rows
            ]
        }
    )


@artists_bp.patch("/artists/<uuid:artist_id>")
@require_artist_owner()
def update_artist(artist_id):  # noqa: ARG001 - resolved by the guard onto g.artist
    artist = g.artist
    body, err = get_json(request)
    if err:
        return err

    if "name" in body:
        value, err = parse_string(body.get("name"), "name", max_length=120)
        if err:
            return err
        artist.name = value

    for field, max_length in (
        ("city", 120),
        ("neighborhood", 120),
        ("one_liner", 300),
        ("sounds_like", 300),
    ):
        if field in body:
            value, err = parse_string(
                body.get(field), field, required=False, max_length=max_length
            )
            if err:
                return err
            setattr(artist, field, value)

    if "bio" in body:
        value, err = parse_string(body.get("bio"), "bio", required=False, max_length=4000)
        if err:
            return err
        artist.bio = value

    if "style_tags" in body:
        value, err = parse_string_list(
            body.get("style_tags"), "style_tags", max_items=12, max_length=40
        )
        if err:
            return err
        artist.style_tags = value or []

    if "available_for_hire" in body:
        value, err = parse_bool(body.get("available_for_hire"), "available_for_hire")
        if err:
            return err
        artist.available_for_hire = value

    if "members" in body:
        raw_members = body.get("members")
        if not isinstance(raw_members, list):
            return error("VALIDATION_ERROR", "members must be a list.", {"members": "invalid"})
        if len(raw_members) > MAX_MEMBERS:
            return error(
                "VALIDATION_ERROR",
                f"A band allows at most {MAX_MEMBERS} members.",
                {"members": "too_many"},
            )
        artist.members.clear()
        for position, raw in enumerate(raw_members):
            if not isinstance(raw, dict):
                db.session.rollback()
                return error(
                    "VALIDATION_ERROR", "Each member must be an object.", {"members": "invalid"}
                )
            name, err = parse_string(raw.get("name"), "members.name", max_length=120)
            if err:
                db.session.rollback()
                return err
            instrument, err = parse_string(
                raw.get("instrument"), "members.instrument", required=False, max_length=120
            )
            if err:
                db.session.rollback()
                return err
            artist.members.append(
                ArtistMember(name=name, instrument=instrument, position=position)
            )

    db.session.commit()
    return ok({"artist": serialize_artist(artist, detail=True)})


# ── Following ──────────────────────────────────────────────────────────────


@artists_bp.post("/artists/<uuid:artist_id>/follow")
@require_auth
@limiter.limit("120 per hour")
def follow_artist(artist_id):
    user = load_current_user()
    artist = db.session.get(Artist, artist_id)
    if artist is None:
        return error("NOT_FOUND", "That band could not be found.", status=404)

    existing = db.session.get(ArtistFollow, {"user_id": user.id, "artist_id": artist.id})
    if existing is None:
        db.session.add(ArtistFollow(user_id=user.id, artist_id=artist.id))
        try:
            db.session.commit()
        except Exception:
            # Two taps racing each other both see "no row" and both insert.
            # The composite primary key is what actually guarantees one row;
            # this just turns the loser's IntegrityError into a success, which
            # is what the user meant either way.
            db.session.rollback()

    return ok({"artist_id": str(artist.id), "is_following": True,
               "follower_count": _follower_count(artist.id)})


@artists_bp.delete("/artists/<uuid:artist_id>/follow")
@require_auth
def unfollow_artist(artist_id):
    user = load_current_user()
    existing = db.session.get(ArtistFollow, {"user_id": user.id, "artist_id": artist_id})
    if existing is not None:
        db.session.delete(existing)
        db.session.commit()
    return ok({"artist_id": str(artist_id), "is_following": False,
               "follower_count": _follower_count(artist_id)})


# ── Sound samples ──────────────────────────────────────────────────────────


@artists_bp.patch("/artists/<uuid:artist_id>/samples/<uuid:sample_id>")
@require_artist_owner()
def update_sample(artist_id, sample_id):  # noqa: ARG001
    artist = g.artist
    sample = db.session.get(AudioSample, sample_id)
    # Scope the sample to the artist from the guard, not to the id in the URL —
    # otherwise owning any band would let you rename any sample.
    if sample is None or sample.artist_id != artist.id:
        return error("NOT_FOUND", "That sample could not be found.", status=404)

    body, err = get_json(request)
    if err:
        return err

    if "title" in body:
        value, err = parse_string(body.get("title"), "title", max_length=140)
        if err:
            return err
        sample.title = value

    if "position" in body:
        value, err = parse_int(body.get("position"), "position", minimum=0, maximum=999)
        if err:
            return err
        sample.position = value

    db.session.commit()
    return ok({"sample": serialize_sample(sample)})


@artists_bp.delete("/artists/<uuid:artist_id>/samples/<uuid:sample_id>")
@require_artist_owner()
def delete_sample(artist_id, sample_id):  # noqa: ARG001
    artist = g.artist
    sample = db.session.get(AudioSample, sample_id)
    if sample is None or sample.artist_id != artist.id:
        return error("NOT_FOUND", "That sample could not be found.", status=404)

    object_key = sample.object_key
    db.session.delete(sample)
    db.session.commit()

    # Delete the row first, then the object. If the R2 call fails the sample is
    # already gone from the UI and the orphan is swept later; doing it the
    # other way round could leave a row pointing at nothing.
    if not R2Storage.delete_object(object_key):
        db.session.get(Artist, artist.id)  # keep the session warm for the log line
        from flask import current_app

        current_app.logger.warning(
            "Sample row deleted but its object remains in R2 (key=%s); the sweeper will retry.",
            object_key,
        )

    return ok({"deleted": True})
