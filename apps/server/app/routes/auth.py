"""Registration, login, refresh, logout.

The access token is returned in the body (clients keep it in memory). The
refresh token only ever travels as an httpOnly cookie for browsers; native
clients ask for it in the body with ``?client=native`` and put it in their
secure store.
"""


from flask import Blueprint, current_app, request

from ..auth_helpers import load_current_user, require_auth, require_csrf
from ..extensions import db, limiter
from ..models import User, UserRole, utcnow
from ..services.notifications import send_verification_email
from ..utils.auth_cookies import clear_auth_cookies, set_auth_cookies
from ..utils.handles import handle_base, unique_handle
from ..utils.passwords import (
    PasswordPolicyError,
    hash_password,
    validate_password,
    verify_password,
    waste_a_hash,
)
from ..utils.tokens import (
    TokenError,
    create_access_token,
    hash_refresh_token,
    issue_refresh_token,
    revoke_family,
    rotate_refresh_token,
)
from .response import error, ok
from .serializers import serialize_user
from .validators import get_json, parse_string

auth_bp = Blueprint("auth", __name__)

# Repeated failures lock the account for a cooling-off period. The threshold is
# high enough not to punish a fat-fingered user and low enough that online
# guessing is hopeless against a 12-character minimum.
#
# KNOWN TRADE-OFF: because the lock lives on the user row, anyone who knows an
# address can trip it and keep that account locked. That is accepted here as
# the lesser evil against credential stuffing, and it is why the locked
# response is byte-identical to a wrong password (below) — an attacker cannot
# even confirm the lock took effect, or that the address is registered. The
# real defence against sustained guessing is the per-IP limit on this route
# plus bcrypt's cost. If lockout abuse is ever observed, the fix is to scope
# the counter to (user, source) rather than to lengthen the window.
MAX_FAILED_LOGINS = 8
LOCKOUT_MINUTES = 15


def _normalize_email(raw: str) -> str:
    return raw.strip().lower()


def _valid_email(candidate: str) -> bool:
    # Deliberately permissive: the authoritative check is a verification mail.
    # This only rejects input that cannot be an address at all.
    if len(candidate) > 255 or candidate.count("@") != 1:
        return False
    local, _, domain = candidate.partition("@")
    if not local or not domain or "." not in domain:
        return False
    return not any(ch.isspace() for ch in candidate)


def _wants_native_tokens() -> bool:
    """Whether to return the refresh token in the body rather than a cookie.

    Native clients cannot use cookies, so they get it in the body. Browsers
    must NOT take this path — a token in a JS-readable response is exactly what
    httpOnly exists to prevent.

    SECURITY: this asks ``?client=native`` **only when no refresh cookie is
    present**. Trusting the query string alone let any same-origin script turn
    an httpOnly cookie into a readable 30-day credential simply by appending
    ``?client=native`` to a refresh call — which is to say, httpOnly bought
    nothing against XSS. A request that arrived with our cookie is by
    definition a browser, whatever it claims in the URL.
    """
    if request.cookies.get(current_app.config["REFRESH_COOKIE_NAME"]):
        return False
    return request.args.get("client") == "native"


def _issue_session(user, response_payload: dict, status: int = 200):
    """Mint a token pair and attach it to the response the right way per client."""
    raw_refresh, _row = issue_refresh_token(
        db.session, user, user_agent=request.headers.get("User-Agent")
    )
    db.session.commit()

    access_token = create_access_token(user)
    payload = {**response_payload, "access_token": access_token}

    if _wants_native_tokens():
        payload["refresh_token"] = raw_refresh
        return ok(payload, status=status)

    response = ok(payload, status=status)
    set_auth_cookies(response, raw_refresh)
    return response


def _incoming_refresh_token(body: dict | None) -> str | None:
    cookie = request.cookies.get(current_app.config["REFRESH_COOKIE_NAME"])
    if cookie:
        return cookie
    if body and isinstance(body.get("refresh_token"), str):
        return body["refresh_token"].strip() or None
    return None


@auth_bp.post("/auth/register")
@limiter.limit("10 per hour")
def register():
    body, err = get_json(request)
    if err:
        return err

    raw_email, err = parse_string(body.get("email"), "email", max_length=255)
    if err:
        return err
    email = _normalize_email(raw_email)
    if not _valid_email(email):
        return error("VALIDATION_ERROR", "Enter a valid email address.", {"email": "invalid"})

    display_name, err = parse_string(body.get("display_name"), "display_name", max_length=80)
    if err:
        return err

    raw_password = body.get("password")
    try:
        validate_password(raw_password if isinstance(raw_password, str) else "", email=email)
    except PasswordPolicyError as exc:
        return error("VALIDATION_ERROR", str(exc), {"password": "weak"})

    home_city, err = parse_string(
        body.get("home_city"), "home_city", required=False, max_length=120
    )
    if err:
        return err

    if db.session.query(User.id).filter(User.email == email).first() is not None:
        # Registration cannot be silent about a duplicate (the user needs to
        # know to sign in instead), so it is rate-limited hard above rather
        # than made ambiguous here.
        return error(
            "EMAIL_IN_USE",
            "An account already exists for that email. Try signing in.",
            {"email": "taken"},
            status=409,
        )

    user = User(
        email=email,
        password_hash=hash_password(raw_password),
        display_name=display_name,
        # Auto-issued from the display name; the owner can change it later
        # from their account page. Never taken from the registration body —
        # one field fewer to squat on at the most-abused endpoint we have.
        handle=unique_handle(db.session, handle_base(display_name)),
        home_city=home_city,
        role=UserRole.LISTENER,
    )
    db.session.add(user)
    db.session.commit()

    # Best-effort: an account whose confirmation mail bounced is still an
    # account, and `send_verification_email` never raises.
    send_verification_email(user)

    return _issue_session(user, {"user": serialize_user(user, include_email=True)}, status=201)


@auth_bp.post("/auth/login")
@limiter.limit("20 per hour")
def login():
    body, err = get_json(request)
    if err:
        return err

    raw_email = body.get("email")
    raw_password = body.get("password")
    if not isinstance(raw_email, str) or not isinstance(raw_password, str):
        return error("VALIDATION_ERROR", "Email and password are required.", {"email": "required"})

    email = _normalize_email(raw_email)
    user = db.session.query(User).filter(User.email == email).one_or_none()

    # One response for every failure mode, and equal work done in each, so
    # neither the body nor the timing tells an attacker whether the account
    # exists.
    invalid = error(
        "INVALID_CREDENTIALS", "That email and password do not match.", status=401
    )

    if user is None:
        waste_a_hash()
        return invalid
    if user.is_locked:
        # Deliberately the SAME response as a wrong password, with the same
        # bcrypt cost paid first. A distinct 423 was both an account-existence
        # oracle (nine wrong guesses tell you whether an address is registered)
        # and a timing outlier, because the branch returned before any hashing.
        # The lock is recorded in the log, where it belongs.
        waste_a_hash()
        current_app.logger.info("Login attempt against a locked account.")
        return invalid
    if not verify_password(raw_password, user.password_hash):
        user.failed_login_count = (user.failed_login_count or 0) + 1
        if user.failed_login_count >= MAX_FAILED_LOGINS:
            from datetime import timedelta

            locked_at = utcnow()
            user.locked_until = locked_at + timedelta(minutes=LOCKOUT_MINUTES)
            user.failed_login_count = 0
            # Locking the account must also cut any session already open on it.
            user.sessions_invalidated_at = locked_at
        db.session.commit()
        return invalid
    if not user.is_active:
        return invalid

    user.failed_login_count = 0
    user.locked_until = None
    return _issue_session(user, {"user": serialize_user(user, include_email=True)})


@auth_bp.post("/auth/refresh")
@limiter.limit("60 per hour")
@require_csrf
def refresh():
    body = request.get_json(silent=True) if request.is_json else None
    raw_token = _incoming_refresh_token(body if isinstance(body, dict) else None)

    try:
        user, new_raw = rotate_refresh_token(
            db.session, raw_token, user_agent=request.headers.get("User-Agent")
        )
    except TokenError as exc:
        db.session.rollback()
        response = error("SESSION_EXPIRED", "Please sign in again.", status=401)
        if str(exc) != "missing":
            clear_auth_cookies(response)
        return response

    db.session.commit()

    payload = {
        "user": serialize_user(user, include_email=True),
        "access_token": create_access_token(user),
    }
    if _wants_native_tokens():
        payload["refresh_token"] = new_raw
        return ok(payload)

    response = ok(payload)
    set_auth_cookies(response, new_raw)
    return response


@auth_bp.post("/auth/logout")
@require_csrf
def logout():
    body = request.get_json(silent=True) if request.is_json else None
    raw_token = _incoming_refresh_token(body if isinstance(body, dict) else None)

    if raw_token:
        from ..models import RefreshToken

        row = (
            db.session.query(RefreshToken)
            .filter(RefreshToken.token_hash == hash_refresh_token(raw_token))
            .one_or_none()
        )
        if row is not None:
            # Revoke the whole family, not just this token: signing out should
            # end the session on that device, including any token already
            # rotated ahead of this request.
            revoke_family(db.session, row.family_id)
            db.session.commit()

    response = ok({"signed_out": True})
    clear_auth_cookies(response)
    return response


@auth_bp.post("/auth/logout-all")
@require_auth
def logout_all():
    """Revoke every session for the caller — the 'sign out everywhere' control."""
    from ..models import RefreshToken

    user = load_current_user()
    rows = (
        db.session.query(RefreshToken)
        .filter(RefreshToken.user_id == user.id, RefreshToken.revoked_at.is_(None))
        .all()
    )
    now = utcnow()
    for row in rows:
        row.revoked_at = now
    # Refresh tokens alone are not enough: an access token already in an
    # attacker's hands stays valid for its full lifetime unless we stamp this.
    user.sessions_invalidated_at = now
    db.session.commit()

    response = ok({"sessions_revoked": len(rows)})
    clear_auth_cookies(response)
    return response
