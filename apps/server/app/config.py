"""Configuration, read from the environment and validated at boot.

Anything security-relevant fails **closed**: a missing secret raises in a real
environment rather than falling back to a development default that would ship
to production unnoticed. Tests set ``TESTING`` and get deterministic values.
"""

import os
from datetime import timedelta


def _truthy(name: str, default: bool = False) -> bool:
    raw = os.getenv(name)
    if raw is None:
        return default
    return raw.strip().lower() in {"true", "1", "yes", "on"}


def _int(name: str, default: int) -> int:
    raw = os.getenv(name)
    if raw is None or not raw.strip():
        return default
    try:
        return int(raw)
    except ValueError as exc:
        raise RuntimeError(f"{name} must be an integer, got {raw!r}") from exc


def _normalize_database_url(raw: str) -> str:
    # Managed Postgres providers hand out `postgres://`, which SQLAlchemy 2
    # no longer recognises as a dialect.
    if raw.startswith("postgres://"):
        return raw.replace("postgres://", "postgresql+psycopg2://", 1)
    return raw


class Config:
    TESTING = _truthy("TESTING")
    ENV = os.getenv("FLASK_ENV", "production")
    IS_DEVELOPMENT = ENV in {"development", "dev", "local"}

    # The dev fallbacks are gated on IS_DEVELOPMENT alone, NOT on TESTING.
    # `TESTING` is an independent env var: `FLASK_ENV=production TESTING=true`
    # used to unlock every fallback here AND skip validate() entirely, booting
    # a production process that signs tokens with a secret committed to this
    # file — forgeable by anyone with the repo. Tests supply their own values
    # through TestConfig, so these fallbacks were never needed for them.
    SECRET_KEY = os.getenv("SECRET_KEY") or ("dev-only-secret" if IS_DEVELOPMENT else "")

    # Signing key for access/refresh JWTs. Deliberately separate from
    # SECRET_KEY so that leaking one does not hand over the other.
    JWT_SECRET = os.getenv("JWT_SECRET") or (
        "dev-only-jwt-secret-that-is-long-enough" if IS_DEVELOPMENT else ""
    )
    JWT_ALGORITHM = "HS256"
    ACCESS_TOKEN_TTL = timedelta(seconds=_int("ACCESS_TOKEN_TTL_SECONDS", 900))
    REFRESH_TOKEN_TTL = timedelta(seconds=_int("REFRESH_TOKEN_TTL_SECONDS", 30 * 24 * 3600))

    SQLALCHEMY_DATABASE_URI = _normalize_database_url(
        os.getenv("DATABASE_URL") or "sqlite:///live_msc.sqlite3"
    )
    SQLALCHEMY_TRACK_MODIFICATIONS = False
    SQLALCHEMY_ENGINE_OPTIONS = {"pool_pre_ping": True}

    FRONTEND_URL = os.getenv("FRONTEND_URL", "")
    CORS_ORIGINS = os.getenv("CORS_ORIGINS", "")

    SESSION_COOKIE_SECURE = not (TESTING or IS_DEVELOPMENT)
    SESSION_COOKIE_HTTPONLY = True
    SESSION_COOKIE_SAMESITE = "Lax"
    # Cookie names — the refresh token is httpOnly; the CSRF token deliberately
    # is NOT, because the client has to read it to echo it back in a header.
    REFRESH_COOKIE_NAME = "live_msc_refresh"
    CSRF_COOKIE_NAME = "csrf_token"
    CSRF_HEADER_NAME = "X-CSRF-Token"

    RATELIMIT_STORAGE_URI = os.getenv("RATELIMIT_STORAGE_URI", "memory://")
    RATELIMIT_DEFAULT = os.getenv("RATELIMIT_DEFAULT", "300 per hour")
    RATELIMIT_HEADERS_ENABLED = True

    # ── R2 ────────────────────────────────────────────────────────────────
    R2_ACCOUNT_ID = os.getenv("R2_ACCOUNT_ID", "")
    R2_ENDPOINT_URL = os.getenv("R2_ENDPOINT_URL", "")
    R2_ACCESS_KEY_ID = os.getenv("R2_ACCESS_KEY_ID", "")
    R2_SECRET_ACCESS_KEY = os.getenv("R2_SECRET_ACCESS_KEY", "")
    R2_BUCKET = os.getenv("R2_BUCKET", "")
    R2_REGION = os.getenv("R2_REGION", "auto")
    R2_SIGNED_URL_TTL_SECONDS = _int("R2_SIGNED_URL_TTL_SECONDS", 900)
    R2_PUBLIC_BASE_URL = os.getenv("R2_PUBLIC_BASE_URL", "")

    # Upload policy. Enforced twice: as a presigned-POST condition (so R2
    # rejects an oversized body at the edge) and again on completion via HEAD.
    AUDIO_MAX_BYTES = _int("AUDIO_MAX_BYTES", 20 * 1024 * 1024)
    IMAGE_MAX_BYTES = _int("IMAGE_MAX_BYTES", 8 * 1024 * 1024)
    AUDIO_SAMPLES_PER_ARTIST = _int("AUDIO_SAMPLES_PER_ARTIST", 12)
    UPLOAD_TICKET_TTL_SECONDS = _int("UPLOAD_TICKET_TTL_SECONDS", 900)

    # ── Email ─────────────────────────────────────────────────────────────
    # Two transports; whichever is configured wins, Resend first. With neither
    # set the app logs what it would have sent and carries on, so development
    # needs no mail credentials at all.
    MAIL_FROM_ADDRESS = os.getenv("MAIL_FROM_ADDRESS", "")
    MAIL_FROM_NAME = os.getenv("MAIL_FROM_NAME", "Live Msc")
    RESEND_API_KEY = os.getenv("RESEND_API_KEY", "")
    SMTP_HOST = os.getenv("SMTP_HOST", "")
    SMTP_PORT = _int("SMTP_PORT", 587)
    SMTP_USERNAME = os.getenv("SMTP_USERNAME", "")
    SMTP_PASSWORD = os.getenv("SMTP_PASSWORD", "")
    SMTP_TIMEOUT_SECONDS = _int("SMTP_TIMEOUT_SECONDS", 15)
    EMAIL_HTTP_TIMEOUT_SECONDS = _int("EMAIL_HTTP_TIMEOUT_SECONDS", 10)
    # Where links that must hit the API directly point — the one-click
    # unsubscribe in particular, which a mail provider POSTs with no browser.
    # Defaults to FRONTEND_URL, which is correct when both are same-origin.
    PUBLIC_API_URL = os.getenv("PUBLIC_API_URL", "")
    # Cap on messages to ONE address per hour, whoever asked for them. Every
    # route limit is keyed by source IP, so without this a rotating-IP caller
    # had unbounded volume at a single inbox — an inbox flood, and a
    # deliverability problem for our sending domain.
    EMAIL_PER_RECIPIENT_HOURLY = _int("EMAIL_PER_RECIPIENT_HOURLY", 6)
    # Wall-clock floor for the "send me a link" endpoints, so a hit and a miss
    # take the same time and cannot be told apart. Set to 0 only in tests.
    EMAIL_RESPONSE_FLOOR_SECONDS = float(os.getenv("EMAIL_RESPONSE_FLOOR_SECONDS", "0.5"))

    # ── LocationIQ ────────────────────────────────────────────────────────
    # Server-side only. The key is never sent to a client — every lookup is
    # proxied, so a leaked key cannot be spent by someone reading our JS.
    LOCATIONIQ_API_KEY = os.getenv("LOCATIONIQ_API_KEY", "")
    LOCATIONIQ_BASE_URL = os.getenv("LOCATIONIQ_BASE_URL", "https://us1.locationiq.com/v1")
    LOCATIONIQ_TIMEOUT_SECONDS = _int("LOCATIONIQ_TIMEOUT_SECONDS", 6)
    # How long an identical lookup is served from memory. LocationIQ's free
    # tier is 5,000/day and 2/second, and an autocomplete field will burn that
    # in an afternoon without a cache.
    GEOCODE_CACHE_SECONDS = _int("GEOCODE_CACHE_SECONDS", 3600)
    GEOCODE_CACHE_MAX_ENTRIES = _int("GEOCODE_CACHE_MAX_ENTRIES", 2000)
    # Upstream calls allowed per process per day. The free tier is 5,000/day;
    # divide by your worker count. 0 disables the ceiling.
    LOCATIONIQ_DAILY_BUDGET = _int("LOCATIONIQ_DAILY_BUDGET", 2000)

    SENTRY_DSN = os.getenv("SENTRY_DSN", "")
    LOG_LEVEL = os.getenv("LOG_LEVEL", "INFO")

    @classmethod
    def validate(cls) -> None:
        """Fail boot on a configuration that is unsafe to serve traffic with."""
        # `TESTING` used to short-circuit this entire method, so setting it in a
        # deployed environment silently disabled every check below. A test
        # environment is a development environment; anything else claiming to
        # be under test in production is a misconfiguration, and that is
        # exactly when these checks matter most.
        if cls.IS_DEVELOPMENT:
            return
        if cls.TESTING:
            raise RuntimeError(
                "Refusing to start: TESTING is set outside a development "
                "environment. This would disable the boot-time safety checks."
            )

        missing = [
            name
            for name in ("SECRET_KEY", "JWT_SECRET")
            if not getattr(cls, name)
        ]
        if missing:
            raise RuntimeError(
                f"Refusing to start: {', '.join(missing)} must be set in a "
                "production environment."
            )
        if len(cls.JWT_SECRET) < 32:
            raise RuntimeError(
                "Refusing to start: JWT_SECRET must be at least 32 characters."
            )
        if cls.JWT_SECRET == cls.SECRET_KEY:
            raise RuntimeError(
                "Refusing to start: JWT_SECRET must differ from SECRET_KEY so "
                "that leaking one does not compromise the other."
            )
        if cls.SQLALCHEMY_DATABASE_URI.startswith("sqlite"):
            raise RuntimeError(
                "Refusing to start: DATABASE_URL must point at Postgres in a "
                "production environment."
            )
        if cls.RATELIMIT_STORAGE_URI.startswith("memory://"):
            raise RuntimeError(
                "Refusing to start: RATELIMIT_STORAGE_URI must be a shared "
                "store (Redis). An in-memory limiter is per-process, so a "
                "multi-worker deploy would multiply every limit by the worker "
                "count."
            )
