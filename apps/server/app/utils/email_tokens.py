"""Single-use tokens that travel by email, and the signature on unsubscribe links.

Two different mechanisms, for two different jobs:

* **Verification and password reset** are database-backed, single-use and
  short-lived. Only the SHA-256 is stored — the raw value is in a mailbox and
  in whatever logs sit between us and it, so a database read must not also
  yield a working credential. Redemption is a conditional ``UPDATE``, because
  mail clients that prefetch links really do click them twice.

* **Unsubscribe** is a keyed HMAC with no stored state. An unsubscribe link in
  a two-year-old email has to keep working — expiring it would trap someone in
  a list they asked to leave, which is both rude and, under CAN-SPAM and GDPR,
  not optional.
"""

import base64
import hashlib
import hmac
import secrets
import uuid
from datetime import timedelta

from flask import current_app

from ..models import EmailToken, EmailTokenPurpose, as_utc, utcnow

TOKEN_BYTES = 32


def _hash(raw: str) -> str:
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def issue_token(session, user, purpose: EmailTokenPurpose, ttl: timedelta) -> str:
    """Mint a token, store its hash, return the raw value once.

    Any outstanding token of the same purpose is invalidated first: requesting
    a new password-reset link must retire the previous one, or a stolen older
    email stays usable after the victim has reacted to it.
    """
    session.query(EmailToken).filter(
        EmailToken.user_id == user.id,
        EmailToken.purpose == purpose,
        EmailToken.used_at.is_(None),
    ).update({"used_at": utcnow()}, synchronize_session=False)

    raw = secrets.token_urlsafe(TOKEN_BYTES)
    session.add(
        EmailToken(
            user_id=user.id,
            purpose=purpose,
            token_hash=_hash(raw),
            expires_at=utcnow() + ttl,
        )
    )
    return raw


def redeem_token(session, raw: str, purpose: EmailTokenPurpose):
    """Consume a token and return its user, or ``None``.

    The claim is a conditional ``UPDATE`` rather than read-then-write, so two
    concurrent clicks cannot both succeed — which matters because scanners and
    prefetching mail clients generate exactly that pattern.
    """
    if not raw or not isinstance(raw, str):
        return None

    row = (
        session.query(EmailToken)
        .filter(EmailToken.token_hash == _hash(raw.strip()), EmailToken.purpose == purpose)
        .one_or_none()
    )
    if row is None:
        return None
    if as_utc(row.expires_at) <= utcnow():
        return None

    claimed = (
        session.query(EmailToken)
        .filter(EmailToken.id == row.id, EmailToken.used_at.is_(None))
        .update({"used_at": utcnow()}, synchronize_session=False)
    )
    if claimed == 0:
        return None

    session.refresh(row)
    user = row.user
    if user is None or not user.is_active:
        return None
    return user


# ── Unsubscribe signatures ────────────────────────────────────────────────


def _unsubscribe_key() -> bytes:
    # Derived from the JWT secret rather than reusing it directly, so a leak of
    # one signature scheme's key material does not immediately forge the other.
    return hashlib.sha256(
        b"live-msc.unsubscribe." + current_app.config["JWT_SECRET"].encode("utf-8")
    ).digest()


def sign_unsubscribe(user_id) -> str:
    digest = hmac.new(_unsubscribe_key(), str(user_id).encode("utf-8"), hashlib.sha256).digest()
    return base64.urlsafe_b64encode(digest).decode("ascii").rstrip("=")


def verify_unsubscribe(user_id: str, signature: str) -> bool:
    """Constant-time check that this signature belongs to this user id.

    Without the signature the endpoint would be an unauthenticated way to
    unsubscribe anyone whose id you could guess or scrape.
    """
    if not user_id or not signature:
        return False
    try:
        uuid.UUID(str(user_id))
    except (ValueError, TypeError, AttributeError):
        return False

    # Compared as bytes. `hmac.compare_digest` refuses `str` arguments holding
    # non-ASCII and raises TypeError — so `?sig=é` was an unauthenticated 500
    # with a traceback in the log, which also made a malformed signature
    # distinguishable from a merely wrong one.
    return hmac.compare_digest(
        sign_unsubscribe(user_id).encode("ascii"),
        signature.encode("utf-8", "ignore"),
    )
