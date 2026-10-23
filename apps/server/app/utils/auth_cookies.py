"""Where the browser session cookies are set and cleared.

Two routes end a session — logout, and closing the account — and both have to
clear exactly the cookies ``_issue_session`` set, at exactly the paths it set
them on. A `delete_cookie` whose path does not match the `set_cookie` is a
silent no-op, so these live in one place rather than being retyped per route.
"""

import secrets

from flask import current_app


def set_auth_cookies(response, raw_refresh: str) -> None:
    config = current_app.config
    secure = config["SESSION_COOKIE_SECURE"]
    max_age = int(config["REFRESH_TOKEN_TTL"].total_seconds())

    response.set_cookie(
        config["REFRESH_COOKIE_NAME"],
        raw_refresh,
        max_age=max_age,
        httponly=True,
        secure=secure,
        samesite="Lax",
        # Scoped to the refresh routes: the cookie is not attached to every
        # API call, so it cannot be replayed by a request that only needed a
        # bearer token.
        path="/api/v1/auth",
    )
    # Readable by JS on purpose — the client has to echo it back in a header
    # for the double-submit check to mean anything.
    response.set_cookie(
        config["CSRF_COOKIE_NAME"],
        secrets.token_urlsafe(32),
        max_age=max_age,
        httponly=False,
        secure=secure,
        samesite="Lax",
        path="/",
    )


def clear_auth_cookies(response) -> None:
    config = current_app.config
    response.delete_cookie(config["REFRESH_COOKIE_NAME"], path="/api/v1/auth")
    response.delete_cookie(config["CSRF_COOKIE_NAME"], path="/")
