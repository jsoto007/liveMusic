"""Sending mail.

Two transports, chosen by configuration rather than by code:

* **SMTP** — works with anything, including Render's own outbound relay,
  Postmark, SES or a self-hosted server.
* **Resend** — a plain HTTPS API, which is usually less painful than SMTP on a
  platform that restricts outbound port 25/587.

Both are behind :func:`send_email`, so nothing above this module knows which
is in use. With neither configured the app logs the message and returns
``False`` — development stays usable and a missing credential never takes down
a request path that merely *wanted* to send mail.

The cardinal rule here: **sending mail must never fail the operation that
triggered it.** Registering an account whose welcome mail bounced is still a
registered account. Every caller gets a boolean, and nothing raises.
"""

import hashlib
import smtplib
import ssl
import threading
import time
from dataclasses import dataclass
from email.message import EmailMessage
from email.utils import formataddr

import requests
from flask import current_app, render_template

from ..extensions import db
from ..models import EmailDelivery, EmailKind, utcnow


@dataclass(frozen=True)
class Message:
    to: str
    subject: str
    html: str
    text: str
    #: RFC 8058 one-click unsubscribe. Gmail and Yahoo require it for bulk
    #: mail, and it is what keeps us out of the spam folder.
    list_unsubscribe: str | None = None


def header_safe(value: str, *, max_length: int = 180) -> str:
    """Collapse a string to something that can be a Subject.

    Interior newlines pass `parse_string` (it only strips the ends), and
    `EmailMessage.__setitem__` refuses a header containing one. That raised,
    got swallowed as a transport failure, released the delivery claim, and the
    scheduler then retried and failed identically forever — so a band whose
    name contained a newline silently killed the announcement to every one of
    its followers. Collapsing here is the fix; nobody is ever emailed by a
    header we could not construct.
    """
    return " ".join((value or "").split())[:max_length]


# ── Per-recipient budget ───────────────────────────────────────────────────
#
# Every rate limit on the routes is keyed by source IP, so a rotating-IP caller
# had unbounded volume at a single inbox: register with the victim's address
# (10/hr), then resend verification (5/hr), then forgot-password (5/hr), from
# our authenticated sending domain. That is an inbox flood and a deliverability
# problem for us. This counts sends per ADDRESS, independent of who asked.
#
# Per-process, like the geocoding budget — a multi-worker deploy multiplies it
# by the worker count. Exact enforcement wants the shared Redis the rate
# limiter already uses; this is the floor, not the ceiling.
_RECIPIENT_LOCK = threading.Lock()
_RECIPIENT_COUNTS: dict[str, list] = {}


def _within_recipient_budget(address: str) -> bool:
    limit = current_app.config.get("EMAIL_PER_RECIPIENT_HOURLY", 0)
    if limit <= 0:
        return True

    # Hashed: this dict would otherwise be a plaintext list of everyone we
    # have mailed, sitting in memory for the life of the process.
    key = hashlib.sha256(address.strip().lower().encode("utf-8")).hexdigest()
    now = time.monotonic()
    window = 3600.0

    with _RECIPIENT_LOCK:
        if len(_RECIPIENT_COUNTS) > 5000:
            # Bounded: drop entries whose window has closed.
            for stale in [k for k, v in _RECIPIENT_COUNTS.items() if now - v[0] > window]:
                _RECIPIENT_COUNTS.pop(stale, None)

        entry = _RECIPIENT_COUNTS.get(key)
        if entry is None or now - entry[0] > window:
            _RECIPIENT_COUNTS[key] = [now, 1]
            return True
        if entry[1] >= limit:
            return False
        entry[1] += 1
        return True


def reset_recipient_budget() -> None:
    """Test seam."""
    with _RECIPIENT_LOCK:
        _RECIPIENT_COUNTS.clear()


def _sender() -> tuple[str, str]:
    config = current_app.config
    return config.get("MAIL_FROM_NAME", "Live Msc"), config.get("MAIL_FROM_ADDRESS", "")


def _transport() -> str:
    config = current_app.config
    if config.get("RESEND_API_KEY"):
        return "resend"
    if config.get("SMTP_HOST") and config.get("MAIL_FROM_ADDRESS"):
        return "smtp"
    return "none"


def send_email(message: Message) -> bool:
    """Deliver one message. Returns whether the transport accepted it.

    Never raises: a caller is always mid-way through something more important
    than the mail.
    """
    transport = _transport()
    try:
        if transport == "resend":
            return _send_via_resend(message)
        if transport == "smtp":
            return _send_via_smtp(message)
    except Exception:
        # Deliberately broad. smtplib, ssl and requests each raise their own
        # families, and none of them should be able to 500 a request whose
        # actual job succeeded.
        current_app.logger.exception("Email delivery failed for subject %r", message.subject)
        return False

    current_app.logger.info(
        "No mail transport configured; would have sent %r to a recipient.", message.subject
    )
    return False


def _send_via_smtp(message: Message) -> bool:
    config = current_app.config
    name, address = _sender()

    envelope = EmailMessage()
    envelope["Subject"] = message.subject
    envelope["From"] = formataddr((name, address))
    envelope["To"] = message.to
    if message.list_unsubscribe:
        envelope["List-Unsubscribe"] = f"<{message.list_unsubscribe}>"
        envelope["List-Unsubscribe-Post"] = "List-Unsubscribe=One-Click"
    envelope.set_content(message.text)
    envelope.add_alternative(message.html, subtype="html")

    host = config["SMTP_HOST"]
    port = int(config.get("SMTP_PORT", 587))
    timeout = int(config.get("SMTP_TIMEOUT_SECONDS", 15))
    username = config.get("SMTP_USERNAME")
    password = config.get("SMTP_PASSWORD")
    context = ssl.create_default_context()

    if int(port) == 465:
        with smtplib.SMTP_SSL(host, port, timeout=timeout, context=context) as server:
            if username:
                server.login(username, password or "")
            server.send_message(envelope)
    else:
        with smtplib.SMTP(host, port, timeout=timeout) as server:
            # STARTTLS is not optional. Credentials and a password-reset link
            # both cross this connection.
            server.starttls(context=context)
            if username:
                server.login(username, password or "")
            server.send_message(envelope)

    current_app.logger.info("Sent %r via SMTP.", message.subject)
    return True


def _send_via_resend(message: Message) -> bool:
    config = current_app.config
    name, address = _sender()

    headers = {}
    if message.list_unsubscribe:
        headers["List-Unsubscribe"] = f"<{message.list_unsubscribe}>"
        headers["List-Unsubscribe-Post"] = "List-Unsubscribe=One-Click"

    response = requests.post(
        "https://api.resend.com/emails",
        headers={"Authorization": f"Bearer {config['RESEND_API_KEY']}"},
        json={
            "from": formataddr((name, address)),
            "to": [message.to],
            "subject": message.subject,
            "html": message.html,
            "text": message.text,
            **({"headers": headers} if headers else {}),
        },
        timeout=int(config.get("EMAIL_HTTP_TIMEOUT_SECONDS", 10)),
    )
    if response.status_code >= 400:
        # The body can echo the recipient address, so it is not logged.
        current_app.logger.error(
            "Resend rejected %r with status %s.", message.subject, response.status_code
        )
        return False

    current_app.logger.info("Sent %r via Resend.", message.subject)
    return True


# ── Composing ──────────────────────────────────────────────────────────────


def render_email(template: str, **context) -> tuple[str, str]:
    """Render the HTML and plain-text halves of a message.

    Both are always sent. A text/plain alternative is not decoration: some
    clients refuse HTML outright, and a message without one scores worse with
    spam filters.
    """
    html = render_template(f"emails/{template}.html", **context)
    text = render_template(f"emails/{template}.txt", **context)
    return html, text


def deliver(
    user,
    kind: EmailKind,
    template: str,
    subject: str,
    *,
    subject_id=None,
    once: bool = False,
    **context,
) -> bool:
    """Render, record and send one message to one reader.

    ``once=True`` makes the send idempotent on ``(user, kind, subject_id)``:
    the delivery row is inserted *before* the transport is called, so a
    scheduler that runs twice — or retries after a crash — cannot mail the same
    person about the same show again. Losing the race means somebody else is
    already sending it, which is the outcome we want.
    """
    if not user.accepts(kind):
        return False
    if not user.email:
        return False
    if not _within_recipient_budget(user.email):
        current_app.logger.warning("Per-recipient send budget reached; dropping %r.", template)
        return False

    # EVERYTHING is inside the try, including the ledger write. It used to sit
    # outside, so a transient database error during the mail step — a reset
    # connection, a statement timeout, a deadlock on the shared session — threw
    # straight through `deliver` and 500'd the registration that had *already
    # committed the user row*. The client was told registration failed, retried,
    # and got EMAIL_IN_USE forever. The contract is that this never raises; it
    # is now enforced at the boundary rather than holding by accident.
    try:
        if once:
            if not _claim_delivery(user, kind, subject_id):
                return False
        else:
            db.session.add(EmailDelivery(user_id=user.id, kind=kind, subject_id=subject_id))
            db.session.commit()
    except Exception:
        current_app.logger.exception("Could not record the delivery of %r.", template)
        db.session.rollback()
        return False

    try:
        from .email_links import unsubscribe_url

        unsubscribe = unsubscribe_url(user) if kind in _OPTIONAL_KINDS else None
        html, text = render_email(
            template,
            user=user,
            unsubscribe_url=unsubscribe,
            site_url=current_app.config.get("FRONTEND_URL", "").split(",")[0].strip(),
            **context,
        )

        sent = send_email(
            Message(
                to=user.email,
                subject=header_safe(subject),
                html=html,
                text=text,
                list_unsubscribe=unsubscribe,
            )
        )
    except Exception:
        current_app.logger.exception("Could not compose or send %r.", template)
        sent = False

    if not sent and once:
        # Release the claim so a later run can retry. Without this a transport
        # blip would silently cost the reader that notification forever.
        _release_delivery(user, kind, subject_id)
    return sent


def _claim_delivery(user, kind: EmailKind, subject_id) -> bool:
    """Insert the delivery row, or report that someone already did."""
    from sqlalchemy.exc import IntegrityError

    db.session.add(EmailDelivery(user_id=user.id, kind=kind, subject_id=subject_id))
    try:
        db.session.commit()
        return True
    except IntegrityError:
        db.session.rollback()
        return False


def _release_delivery(user, kind: EmailKind, subject_id) -> None:
    db.session.query(EmailDelivery).filter(
        EmailDelivery.user_id == user.id,
        EmailDelivery.kind == kind,
        EmailDelivery.subject_id == subject_id,
    ).delete(synchronize_session=False)
    db.session.commit()


def already_delivered(user_id, kind: EmailKind, subject_id) -> bool:
    return (
        db.session.query(EmailDelivery.id)
        .filter(
            EmailDelivery.user_id == user_id,
            EmailDelivery.kind == kind,
            EmailDelivery.subject_id == subject_id,
        )
        .first()
        is not None
    )


def _optional_kinds() -> set:
    from ..models import OPTIONAL_EMAIL_KINDS

    return set(OPTIONAL_EMAIL_KINDS)


_OPTIONAL_KINDS = {EmailKind.NEW_SHOW_FROM_FOLLOWED, EmailKind.SHOW_REMINDER}


def transport_name() -> str:
    """For the health endpoint and for boot-time logging."""
    return _transport()


__all__ = [
    "Message",
    "header_safe",
    "reset_recipient_budget",
    "deliver",
    "render_email",
    "send_email",
    "transport_name",
    "already_delivered",
    "utcnow",
]
