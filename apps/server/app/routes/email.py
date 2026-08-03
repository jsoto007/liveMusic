"""Email verification, password reset, preferences and unsubscribe.

The forgot-password and resend-verification endpoints answer identically
whether or not the address exists. An endpoint that says "no such account" is
a free membership oracle for anyone with a list of addresses, and it is the
single most common way these flows leak.
"""

import time
import uuid

from flask import Blueprint, current_app, request

from ..auth_helpers import load_current_user, require_auth
from ..extensions import db, limiter
from ..models import (
    EmailTokenPurpose,
    RefreshToken,
    User,
    utcnow,
)
from ..services.notifications import send_password_reset_email, send_verification_email
from ..utils.email_tokens import redeem_token, verify_unsubscribe
from ..utils.passwords import PasswordPolicyError, hash_password, validate_password
from .response import error, ok
from .serializers import serialize_user
from .validators import get_json, parse_bool, parse_string

email_bp = Blueprint("email", __name__)

#: The same body for every outcome of a "send me a link" request.
_ACCEPTED = {
    "accepted": True,
    "message": "If that address has an account, a link is on its way.",
}

#: Wall-clock floor for the endpoints above, in seconds.
#
# The bodies and statuses already matched, but only the *hit* branch did any
# work: issue a token, two commits, two template renders, and a synchronous
# SMTP handshake. The miss branch returned immediately. Measured with a
# realistic transport that is 132ms versus 0.5ms — a membership oracle
# readable in a single request, no statistics required. `login` already solved
# this by burning a dummy bcrypt; these pad to a fixed budget instead, because
# the work being hidden is I/O rather than CPU.
def _leveled(started_at: float):
    """Hold the response until the fixed budget has elapsed."""
    floor = current_app.config.get("EMAIL_RESPONSE_FLOOR_SECONDS", 0.5)
    remaining = floor - (time.monotonic() - started_at)
    if remaining > 0:
        time.sleep(remaining)
    return ok(_ACCEPTED)


@email_bp.post("/auth/verify-email/resend")
@limiter.limit("5 per hour")
def resend_verification():
    """Ask for another confirmation link.

    Unauthenticated by design — someone who cannot receive the first link
    cannot necessarily sign in to ask for a second.
    """
    body, err = get_json(request)
    if err:
        return err

    raw_email, err = parse_string(body.get("email"), "email", max_length=255)
    if err:
        return err

    started_at = time.monotonic()
    user = (
        db.session.query(User)
        .filter(User.email == raw_email.strip().lower())
        .one_or_none()
    )
    # Only actually send for an unverified, active account — but neither the
    # response nor its timing reveals which of those conditions failed.
    if user is not None and user.is_active and user.email_verified_at is None:
        send_verification_email(user)

    return _leveled(started_at)


@email_bp.post("/auth/verify-email")
@limiter.limit("20 per hour")
def verify_email():
    body, err = get_json(request)
    if err:
        return err

    token, err = parse_string(body.get("token"), "token", max_length=200)
    if err:
        return err

    user = redeem_token(db.session, token, EmailTokenPurpose.VERIFY_EMAIL)
    if user is None:
        db.session.rollback()
        return error(
            "INVALID_TOKEN",
            "That link is no longer valid. Ask for a new one.",
            status=400,
        )

    if user.email_verified_at is None:
        user.email_verified_at = utcnow()
    db.session.commit()

    return ok({"user": serialize_user(user, include_email=True), "verified": True})


@email_bp.post("/auth/forgot-password")
@limiter.limit("5 per hour")
def forgot_password():
    body, err = get_json(request)
    if err:
        return err

    raw_email, err = parse_string(body.get("email"), "email", max_length=255)
    if err:
        return err

    started_at = time.monotonic()
    user = (
        db.session.query(User)
        .filter(User.email == raw_email.strip().lower())
        .one_or_none()
    )
    if user is not None and user.is_active:
        send_password_reset_email(user)

    # Identical body, status AND timing whether or not the account exists.
    return _leveled(started_at)


@email_bp.post("/auth/reset-password")
@limiter.limit("10 per hour")
def reset_password():
    body, err = get_json(request)
    if err:
        return err

    token, err = parse_string(body.get("token"), "token", max_length=200)
    if err:
        return err

    raw_password = body.get("password")
    try:
        validate_password(raw_password if isinstance(raw_password, str) else "")
    except PasswordPolicyError as exc:
        return error("VALIDATION_ERROR", str(exc), {"password": "weak"})

    user = redeem_token(db.session, token, EmailTokenPurpose.RESET_PASSWORD)
    if user is None:
        db.session.rollback()
        return error(
            "INVALID_TOKEN",
            "That link is no longer valid. Ask for a new one.",
            status=400,
        )

    # Re-validate against the address now that we know who it is — the policy
    # forbids a password containing the account's own email.
    try:
        validate_password(raw_password, email=user.email)
    except PasswordPolicyError as exc:
        db.session.rollback()
        return error("VALIDATION_ERROR", str(exc), {"password": "weak"})

    now = utcnow()
    user.password_hash = hash_password(raw_password)
    user.failed_login_count = 0
    user.locked_until = None
    # A password reset is a security event: every existing session ends. If the
    # reset was prompted by a compromise, leaving the attacker's session alive
    # would defeat the entire exercise.
    user.sessions_invalidated_at = now
    db.session.query(RefreshToken).filter(
        RefreshToken.user_id == user.id, RefreshToken.revoked_at.is_(None)
    ).update({"revoked_at": now}, synchronize_session=False)

    # Reaching a mailbox proves control of the address.
    if user.email_verified_at is None:
        user.email_verified_at = now

    db.session.commit()
    current_app.logger.info("Password reset completed; all sessions revoked.")

    return ok({"reset": True})


# ── Preferences ────────────────────────────────────────────────────────────


@email_bp.get("/me/email-preferences")
@require_auth
def get_preferences():
    user = load_current_user()
    return ok({"preferences": _serialize_preferences(user)})


@email_bp.patch("/me/email-preferences")
@require_auth
def update_preferences():
    user = load_current_user()
    body, err = get_json(request)
    if err:
        return err

    for field in ("notify_new_shows", "notify_show_reminders"):
        if field in body:
            value, err = parse_bool(body.get(field), field)
            if err:
                return err
            setattr(user, field, value)
            # Turning any category back on lifts the master switch — otherwise
            # the toggle would appear to work and silently change nothing.
            if value:
                user.unsubscribed_all_at = None

    if "unsubscribed_all" in body:
        value, err = parse_bool(body.get("unsubscribed_all"), "unsubscribed_all")
        if err:
            return err
        user.unsubscribed_all_at = utcnow() if value else None

    db.session.commit()
    return ok({"preferences": _serialize_preferences(user)})


def _serialize_preferences(user) -> dict:
    return {
        "notify_new_shows": user.notify_new_shows,
        "notify_show_reminders": user.notify_show_reminders,
        "unsubscribed_all": user.unsubscribed_all_at is not None,
    }


# ── One-click unsubscribe ──────────────────────────────────────────────────


@email_bp.route("/email/unsubscribe", methods=["GET", "POST"])
@limiter.limit("60 per hour")
def unsubscribe():
    """The link at the foot of every optional email.

    Authenticated by an HMAC over the user id, not by a session. Someone
    unsubscribing is very often not signed in, and making them sign in first
    is exactly the dark pattern the one-click standard exists to prevent.

    **Only POST changes anything.** GET renders a one-button confirmation.
    That is not pedantry about HTTP verbs: Microsoft Defender Safe Links,
    Proofpoint, Barracuda, Gmail's scanner and iOS Mail's link preview all
    fetch URLs found in message bodies. With GET mutating, the recipient's own
    mail security silently unsubscribed them from everything, with no click
    and no signal. RFC 8058 requires POST for exactly this reason — and Flask
    routes HEAD alongside GET, so a bare HEAD did it too.
    """
    user_id = (request.args.get("user") or "").strip()
    signature = (request.args.get("sig") or "").strip()

    if not verify_unsubscribe(user_id, signature):
        # Deliberately vague: this must not confirm whether an id is real.
        return _unsubscribe_page("That unsubscribe link is not valid.", state="invalid")

    if request.method != "POST":
        return _unsubscribe_page(
            "Confirm that you want to stop receiving notices about new shows "
            "and reminders.",
            state="confirm",
            user_id=user_id,
            signature=signature,
        )

    # The id arrives as text but the column is a real UUID type, so it has to
    # be parsed rather than handed to the ORM as a string.
    try:
        parsed_id = uuid.UUID(user_id)
    except (ValueError, TypeError):
        return _unsubscribe_page("That unsubscribe link is not valid.", state="invalid")

    user = db.session.get(User, parsed_id)
    if user is not None:
        user.unsubscribed_all_at = utcnow()
        db.session.commit()

    # The same page either way — a valid signature for a deleted account should
    # not read differently from a live one.
    return _unsubscribe_page(
        "You're unsubscribed. You won't get notices about new shows or reminders.",
        state="done",
    )


def _unsubscribe_page(
    message: str,
    *,
    state: str,
    user_id: str | None = None,
    signature: str | None = None,
):
    """A tiny self-contained page.

    Deliberately not an SPA route: a one-click POST from a mail provider runs
    no JavaScript, so both the form and the confirmation have to be in the
    response body itself.
    """
    from flask import render_template

    html = render_template(
        "emails/unsubscribed.html",
        message=message,
        state=state,
        user_id=user_id,
        signature=signature,
        site_url=(current_app.config.get("FRONTEND_URL") or "").split(",")[0].strip(),
    )
    status = 400 if state == "invalid" else 200
    return html, status, {"Content-Type": "text/html; charset=utf-8"}
