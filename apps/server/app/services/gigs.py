"""The classifieds board: gigs wanted, hands raised, decisions made."""

from ..models import (
    Gig,
    GigApplication,
    GigApplicationStatus,
    GigStatus,
    NotificationKind,
)
from . import inbox


class GigRefused(Exception):
    def __init__(self, code: str, message: str, status: int = 409):
        super().__init__(message)
        self.code = code
        self.message = message
        self.status = status


def apply_to_gig(session, applicant, artist, gig: Gig, *, message: str | None):
    """One band, one hand, one gig. Caller commits.

    Ownership of ``artist`` has already been proven by the route against the
    *authenticated* user — strictly, not via the admin bypass: an editor
    moderates gigs, they do not audition other people's bands.
    """
    if gig.status is not GigStatus.OPEN:
        raise GigRefused("GIG_CLOSED", "That listing is no longer taking applications.")
    if gig.posted_by_user_id == applicant.id:
        raise GigRefused(
            "OWN_GIG", "You posted this gig — you cannot also apply to it.", status=400
        )

    existing = (
        session.query(GigApplication.id)
        .filter(GigApplication.gig_id == gig.id, GigApplication.artist_id == artist.id)
        .first()
    )
    if existing is not None:
        # Friendly shape for the common case; the unique constraint on
        # (gig_id, artist_id) is what actually holds under concurrency.
        raise GigRefused("ALREADY_APPLIED", "That band has already applied to this gig.")

    application = GigApplication(
        gig_id=gig.id,
        artist_id=artist.id,
        applicant_user_id=applicant.id,
        message=message,
    )
    session.add(application)
    session.flush()

    inbox.notify(
        session,
        gig.posted_by_user_id,
        NotificationKind.GIG_APPLICATION,
        actor=applicant,
        gig_id=gig.id,
    )
    return application


def decide_application(session, decider, gig: Gig, application: GigApplication,
                       status: GigApplicationStatus):
    """Accept or decline, and tell the band's *current* owner. Caller commits."""
    if status is GigApplicationStatus.PENDING:
        raise GigRefused(
            "VALIDATION_ERROR", "A decision is accepted or declined.", status=400
        )
    application.status = status

    kind = (
        NotificationKind.GIG_ACCEPTED
        if status is GigApplicationStatus.ACCEPTED
        else NotificationKind.GIG_DECLINED
    )
    recipient_id = (
        application.artist.owner_user_id
        if application.artist is not None
        else application.applicant_user_id
    )
    # dedupe: flip-flopping a decision should not stack identical lines.
    inbox.notify(
        session, recipient_id, kind, actor=decider, gig_id=gig.id, dedupe=True
    )
    return application
