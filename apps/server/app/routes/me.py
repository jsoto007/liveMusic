"""The caller's own account: profile, list, band accounts."""

from flask import Blueprint, request

from ..auth_helpers import load_current_user, require_auth
from ..extensions import db, limiter
from ..models import (
    Artist,
    ArtistFollow,
    Event,
    EventInterest,
    EventStatus,
    UserRole,
    utcnow,
)
from ..services import events as event_service
from ..utils.slugs import unique_slug
from .response import error, ok
from .serializers import serialize_artist, serialize_event, serialize_user
from .validators import get_json, parse_string, parse_string_list

me_bp = Blueprint("me", __name__)

# A single person running three side projects is normal; a hundred is abuse.
MAX_ARTISTS_PER_USER = 5


@me_bp.get("/me")
@require_auth
def get_me():
    user = load_current_user()
    artists = (
        db.session.query(Artist)
        .filter(Artist.owner_user_id == user.id)
        .order_by(Artist.created_at.asc())
        .all()
    )
    return ok(
        {
            "user": serialize_user(user, include_email=True),
            "artists": [serialize_artist(artist) for artist in artists],
        }
    )


@me_bp.patch("/me")
@require_auth
def update_me():
    user = load_current_user()
    body, err = get_json(request)
    if err:
        return err

    if "display_name" in body:
        value, err = parse_string(body.get("display_name"), "display_name", max_length=80)
        if err:
            return err
        user.display_name = value

    if "home_city" in body:
        value, err = parse_string(
            body.get("home_city"), "home_city", required=False, max_length=120
        )
        if err:
            return err
        user.home_city = value

    # `role`, `email` and `is_active` are deliberately absent: a client cannot
    # promote itself to admin or take over an address by PATCHing its profile.

    db.session.commit()
    return ok({"user": serialize_user(user, include_email=True)})


@me_bp.get("/me/list")
@require_auth
def my_list():
    """Your list — what you are going to, and what you kept for later."""
    user = load_current_user()
    now = utcnow()

    rows = (
        db.session.query(EventInterest, Event)
        .join(Event, Event.id == EventInterest.event_id)
        .filter(
            EventInterest.user_id == user.id,
            Event.status != EventStatus.DRAFT,
            Event.starts_at >= now - event_service.GRACE,
        )
        .order_by(Event.starts_at.asc())
        .limit(200)
        .all()
    )

    going, saved = [], []
    for interest, event in rows:
        payload = serialize_event(event, interest=interest, now=now)
        if interest.going:
            going.append(payload)
        # A show can be both; it appears under "Going" and stays in the kept
        # list, which is what the prototype shows.
        if interest.saved:
            saved.append(payload)

    return ok(
        {
            "going": going,
            "saved": saved,
            "summary": f"{len(going)} going · {len(saved)} kept",
        }
    )


@me_bp.get("/me/following")
@require_auth
def my_following():
    user = load_current_user()
    artists = (
        db.session.query(Artist)
        .join(ArtistFollow, ArtistFollow.artist_id == Artist.id)
        .filter(ArtistFollow.user_id == user.id)
        .order_by(Artist.name.asc())
        .limit(500)
        .all()
    )
    return ok({"artists": [serialize_artist(artist, is_following=True) for artist in artists]})


@me_bp.post("/me/artists")
@require_auth
@limiter.limit("10 per day")
def create_artist():
    """Claim a band account. The caller becomes its owner."""
    user = load_current_user()
    body, err = get_json(request)
    if err:
        return err

    existing = (
        db.session.query(db.func.count(Artist.id))
        .filter(Artist.owner_user_id == user.id)
        .scalar()
        or 0
    )
    if existing >= MAX_ARTISTS_PER_USER:
        return error(
            "LIMIT_REACHED",
            f"You can hold at most {MAX_ARTISTS_PER_USER} band accounts.",
            status=409,
        )

    name, err = parse_string(body.get("name"), "name", max_length=120)
    if err:
        return err
    city, err = parse_string(body.get("city"), "city", required=False, max_length=120)
    if err:
        return err
    neighborhood, err = parse_string(
        body.get("neighborhood"), "neighborhood", required=False, max_length=120
    )
    if err:
        return err
    one_liner, err = parse_string(
        body.get("one_liner"), "one_liner", required=False, max_length=300
    )
    if err:
        return err
    style_tags, err = parse_string_list(
        body.get("style_tags"), "style_tags", max_items=12, max_length=40
    )
    if err:
        return err

    artist = Artist(
        owner_user_id=user.id,
        name=name,
        slug=unique_slug(db.session, Artist, name),
        city=city or user.home_city,
        neighborhood=neighborhood,
        one_liner=one_liner,
        style_tags=style_tags or [],
    )
    db.session.add(artist)

    # Holding a band account is what the `artist` role means. Never downgrade
    # an admin here.
    if user.role is UserRole.LISTENER:
        user.role = UserRole.ARTIST

    db.session.commit()
    return ok({"artist": serialize_artist(artist, detail=True)}, status=201)


@me_bp.get("/me/artists/<uuid:artist_id>/events")
@require_auth
def my_artist_events(artist_id):
    """A band's own listings, drafts included — the 'Your listings' section."""
    from ..auth_helpers import get_owned_artist

    artist = get_owned_artist(artist_id)
    if artist is None:
        return error("NOT_FOUND", "Not found.", status=404)

    events = (
        db.session.query(Event)
        .filter(Event.artist_id == artist.id)
        .order_by(Event.starts_at.desc())
        .limit(100)
        .all()
    )
    now = utcnow()
    return ok({"events": [serialize_event(event, detail=True, now=now) for event in events]})
