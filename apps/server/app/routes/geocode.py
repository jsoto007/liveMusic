"""The geocoding proxy.

Thin on purpose: it exists so the LocationIQ key stays on the server. The
useful behaviour — caching, timeouts, failing soft — lives in
``services/geocoding.py``.

Authentication is required. An open proxy would let anyone spend our
LocationIQ quota, and address lookup is only ever needed by someone filling in
a form, who is signed in by definition.
"""

from flask import Blueprint, request

from ..auth_helpers import require_auth
from ..extensions import limiter
from ..services import geocoding
from .response import error, ok
from .validators import parse_latitude, parse_longitude, parse_string

geocode_bp = Blueprint("geocode", __name__)

MAX_QUERY = 120


def _rate_key() -> str:
    """Per-user, not per-IP: the quota being protected is ours, and an office
    behind one NAT should not share a single allowance."""
    from flask_limiter.util import get_remote_address

    from ..auth_helpers import load_current_user

    user = load_current_user()
    return f"user:{user.id}" if user is not None else f"ip:{get_remote_address()}"


@geocode_bp.get("/geocode/autocomplete")
@require_auth
@limiter.limit("300 per hour", key_func=_rate_key)
def autocomplete():
    """Address suggestions for a partial string, for a typeahead field."""
    query, err = parse_string(
        request.args.get("q"), "q", required=False, max_length=MAX_QUERY
    )
    if err:
        return err
    if not query:
        return ok({"places": [], "configured": geocoding.is_configured()})

    # Optional ISO country filter, e.g. "us" or "us,ca". Narrowing the search
    # is what makes suggestions useful rather than global noise.
    country, err = parse_string(
        request.args.get("countries"), "countries", required=False, max_length=40
    )
    if err:
        return err
    if country:
        # Canonicalised here so the cache key cannot be varied by casing,
        # ordering or repetition — that was a trivial way to bypass the cache
        # and burn the daily quota on one repeated query.
        normalized = geocoding.normalize_countries(country)
        if not normalized:
            return error(
                "VALIDATION_ERROR",
                "countries must be comma-separated two-letter ISO codes.",
                {"countries": "invalid"},
            )
        country = normalized

    places = geocoding.autocomplete(query, country_codes=country)
    return ok({"places": places, "configured": geocoding.is_configured()})


@geocode_bp.get("/geocode/reverse")
@require_auth
@limiter.limit("120 per hour", key_func=_rate_key)
def reverse():
    """Name the place at a coordinate — used to fill in a home city."""
    latitude, err = parse_latitude(request.args.get("latitude"))
    if err:
        return err
    longitude, err = parse_longitude(request.args.get("longitude"))
    if err:
        return err

    place = geocoding.reverse(latitude, longitude)
    return ok({"place": place, "configured": geocoding.is_configured()})
