"""URL slugs that stay unique without a retry loop on the client."""

import re
import secrets
import unicodedata

_NON_SLUG = re.compile(r"[^a-z0-9]+")


def slugify(value: str, *, max_length: int = 80) -> str:
    # Decompose accents to ASCII so "Fête" becomes "fete" rather than
    # collapsing to an empty slug.
    normalized = unicodedata.normalize("NFKD", value or "")
    ascii_only = normalized.encode("ascii", "ignore").decode("ascii").lower()
    slug = _NON_SLUG.sub("-", ascii_only).strip("-")[:max_length].strip("-")
    return slug or "untitled"


def unique_slug(session, model, value: str, *, max_length: int = 80) -> str:
    """A slug not currently taken on ``model``.

    Collisions are broken with random suffixes rather than an incrementing
    counter: a counter both leaks how many similarly-named records exist and
    needs a serialized read to be correct under concurrency. A unique index on
    the column is still the real guarantee — this only avoids the common case
    reaching it.
    """
    base = slugify(value, max_length=max_length - 7)
    candidate = base
    for _ in range(5):
        exists = session.query(model.id).filter(model.slug == candidate).first()
        if exists is None:
            return candidate
        candidate = f"{base}-{secrets.token_hex(3)}"
    return f"{base}-{secrets.token_hex(4)}"
