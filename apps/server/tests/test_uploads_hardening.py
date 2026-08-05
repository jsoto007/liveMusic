"""Regressions for the upload defects found in the 2026-08-03 review.

The concurrency findings were reproduced against real Postgres; SQLite cannot
exhibit them because the suite pins a single connection. What is asserted here
is the *mechanism* that closes them — the atomic claim, the lock, the sweep
bookkeeping — which is testable on either backend.
"""

from datetime import timedelta

import pytest

from app.extensions import db
from app.models import Artist, AudioSample, MediaUpload, UploadStatus, utcnow


@pytest.fixture()
def band(client, auth, db):
    headers = auth(email="band@example.com")
    response = client.post(
        "/api/v1/me/artists", json={"name": "Bloodroot Choir"}, headers=headers
    )
    assert response.status_code == 201
    import uuid

    artist_id = response.get_json()["data"]["artist"]["id"]
    return headers, db.session.get(Artist, uuid.UUID(artist_id))


def request_upload(client, headers, artist, **overrides):
    payload = {
        "purpose": "artist_audio",
        "target_id": str(artist.id),
        "content_type": "audio/mpeg",
    }
    payload.update(overrides)
    return client.post("/api/v1/uploads", json=payload, headers=headers)


def complete(client, headers, upload_id, **body):
    return client.post(f"/api/v1/uploads/{upload_id}/complete", json=body, headers=headers)


# ── The signature must not outlive the ticket ──────────────────────────────


def test_the_presigned_url_expires_with_the_ticket(client, band, stub_r2, app, monkeypatch):
    """Left on the shared R2_SIGNED_URL_TTL the signature had a lifetime
    independent of the ticket, so bytes could land after the row was closed."""
    captured = {}

    from app.services import r2_storage

    def _capture(key, content_type, expires_in=None):
        captured["expires_in"] = expires_in
        return f"https://r2.example/bucket/{key}"

    monkeypatch.setattr(
        r2_storage.R2Storage, "generate_presigned_put", staticmethod(_capture)
    )

    headers, artist = band
    request_upload(client, headers, artist)
    assert captured["expires_in"] == app.config["UPLOAD_TICKET_TTL_SECONDS"]


# ── Completion is one-shot by logic, not by accident of schema ─────────────


def test_a_second_completion_is_refused_cleanly_not_with_a_500(client, band, stub_r2):
    headers, artist = band
    data = request_upload(client, headers, artist).get_json()["data"]
    stub_r2["put"](data["key"])

    assert complete(client, headers, data["upload_id"]).status_code == 201
    second = complete(client, headers, data["upload_id"])

    assert second.status_code == 409
    assert second.get_json()["error"]["code"] == "ALREADY_COMPLETED"
    assert db.session.query(AudioSample).count() == 1


def test_the_ticket_is_claimed_before_the_attach_runs(client, band, stub_r2):
    """The claim happens up front, so a failure afterwards leaves the ticket
    closed rather than replayable."""
    headers, artist = band
    data = request_upload(client, headers, artist).get_json()["data"]
    # Never uploaded, so the HEAD finds nothing.
    assert complete(client, headers, data["upload_id"]).status_code == 409

    import uuid

    ticket = db.session.get(MediaUpload, uuid.UUID(data["upload_id"]))
    assert ticket.status is UploadStatus.COMPLETED
    assert complete(client, headers, data["upload_id"]).status_code == 409


# ── The sweeper must not lose objects ──────────────────────────────────────


def test_the_sweeper_retries_when_the_delete_fails(client, band, stub_r2, monkeypatch):
    """Marking the row regardless meant one R2 hiccup permanently orphaned the
    whole batch — the sweep query would never look at it again."""
    from app.services import r2_storage
    from app.services.upload_sweeper import sweep_abandoned_uploads

    headers, artist = band
    data = request_upload(client, headers, artist).get_json()["data"]
    stub_r2["put"](data["key"])

    import uuid

    ticket = db.session.get(MediaUpload, uuid.UUID(data["upload_id"]))
    ticket.expires_at = utcnow() - timedelta(hours=2)
    db.session.commit()

    monkeypatch.setattr(r2_storage.R2Storage, "delete_object", staticmethod(lambda key: False))
    result = sweep_abandoned_uploads()

    assert result["objects_deleted"] == 0
    assert result["retry"] == 1
    db.session.refresh(ticket)
    assert ticket.swept_at is None, "an unconfirmed delete must stay sweepable"

    # A later sweep, once R2 is healthy, reclaims it.
    monkeypatch.setattr(r2_storage.R2Storage, "delete_object", staticmethod(lambda key: True))
    assert sweep_abandoned_uploads()["objects_deleted"] == 1
    db.session.refresh(ticket)
    assert ticket.swept_at is not None


def test_abandon_then_upload_leaves_the_object_reclaimable(client, band, stub_r2):
    """Abandoning before uploading used to delete nothing (the object did not
    exist yet), mark the ticket ABANDONED, and hide it from a sweeper that
    only looked at PENDING rows."""
    from app.services.upload_sweeper import sweep_abandoned_uploads

    headers, artist = band
    data = request_upload(client, headers, artist).get_json()["data"]
    key = data["key"]

    client.delete(f"/api/v1/uploads/{data['upload_id']}", headers=headers)
    # The client races in with the bytes afterwards.
    stub_r2["put"](key)

    import uuid

    ticket = db.session.get(MediaUpload, uuid.UUID(data["upload_id"]))
    ticket.expires_at = utcnow() - timedelta(hours=2)
    db.session.commit()

    result = sweep_abandoned_uploads()
    assert result["objects_deleted"] == 1
    assert key in stub_r2["deleted"]


def test_a_completed_ticket_is_never_swept(client, band, stub_r2):
    """Its object is referenced by a durable row."""
    from app.services.upload_sweeper import sweep_abandoned_uploads

    headers, artist = band
    data = request_upload(client, headers, artist).get_json()["data"]
    key = data["key"]
    stub_r2["put"](key)
    complete(client, headers, data["upload_id"])

    import uuid

    ticket = db.session.get(MediaUpload, uuid.UUID(data["upload_id"]))
    ticket.expires_at = utcnow() - timedelta(days=1)
    db.session.commit()

    assert sweep_abandoned_uploads()["tickets"] == 0
    assert key not in stub_r2["deleted"]


# ── Quota ──────────────────────────────────────────────────────────────────


def test_the_quota_counts_samples_and_live_tickets_together(client, band, stub_r2, app):
    headers, artist = band
    quota = app.config["AUDIO_SAMPLES_PER_ARTIST"]

    # Half as finished samples, half as outstanding tickets.
    for _ in range(quota // 2):
        data = request_upload(client, headers, artist).get_json()["data"]
        stub_r2["put"](data["key"])
        assert complete(client, headers, data["upload_id"]).status_code == 201
    for _ in range(quota - quota // 2):
        assert request_upload(client, headers, artist).status_code == 201

    refused = request_upload(client, headers, artist)
    assert refused.status_code == 409
    assert refused.get_json()["error"]["code"] == "LIMIT_REACHED"


def test_the_completion_side_also_enforces_the_quota(client, band, stub_r2, app, db):
    """An expired ticket frees quota at issue time; completion must still
    refuse to exceed it."""
    headers, artist = band
    quota = app.config["AUDIO_SAMPLES_PER_ARTIST"]

    data = request_upload(client, headers, artist).get_json()["data"]
    stub_r2["put"](data["key"])

    # Fill the quota behind the ticket's back.
    for index in range(quota):
        db.session.add(
            AudioSample(
                artist_id=artist.id,
                title=f"Filler {index}",
                object_key=f"artists/audio/{artist.id}/filler{index}.mp3",
                content_type="audio/mpeg",
                size_bytes=1024,
                position=index,
            )
        )
    db.session.commit()

    response = complete(client, headers, data["upload_id"])
    assert response.status_code == 409
    assert db.session.query(AudioSample).count() == quota
