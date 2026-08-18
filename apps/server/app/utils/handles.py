"""Public handles — the @name a profile lives at.

Same posture as slugs: lowercase, URL-safe, unique index as the real
guarantee. The alphabet is deliberately tighter than slugs (no hyphens) so a
handle is also a mention token — ``@ada_fournier`` parses out of a comment
with one regex and no ambiguity about where it ends.
"""

import re
import secrets
import unicodedata

#: The whole grammar: 3–30 of [a-z0-9_]. Mentions reuse this (see
#: services/comments.py), so loosening it means revisiting the mention parser.
HANDLE_RE = re.compile(r"^[a-z0-9_]{3,30}$")

_NON_HANDLE = re.compile(r"[^a-z0-9_]+")

#: Never issued and never claimable — either they collide with routes and
#: URL space (``/u/me``), or they read as the paper speaking.
RESERVED_HANDLES = frozenset(
    {
        "me",
        "you",
        "admin",
        "admins",
        "api",
        "search",
        "settings",
        "support",
        "moderator",
        "editor",
        "everyone",
        "livemsc",
        "live_msc",
        "themgmt",
    }
)


def normalize_handle(value: str) -> str:
    return (value or "").strip().lower()


def is_valid_handle(value: str) -> bool:
    """Grammar and reservations only — uniqueness is the database's job."""
    return bool(HANDLE_RE.match(value)) and value not in RESERVED_HANDLES


def handle_base(value: str, *, fallback: str = "reader") -> str:
    """Collapse a display name or email local-part into handle alphabet."""
    normalized = unicodedata.normalize("NFKD", value or "")
    ascii_only = normalized.encode("ascii", "ignore").decode("ascii").lower()
    base = _NON_HANDLE.sub("_", ascii_only).strip("_")[:24].strip("_")
    if len(base) < 3 or base in RESERVED_HANDLES:
        return fallback
    return base


def unique_handle(session, base: str) -> str:
    """A handle not currently taken.

    Collisions get a random suffix, exactly as ``unique_slug`` does and for
    the same two reasons: a counter leaks how many near-namesakes exist, and
    it needs a serialized read to be correct under concurrency. The unique
    index on ``users.handle`` remains the actual guarantee.
    """
    from ..models import User

    candidate = base
    for _ in range(5):
        exists = session.query(User.id).filter(User.handle == candidate).first()
        if exists is None:
            return candidate
        candidate = f"{base[:23]}_{secrets.token_hex(3)}"
    return f"{base[:21]}_{secrets.token_hex(4)}"
