"""Application factory.

Boot order matters: configuration is validated before anything binds to it,
logging is configured before the first log line, and the request-id middleware
is installed before any handler can emit one.
"""

import os
from pathlib import Path

from dotenv import find_dotenv, load_dotenv
from flask import Flask, request
from werkzeug.exceptions import HTTPException
from werkzeug.middleware.proxy_fix import ProxyFix

from .auth_helpers import init_auth
from .extensions import cors, db, limiter, migrate
from .logging_config import configure_logging
from .middleware.request_id import init_request_id
from .routes import register_api_blueprints
from .routes.response import error
from .security import build_csp_policy, init_security, parse_origins, should_force_https


def create_app(config_object=None) -> Flask:
    load_dotenv(find_dotenv())

    from .config import Config

    config_object = config_object or Config

    app = Flask(__name__)
    app.config.from_object(config_object)
    configure_logging(app)

    # Validate AFTER config is loaded so the error message can reference the
    # resolved values, but BEFORE any extension binds to a bad configuration.
    if hasattr(config_object, "validate"):
        config_object.validate()

    # Behind a platform load balancer, the real scheme/host arrive in
    # X-Forwarded-*. Without this, url_for and the HTTPS redirect both see
    # plain http and loop.
    app.wsgi_app = ProxyFix(app.wsgi_app, x_for=1, x_proto=1, x_host=1, x_prefix=1)

    init_request_id(app)
    init_auth(app)

    db.init_app(app)
    migrate.init_app(app, db, directory=str(Path(__file__).resolve().parent.parent / "migrations"))

    origins = parse_origins(app)
    cors.init_app(
        app,
        resources={r"/api/.*": {"origins": origins}},
        supports_credentials=True,
        allow_headers=["Content-Type", "Authorization", app.config["CSRF_HEADER_NAME"]],
    )
    app.logger.info("CORS allowlist: %s", ", ".join(origins) or "(empty)")

    app.config.setdefault("RATELIMIT_STORAGE_URI", "memory://")
    limiter.init_app(app)
    if getattr(limiter, "_is_noop_limiter", False) and not app.config.get("TESTING"):
        raise RuntimeError(
            "flask-limiter is not installed; refusing to start a non-testing "
            "app with an unprotected rate-limit surface."
        )

    init_security(app)

    from flask_talisman import Talisman

    Talisman(
        app,
        content_security_policy=build_csp_policy(app),
        force_https=should_force_https(app),
        session_cookie_secure=app.config["SESSION_COOKIE_SECURE"],
        strict_transport_security=True,
        strict_transport_security_max_age=31_536_000,
    )

    from . import models  # noqa: F401  (registers mappers before migrate runs)

    @app.get("/health")
    @limiter.exempt
    def health():
        # Polled continuously by the platform from a single internal IP, so it
        # has to be exempt from the default per-IP limit or the health check
        # itself trips a 429 and the instance is marked unhealthy.
        return {"status": "ok"}

    _warn_if_media_is_unconfigured(app)

    register_api_blueprints(app)
    _register_error_handlers(app)

    from .cli import register_cli

    register_cli(app)

    return app


def _register_error_handlers(app: Flask) -> None:
    """Every error leaves through the same envelope, including the ones Flask
    raises before a route is reached (404, 405, 415)."""

    friendly = {
        400: "Invalid request.",
        401: "Authentication required.",
        403: "Access denied.",
        404: "Not found.",
        405: "Method not allowed.",
        409: "Request conflict.",
        413: "The uploaded file is too large.",
        415: "Unsupported media type.",
        422: "Invalid request.",
        429: "Too many requests. Please slow down.",
    }

    @app.errorhandler(HTTPException)
    def _http_exception(exc: HTTPException):
        status = exc.code or 400
        return error("HTTP_ERROR", friendly.get(status, "Request failed."), status=status)

    @app.errorhandler(Exception)
    def _unexpected(exc: Exception):  # noqa: ARG001 - logged via exc_info
        app.logger.exception("Unhandled exception on %s %s", request.method, request.path)
        # Deliberately opaque: an exception message can carry SQL fragments,
        # file paths or column values. The request id in the response header is
        # what ties a user report back to the log line that has the detail.
        return error("INTERNAL_ERROR", "Something went wrong. Please try again.", status=500)


__all__ = ["create_app", "db"]

# Kept out of create_app so `flask --app app run` still works without it.
os.environ.setdefault("PYTHONUNBUFFERED", "1")


def _warn_if_media_is_unconfigured(app) -> None:
    """Say so at boot when R2 is missing, loudly, once.

    An unconfigured bucket does not stop the app serving — that is deliberate,
    listings are the product and pictures are not worth refusing traffic over.
    But it is silent from the outside: every upload answers 503 and every
    ``photo_url`` and ``poster_url`` serialises as ``null``, which looks to
    everyone involved like a broken button rather than an unset variable. The
    only trace was a warning buried in whichever request happened to try first.

    This puts it in the startup log, where a deploy is actually read, and names
    the variables rather than the symptom.
    """
    if app.config.get("TESTING"):
        return
    from .services.r2_storage import R2Storage

    with app.app_context():
        if R2Storage.is_configured():
            return

    missing = [
        name
        for name in ("R2_ACCESS_KEY_ID", "R2_SECRET_ACCESS_KEY", "R2_BUCKET")
        if not app.config.get(name)
    ]
    if not (app.config.get("R2_ENDPOINT_URL") or app.config.get("R2_ACCOUNT_ID")):
        missing.append("R2_ACCOUNT_ID (or R2_ENDPOINT_URL)")

    app.logger.warning(
        "Media storage is NOT configured: %s unset. Band photos and show "
        "posters cannot be uploaded — every upload will answer 503 "
        "STORAGE_UNAVAILABLE — and existing images will serialise as null. "
        "Everything else runs normally. See README 'How media works'.",
        ", ".join(missing) or "R2 credentials",
    )

