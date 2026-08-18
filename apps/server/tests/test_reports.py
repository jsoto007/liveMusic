"""Content reports and the editors' desk."""

from app.extensions import db
from app.models import Comment, ContentReport, User, UserRole


def _user(email):
    return db.session.query(User).filter_by(email=email).one()


def _admin_headers(client, make_user):
    make_user(email="editor@example.com", role=UserRole.ADMIN)
    token = client.post(
        "/api/v1/auth/login",
        json={"email": "editor@example.com", "password": "correct-horse-battery"},
    ).get_json()["data"]["access_token"]
    return {"Authorization": f"Bearer {token}"}


def _comment(client, headers, event, body="A comment."):
    response = client.post(
        f"/api/v1/events/{event.id}/comments", json={"body": body}, headers=headers
    )
    assert response.status_code == 201
    return response.get_json()["data"]["comment"]


def test_report_a_comment(client, auth, make_event):
    event = make_event()
    comment = _comment(client, auth(email="author@example.com"), event)

    reporter = auth(email="reporter@example.com")
    response = client.post(
        "/api/v1/reports",
        json={"comment_id": comment["id"], "reason": "spam", "detail": "Bot text."},
        headers=reporter,
    )
    assert response.status_code == 201
    assert db.session.query(ContentReport).count() == 1


def test_reports_require_auth_and_shape(client, auth, make_event):
    event = make_event()
    comment = _comment(client, auth(email="author@example.com"), event)
    reporter = auth(email="reporter@example.com")

    assert (
        client.post(
            "/api/v1/reports", json={"comment_id": comment["id"], "reason": "spam"}
        ).status_code
        == 401
    )
    # No subject at all.
    assert (
        client.post("/api/v1/reports", json={"reason": "spam"}, headers=reporter).status_code
        == 400
    )
    # Two subjects at once.
    assert (
        client.post(
            "/api/v1/reports",
            json={
                "comment_id": comment["id"],
                "reported_user_id": str(_user("author@example.com").id),
                "reason": "spam",
            },
            headers=reporter,
        ).status_code
        == 400
    )
    # Unknown reason.
    assert (
        client.post(
            "/api/v1/reports",
            json={"comment_id": comment["id"], "reason": "ugly"},
            headers=reporter,
        ).status_code
        == 400
    )
    # Nonexistent subject.
    assert (
        client.post(
            "/api/v1/reports",
            json={"comment_id": str(event.id), "reason": "spam"},
            headers=reporter,
        ).status_code
        == 404
    )


def test_cannot_report_your_own_writing(client, auth, make_event):
    event = make_event()
    author = auth(email="author@example.com")
    comment = _comment(client, author, event)

    response = client.post(
        "/api/v1/reports",
        json={"comment_id": comment["id"], "reason": "spam"},
        headers=author,
    )
    assert response.status_code == 400


def test_admin_surface_is_invisible_to_readers(client, auth):
    headers = auth()
    assert client.get("/api/v1/admin/reports", headers=headers).status_code == 404
    assert client.get("/api/v1/admin/reports").status_code == 401


def test_admin_reads_the_queue_with_subjects(client, auth, make_user, make_event):
    event = make_event()
    comment = _comment(client, auth(email="author@example.com"), event, body="Flagged.")
    client.post(
        "/api/v1/reports",
        json={"comment_id": comment["id"], "reason": "harassment"},
        headers=auth(email="reporter@example.com"),
    )

    admin = _admin_headers(client, make_user)
    response = client.get("/api/v1/admin/reports?status=open", headers=admin)
    assert response.status_code == 200
    report = response.get_json()["data"]["reports"][0]
    assert report["subject_type"] == "comment"
    assert report["comment"]["body"] == "Flagged."
    assert report["reporter"]["handle"] == _user("reporter@example.com").handle


def test_dismissing_a_report(client, auth, make_user, make_event):
    event = make_event()
    comment = _comment(client, auth(email="author@example.com"), event)
    client.post(
        "/api/v1/reports",
        json={"comment_id": comment["id"], "reason": "spam"},
        headers=auth(email="reporter@example.com"),
    )
    admin = _admin_headers(client, make_user)
    report_id = client.get("/api/v1/admin/reports", headers=admin).get_json()["data"][
        "reports"
    ][0]["id"]

    resolved = client.post(
        f"/api/v1/admin/reports/{report_id}/resolve",
        json={"action": "dismiss"},
        headers=admin,
    )
    assert resolved.status_code == 200
    assert resolved.get_json()["data"]["status"] == "dismissed"

    # The comment is untouched.
    assert db.session.query(Comment).count() == 1

    # A second resolution is refused.
    again = client.post(
        f"/api/v1/admin/reports/{report_id}/resolve",
        json={"action": "dismiss"},
        headers=admin,
    )
    assert again.status_code == 409


def test_removing_reported_content_keeps_the_audit_row(
    client, auth, make_user, make_event
):
    event = make_event()
    comment = _comment(client, auth(email="author@example.com"), event)
    client.post(
        "/api/v1/reports",
        json={"comment_id": comment["id"], "reason": "harassment"},
        headers=auth(email="reporter@example.com"),
    )
    admin = _admin_headers(client, make_user)
    report_id = client.get("/api/v1/admin/reports", headers=admin).get_json()["data"][
        "reports"
    ][0]["id"]

    resolved = client.post(
        f"/api/v1/admin/reports/{report_id}/resolve",
        json={"action": "remove_content"},
        headers=admin,
    )
    assert resolved.status_code == 200
    assert resolved.get_json()["data"]["status"] == "resolved"

    assert db.session.query(Comment).count() == 0
    report = db.session.query(ContentReport).one()
    assert report.comment_id is None  # detached, not destroyed


def test_user_reports_cannot_remove_content(client, auth, make_user):
    auth(email="target@example.com")
    client.post(
        "/api/v1/reports",
        json={
            "reported_user_id": str(_user("target@example.com").id),
            "reason": "spam",
        },
        headers=auth(email="reporter@example.com"),
    )
    admin = _admin_headers(client, make_user)
    report_id = client.get("/api/v1/admin/reports", headers=admin).get_json()["data"][
        "reports"
    ][0]["id"]

    response = client.post(
        f"/api/v1/admin/reports/{report_id}/resolve",
        json={"action": "remove_content"},
        headers=admin,
    )
    assert response.status_code == 400
