"""Direct-to-R2 uploads.

The API never touches file bytes. It issues a narrowly-scoped presigned PUT,
then verifies with a ``HEAD`` that what landed matches what it signed for
before any durable row is written. See CLAUDE.md §4: R2 does not implement
presigned POST, so PUT is the only direct-upload path available, and the size
cap is enforced entirely at the HEAD check rather than by a POST condition.

The threat model this is written against:

* A caller uploading on behalf of a band it does not own — ownership is
  re-derived from the authenticated user at *both* issue and completion, and
  the target is pinned on the ticket so it cannot be swapped in between.
* A caller choosing its own object key — it cannot; the server mints one.
* A caller declaring a small size and pushing a huge file — PUT cannot bound
  this at signing time, so the HEAD check at completion is the only gate;
  an oversized object is deleted rather than attached to a durable row.
* A caller completing someone else's ticket — tickets are scoped to the user.
* A caller replaying a completed ticket — completion is one-shot.
"""

from datetime import timedelta

from flask import Blueprint, current_app, request
from flask_limiter.util import get_remote_address

from ..auth_helpers import (
    get_owned_artist,
    load_current_user,
    may_manage_event_media,
    require_auth,
)
from ..extensions import db, limiter
from ..models import (
    AudioSample,
    Event,
    MediaUpload,
    UploadPurpose,
    UploadStatus,
    utcnow,
)
from ..services.r2_storage import (
    AUDIO_CONTENT_TYPES,
    IMAGE_CONTENT_TYPES,
    R2Storage,
)
from .response import error, ok
from .serializers import (
    serialize_artist,
    serialize_event,
    serialize_sample,
    serialize_user,
)
from .validators import get_json, parse_enum, parse_int, parse_string, parse_uuid

uploads_bp = Blueprint("uploads", __name__)

_KEY_PREFIX = {
    UploadPurpose.ARTIST_AUDIO: "artists/audio",
    UploadPurpose.ARTIST_PHOTO: "artists/photo",
    UploadPurpose.EVENT_POSTER: "events/poster",
    UploadPurpose.USER_AVATAR: "users/avatar",
}

_KIND = {
    UploadPurpose.ARTIST_AUDIO: "audio",
    UploadPurpose.ARTIST_PHOTO: "image",
    UploadPurpose.EVENT_POSTER: "image",
    UploadPurpose.USER_AVATAR: "image",
}


def _max_bytes(purpose: UploadPurpose) -> int:
    if purpose is UploadPurpose.ARTIST_AUDIO:
        return current_app.config["AUDIO_MAX_BYTES"]
    return current_app.config["IMAGE_MAX_BYTES"]


def _allowed_types(purpose: UploadPurpose) -> dict[str, str]:
    return AUDIO_CONTENT_TYPES if _KIND[purpose] == "audio" else IMAGE_CONTENT_TYPES


def _lock_artist(artist_id):
    """Take a row lock on an artist so a quota decision can be serialized.

    ``with_for_update`` is a no-op on SQLite (single-writer anyway) and a real
    ``SELECT ... FOR UPDATE`` on Postgres, which is where the race lives.
    """
    from ..models import Artist

    return db.session.get(Artist, artist_id, with_for_update=True)


def _audio_quota_used(artist_id) -> int:
    """Samples already held plus live tickets that could still become samples.

    Both halves matter: counting only the durable rows would let a caller mint
    a batch of tickets while sitting under the quota and redeem them all.
    """
    used = (
        db.session.query(db.func.count(AudioSample.id))
        .filter(AudioSample.artist_id == artist_id)
        .scalar()
        or 0
    )
    pending = (
        db.session.query(db.func.count(MediaUpload.id))
        .filter(
            MediaUpload.purpose == UploadPurpose.ARTIST_AUDIO,
            MediaUpload.target_id == artist_id,
            MediaUpload.status == UploadStatus.PENDING,
            MediaUpload.expires_at > utcnow(),
        )
        .scalar()
        or 0
    )
    return int(used) + int(pending)


def _authorize_target(purpose: UploadPurpose, target_id):
    """Confirm the caller may attach media to this target.

    Returns ``(target, None)`` or ``(None, response)``. A target that does not
    exist and one owned by somebody else both come back as 404, so the endpoint
    cannot be used to discover which ids are real.
    """
    not_found = error("NOT_FOUND", "Not found.", status=404)

    if purpose in (UploadPurpose.ARTIST_AUDIO, UploadPurpose.ARTIST_PHOTO):
        artist = get_owned_artist(target_id)
        if artist is None:
            return None, not_found
        return artist, None

    if purpose is UploadPurpose.USER_AVATAR:
        # The only target you may aim an avatar at is yourself. No admin
        # bypass either — an editor has no business wearing someone's face.
        user = load_current_user()
        if target_id != user.id:
            return None, not_found
        return user, None

    # EVENT_POSTER
    event = db.session.get(Event, target_id)
    if event is None:
        return None, not_found
    if not may_manage_event_media(event, load_current_user()):
        return None, not_found
    return event, None


def _upload_rate_key() -> str:
    """Rate-limit key for the upload routes.

    Keyed on the authenticated user rather than the source IP: an attacker
    with a handful of egress addresses multiplied a per-IP ceiling linearly,
    while an office behind one NAT had to share a single budget.
    """
    user = load_current_user()
    return f"user:{user.id}" if user is not None else f"ip:{get_remote_address()}"


@uploads_bp.post("/uploads")
@require_auth
@limiter.limit("60 per hour", key_func=_upload_rate_key)
def create_upload():
    body, err = get_json(request)
    if err:
        return err

    purpose, err = parse_enum(body.get("purpose"), UploadPurpose, "purpose")
    if err:
        return err

    target_id, err = parse_uuid(body.get("target_id"), "target_id")
    if err:
        return err

    target, err = _authorize_target(purpose, target_id)
    if err:
        return err

    content_type, err = parse_string(body.get("content_type"), "content_type", max_length=100)
    if err:
        return err
    content_type = content_type.split(";")[0].strip().lower()

    allowed = _allowed_types(purpose)
    if content_type not in allowed:
        return error(
            "UNSUPPORTED_TYPE",
            f"{content_type} is not an accepted format.",
            {"content_type": "unsupported", "accepted": sorted(allowed)},
            status=415,
        )

    cap = _max_bytes(purpose)
    size_bytes, err = parse_int(
        body.get("size_bytes"), "size_bytes", required=False, minimum=1, maximum=cap
    )
    if err:
        return err

    if purpose is UploadPurpose.ARTIST_AUDIO:
        # The whole quota decision happens under a lock on the artist row.
        # Count-then-check-then-insert is not atomic: under READ COMMITTED
        # (Postgres's default) concurrent requests all read the same
        # pre-attack count and all pass, so firing 30 requests at once against
        # a quota of 12 yielded 30 samples. Counting pending tickets does not
        # help when the count itself is what is being raced.
        if _lock_artist(target.id) is None:  # pragma: no cover - target existed above
            return error("NOT_FOUND", "Not found.", status=404)

        quota = current_app.config["AUDIO_SAMPLES_PER_ARTIST"]
        if _audio_quota_used(target.id) >= quota:
            return error(
                "LIMIT_REACHED",
                f"A band can hold {quota} sound samples. Remove one to add another.",
                {"samples": "quota"},
                status=409,
            )

    if not R2Storage.is_configured():
        current_app.logger.error("Upload requested but R2 is not configured.")
        return error(
            "STORAGE_UNAVAILABLE",
            "Uploads are temporarily unavailable. Please try again later.",
            status=503,
        )

    key = R2Storage.build_key(
        _KEY_PREFIX[purpose], target.id, content_type, kind=_KIND[purpose]
    )
    if key is None:  # pragma: no cover - unreachable while the allowlist holds
        return error("UNSUPPORTED_TYPE", "That format is not accepted.", status=415)

    # The signature must not outlive the ticket. Left to the shared
    # R2_SIGNED_URL_TTL_SECONDS it had a lifetime independent of
    # UPLOAD_TICKET_TTL_SECONDS, so an abandoned ticket's presigned URL stayed
    # usable — bytes could be pushed into the bucket after the row that tracks
    # them was already closed, leaving an object nothing would ever reclaim.
    ticket_ttl = current_app.config["UPLOAD_TICKET_TTL_SECONDS"]
    url = R2Storage.generate_presigned_put(key, content_type, expires_in=ticket_ttl)
    if url is None:
        return error(
            "STORAGE_UNAVAILABLE",
            "Uploads are temporarily unavailable. Please try again later.",
            status=503,
        )

    ticket = MediaUpload(
        user_id=load_current_user().id,
        purpose=purpose,
        target_id=target.id,
        object_key=key,
        content_type=content_type,
        max_bytes=cap,
        declared_size_bytes=size_bytes,
        expires_at=utcnow() + timedelta(seconds=ticket_ttl),
    )
    db.session.add(ticket)
    db.session.commit()

    return ok(
        {
            "upload_id": str(ticket.id),
            # The client PUTs the raw file body to `url` with `headers` set
            # exactly as given — notably Content-Type, which the signature
            # pins, so sending a different value fails the signature rather
            # than silently landing as the wrong type.
            "url": url,
            "key": key,
            "headers": {"Content-Type": content_type},
            "max_bytes": cap,
            "expires_at": ticket.expires_at.isoformat(),
        },
        status=201,
    )


@uploads_bp.post("/uploads/<uuid:upload_id>/complete")
@require_auth
@limiter.limit("60 per hour", key_func=_upload_rate_key)
def complete_upload(upload_id):
    user = load_current_user()
    ticket = db.session.get(MediaUpload, upload_id)

    # Scoped to the caller: one user cannot finish another's upload and attach
    # the object to their own record.
    if ticket is None or ticket.user_id != user.id:
        return error("NOT_FOUND", "That upload could not be found.", status=404)

    # Claim the ticket atomically. The old check-then-set left the whole attach
    # unguarded, so concurrent completions of one ticket all passed; only the
    # unique index on `audio_samples.object_key` stopped a duplicate row, and
    # the losers surfaced as opaque 500s. One-shot is now enforced by the
    # logic, not by accident of schema.
    claimed = (
        db.session.query(MediaUpload)
        .filter(
            MediaUpload.id == ticket.id,
            MediaUpload.status == UploadStatus.PENDING,
        )
        .update(
            {"status": UploadStatus.COMPLETED, "completed_at": utcnow()},
            synchronize_session=False,
        )
    )
    if claimed == 0:
        db.session.rollback()
        return error("ALREADY_COMPLETED", "That upload was already finished.", status=409)
    db.session.refresh(ticket)

    if not ticket.is_redeemable_now():
        ticket.status = UploadStatus.ABANDONED
        db.session.commit()
        return error("UPLOAD_EXPIRED", "That upload expired. Please start again.", status=410)

    # Re-check ownership at completion. The ticket may have been minted before
    # the band account changed hands, or the event may since have been deleted.
    target, err = _authorize_target(ticket.purpose, ticket.target_id)
    if err:
        return err

    head = R2Storage.head_object(ticket.object_key)
    if head is None:
        return error(
            "UPLOAD_NOT_FOUND",
            "We could not find that file in storage. Please upload it again.",
            status=409,
        )

    size_bytes = head.get("size_bytes") or 0
    if size_bytes <= 0 or size_bytes > ticket.max_bytes:
        # The only size gate there is — PUT carries no content-length-range
        # condition for R2 to enforce, so this HEAD check is it.
        ticket.status = UploadStatus.ABANDONED
        if R2Storage.delete_object(ticket.object_key):
            ticket.swept_at = utcnow()
        db.session.commit()
        return error("FILE_TOO_LARGE", "That file is larger than we accept.", status=413)

    stored_type = (head.get("content_type") or "").split(";")[0].strip().lower()
    if stored_type != ticket.content_type:
        # The signature pinned Content-Type; a mismatch means the object is not
        # the one we authorised.
        ticket.status = UploadStatus.ABANDONED
        if R2Storage.delete_object(ticket.object_key):
            ticket.swept_at = utcnow()
        db.session.commit()
        return error(
            "UNSUPPORTED_TYPE",
            "The uploaded file did not match the format you declared.",
            status=415,
        )

    body = request.get_json(silent=True) if request.is_json else {}
    body = body if isinstance(body, dict) else {}

    if ticket.purpose is UploadPurpose.ARTIST_AUDIO:
        result, err = _attach_audio_sample(ticket, target, body, size_bytes)
    elif ticket.purpose is UploadPurpose.ARTIST_PHOTO:
        result, err = _attach_artist_photo(ticket, target)
    elif ticket.purpose is UploadPurpose.USER_AVATAR:
        result, err = _attach_user_avatar(ticket, target)
    else:
        result, err = _attach_event_poster(ticket, target)

    if err:
        db.session.rollback()
        return err

    # Every image that lands is filed for the photo desk (post-moderation —
    # see services/photo_desk.py). Same transaction as the attach: an image
    # cannot go live unreviewed-and-unqueued.
    if _KIND[ticket.purpose] == "image":
        from ..services import photo_desk

        photo_desk.queue_image(db.session, ticket)

    # The status was already claimed atomically at the top of this handler.
    db.session.commit()
    return ok(result, status=201)


def _attach_audio_sample(ticket: MediaUpload, artist, body: dict, size_bytes: int):
    # Same lock as at issue time: without it, concurrent completions all read
    # the same count and all insert, and the quota is whatever the attacker's
    # concurrency happens to be.
    _lock_artist(artist.id)
    quota = current_app.config["AUDIO_SAMPLES_PER_ARTIST"]
    used = (
        db.session.query(db.func.count(AudioSample.id))
        .filter(AudioSample.artist_id == artist.id)
        .scalar()
        or 0
    )
    if used >= quota:
        ticket.status = UploadStatus.ABANDONED
        if R2Storage.delete_object(ticket.object_key):
            ticket.swept_at = utcnow()
        db.session.commit()
        return None, error(
            "LIMIT_REACHED",
            f"A band can hold {quota} sound samples.",
            status=409,
        )

    title, err = parse_string(body.get("title"), "title", required=False, max_length=140)
    if err:
        return None, err

    duration, err = parse_int(
        body.get("duration_seconds"), "duration_seconds", required=False,
        minimum=0, maximum=3 * 60 * 60,
    )
    if err:
        return None, err

    sample = AudioSample(
        artist_id=artist.id,
        title=title or "New sample",
        object_key=ticket.object_key,
        content_type=ticket.content_type,
        size_bytes=size_bytes,
        duration_seconds=duration,
        position=used,
    )
    db.session.add(sample)
    db.session.flush()
    return {"sample": serialize_sample(sample)}, None


def _attach_artist_photo(ticket: MediaUpload, artist):
    # Locked before the read-modify-write: two concurrent photo completions
    # both read the same `previous_key`, so the loser's object was written,
    # immediately overwritten, and then deleted by nobody — an orphan its own
    # COMPLETED ticket hid from the sweeper. A double-tap was enough.
    from ..models import Artist

    locked = db.session.get(Artist, artist.id, with_for_update=True)
    previous_key = locked.photo_key
    locked.photo_key = ticket.object_key
    db.session.flush()
    _displace(previous_key, ticket.object_key)
    return {"artist": serialize_artist(locked, detail=True)}, None


def _attach_user_avatar(ticket: MediaUpload, user):
    # Same locked read-modify-write as artist photos, same reason: two
    # concurrent completions must not orphan the loser's object.
    from ..models import User

    locked = db.session.get(User, user.id, with_for_update=True)
    previous_key = locked.avatar_key
    locked.avatar_key = ticket.object_key
    db.session.flush()
    _displace(previous_key, ticket.object_key)
    return {"user": serialize_user(locked, include_email=True)}, None


def _attach_event_poster(ticket: MediaUpload, event):
    locked = db.session.get(Event, event.id, with_for_update=True)
    previous_key = locked.poster_key
    locked.poster_key = ticket.object_key
    # A fresh upload is the band's own photo, not whatever attribution the
    # poster it replaces might have carried (see the field's docstring).
    locked.poster_credit = None
    db.session.flush()
    _displace(previous_key, ticket.object_key)
    return {"event": serialize_event(locked, detail=True)}, None


def _displace(previous_key: str | None, new_key: str) -> None:
    """Remove the object a replacement just displaced.

    Best-effort: a failure here leaves a stray object rather than failing the
    upload the user just made, and is logged so it can be reconciled.
    """
    if not previous_key or previous_key == new_key:
        return
    if not R2Storage.delete_object(previous_key):
        current_app.logger.warning(
            "Replaced media object could not be deleted (key=%s); it is now orphaned.",
            previous_key,
        )


@uploads_bp.delete("/uploads/<uuid:upload_id>")
@require_auth
@limiter.limit("120 per hour", key_func=_upload_rate_key)
def abandon_upload(upload_id):
    """Let a client give up on a ticket instead of waiting for the sweeper."""
    user = load_current_user()
    ticket = db.session.get(MediaUpload, upload_id)
    if ticket is None or ticket.user_id != user.id:
        return error("NOT_FOUND", "That upload could not be found.", status=404)
    if ticket.status is UploadStatus.PENDING:
        ticket.status = UploadStatus.ABANDONED
        db.session.commit()
        # Best-effort cleanup for the common case where the bytes did land.
        # `swept_at` is deliberately NOT set: deleting a key that does not
        # exist succeeds on S3-compatible storage, so a success here proves
        # nothing about whether the client has uploaded yet. The signature
        # stays live until the ticket expires, so the row must remain
        # sweepable — otherwise abandon-then-upload leaves an object no
        # automation would ever look at again.
        R2Storage.delete_object(ticket.object_key)
    return ok({"abandoned": True})
