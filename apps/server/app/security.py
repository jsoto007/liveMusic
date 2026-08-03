"""Origin allowlist and Content Security Policy.

The CSP is strict by default — no ``unsafe-inline``, no ``unsafe-eval``. The
SPA ships no inline scripts and no ``dangerouslySetInnerHTML``, so there is
nothing to grandfather in. ``connect-src`` has to include the R2 endpoint
because the browser uploads audio and posters **directly** to R2 with a
presigned POST; without it the upload is blocked by the policy.
"""

from urllib.parse import urlparse

# Hostnames treated as loopback. `0.0.0.0` here is a value being *matched
# against*, not an address anything binds to — hence the noqa.
_LOOPBACK_HOSTS = {"localhost", "127.0.0.1", "0.0.0.0", "[::1]", "::1"}  # noqa: S104

_DEV_ORIGINS = (
    "http://localhost:5173",
    "http://127.0.0.1:5173",
    "http://localhost:8081",
    "http://127.0.0.1:8081",
)


def _clean(raw: str) -> str:
    """Normalise one configured origin.

    Render's `fromService: property: host` yields a bare hostname
    (``live-msc-web.onrender.com``) rather than a URL, and a bare host would
    make every origin comparison and every emailed link wrong. A scheme is
    added when one is missing — https, except for loopback, where a dev server
    is plain http.
    """
    cleaned = raw.strip().strip('"').strip("'").rstrip("/")
    if not cleaned or "://" in cleaned:
        return cleaned
    host = cleaned.split(":")[0].split("/")[0].lower()
    scheme = "http" if host in _LOOPBACK_HOSTS else "https"
    return f"{scheme}://{cleaned}"


#: Public alias — `_clean` is the internal name but other modules need this.
def normalize_origin(raw: str) -> str:
    return _clean(raw or "")


def parse_origins(app) -> list[str]:
    """Build the origin allowlist from FRONTEND_URL + CORS_ORIGINS."""
    origins: set[str] = set()
    for raw_group in (app.config.get("FRONTEND_URL"), app.config.get("CORS_ORIGINS")):
        if not raw_group:
            continue
        for candidate in str(raw_group).split(","):
            cleaned = _clean(candidate)
            if cleaned:
                origins.add(cleaned)

    if app.config.get("TESTING") or app.config.get("IS_DEVELOPMENT"):
        origins.update(_DEV_ORIGINS)

    return sorted(origins)


def origin_is_loopback(raw: str) -> bool:
    try:
        parsed = urlparse(_clean(raw))
    except (ValueError, AttributeError):
        return False
    return (parsed.hostname or "").lower() in _LOOPBACK_HOSTS


def should_force_https(app) -> bool:
    """HTTPS is forced unless every configured origin is loopback.

    A substring check (``"localhost" in url``) misfires on a real hostname that
    merely contains "localhost", and would flip the entire app out of HTTPS if
    any single entry in a comma-separated list referenced loopback. Parse each
    origin and require *all* of them to be local before relaxing.
    """
    if app.debug or app.config.get("TESTING") or app.config.get("IS_DEVELOPMENT"):
        return False
    raw = app.config.get("FRONTEND_URL") or ""
    candidates = [u for u in raw.split(",") if u.strip()]
    if not candidates:
        return True
    return not all(origin_is_loopback(u) for u in candidates)


def _r2_connect_sources(app) -> list[str]:
    """Origins the browser must be allowed to POST/GET media to."""
    sources: set[str] = set()
    for key in ("R2_ENDPOINT_URL", "R2_PUBLIC_BASE_URL"):
        raw = app.config.get(key) or ""
        if not raw:
            continue
        parsed = urlparse(_clean(raw))
        if parsed.scheme and parsed.netloc:
            sources.add(f"{parsed.scheme}://{parsed.netloc}")
    account_id = app.config.get("R2_ACCOUNT_ID")
    if account_id and not sources:
        sources.add(f"https://{account_id}.r2.cloudflarestorage.com")
    return sorted(sources)


def build_csp_policy(app) -> dict:
    media_sources = _r2_connect_sources(app)

    return {
        "default-src": "'self'",
        "base-uri": "'self'",
        "frame-ancestors": "'none'",
        "form-action": "'self'",
        "object-src": "'none'",
        "script-src": "'self'",
        # Vite injects the stylesheet as a <link>, but Tailwind's preflight and
        # a handful of computed inline styles (the map pin positions) need
        # 'unsafe-inline' for *styles only*. Style injection is not script
        # execution; script-src stays strict.
        "style-src": ["'self'", "'unsafe-inline'", "https://fonts.googleapis.com"],
        "font-src": ["'self'", "https://fonts.gstatic.com", "data:"],
        "img-src": ["'self'", "data:", "blob:", *media_sources],
        "media-src": ["'self'", "blob:", *media_sources],
        "connect-src": ["'self'", *media_sources],
    }


def init_security(app) -> None:
    """Response headers Talisman does not set for us."""

    @app.after_request
    def _hardening_headers(response):
        response.headers.setdefault("X-Content-Type-Options", "nosniff")
        response.headers.setdefault("Referrer-Policy", "strict-origin-when-cross-origin")
        # Assigned, not setdefault: Talisman sets its own `browsing-topics=()`
        # default, and a setdefault here silently loses to it — the camera and
        # microphone restrictions would never actually ship. This handler is
        # registered before Talisman's, and Flask runs after_request handlers in
        # reverse registration order, so this one runs last and wins.
        response.headers["Permissions-Policy"] = (
            "camera=(), microphone=(), geolocation=(self), browsing-topics=()"
        )
        response.headers.setdefault("Cross-Origin-Opener-Policy", "same-origin")
        # An API response must never be cached by a shared proxy — several
        # carry presigned URLs and user-scoped data.
        if response.mimetype == "application/json":
            response.headers.setdefault("Cache-Control", "no-store")
        return response
