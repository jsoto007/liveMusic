"""Access and refresh token minting.

The access token is a short-lived JWT the client holds **in memory only**. The
refresh token is a long random string — not a JWT — whose SHA-256 is the only
thing stored, so a database read alone yields nothing usable. Refresh tokens
rotate on every use; presenting one that has already been rotated is treated as
theft and revokes the entire family.
"""

import hashlib
import secrets
import uuid

import jwt
from flask import current_app

from ..models import RefreshToken, as_utc, utcnow

REFRESH_TOKEN_BYTES = 48


class TokenError(Exception):
    """An access token that cannot be trusted, for any reason."""


def _secret() -> str:
    return current_app.config["JWT_SECRET"]


def _algorithm() -> str:
    return current_app.config["JWT_ALGORITHM"]


def create_access_token(user) -> str:
    now = utcnow()
    payload = {
        "sub": str(user.id),
        "role": user.role.value,
        "typ": "access",
        "iat": int(now.timestamp()),
        "exp": int((now + current_app.config["ACCESS_TOKEN_TTL"]).timestamp()),
        "jti": uuid.uuid4().hex,
    }
    return jwt.encode(payload, _secret(), algorithm=_algorithm())


def decode_access_token(token: str) -> dict:
    try:
        payload = jwt.decode(
            token,
            _secret(),
            # Pinning the algorithm list is what stops an attacker swapping in
            # `alg: none` or downgrading an RS256 deployment to HS256 with the
            # public key as the secret.
            algorithms=[_algorithm()],
            options={"require": ["exp", "iat", "sub"]},
        )
    except jwt.ExpiredSignatureError as exc:
        raise TokenError("expired") from exc
    except jwt.InvalidTokenError as exc:
        raise TokenError("invalid") from exc

    if payload.get("typ") != "access":
        # A refresh token must never be usable as a bearer credential.
        raise TokenError("wrong_type")
    return payload


def hash_refresh_token(raw: str) -> str:
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def issue_refresh_token(session, user, *, family_id=None, user_agent: str | None = None):
    """Mint a refresh token and persist its hash. Returns ``(raw, row)``.

    The raw value is returned once and never stored; it goes straight into the
    httpOnly cookie (web) or the secure store (mobile).
    """
    raw = secrets.token_urlsafe(REFRESH_TOKEN_BYTES)
    row = RefreshToken(
        user_id=user.id,
        token_hash=hash_refresh_token(raw),
        family_id=family_id or uuid.uuid4(),
        expires_at=utcnow() + current_app.config["REFRESH_TOKEN_TTL"],
        user_agent=(user_agent or "")[:200] or None,
    )
    session.add(row)
    return raw, row


def revoke_family(session, family_id) -> int:
    """Revoke every live token in a family. Returns the number revoked."""
    rows = (
        session.query(RefreshToken)
        .filter(RefreshToken.family_id == family_id, RefreshToken.revoked_at.is_(None))
        .all()
    )
    now = utcnow()
    for row in rows:
        row.revoked_at = now
    return len(rows)


def rotate_refresh_token(session, raw_token: str, *, user_agent: str | None = None):
    """Exchange a refresh token for a new one.

    Returns ``(user, new_raw_token)``. Raises :class:`TokenError` if the token
    is unknown, expired, or already rotated — and in the last case revokes the
    whole family first, because a rotated token appearing again means a copy of
    it is in someone else's hands.
    """
    if not raw_token:
        raise TokenError("missing")

    token_hash = hash_refresh_token(raw_token)
    row = (
        session.query(RefreshToken)
        .filter(RefreshToken.token_hash == token_hash)
        .one_or_none()
    )
    if row is None:
        raise TokenError("unknown")

    if as_utc(row.expires_at) <= utcnow():
        # Revoke the family here too. An expired token turning up is the same
        # signal as a rotated one — if it leaked, the leak is what matters, and
        # returning early without revoking meant an expired replay was never
        # treated as theft.
        revoke_family(session, row.family_id)
        session.commit()
        raise TokenError("expired")

    now = utcnow()

    # Claim the token atomically. Read-then-write left a window in which two
    # concurrent refreshes both saw `revoked_at IS NULL`, both succeeded, and
    # theft detection never fired — precisely the race the family design exists
    # to catch. A single conditional UPDATE means exactly one caller wins, and
    # the loser is indistinguishable from a replay, which is what it is.
    claimed = (
        session.query(RefreshToken)
        .filter(
            RefreshToken.token_hash == token_hash,
            RefreshToken.revoked_at.is_(None),
        )
        .update({"revoked_at": now}, synchronize_session=False)
    )
    if claimed == 0:
        revoke_family(session, row.family_id)
        session.commit()
        raise TokenError("reused")

    session.refresh(row)
    if row.user is None or not row.user.is_active:
        raise TokenError("inactive")

    new_raw, new_row = issue_refresh_token(
        session, row.user, family_id=row.family_id, user_agent=user_agent
    )
    session.flush()
    row.rotated_to_id = new_row.id
    return row.user, new_raw
