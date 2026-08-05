"""Reclaim storage from uploads that were started and never finished.

A presigned PUT can succeed while the client dies before calling
``/complete``. Nothing references that object, so without a sweep it sits in
the bucket forever, billed monthly and invisible.
"""

from flask import current_app
from sqlalchemy import or_

from ..extensions import db
from ..models import MediaUpload, UploadStatus, utcnow
from .r2_storage import R2Storage


def sweep_abandoned_uploads(batch_size: int = 200) -> dict:
    """Delete the objects behind tickets that will never be completed.

    Two things this gets right that the obvious version does not:

    * It selects on ``swept_at IS NULL``, not on ``status == PENDING``. A
      ticket the client abandoned explicitly — or one a failed completion
      marked ABANDONED — still has an object in the bucket, and filtering by
      status made those permanently unreachable.
    * It advances ``swept_at`` **only when the delete actually succeeded**.
      ``delete_object`` swallows transport errors and returns False, so
      marking unconditionally meant one R2 hiccup orphaned the whole batch
      (up to ``batch_size`` × 20 MB) with no way to find it again.
    """
    now = utcnow()
    stale = (
        db.session.query(MediaUpload)
        .filter(
            MediaUpload.swept_at.is_(None),
            MediaUpload.expires_at < now,
            # A completed ticket's object is referenced by a durable row and
            # must never be swept; everything else is fair game once its
            # signature is dead.
            or_(
                MediaUpload.status == UploadStatus.PENDING,
                MediaUpload.status == UploadStatus.ABANDONED,
            ),
        )
        .order_by(MediaUpload.expires_at.asc())
        .limit(batch_size)
        .all()
    )

    deleted_objects = 0
    failed = 0
    for ticket in stale:
        if R2Storage.delete_object(ticket.object_key):
            deleted_objects += 1
            ticket.swept_at = now
            ticket.status = UploadStatus.ABANDONED
        else:
            # Left untouched so the next sweep retries it.
            failed += 1

    db.session.commit()

    if stale:
        current_app.logger.info(
            "Upload sweep: %d candidates, %d objects removed, %d left for retry.",
            len(stale),
            deleted_objects,
            failed,
        )
    return {"tickets": len(stale), "objects_deleted": deleted_objects, "retry": failed}
