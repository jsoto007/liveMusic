"""The URLs that go inside emails.

All of them are built from ``FRONTEND_URL`` — the address a reader actually
sees — never from the request's own Host header. Trusting the inbound Host is
how password-reset links end up pointing at an attacker's domain: send a
forgot-password request with ``Host: evil.example``, and the victim receives a
genuine token addressed somewhere else entirely.
"""

from urllib.parse import quote, urlencode

from flask import current_app

from ..utils.email_tokens import sign_unsubscribe


def site_url() -> str:
    """The canonical public origin, from configuration only."""
    from ..security import normalize_origin

    raw = (current_app.config.get("FRONTEND_URL") or "").split(",")[0]
    return normalize_origin(raw) or "http://localhost:5173"


def api_url() -> str:
    """Where links that must hit the API directly should point.

    The one-click unsubscribe has to be a real endpoint, not an SPA route:
    Gmail POSTs it without a browser, so nothing JavaScript-rendered would
    ever run.
    """
    from ..security import normalize_origin

    raw = normalize_origin(current_app.config.get("PUBLIC_API_URL") or "")
    return raw or site_url()


def verify_email_url(token: str) -> str:
    return f"{site_url()}/verify-email?{urlencode({'token': token})}"


def reset_password_url(token: str) -> str:
    return f"{site_url()}/reset-password?{urlencode({'token': token})}"


def unsubscribe_url(user) -> str:
    signature = sign_unsubscribe(user.id)
    return (
        f"{api_url()}/api/v1/email/unsubscribe"
        f"?{urlencode({'user': str(user.id), 'sig': signature})}"
    )


def event_url(event) -> str:
    return f"{site_url()}/shows/{quote(str(event.id))}"


def artist_url(artist) -> str:
    return f"{site_url()}/bands/{quote(artist.slug)}"


def email_preferences_url() -> str:
    return f"{site_url()}/account"
