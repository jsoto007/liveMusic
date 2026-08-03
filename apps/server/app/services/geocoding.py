"""LocationIQ, behind a server-side proxy.

**The API key never reaches a client.** Every lookup is made from here, so a
key cannot be lifted out of a JS bundle or a mobile binary and spent by
someone else. That is the whole reason this module exists rather than the
clients calling LocationIQ directly.

Two other things it has to do:

* **Cache.** LocationIQ's free tier is 5,000 requests a day at 2/second, and an
  autocomplete field fires on nearly every keystroke. An in-process LRU with a
  short TTL absorbs the repetition — the same partial address typed by ten
  people costs one upstream call.
* **Fail soft.** Address lookup is an assist, never a gate. If LocationIQ is
  down, slow, or unconfigured, posting a show must still work — the venue just
  has no coordinates, and the map skips it. Nothing here raises.
"""

import threading
import time
import unicodedata
from dataclasses import dataclass
from datetime import date

import requests
from flask import current_app

#: Results are cheap to hold and identical for everyone, so one process-wide
#: cache serves all requests. A shared Redis cache would be better across many
#: dynos; this is deliberately the simpler thing until that is a real problem.
_CACHE: dict[tuple, tuple[float, list]] = {}
_CACHE_LOCK = threading.Lock()


@dataclass(frozen=True)
class Place:
    """One address suggestion, flattened to what a form actually needs."""

    label: str
    name: str
    city: str | None
    neighborhood: str | None
    postcode: str | None
    country: str | None
    latitude: float
    longitude: float

    def as_dict(self) -> dict:
        return {
            "label": self.label,
            "name": self.name,
            "city": self.city,
            "neighborhood": self.neighborhood,
            "postcode": self.postcode,
            "country": self.country,
            "latitude": self.latitude,
            "longitude": self.longitude,
        }


def is_configured() -> bool:
    return bool(current_app.config.get("LOCATIONIQ_API_KEY"))


#: How long an upstream failure is remembered. Short, so a blip does not cost
#: an hour of lookups, but long enough that an outage is not re-hammered.
_FAILURE_CACHE_SECONDS = 45


def _cache_get(key: tuple):
    with _CACHE_LOCK:
        entry = _CACHE.get(key)
        if entry is None:
            return None
        stored_at, ttl, value = entry
        if time.monotonic() - stored_at > ttl:
            _CACHE.pop(key, None)
            return None
        # A copy: the stored list would otherwise be shared with every future
        # caller, so one mutation downstream would corrupt it for everyone.
        return [dict(item) for item in value]


def _cache_put(key: tuple, value: list, *, ttl: float | None = None) -> None:
    limit = current_app.config["GEOCODE_CACHE_MAX_ENTRIES"]
    with _CACHE_LOCK:
        if len(_CACHE) >= limit:
            # Cheap eviction: drop the oldest quarter rather than tracking
            # exact LRU order. This is a cost cache, not a correctness one.
            for stale_key in sorted(_CACHE, key=lambda k: _CACHE[k][0])[: limit // 4 or 1]:
                _CACHE.pop(stale_key, None)
        effective_ttl = ttl if ttl is not None else current_app.config["GEOCODE_CACHE_SECONDS"]
        # Stored as a copy as well as returned as one: the first caller
        # otherwise holds the very dicts that every later caller will be given.
        _CACHE[key] = (
            time.monotonic(),
            effective_ttl,
            [dict(item) for item in value],
        )


def _request(path: str, params: dict) -> list | dict | None:
    """One upstream call. Returns parsed JSON, or ``None`` on any failure."""
    config = current_app.config
    if not is_configured():
        current_app.logger.warning("LocationIQ is not configured; lookup skipped.")
        return None

    if not _spend_budget():
        current_app.logger.warning("LocationIQ daily budget exhausted; lookup skipped.")
        return None

    base = config["LOCATIONIQ_BASE_URL"].rstrip("/")
    try:
        response = requests.get(
            f"{base}/{path}",
            params={**params, "key": config["LOCATIONIQ_API_KEY"], "format": "json"},
            timeout=config["LOCATIONIQ_TIMEOUT_SECONDS"],
        )
    except requests.RequestException as exc:
        # ONLY the exception type. `requests` embeds the fully-rendered URL —
        # query string, and therefore the API key — in every connection-level
        # error: DNS failure, TLS error, connection refused, too many
        # redirects. Interpolating the exception wrote the key straight to
        # stdout, which on any platform means the log aggregator, whose
        # readership is far wider than the secret store's. This fires on
        # exactly the outage this module exists to survive.
        current_app.logger.warning(
            "LocationIQ %s failed: %s", path, type(exc).__name__
        )
        return None

    # 404 is LocationIQ's "no matches", which is an answer, not an error.
    if response.status_code == 404:
        return []
    if response.status_code == 429:
        current_app.logger.warning("LocationIQ rate limit reached.")
        return None
    if response.status_code >= 400:
        current_app.logger.warning(
            "LocationIQ returned status %s for %s.", response.status_code, path
        )
        return None

    try:
        return response.json()
    except ValueError:
        current_app.logger.warning("LocationIQ returned a body that was not JSON.")
        return None


# ── Spend control ──────────────────────────────────────────────────────────
#
# The per-user rate limit bounds one caller; this bounds the bill. LocationIQ's
# free tier is 5,000 lookups a day, and without a ceiling a handful of accounts
# — or one account making 300 distinct queries an hour — exhausts it. The
# counter is per-process, so a multi-worker deploy gets a budget per worker;
# set LOCATIONIQ_DAILY_BUDGET to the quota divided by the worker count. A
# shared Redis counter would be exact, and is the upgrade if this ever matters
# more than its complexity.
_BUDGET_LOCK = threading.Lock()
_BUDGET = {"day": None, "spent": 0}


def _spend_budget() -> bool:
    """Take one unit from today's budget. False when it is gone."""
    limit = current_app.config.get("LOCATIONIQ_DAILY_BUDGET", 0)
    if limit <= 0:
        return True

    today = date.today()
    with _BUDGET_LOCK:
        if _BUDGET["day"] != today:
            _BUDGET["day"] = today
            _BUDGET["spent"] = 0
        if _BUDGET["spent"] >= limit:
            return False
        _BUDGET["spent"] += 1
        return True


def budget_remaining() -> int | None:
    """For the health endpoint. ``None`` when no budget is configured."""
    limit = current_app.config.get("LOCATIONIQ_DAILY_BUDGET", 0)
    if limit <= 0:
        return None
    with _BUDGET_LOCK:
        if _BUDGET["day"] != date.today():
            return limit
        return max(0, limit - _BUDGET["spent"])


#: Column widths in `models.Venue`. Upstream strings are clamped to these
#: before they can reach the ORM: an over-long value is silently accepted by
#: SQLite (the test backend) and raises `StringDataRightTruncation` on
#: Postgres — a DataError, which is not a `requests` exception and so escapes
#: this module's "nothing raises" contract entirely, 500-ing the show post it
#: was only meant to decorate.
_MAX_LENGTHS = {
    "label": 300,
    "name": 160,
    "city": 120,
    "neighborhood": 120,
    "postcode": 20,
    "country": 80,
}


def _clamp(value, field: str) -> str | None:
    """Coerce one upstream string field to something safe to store."""
    if value is None:
        return None
    if not isinstance(value, str):
        # Upstream is not obliged to send us strings; anything else is dropped
        # rather than handed to the ORM.
        return None
    cleaned = value.strip()
    return cleaned[: _MAX_LENGTHS[field]] or None


def _to_place(raw: dict) -> Place | None:
    """Flatten one LocationIQ result, or drop it if it is unusable."""
    if not isinstance(raw, dict):
        return None
    try:
        latitude = float(raw["lat"])
        longitude = float(raw["lon"])
    except (KeyError, TypeError, ValueError):
        return None

    # The same guard `validators.py` applies to client input, for the same
    # reason: NaN fails every comparison, so it slips past a naive range check.
    # Unvalidated, these reach the response as literal `NaN`/`Infinity` — which
    # is not valid JSON, so every client's parse throws — and are copied onto
    # the venue row, permanently poisoning every listing that serializes it.
    if latitude != latitude or longitude != longitude:
        return None
    if not (-90.0 <= latitude <= 90.0) or not (-180.0 <= longitude <= 180.0):
        return None

    address = raw.get("address") or {}
    if not isinstance(address, dict):
        address = {}
    # LocationIQ names the city field differently depending on what kind of
    # place it is; take the first that is present rather than assuming.
    city = (
        address.get("city")
        or address.get("town")
        or address.get("village")
        or address.get("municipality")
        or address.get("county")
    )
    neighborhood = (
        address.get("neighbourhood") or address.get("suburb") or address.get("quarter")
    )
    display_name = raw.get("display_name")
    name = (
        raw.get("name")
        or address.get("name")
        or (display_name.split(",")[0] if isinstance(display_name, str) else None)
    )

    return Place(
        label=_clamp(display_name, "label") or _clamp(name, "label") or "",
        name=_clamp(name, "name") or "",
        city=_clamp(city, "city"),
        neighborhood=_clamp(neighborhood, "neighborhood"),
        postcode=_clamp(address.get("postcode"), "postcode"),
        country=_clamp(address.get("country"), "country"),
        latitude=latitude,
        longitude=longitude,
    )


def _cache_term(query: str) -> str:
    """Fold cosmetic variants of one query onto a single cache key.

    `strip().lower()` alone was defeated by anything trivial: a double space, a
    trailing comma, a non-breaking space, a fullwidth character. Seven
    cosmetically different spellings of the same address were seven upstream
    calls. NFKC folds the unicode lookalikes, casefold beats Turkish-i style
    edge cases, the whitespace is collapsed, and trailing punctuation goes.
    """
    folded = unicodedata.normalize("NFKC", query or "").casefold()
    collapsed = " ".join(folded.split())
    return collapsed.strip(" ,.;:-")


def normalize_countries(raw: str | None) -> str:
    """Canonicalise an ISO country filter.

    Un-normalised, this was the easiest cache bypass in the system: `us`, `US`,
    `us,us`, `us, us`, `ca,us` all keyed differently and all meant the same
    thing. Sorted, de-duplicated, and bounded.
    """
    if not raw:
        return ""
    codes = {part.strip().lower() for part in raw.split(",") if part.strip()}
    valid = sorted(code for code in codes if len(code) == 2 and code.isalpha())
    return ",".join(valid[:5])


def autocomplete(query: str, *, limit: int = 6, country_codes: str | None = None) -> list[dict]:
    """Address suggestions for a partial string.

    Returns ``[]`` rather than raising when LocationIQ is unavailable — the
    caller's form must stay usable without it.
    """
    term = (query or "").strip()
    # LocationIQ rejects very short queries anyway, and firing on one or two
    # characters is what exhausts a daily quota.
    if len(term) < 3:
        return []

    country_codes = normalize_countries(country_codes)
    key = ("autocomplete", _cache_term(term), limit, country_codes)
    cached = _cache_get(key)
    if cached is not None:
        return cached

    params = {
        "q": term,
        "limit": limit,
        "normalizecity": 1,
        "addressdetails": 1,
        "dedupe": 1,
    }
    if country_codes:
        params["countrycodes"] = country_codes

    raw = _request("autocomplete", params)
    if raw is None:
        # A failure is cached briefly — not for the full TTL, which would
        # suppress lookups for an hour, but long enough that an outage or an
        # exhausted quota is not re-hammered on every keystroke while each
        # request pays the full upstream timeout on a form's critical path.
        _cache_put(key, [], ttl=_FAILURE_CACHE_SECONDS)
        return []

    places = [place.as_dict() for place in (_to_place(item) for item in raw or []) if place]
    _cache_put(key, places)
    return places


def reverse(latitude: float, longitude: float) -> dict | None:
    """The place at a coordinate — used to name the reader's own location."""
    key = ("reverse", round(latitude, 4), round(longitude, 4))
    cached = _cache_get(key)
    if cached is not None:
        return cached[0] if cached else None

    raw = _request("reverse", {"lat": latitude, "lon": longitude, "addressdetails": 1})
    if raw is None:
        _cache_put(key, [], ttl=_FAILURE_CACHE_SECONDS)
        return None
    if isinstance(raw, list):
        raw = raw[0] if raw else None
    if not isinstance(raw, dict):
        return None

    place = _to_place(raw)
    result = [place.as_dict()] if place else []
    _cache_put(key, result)
    return result[0] if result else None


def geocode_one(query: str) -> dict | None:
    """The single best match for a full address string.

    Used server-side when a venue is created from a typed name — the listing
    gets coordinates so it can appear on the map, without the client having to
    supply them.
    """
    results = autocomplete(query, limit=1)
    return results[0] if results else None


def clear_cache() -> None:
    """Test seam. Also useful from a shell if a bad result gets stuck."""
    with _CACHE_LOCK:
        _CACHE.clear()


def reset_budget() -> None:
    """Test seam."""
    with _BUDGET_LOCK:
        _BUDGET["day"] = None
        _BUDGET["spent"] = 0
