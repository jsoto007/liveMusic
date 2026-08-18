"""The classifieds board: post a gig, browse the board, raise a hand, decide.

Authorization notes:

* Managing a gig = being its poster (or an editor). Re-derived per request.
* Applying = owning the artist you apply as — *strict* ownership, no admin
  bypass: an editor moderates the board, they do not audition other people's
  bands. ``applicant_user_id`` is recorded at apply time as audit.
* Reading a gig's applications = poster/editor. An applicant sees only their
  own artists' applications, via ``my_applications`` on the gig detail.
"""

from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from flask import Blueprint, request
from sqlalchemy.orm import joinedload

from ..auth_helpers import load_current_user, require_auth
from ..extensions import db, limiter
from ..models import (
    Artist,
    Genre,
    Gig,
    GigApplication,
    GigApplicationStatus,
    GigStatus,
    UserRole,
)
from ..services import events as event_service
from ..services import gigs as gig_service
from ..services.gigs import GigRefused
from .response import error, ok
from .serializers import serialize_gig, serialize_gig_application
from .validators import (
    get_json,
    parse_cents,
    parse_datetime,
    parse_enum,
    parse_pagination,
    parse_string,
    parse_uuid,
)

gigs_bp = Blueprint("gigs", __name__)

MAX_DESCRIPTION = 4000


def _can_manage_gig(gig, user) -> bool:
    if user is None:
        return False
    return gig.posted_by_user_id == user.id or user.role is UserRole.ADMIN


def _parse_timezone(value):
    if value is None:
        return None, None
    name, err = parse_string(value, "timezone", max_length=64)
    if err:
        return None, err
    try:
        ZoneInfo(name)
    except (ZoneInfoNotFoundError, ValueError):
        return None, error(
            "VALIDATION_ERROR", "timezone must be an IANA zone name.",
            {"timezone": "invalid"},
        )
    return name, None


@gigs_bp.get("/gigs")
@limiter.limit("120 per minute")
def list_gigs():
    limit, offset, err = parse_pagination(request.args, default_limit=30, max_limit=100)
    if err:
        return err

    genre, err = parse_enum(request.args.get("genre"), Genre, "genre", required=False)
    if err:
        return err

    base = db.session.query(Gig).options(joinedload(Gig.posted_by))

    include_closed = request.args.get("include_closed") in ("1", "true")
    if not include_closed:
        base = base.filter(Gig.status == GigStatus.OPEN)

    city = (request.args.get("city") or "").strip()
    if city:
        base = base.filter(
            db.func.lower(Gig.city).like(
                f"%{event_service._escape_like(city.lower())}%", escape="\\"
            )
        )
    if genre is not None:
        base = base.filter(Gig.genre == genre)

    query = (request.args.get("q") or "").strip()
    if query:
        needle = f"%{event_service._escape_like(query.lower())}%"
        base = base.filter(
            db.or_(
                db.func.lower(Gig.title).like(needle, escape="\\"),
                db.func.lower(Gig.description).like(needle, escape="\\"),
                db.func.lower(db.func.coalesce(Gig.venue_name, "")).like(
                    needle, escape="\\"
                ),
            )
        )

    total = int(base.with_entities(db.func.count(Gig.id)).scalar() or 0)
    rows = base.order_by(Gig.created_at.desc()).limit(limit).offset(offset).all()

    return ok(
        {
            "gigs": [serialize_gig(gig) for gig in rows],
            "total": total,
            "has_more": offset + limit < total,
        }
    )


@gigs_bp.post("/gigs")
@require_auth
@limiter.limit("10 per day")
def create_gig():
    user = load_current_user()
    body, err = get_json(request)
    if err:
        return err

    title, err = parse_string(body.get("title"), "title", max_length=160)
    if err:
        return err
    description, err = parse_string(
        body.get("description"), "description", max_length=MAX_DESCRIPTION
    )
    if err:
        return err
    city, err = parse_string(body.get("city"), "city", max_length=120)
    if err:
        return err
    neighborhood, err = parse_string(
        body.get("neighborhood"), "neighborhood", required=False, max_length=120
    )
    if err:
        return err
    venue_name, err = parse_string(
        body.get("venue_name"), "venue_name", required=False, max_length=160
    )
    if err:
        return err
    starts_at, err = parse_datetime(body.get("starts_at"), "starts_at", required=False)
    if err:
        return err
    timezone_name, err = _parse_timezone(body.get("timezone"))
    if err:
        return err
    pay_cents, err = parse_cents(body.get("pay_cents"), "pay_cents", required=False)
    if err:
        return err
    pay_note, err = parse_string(
        body.get("pay_note"), "pay_note", required=False, max_length=140
    )
    if err:
        return err
    genre, err = parse_enum(body.get("genre"), Genre, "genre", required=False)
    if err:
        return err

    gig = Gig(
        posted_by_user_id=user.id,
        title=title,
        description=description,
        city=city,
        neighborhood=neighborhood,
        venue_name=venue_name,
        starts_at=starts_at,
        timezone_name=timezone_name or "UTC",
        pay_cents=pay_cents,
        pay_note=pay_note,
        genre=genre,
    )
    db.session.add(gig)
    db.session.commit()

    return ok({"gig": serialize_gig(gig, detail=True, can_manage=True)}, status=201)


@gigs_bp.get("/gigs/<uuid:gig_id>")
def get_gig(gig_id):
    gig = (
        db.session.query(Gig)
        .options(joinedload(Gig.posted_by))
        .filter(Gig.id == gig_id)
        .one_or_none()
    )
    if gig is None:
        return error("NOT_FOUND", "That listing could not be found.", status=404)

    user = load_current_user()
    can_manage = _can_manage_gig(gig, user)

    application_count = None
    if can_manage:
        application_count = int(
            db.session.query(db.func.count(GigApplication.id))
            .filter(GigApplication.gig_id == gig.id)
            .scalar()
            or 0
        )

    my_applications = None
    if user is not None:
        rows = (
            db.session.query(GigApplication)
            .join(Artist, Artist.id == GigApplication.artist_id)
            .options(joinedload(GigApplication.artist))
            .filter(
                GigApplication.gig_id == gig.id,
                Artist.owner_user_id == user.id,
            )
            .all()
        )
        my_applications = [serialize_gig_application(row) for row in rows]

    return ok(
        {
            "gig": serialize_gig(
                gig,
                detail=True,
                can_manage=can_manage,
                application_count=application_count,
                my_applications=my_applications,
            )
        }
    )


@gigs_bp.patch("/gigs/<uuid:gig_id>")
@require_auth
def update_gig(gig_id):
    user = load_current_user()
    gig = db.session.get(Gig, gig_id)
    if gig is None or not _can_manage_gig(gig, user):
        return error("NOT_FOUND", "That listing could not be found.", status=404)

    body, err = get_json(request)
    if err:
        return err

    if "title" in body:
        value, err = parse_string(body.get("title"), "title", max_length=160)
        if err:
            return err
        gig.title = value
    if "description" in body:
        value, err = parse_string(
            body.get("description"), "description", max_length=MAX_DESCRIPTION
        )
        if err:
            return err
        gig.description = value
    if "city" in body:
        value, err = parse_string(body.get("city"), "city", max_length=120)
        if err:
            return err
        gig.city = value
    for field, cap in (("neighborhood", 120), ("venue_name", 160), ("pay_note", 140)):
        if field in body:
            value, err = parse_string(body.get(field), field, required=False, max_length=cap)
            if err:
                return err
            setattr(gig, field, value)
    if "starts_at" in body:
        value, err = parse_datetime(body.get("starts_at"), "starts_at", required=False)
        if err:
            return err
        gig.starts_at = value
    if "timezone" in body:
        value, err = _parse_timezone(body.get("timezone"))
        if err:
            return err
        gig.timezone_name = value or "UTC"
    if "pay_cents" in body:
        value, err = parse_cents(body.get("pay_cents"), "pay_cents", required=False)
        if err:
            return err
        gig.pay_cents = value
    if "genre" in body:
        value, err = parse_enum(body.get("genre"), Genre, "genre", required=False)
        if err:
            return err
        gig.genre = value
    if "status" in body:
        value, err = parse_enum(body.get("status"), GigStatus, "status")
        if err:
            return err
        gig.status = value

    db.session.commit()
    return ok({"gig": serialize_gig(gig, detail=True, can_manage=True)})


@gigs_bp.delete("/gigs/<uuid:gig_id>")
@require_auth
def delete_gig(gig_id):
    user = load_current_user()
    gig = db.session.get(Gig, gig_id)
    if gig is None or not _can_manage_gig(gig, user):
        return error("NOT_FOUND", "That listing could not be found.", status=404)

    db.session.delete(gig)
    db.session.commit()
    return ok({"deleted": True})


# ── Applications ───────────────────────────────────────────────────────────


@gigs_bp.post("/gigs/<uuid:gig_id>/applications")
@require_auth
@limiter.limit("20 per day")
def apply_to_gig(gig_id):
    user = load_current_user()
    gig = db.session.get(Gig, gig_id)
    if gig is None:
        return error("NOT_FOUND", "That listing could not be found.", status=404)

    body, err = get_json(request)
    if err:
        return err

    artist_id, err = parse_uuid(body.get("artist_id"), "artist_id")
    if err:
        return err
    message, err = parse_string(
        body.get("message"), "message", required=False, max_length=1000
    )
    if err:
        return err

    # Strict ownership — deliberately NOT get_owned_artist, whose admin
    # bypass exists for moderation, not for applying as someone else's band.
    artist = db.session.get(Artist, artist_id)
    if artist is None or artist.owner_user_id != user.id:
        return error("NOT_FOUND", "That band could not be found.", status=404)

    try:
        application = gig_service.apply_to_gig(
            db.session, user, artist, gig, message=message
        )
        db.session.commit()
    except GigRefused as refusal:
        db.session.rollback()
        return error(refusal.code, refusal.message, status=refusal.status)
    except Exception:
        # The unique (gig, artist) constraint beat the friendly check.
        db.session.rollback()
        return error(
            "ALREADY_APPLIED", "That band has already applied to this gig.", status=409
        )

    return ok({"application": serialize_gig_application(application)}, status=201)


@gigs_bp.get("/gigs/<uuid:gig_id>/applications")
@require_auth
def list_applications(gig_id):
    user = load_current_user()
    gig = db.session.get(Gig, gig_id)
    if gig is None or not _can_manage_gig(gig, user):
        return error("NOT_FOUND", "That listing could not be found.", status=404)

    rows = (
        db.session.query(GigApplication)
        .options(joinedload(GigApplication.artist))
        .filter(GigApplication.gig_id == gig.id)
        .order_by(GigApplication.created_at.asc())
        .all()
    )
    return ok(
        {"applications": [serialize_gig_application(row) for row in rows]}
    )


@gigs_bp.patch("/gigs/<uuid:gig_id>/applications/<uuid:application_id>")
@require_auth
def decide_application(gig_id, application_id):
    user = load_current_user()
    gig = db.session.get(Gig, gig_id)
    if gig is None or not _can_manage_gig(gig, user):
        return error("NOT_FOUND", "That listing could not be found.", status=404)

    application = db.session.get(GigApplication, application_id)
    # Scoped to the guard's gig, not the URL's id pair alone — owning any gig
    # must not let you decide another gig's applications.
    if application is None or application.gig_id != gig.id:
        return error("NOT_FOUND", "That application could not be found.", status=404)

    body, err = get_json(request)
    if err:
        return err
    status, err = parse_enum(body.get("status"), GigApplicationStatus, "status")
    if err:
        return err

    try:
        gig_service.decide_application(db.session, user, gig, application, status)
        db.session.commit()
    except GigRefused as refusal:
        db.session.rollback()
        return error(refusal.code, refusal.message, status=refusal.status)

    return ok({"application": serialize_gig_application(application)})


@gigs_bp.delete("/gigs/<uuid:gig_id>/applications/<uuid:application_id>")
@require_auth
def withdraw_application(gig_id, application_id):
    """The band pulls out. Allowed for whoever currently owns the artist."""
    user = load_current_user()
    application = (
        db.session.query(GigApplication)
        .join(Artist, Artist.id == GigApplication.artist_id)
        .filter(
            GigApplication.id == application_id,
            GigApplication.gig_id == gig_id,
            Artist.owner_user_id == user.id,
        )
        .one_or_none()
    )
    if application is None:
        return error("NOT_FOUND", "That application could not be found.", status=404)

    db.session.delete(application)
    db.session.commit()
    return ok({"withdrawn": True})


# ── The caller's side of the board ─────────────────────────────────────────


@gigs_bp.get("/me/gigs")
@require_auth
def my_gigs():
    user = load_current_user()
    rows = (
        db.session.query(Gig)
        .options(joinedload(Gig.posted_by))
        .filter(Gig.posted_by_user_id == user.id)
        .order_by(Gig.created_at.desc())
        .limit(100)
        .all()
    )
    counts = {}
    if rows:
        for gig_id, count in (
            db.session.query(GigApplication.gig_id, db.func.count(GigApplication.id))
            .filter(GigApplication.gig_id.in_([gig.id for gig in rows]))
            .group_by(GigApplication.gig_id)
            .all()
        ):
            counts[gig_id] = int(count)
    return ok(
        {
            "gigs": [
                serialize_gig(gig, application_count=counts.get(gig.id, 0))
                for gig in rows
            ]
        }
    )


@gigs_bp.get("/me/applications")
@require_auth
def my_applications():
    user = load_current_user()
    rows = (
        db.session.query(GigApplication)
        .join(Artist, Artist.id == GigApplication.artist_id)
        .options(
            joinedload(GigApplication.artist),
            joinedload(GigApplication.gig).joinedload(Gig.posted_by),
        )
        .filter(Artist.owner_user_id == user.id)
        .order_by(GigApplication.created_at.desc())
        .limit(100)
        .all()
    )
    return ok(
        {
            "applications": [
                serialize_gig_application(row, include_gig=True) for row in rows
            ]
        }
    )
