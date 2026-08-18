"""Authentication and authorization decorators.

Every object-scoped guard re-derives ownership from the authenticated user.
Nothing here trusts an identifier that arrived in a URL, a body, or a header —
assume every one of them is attacker-chosen.
"""

import hmac
import uuid
from functools import wraps

from flask import current_app, g, request

from .extensions import db
from .models import Artist, User, UserRole, as_utc
from .routes.response import error
from .utils.tokens import TokenError, decode_access_token

_CACHE_KEY = "current_user"


def init_auth(app) -> None:
    """Clear the per-request identity cache at the start of every request.

    ``flask.g`` is bound to the *application* context, not the request. Any
    process that holds one app context open across several requests — the test
    client, a CLI command, a worker — would otherwise let the first caller's
    identity leak into every later request on that context. Authenticating as
    the previous caller is about as bad as a bug gets, so the cache is reset
    explicitly rather than relying on the context lifecycle.
    """

    @app.before_request
    def _reset_identity_cache():
        g.pop(_CACHE_KEY, None)


def _unauthorized(message: str = "Authentication required."):
    return error("UNAUTHORIZED", message, status=401)


def _bearer_token() -> str | None:
    header = request.headers.get("Authorization", "")
    if not header.startswith("Bearer "):
        return None
    token = header[7:].strip()
    return token or None


def load_current_user():
    """Resolve the caller from the Authorization header, or None.

    Cached on ``g`` for the request so a route with several guards does not pay
    for repeated decode + lookup.
    """
    if _CACHE_KEY in g:
        return g.current_user

    g.current_user = None
    token = _bearer_token()
    if not token:
        return None

    try:
        payload = decode_access_token(token)
    except TokenError:
        return None

    # `sub` is a string in the JWT but the column is a real UUID type, so it
    # has to be parsed rather than handed to the ORM as text. A malformed value
    # here is a forged token, not a lookup miss.
    try:
        user_id = uuid.UUID(str(payload["sub"]))
    except (KeyError, ValueError, TypeError, AttributeError):
        return None

    user = db.session.get(User, user_id)
    if user is None or not user.is_active:
        return None

    # An access token minted before the account's sessions were invalidated is
    # refused, so "sign out everywhere" and account lockout take effect
    # immediately rather than after the token's remaining lifetime.
    cutoff = as_utc(user.sessions_invalidated_at)
    if cutoff is not None:
        issued_at = payload.get("iat")
        if not isinstance(issued_at, (int, float)) or issued_at < cutoff.timestamp():
            return None

    g.current_user = user
    return user


def require_auth(func):
    @wraps(func)
    def wrapper(*args, **kwargs):
        user = load_current_user()
        if user is None:
            return _unauthorized()
        return func(*args, **kwargs)

    return wrapper


def require_csrf(func):
    """Double-submit CSRF check for cookie-authenticated requests.

    Only the refresh and logout routes authenticate from a cookie; everything
    else uses a bearer token and is not reachable cross-site in the first
    place. The comparison is constant-time — a naive ``==`` leaks the token a
    character at a time.
    """

    @wraps(func)
    def wrapper(*args, **kwargs):
        cookie_name = current_app.config["CSRF_COOKIE_NAME"]
        header_name = current_app.config["CSRF_HEADER_NAME"]
        cookie_value = request.cookies.get(cookie_name)
        header_value = request.headers.get(header_name)
        if not cookie_value or not header_value:
            return error("CSRF_REQUIRED", "Missing CSRF token.", status=403)
        if not hmac.compare_digest(cookie_value, header_value):
            return error("CSRF_INVALID", "Invalid CSRF token.", status=403)
        return func(*args, **kwargs)

    return wrapper


def require_admin(func):
    """Editors only. A non-admin gets the same 404 a wrong id would.

    403 would advertise that an admin surface exists at this path; these
    routes are not linked anywhere client-side, so to everyone but an editor
    they simply do not exist.
    """

    @wraps(func)
    def wrapper(*args, **kwargs):
        user = load_current_user()
        if user is None:
            return _unauthorized()
        if user.role is not UserRole.ADMIN:
            return error("NOT_FOUND", "Not found.", status=404)
        return func(*args, **kwargs)

    return wrapper


def get_owned_artist(artist_id):
    """Return the artist if the caller may act as it, else ``None``.

    Ownership is read off the artist row itself, so a caller cannot reach
    another band's shows or samples by guessing an id. Admins are allowed
    through for moderation.
    """
    user = load_current_user()
    if user is None or artist_id is None:
        return None
    artist = db.session.get(Artist, artist_id)
    if artist is None:
        return None
    if user.role is UserRole.ADMIN:
        return artist
    if artist.owner_user_id != user.id:
        return None
    return artist


def may_manage_event_media(event, user) -> bool:
    """Whether ``user`` may attach a poster to ``event``.

    One definition, deliberately. It is enforced in ``routes/uploads.py`` and
    it is also what decides whether the client is *shown* the control at all
    (``can_manage`` on the serialized detail). Two copies of this rule drift,
    and the drift surfaces as a button that 404s — or, worse, as a control
    hidden from someone who is in fact allowed.

    Note this is the upload rule, not the edit rule: ``_load_editable_event``
    additionally lets an admin through for moderation, which is a different
    question and stays where it is.
    """
    if event is None or user is None:
        return False
    if event.artist_id is not None and get_owned_artist(event.artist_id) is not None:
        return True
    return event.created_by_user_id == user.id


def require_artist_owner(artist_id_arg: str = "artist_id"):
    """Guard a route scoped to one artist, injecting it as ``g.artist``.

    A missing artist and an artist owned by somebody else both return 404 —
    deliberately identical, so the endpoint cannot be used to probe which
    artist ids exist.
    """

    def decorator(func):
        @wraps(func)
        def wrapper(*args, **kwargs):
            user = load_current_user()
            if user is None:
                return _unauthorized()
            artist = get_owned_artist(kwargs.get(artist_id_arg))
            if artist is None:
                return error("NOT_FOUND", "Not found.", status=404)
            g.artist = artist
            return func(*args, **kwargs)

        return wrapper

    return decorator
