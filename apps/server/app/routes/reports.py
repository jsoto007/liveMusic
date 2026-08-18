"""Content reports, and the editors' desk that works through them.

The admin surface answers 404 to everyone who is not an editor — see
``require_admin``. Resolution is deliberately narrow: dismiss, or remove the
reported comment/review. There is no "ban user" button here; account action
is a bigger decision than a queue click.
"""

from flask import Blueprint, request
from sqlalchemy.orm import joinedload

from ..auth_helpers import load_current_user, require_admin, require_auth
from ..extensions import db, limiter
from ..models import (
    Comment,
    ContentReport,
    ImageReview,
    ImageReviewStatus,
    ReportReason,
    ReportStatus,
    Review,
    User,
    utcnow,
)
from ..services import photo_desk
from ..services.photo_desk import ReviewRefused
from .response import error, ok
from .serializers import serialize_image_review, serialize_report
from .validators import get_json, parse_enum, parse_pagination, parse_string, parse_uuid

reports_bp = Blueprint("reports", __name__)


@reports_bp.post("/reports")
@require_auth
@limiter.limit("20 per day")
def create_report():
    reporter = load_current_user()
    body, err = get_json(request)
    if err:
        return err

    reason, err = parse_enum(body.get("reason"), ReportReason, "reason")
    if err:
        return err
    detail, err = parse_string(
        body.get("detail"), "detail", required=False, max_length=500
    )
    if err:
        return err

    subjects = [
        key for key in ("comment_id", "review_id", "reported_user_id") if body.get(key)
    ]
    if len(subjects) != 1:
        return error(
            "VALIDATION_ERROR",
            "Report exactly one thing: a comment, a review, or a person.",
            {"subject": "exactly_one"},
        )

    comment = review = reported_user = None
    not_found = error("NOT_FOUND", "That could not be found.", status=404)

    if subjects[0] == "comment_id":
        comment_id, err = parse_uuid(body.get("comment_id"), "comment_id")
        if err:
            return err
        comment = db.session.get(Comment, comment_id)
        if comment is None:
            return not_found
        if comment.author_user_id == reporter.id:
            return error(
                "VALIDATION_ERROR", "You wrote that — delete it instead.",
                {"subject": "own_content"},
            )
    elif subjects[0] == "review_id":
        review_id, err = parse_uuid(body.get("review_id"), "review_id")
        if err:
            return err
        review = db.session.get(Review, review_id)
        if review is None:
            return not_found
        if review.author_user_id == reporter.id:
            return error(
                "VALIDATION_ERROR", "You wrote that — delete it instead.",
                {"subject": "own_content"},
            )
    else:
        user_id, err = parse_uuid(body.get("reported_user_id"), "reported_user_id")
        if err:
            return err
        reported_user = db.session.get(User, user_id)
        if reported_user is None or not reported_user.is_active:
            return not_found
        if reported_user.id == reporter.id:
            return error(
                "VALIDATION_ERROR", "You cannot report yourself.",
                {"subject": "self"},
            )

    report = ContentReport(
        reporter_user_id=reporter.id,
        comment_id=comment.id if comment else None,
        review_id=review.id if review else None,
        reported_user_id=reported_user.id if reported_user else None,
        reason=reason,
        detail=detail,
    )
    db.session.add(report)
    db.session.commit()

    # The reporter gets an acknowledgement, not the report id's fate — the
    # moderation queue is not a public ledger.
    return ok({"reported": True}, status=201)


# ── The editors' desk ──────────────────────────────────────────────────────


@reports_bp.get("/admin/reports")
@require_admin
def list_reports():
    limit, offset, err = parse_pagination(request.args, default_limit=50, max_limit=100)
    if err:
        return err

    status, err = parse_enum(
        request.args.get("status"), ReportStatus, "status", required=False
    )
    if err:
        return err

    base = db.session.query(ContentReport)
    if status is not None:
        base = base.filter(ContentReport.status == status)

    total = int(base.with_entities(db.func.count(ContentReport.id)).scalar() or 0)
    rows = (
        base.order_by(ContentReport.created_at.asc())
        .limit(limit)
        .offset(offset)
        .all()
    )

    # Batch the subjects — one query per table, not one per row.
    comment_ids = [r.comment_id for r in rows if r.comment_id]
    review_ids = [r.review_id for r in rows if r.review_id]
    user_ids = {r.reporter_user_id for r in rows} | {
        r.reported_user_id for r in rows if r.reported_user_id
    }

    comments = {
        c.id: c
        for c in db.session.query(Comment)
        .options(joinedload(Comment.author))
        .filter(Comment.id.in_(comment_ids))
        .all()
    } if comment_ids else {}
    reviews = {
        r.id: r
        for r in db.session.query(Review)
        .options(joinedload(Review.author))
        .filter(Review.id.in_(review_ids))
        .all()
    } if review_ids else {}
    users = {
        u.id: u for u in db.session.query(User).filter(User.id.in_(user_ids)).all()
    }

    return ok(
        {
            "reports": [
                serialize_report(
                    row,
                    comment=comments.get(row.comment_id),
                    review=reviews.get(row.review_id),
                    reported_user=users.get(row.reported_user_id),
                    reporter=users.get(row.reporter_user_id),
                )
                for row in rows
            ],
            "total": total,
            "has_more": offset + limit < total,
        }
    )


@reports_bp.post("/admin/reports/<uuid:report_id>/resolve")
@require_admin
def resolve_report(report_id):
    editor = load_current_user()
    report = db.session.get(ContentReport, report_id)
    if report is None:
        return error("NOT_FOUND", "Not found.", status=404)
    if report.status is not ReportStatus.OPEN:
        return error("ALREADY_RESOLVED", "That report was already handled.", status=409)

    body, err = get_json(request)
    if err:
        return err
    action = body.get("action")
    if action not in ("dismiss", "remove_content"):
        return error(
            "VALIDATION_ERROR",
            "action must be dismiss or remove_content.",
            {"action": "invalid"},
        )

    if action == "remove_content":
        if report.reported_user_id is not None:
            return error(
                "VALIDATION_ERROR",
                "A report about a person has no content to remove — dismiss it, "
                "and act on the account separately.",
                {"action": "invalid_for_user_report"},
            )
        # The FK from the report is ON DELETE CASCADE, so removing the content
        # would take this report row with it and lose the audit line. Detach
        # the pointer first; the resolution row itself is the record.
        if report.comment_id is not None:
            comment = db.session.get(Comment, report.comment_id)
            report.comment_id = None
            if comment is not None:
                db.session.delete(comment)
        elif report.review_id is not None:
            review = db.session.get(Review, report.review_id)
            report.review_id = None
            if review is not None:
                db.session.delete(review)
        report.status = ReportStatus.RESOLVED
    else:
        report.status = ReportStatus.DISMISSED

    report.resolved_by_user_id = editor.id
    report.resolved_at = utcnow()
    db.session.commit()
    return ok({"report_id": str(report.id), "status": report.status.value})


# ── The photo desk ─────────────────────────────────────────────────────────


@reports_bp.get("/admin/image-reviews")
@require_admin
def list_image_reviews():
    limit, offset, err = parse_pagination(request.args, default_limit=50, max_limit=100)
    if err:
        return err

    status, err = parse_enum(
        request.args.get("status"), ImageReviewStatus, "status", required=False
    )
    if err:
        return err

    base = db.session.query(ImageReview)
    base = base.filter(
        ImageReview.status == (status or ImageReviewStatus.PENDING)
    )

    total = int(base.with_entities(db.func.count(ImageReview.id)).scalar() or 0)
    rows = (
        base.order_by(ImageReview.created_at.asc()).limit(limit).offset(offset).all()
    )

    uploaders = {
        user.id: user
        for user in db.session.query(User)
        .filter(User.id.in_({row.uploader_user_id for row in rows}))
        .all()
    } if rows else {}

    return ok(
        {
            "reviews": [
                serialize_image_review(
                    row, uploader=uploaders.get(row.uploader_user_id)
                )
                for row in rows
            ],
            "total": total,
            "has_more": offset + limit < total,
        }
    )


@reports_bp.post("/admin/image-reviews/<uuid:review_id>/resolve")
@require_admin
def resolve_image_review(review_id):
    editor = load_current_user()
    review = db.session.get(ImageReview, review_id)
    if review is None:
        return error("NOT_FOUND", "Not found.", status=404)

    body, err = get_json(request)
    if err:
        return err
    action = body.get("action")

    try:
        photo_desk.resolve(db.session, editor, review, action)
        db.session.commit()
    except ReviewRefused as refusal:
        db.session.rollback()
        return error(refusal.code, refusal.message, status=refusal.status)

    return ok({"review_id": str(review.id), "status": review.status.value})
