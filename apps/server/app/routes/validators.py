"""Request parsing helpers.

Every one returns ``(value, error_response)`` — exactly one of which is None —
so a route reads as a flat sequence of guards and malformed input can never
reach the ORM. A bad body is always a 400 ``VALIDATION_ERROR``, never a 500.
"""

import re
import uuid
from datetime import datetime, timezone
from typing import Any

from .response import error

# Upper bound for a monetary field: $10,000 in cents. Well above any door
# price; guards against overflow and absurd input.
MAX_PRICE_CENTS = 1_000_000

#: C0/C1 control characters, minus nothing — none of them belong in a name, a
#: headline or a one-line blurb.
_CONTROL_CHARS = re.compile(r"[\x00-\x1f\x7f-\x9f]")

MAX_TEXT_LENGTHS = {
    "short": 120,
    "line": 300,
    "blurb": 4000,
}


def get_json(request):
    if not request.is_json:
        return None, error("VALIDATION_ERROR", "A JSON body is required.", {"body": "invalid"})
    body = request.get_json(silent=True)
    if body is None:
        return None, error(
            "VALIDATION_ERROR", "The JSON body could not be parsed.", {"body": "invalid"}
        )
    if not isinstance(body, dict):
        return None, error(
            "VALIDATION_ERROR", "The JSON body must be an object.", {"body": "invalid"}
        )
    return body, None


def parse_string(
    value: Any,
    field: str,
    *,
    required: bool = True,
    max_length: int = 300,
    min_length: int = 1,
):
    if value is None:
        if required:
            return None, error("VALIDATION_ERROR", f"{field} is required.", {field: "required"})
        return None, None
    if not isinstance(value, str):
        return None, error("VALIDATION_ERROR", f"{field} must be text.", {field: "invalid"})
    # Strip control characters before anything else. `strip()` only touches the
    # ends, so an interior newline used to survive into an email Subject —
    # where Python's header policy refuses it, the send fails, the delivery
    # claim is released, and the scheduler then retries and fails identically
    # forever. Nothing legitimate needs a control character in these fields.
    cleaned = _CONTROL_CHARS.sub(" ", value).strip()
    if not cleaned:
        if required:
            return None, error("VALIDATION_ERROR", f"{field} is required.", {field: "required"})
        return None, None
    if len(cleaned) < min_length:
        return None, error(
            "VALIDATION_ERROR",
            f"{field} must be at least {min_length} characters.",
            {field: "too_short"},
        )
    if len(cleaned) > max_length:
        return None, error(
            "VALIDATION_ERROR",
            f"{field} must be at most {max_length} characters.",
            {field: "too_long"},
        )
    return cleaned, None


def parse_uuid(value: Any, field: str, *, required: bool = True):
    if value is None:
        if required:
            return None, error("VALIDATION_ERROR", f"{field} is required.", {field: "required"})
        return None, None
    try:
        return uuid.UUID(str(value)), None
    except (ValueError, TypeError, AttributeError):
        return None, error("VALIDATION_ERROR", f"{field} must be a valid id.", {field: "invalid"})


def parse_datetime(value: Any, field: str, *, required: bool = True):
    """Parse an ISO-8601 datetime and always return an aware UTC value.

    A naive input is interpreted as UTC — the same convention the storage layer
    uses — so a client that forgets its offset gets a predictable result rather
    than a comparison that silently comes out wrong.
    """
    if value is None:
        if required:
            return None, error("VALIDATION_ERROR", f"{field} is required.", {field: "required"})
        return None, None
    if isinstance(value, datetime):
        parsed = value
    elif isinstance(value, str):
        try:
            parsed = datetime.fromisoformat(value.strip().replace("Z", "+00:00"))
        except ValueError:
            return None, error(
                "VALIDATION_ERROR",
                f"{field} must be an ISO-8601 datetime.",
                {field: "invalid"},
            )
    else:
        return None, error(
            "VALIDATION_ERROR", f"{field} must be an ISO-8601 datetime.", {field: "invalid"}
        )
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc), None


def parse_int(value: Any, field: str, *, required: bool = True, minimum: int | None = None,
              maximum: int | None = None):
    if value is None:
        if required:
            return None, error("VALIDATION_ERROR", f"{field} is required.", {field: "required"})
        return None, None
    # `True` is an int in Python; a boolean here is a client bug, not a count.
    if isinstance(value, bool):
        return None, error("VALIDATION_ERROR", f"{field} must be a number.", {field: "invalid"})
    try:
        parsed = int(value)
    except (ValueError, TypeError):
        return None, error("VALIDATION_ERROR", f"{field} must be a number.", {field: "invalid"})
    if minimum is not None and parsed < minimum:
        return None, error(
            "VALIDATION_ERROR", f"{field} must be at least {minimum}.", {field: f"min_{minimum}"}
        )
    if maximum is not None and parsed > maximum:
        return None, error(
            "VALIDATION_ERROR", f"{field} is above the maximum allowed.", {field: "max"}
        )
    return parsed, None


def parse_cents(value: Any, field: str, *, required: bool = True):
    """A door price in integer cents.

    ``None`` means "price not stated" and is distinct from ``0``, which means
    the show is free. They render differently, so never coalesce them.
    """
    return parse_int(value, field, required=required, minimum=0, maximum=MAX_PRICE_CENTS)


def parse_bool(value: Any, field: str, *, required: bool = True):
    if value is None:
        if required:
            return None, error("VALIDATION_ERROR", f"{field} is required.", {field: "required"})
        return None, None
    if isinstance(value, bool):
        return value, None
    return None, error("VALIDATION_ERROR", f"{field} must be true or false.", {field: "invalid"})


def parse_enum(value: Any, enum_cls, field: str, *, required: bool = True):
    if value is None:
        if required:
            return None, error("VALIDATION_ERROR", f"{field} is required.", {field: "required"})
        return None, None
    try:
        return enum_cls(value), None
    except (ValueError, TypeError):
        allowed = ", ".join(member.value for member in enum_cls)
        return None, error(
            "VALIDATION_ERROR",
            f"{field} must be one of: {allowed}.",
            {field: "invalid"},
        )


def parse_string_list(
    value: Any,
    field: str,
    *,
    required: bool = False,
    max_items: int = 20,
    max_length: int = 60,
):
    if value is None:
        if required:
            return None, error("VALIDATION_ERROR", f"{field} is required.", {field: "required"})
        return None, None
    if not isinstance(value, list):
        return None, error("VALIDATION_ERROR", f"{field} must be a list.", {field: "invalid"})
    if len(value) > max_items:
        return None, error(
            "VALIDATION_ERROR", f"{field} allows at most {max_items} entries.", {field: "too_many"}
        )
    cleaned: list[str] = []
    for item in value:
        parsed, err = parse_string(item, field, max_length=max_length)
        if err:
            return None, err
        if parsed not in cleaned:
            cleaned.append(parsed)
    return cleaned, None


def parse_latitude(value: Any, field: str = "latitude", *, required: bool = True):
    return _parse_float(value, field, required=required, minimum=-90.0, maximum=90.0)


def parse_longitude(value: Any, field: str = "longitude", *, required: bool = True):
    return _parse_float(value, field, required=required, minimum=-180.0, maximum=180.0)


def _parse_float(value: Any, field: str, *, required: bool, minimum: float, maximum: float):
    if value is None or value == "":
        if required:
            return None, error("VALIDATION_ERROR", f"{field} is required.", {field: "required"})
        return None, None
    if isinstance(value, bool):
        return None, error("VALIDATION_ERROR", f"{field} must be a number.", {field: "invalid"})
    try:
        parsed = float(value)
    except (ValueError, TypeError):
        return None, error("VALIDATION_ERROR", f"{field} must be a number.", {field: "invalid"})
    # NaN fails every comparison, so it would slip through a naive range check
    # and then poison any distance arithmetic downstream.
    if parsed != parsed or not (minimum <= parsed <= maximum):
        return None, error(
            "VALIDATION_ERROR",
            f"{field} must be between {minimum} and {maximum}.",
            {field: "out_of_range"},
        )
    return parsed, None


def parse_pagination(args, default_limit: int = 20, max_limit: int = 100):
    try:
        limit = int(args.get("limit", default_limit))
        offset = int(args.get("offset", 0))
    except (TypeError, ValueError):
        return None, None, error(
            "VALIDATION_ERROR", "limit and offset must be numbers.", {"limit": "invalid"}
        )
    if limit < 1 or offset < 0:
        return None, None, error(
            "VALIDATION_ERROR",
            "limit must be at least 1 and offset at least 0.",
            {"limit": "min_1"},
        )
    # Cap offset too: an unbounded OFFSET on a large table is a cheap way for a
    # caller to make Postgres scan the whole thing.
    if offset > 10_000:
        return None, None, error(
            "VALIDATION_ERROR", "offset is above the maximum allowed.", {"offset": "max"}
        )
    return min(limit, max_limit), offset, None
