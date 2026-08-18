"""The photo desk: every image that lands queues for an editor's eye.

Post-moderation, deliberately: photos go live on upload and are reviewed
after the fact. Pre-moderation would hold every poster hostage to editor
latency, which kills the product for the honest majority; the desk plus the
existing report flow handles the rest. If an automated classifier is ever
added, it belongs in :func:`queue_image` — score the object there and
auto-resolve the obvious cases, leaving the queue for the borderline.
"""

from ..models import (
    Artist,
    Event,
    ImageReview,
    ImageReviewStatus,
    NotificationKind,
    UploadPurpose,
    User,
    utcnow,
)
from . import inbox
from .r2_storage import R2Storage


class ReviewRefused(Exception):
    def __init__(self, code: str, message: str, status: int = 409):
        super().__init__(message)
        self.code = code
        self.message = message
        self.status = status


def queue_image(session, ticket) -> ImageReview:
    """File a completed image upload for review. Caller commits."""
    review = ImageReview(
        uploader_user_id=ticket.user_id,
        purpose=ticket.purpose,
        target_id=ticket.target_id,
        object_key=ticket.object_key,
    )
    session.add(review)
    return review


def resolve(session, editor: User, review: ImageReview, action: str) -> ImageReview:
    """Approve, or remove everywhere the object still shows. Caller commits."""
    if action not in ("approve", "remove"):
        raise ReviewRefused(
            "VALIDATION_ERROR", "action must be approve or remove.", status=400
        )

    # Claim the row with a conditional UPDATE, same shape as upload-ticket
    # completion: two editors clicking at once must produce one verdict and
    # one notification, not two of each.
    resolved_to = (
        ImageReviewStatus.APPROVED if action == "approve" else ImageReviewStatus.REMOVED
    )
    claimed = (
        session.query(ImageReview)
        .filter(
            ImageReview.id == review.id,
            ImageReview.status == ImageReviewStatus.PENDING,
        )
        .update(
            {
                "status": resolved_to,
                "reviewed_by_user_id": editor.id,
                "reviewed_at": utcnow(),
            },
            synchronize_session=False,
        )
    )
    if claimed == 0:
        raise ReviewRefused("ALREADY_RESOLVED", "That photo was already reviewed.")
    session.refresh(review)

    if action == "remove":
        _detach_everywhere(session, review)
        # Best-effort delete, same posture as every other object removal:
        # a failed delete leaves an orphan for reconciliation, not a broken
        # review. The row's status is the editorial record either way.
        R2Storage.delete_object(review.object_key)
        inbox.notify(
            session,
            review.uploader_user_id,
            NotificationKind.IMAGE_REMOVED,
            actor=editor,
        )

    return review


def _detach_everywhere(session, review: ImageReview) -> None:
    """Clear whichever row still wears this object.

    Keyed on the *object key*, not just the target: if the owner already
    replaced the photo, the target row points at a different key and must be
    left alone — the stale object still gets deleted from storage.
    """
    if review.purpose is UploadPurpose.USER_AVATAR:
        session.query(User).filter(User.avatar_key == review.object_key).update(
            {"avatar_key": None}, synchronize_session=False
        )
    elif review.purpose is UploadPurpose.ARTIST_PHOTO:
        session.query(Artist).filter(Artist.photo_key == review.object_key).update(
            {"photo_key": None}, synchronize_session=False
        )
    elif review.purpose is UploadPurpose.EVENT_POSTER:
        session.query(Event).filter(Event.poster_key == review.object_key).update(
            {"poster_key": None, "poster_credit": None}, synchronize_session=False
        )
