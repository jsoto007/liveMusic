"""What we email, and when.

Every function here is safe to call from inside a request: none of them raise,
and none of them let a mail failure roll back the work that triggered it.
Registering an account whose welcome mail bounced is still a registered
account.

The bulk sends (`notify_followers_of_new_show`, `send_due_show_reminders`)
are idempotent on ``(user, kind, subject)`` via the ``email_deliveries``
unique constraint, so a scheduler that overlaps with itself or retries after a
crash cannot mail the same person twice about the same show.
"""

from datetime import timedelta

from flask import current_app

from ..extensions import db
from ..models import (
    Artist,
    ArtistFollow,
    EmailKind,
    EmailTokenPurpose,
    Event,
    EventInterest,
    EventStatus,
    User,
    as_utc,
    utcnow,
)
from ..routes.serializers import serialize_event
from ..utils.email_tokens import issue_token
from .email_links import artist_url, event_url, reset_password_url, verify_email_url
from .email_service import deliver

VERIFY_TTL = timedelta(hours=48)
RESET_TTL = timedelta(minutes=30)

#: How far ahead of a show its reminder goes out.
REMINDER_LEAD = timedelta(hours=24)
#: The reminder job looks at a window rather than an instant, so a late or
#: skipped run still catches the shows it missed instead of silently dropping
#: them. Overlap is harmless — delivery is idempotent.
REMINDER_WINDOW = timedelta(hours=6)


def send_verification_email(user) -> bool:
    """Ask a new account to confirm its address."""
    # Guarded like everything else here: a transient database error while
    # minting the token used to throw straight through into the registration
    # that had *already committed the user row*, so the client was told
    # registration failed and then got EMAIL_IN_USE on every retry.
    try:
        raw = issue_token(db.session, user, EmailTokenPurpose.VERIFY_EMAIL, VERIFY_TTL)
        db.session.commit()
    except Exception:
        current_app.logger.exception("Could not issue a verification token.")
        db.session.rollback()
        return False

    return deliver(
        user,
        EmailKind.VERIFY_EMAIL,
        "verify_email",
        "Confirm your email — Live Msc",
        verify_url=verify_email_url(raw),
        ttl_hours=int(VERIFY_TTL.total_seconds() // 3600),
    )


def send_password_reset_email(user) -> bool:
    try:
        raw = issue_token(db.session, user, EmailTokenPurpose.RESET_PASSWORD, RESET_TTL)
        db.session.commit()
    except Exception:
        current_app.logger.exception("Could not issue a password-reset token.")
        db.session.rollback()
        return False

    return deliver(
        user,
        EmailKind.RESET_PASSWORD,
        "reset_password",
        "Reset your password — Live Msc",
        reset_url=reset_password_url(raw),
        ttl_minutes=int(RESET_TTL.total_seconds() // 60),
    )


def notify_followers_of_new_show(event: Event) -> int:
    """Tell an artist's followers about a newly published listing.

    Returns the number of messages accepted by the transport. Called inline
    from the publish path: the follower count for a local band is small, and a
    queue is not worth its operational cost yet. If a band ever has tens of
    thousands of followers this needs to move to a background job — the
    delivery table already makes that safe to resume.
    """
    if event.status is not EventStatus.PUBLISHED or event.artist_id is None:
        return 0
    # Nothing useful to say about a show that has already happened.
    if event.starts_at is None or as_utc(event.starts_at) <= utcnow():
        return 0

    artist = db.session.get(Artist, event.artist_id)
    if artist is None:
        return 0

    followers = (
        db.session.query(User)
        .join(ArtistFollow, ArtistFollow.user_id == User.id)
        .filter(
            ArtistFollow.artist_id == artist.id,
            User.is_active.is_(True),
            # Don't email the band its own listing.
            User.id != artist.owner_user_id,
        )
        .all()
    )
    if not followers:
        return 0

    payload = serialize_event(event)
    sent = 0
    for follower in followers:
        try:
            if deliver(
                follower,
                EmailKind.NEW_SHOW_FROM_FOLLOWED,
                "new_show_from_followed",
                f"{artist.name} — {payload['day_label'].lower()} at "
                f"{payload['venue']['name'] if payload['venue'] else 'a room near you'}",
                subject_id=event.id,
                once=True,
                artist=artist,
                artist_url=artist_url(artist),
                event=payload,
                event_url=event_url(event),
            ):
                sent += 1
        except Exception:
            # One bad address must not stop the rest of the list.
            current_app.logger.exception("Follower notification failed; continuing.")
            db.session.rollback()

    current_app.logger.info(
        "New-show notification: %d of %d followers mailed.", sent, len(followers)
    )
    return sent


def _reminder_key(event: Event):
    """A per-(show, start-time) idempotency key.

    Derived rather than stored: a UUID5 over the event id and its start
    instant, so a reschedule produces a different key and the reminder goes
    out again for the date that will actually happen.
    """
    import uuid as _uuid

    starts = as_utc(event.starts_at)
    stamp = starts.isoformat() if starts else "unscheduled"
    return _uuid.uuid5(_uuid.NAMESPACE_URL, f"reminder:{event.id}:{stamp}")


def send_due_show_reminders() -> dict:
    """Remind readers about shows they said they were going to.

    Run on a schedule (``flask notify reminders``). The window is deliberately
    wider than the interval so a missed run recovers on the next one.
    """
    now = utcnow()
    window_start = now + REMINDER_LEAD - REMINDER_WINDOW
    window_end = now + REMINDER_LEAD

    rows = (
        db.session.query(User, Event)
        .join(EventInterest, EventInterest.user_id == User.id)
        .join(Event, Event.id == EventInterest.event_id)
        .filter(
            EventInterest.going.is_(True),
            Event.status == EventStatus.PUBLISHED,
            Event.starts_at > window_start,
            Event.starts_at <= window_end,
            User.is_active.is_(True),
        )
        .all()
    )

    sent = 0
    for user, event in rows:
        try:
            payload = serialize_event(event, now=now)
            if deliver(
                user,
                EmailKind.SHOW_REMINDER,
                "show_reminder",
                f"Tomorrow: {event.headline}",
                # Keyed on the show AND its start time. Keyed on the id alone,
                # a band that rescheduled left its attendees with a reminder
                # for the old date and none for the new one — the delivery row
                # from the first date suppressed the second.
                subject_id=_reminder_key(event),
                once=True,
                event=payload,
                event_url=event_url(event),
            ):
                sent += 1
        except Exception:
            current_app.logger.exception("Show reminder failed; continuing.")
            db.session.rollback()

    current_app.logger.info("Show reminders: %d sent from %d candidates.", sent, len(rows))
    return {"candidates": len(rows), "sent": sent}
