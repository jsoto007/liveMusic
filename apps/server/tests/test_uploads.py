"""The direct-to-R2 upload path, written to break it.

Every test here corresponds to a way a caller could try to get bytes into the
bucket, or a row into the database, that it is not entitled to.
"""

from datetime import timedelta

import pytest

from app.extensions import db
from app.models import (
    Artist,
    AudioSample,
    Event,
    MediaUpload,
    UploadStatus,
    utcnow,
)


@pytest.fixture()
def band(client, auth, db):
    """A signed-in user who owns a band. Returns (headers, artist)."""
    headers = auth(email="band@example.com")
    response = client.post(
        "/api/v1/me/artists", json={"name": "Bloodroot Choir"}, headers=headers
    )
    assert response.status_code == 201
    artist_id = response.get_json()["data"]["artist"]["id"]
    import uuid

    return headers, db.session.get(Artist, uuid.UUID(artist_id))


def request_upload(client, headers, artist, **overrides):
    payload = {
        "purpose": "artist_audio",
        "target_id": str(artist.id),
        "content_type": "audio/mpeg",
        "size_bytes": 2048,
    }
    payload.update(overrides)
    return client.post("/api/v1/uploads", json=payload, headers=headers)


# ── Issuing a ticket ───────────────────────────────────────────────────────


def test_upload_returns_a_presigned_put_not_an_api_upload_url(client, band, stub_r2):
    headers, artist = band
    response = request_upload(client, headers, artist)
    assert response.status_code == 201

    data = response.get_json()["data"]
    assert data["url"].startswith("https://")
    assert data["headers"]["Content-Type"] == "audio/mpeg"
    # The client uploads to R2 directly; the API must not be in the byte path.
    assert "/api/" not in data["url"]


def test_the_server_chooses_the_object_key(client, band, stub_r2):
    """A client-chosen key could target another band's prefix, or escape the
    namespace entirely."""
    headers, artist = band
    request_upload(
        client, headers, artist, object_key="../../etc/passwd", key="anything-i-like"
    )

    signed = stub_r2["signed"][0]["key"]
    assert signed.startswith(f"artists/audio/{artist.id}/")
    assert ".." not in signed
    assert signed.endswith(".mp3")


def test_the_ticket_carries_the_size_cap_for_completion_to_enforce(client, band, stub_r2, app):
    """A presigned PUT cannot bound size itself, unlike the POST condition it
    replaced — the cap travels on the ticket instead, for the HEAD check at
    completion to enforce (see test_an_oversized_object_is_rejected_and_deleted)."""
    headers, artist = band
    response = request_upload(client, headers, artist)
    assert response.get_json()["data"]["max_bytes"] == app.config["AUDIO_MAX_BYTES"]


def test_uploading_requires_authentication(client, band, stub_r2):
    _headers, artist = band
    response = client.post(
        "/api/v1/uploads",
        json={"purpose": "artist_audio", "target_id": str(artist.id),
              "content_type": "audio/mpeg"},
    )
    assert response.status_code == 401


def test_cannot_upload_to_a_band_you_do_not_own(client, band, auth, stub_r2):
    _owner_headers, artist = band
    intruder = auth(email="intruder@example.com")

    response = request_upload(client, intruder, artist)
    assert response.status_code == 404
    assert stub_r2["signed"] == [], "nothing may be signed for an unauthorized target"


def test_executable_content_type_is_rejected(client, band, stub_r2):
    headers, artist = band
    response = request_upload(client, headers, artist, content_type="application/x-httpd-php")
    assert response.status_code == 415
    assert stub_r2["signed"] == []


def test_image_type_is_rejected_for_an_audio_purpose(client, band, stub_r2):
    headers, artist = band
    response = request_upload(client, headers, artist, content_type="image/png")
    assert response.status_code == 415


def test_declared_size_above_the_cap_is_rejected(client, band, stub_r2, app):
    headers, artist = band
    response = request_upload(
        client, headers, artist, size_bytes=app.config["AUDIO_MAX_BYTES"] + 1
    )
    assert response.status_code == 400


def test_sample_quota_counts_pending_tickets(client, band, stub_r2, app):
    """Otherwise a caller sitting on the quota could mint unlimited tickets and
    redeem them all at once."""
    headers, artist = band
    quota = app.config["AUDIO_SAMPLES_PER_ARTIST"]

    for _ in range(quota):
        assert request_upload(client, headers, artist).status_code == 201

    response = request_upload(client, headers, artist)
    assert response.status_code == 409
    assert response.get_json()["error"]["code"] == "LIMIT_REACHED"


def test_upload_is_unavailable_when_r2_is_not_configured(client, band, monkeypatch):
    from app.services import r2_storage

    headers, artist = band
    monkeypatch.setattr(r2_storage.R2Storage, "is_configured", staticmethod(lambda: False))

    response = request_upload(client, headers, artist)
    assert response.status_code == 503
    assert response.get_json()["error"]["code"] == "STORAGE_UNAVAILABLE"


# ── Completing ─────────────────────────────────────────────────────────────


def complete(client, headers, upload_id, **body):
    return client.post(f"/api/v1/uploads/{upload_id}/complete", json=body, headers=headers)


def test_happy_path_creates_the_sample(client, band, stub_r2):
    headers, artist = band
    data = request_upload(client, headers, artist).get_json()["data"]
    stub_r2["put"](data["key"], size_bytes=4096, content_type="audio/mpeg")

    response = complete(
        client, headers, data["upload_id"], title="Practice Room, Take 2",
        duration_seconds=134,
    )
    assert response.status_code == 201

    sample = response.get_json()["data"]["sample"]
    assert sample["title"] == "Practice Room, Take 2"
    assert sample["duration_label"] == "2:14"
    assert sample["stream_url"].startswith("https://")

    row = db.session.query(AudioSample).one()
    assert row.artist_id == artist.id
    assert row.size_bytes == 4096


def test_completing_without_uploading_anything_fails(client, band, stub_r2):
    """The ticket is not proof the bytes arrived — only a HEAD is."""
    headers, artist = band
    data = request_upload(client, headers, artist).get_json()["data"]

    response = complete(client, headers, data["upload_id"])
    assert response.status_code == 409
    assert response.get_json()["error"]["code"] == "UPLOAD_NOT_FOUND"
    assert db.session.query(AudioSample).count() == 0


def test_an_oversized_object_is_rejected_and_deleted(client, band, stub_r2, app):
    """The HEAD check at completion is the only size gate PUT has."""
    headers, artist = band
    data = request_upload(client, headers, artist).get_json()["data"]
    key = data["key"]
    stub_r2["put"](key, size_bytes=app.config["AUDIO_MAX_BYTES"] + 1)

    response = complete(client, headers, data["upload_id"])
    assert response.status_code == 413
    assert key in stub_r2["deleted"], "the rejected object must not be left in the bucket"
    assert db.session.query(AudioSample).count() == 0


def test_a_content_type_swap_is_rejected(client, band, stub_r2):
    """Signed as audio, uploaded as HTML — the object is not what we allowed."""
    headers, artist = band
    data = request_upload(client, headers, artist).get_json()["data"]
    key = data["key"]
    stub_r2["put"](key, content_type="text/html")

    response = complete(client, headers, data["upload_id"])
    assert response.status_code == 415
    assert key in stub_r2["deleted"]


def test_a_ticket_cannot_be_completed_twice(client, band, stub_r2):
    headers, artist = band
    data = request_upload(client, headers, artist).get_json()["data"]
    stub_r2["put"](data["key"])

    assert complete(client, headers, data["upload_id"]).status_code == 201
    replay = complete(client, headers, data["upload_id"])
    assert replay.status_code == 409
    assert replay.get_json()["error"]["code"] == "ALREADY_COMPLETED"
    assert db.session.query(AudioSample).count() == 1


def test_another_user_cannot_complete_your_ticket(client, band, auth, stub_r2):
    headers, artist = band
    data = request_upload(client, headers, artist).get_json()["data"]
    stub_r2["put"](data["key"])

    intruder = auth(email="intruder@example.com")
    assert complete(client, intruder, data["upload_id"]).status_code == 404
    assert db.session.query(AudioSample).count() == 0


def test_an_expired_ticket_cannot_be_completed(client, band, stub_r2):
    headers, artist = band
    data = request_upload(client, headers, artist).get_json()["data"]
    stub_r2["put"](data["key"])

    import uuid

    ticket = db.session.get(MediaUpload, uuid.UUID(data["upload_id"]))
    ticket.expires_at = utcnow() - timedelta(minutes=1)
    db.session.commit()

    response = complete(client, headers, data["upload_id"])
    assert response.status_code == 410
    assert response.get_json()["error"]["code"] == "UPLOAD_EXPIRED"


def test_ownership_is_rechecked_at_completion(client, band, stub_r2, make_user):
    """The band could change hands between issuing and redeeming the ticket."""
    headers, artist = band
    data = request_upload(client, headers, artist).get_json()["data"]
    stub_r2["put"](data["key"])

    new_owner = make_user(email="newowner@example.com")
    artist.owner_user_id = new_owner.id
    db.session.commit()

    assert complete(client, headers, data["upload_id"]).status_code == 404


def test_sample_title_is_length_capped(client, band, stub_r2):
    headers, artist = band
    data = request_upload(client, headers, artist).get_json()["data"]
    stub_r2["put"](data["key"])

    response = complete(client, headers, data["upload_id"], title="x" * 500)
    assert response.status_code == 400


# ── Posters ────────────────────────────────────────────────────────────────


def test_poster_upload_attaches_to_the_event(client, band, stub_r2):
    from datetime import timedelta as td

    headers, artist = band
    created = client.post(
        "/api/v1/events",
        json={
            "headline": "Bloodroot Choir",
            "artist_id": str(artist.id),
            "starts_at": (utcnow() + td(days=1)).isoformat(),
            "venue": {"name": "Dusk", "city": "Providence"},
        },
        headers=headers,
    ).get_json()["data"]["event"]

    data = client.post(
        "/api/v1/uploads",
        json={"purpose": "event_poster", "target_id": created["id"],
              "content_type": "image/jpeg"},
        headers=headers,
    ).get_json()["data"]
    stub_r2["put"](data["key"], content_type="image/jpeg")

    response = complete(client, headers, data["upload_id"])
    assert response.status_code == 201
    assert response.get_json()["data"]["event"]["poster_url"]


def test_cannot_attach_a_poster_to_someone_elses_event(client, band, auth, stub_r2, db,
                                                       make_venue):
    headers, artist = band
    venue = make_venue()
    event = Event(
        venue_id=venue.id, headline="Someone else's show",
        starts_at=utcnow() + timedelta(days=1),
    )
    db.session.add(event)
    db.session.commit()

    response = client.post(
        "/api/v1/uploads",
        json={"purpose": "event_poster", "target_id": str(event.id),
              "content_type": "image/jpeg"},
        headers=headers,
    )
    assert response.status_code == 404


def test_can_manage_agrees_with_who_the_upload_route_actually_lets_in(
    client, band, auth, stub_r2, db, make_venue
):
    """The flag the client trusts and the rule the server enforces are one rule.

    This is the adversarial pairing, not two independent assertions: for each
    caller the serialized ``can_manage`` is compared against what
    ``POST /api/v1/uploads`` really does. A flag that says yes where the route
    says 404 is a button that breaks; a flag that says no where the route says
    yes silently removes a capability from its owner.
    """
    from datetime import timedelta as td

    headers, artist = band
    event_id = client.post(
        "/api/v1/events",
        json={
            "headline": "Bloodroot Choir",
            "artist_id": str(artist.id),
            "starts_at": (utcnow() + td(days=1)).isoformat(),
            "venue": {"name": "Dusk", "city": "Providence"},
        },
        headers=headers,
    ).get_json()["data"]["event"]["id"]

    client.post(f"/api/v1/events/{event_id}/publish", headers=headers)

    stranger = auth(email="stranger@example.com")

    for label, caller in (("owner", headers), ("stranger", stranger), ("anonymous", {})):
        detail = client.get(f"/api/v1/events/{event_id}", headers=caller)
        assert detail.status_code == 200, label
        claimed = detail.get_json()["data"]["event"]["can_manage"]

        attempt = client.post(
            "/api/v1/uploads",
            json={
                "purpose": "event_poster",
                "target_id": event_id,
                "content_type": "image/jpeg",
            },
            headers=caller,
        )
        permitted = attempt.status_code == 201

        assert claimed is permitted, (
            f"{label}: can_manage={claimed} but the upload route returned "
            f"{attempt.status_code}"
        )

    # And the owner's yes is a real yes, not merely a matching pair of noes.
    assert (
        client.get(f"/api/v1/events/{event_id}", headers=headers)
        .get_json()["data"]["event"]["can_manage"]
        is True
    )


def test_a_poster_can_be_replaced_after_the_show_is_posted(client, band, stub_r2):
    """The post flow tells a band it can add the poster later. It must be true.

    When the first upload failed the only message shown was "you can add it
    later" — with no route that did. This walks the recovery path: post the
    show with no poster, then attach one, then replace it.
    """
    from datetime import timedelta as td

    headers, artist = band
    event_id = client.post(
        "/api/v1/events",
        json={
            "headline": "Bloodroot Choir",
            "artist_id": str(artist.id),
            "starts_at": (utcnow() + td(days=1)).isoformat(),
            "venue": {"name": "Dusk", "city": "Providence"},
        },
        headers=headers,
    ).get_json()["data"]["event"]

    assert event_id["poster_url"] is None
    assert event_id["poster_credit"] is None
    assert event_id["can_manage"] is True

    keys = []
    for _ in range(2):
        ticket = client.post(
            "/api/v1/uploads",
            json={
                "purpose": "event_poster",
                "target_id": event_id["id"],
                "content_type": "image/jpeg",
            },
            headers=headers,
        ).get_json()["data"]
        stub_r2["put"](ticket["key"], content_type="image/jpeg")
        done = complete(client, headers, ticket["upload_id"])
        assert done.status_code == 201
        assert done.get_json()["data"]["event"]["poster_url"]
        keys.append(ticket["key"])

    assert keys[0] != keys[1], "a replacement must land on a fresh key"
    # The superseded object is reclaimed rather than billed forever.
    assert keys[0] in stub_r2["deleted"], stub_r2["deleted"]


def test_uploading_a_poster_clears_any_prior_attribution(client, band, stub_r2, db):
    """A poster this app attached from an openly-licensed source (see
    scripts/seed_real_nyc.py) carries a credit line. A band replacing it with
    their own photo must not have that credit survive onto an image it does
    not describe."""
    import uuid
    from datetime import timedelta as td

    headers, artist = band
    event_id = client.post(
        "/api/v1/events",
        json={
            "headline": "Bloodroot Choir",
            "artist_id": str(artist.id),
            "starts_at": (utcnow() + td(days=1)).isoformat(),
            "venue": {"name": "Dusk", "city": "Providence"},
        },
        headers=headers,
    ).get_json()["data"]["event"]["id"]

    event = db.session.get(Event, uuid.UUID(event_id))
    event.poster_key = "events/poster/seeded-by-script.jpg"
    event.poster_credit = "Some Photographer — Wikimedia Commons, CC BY-SA 4.0"
    db.session.commit()

    detail = client.get(f"/api/v1/events/{event_id}", headers=headers).get_json()["data"]["event"]
    assert detail["poster_credit"] == "Some Photographer — Wikimedia Commons, CC BY-SA 4.0"

    ticket = client.post(
        "/api/v1/uploads",
        json={"purpose": "event_poster", "target_id": event_id, "content_type": "image/jpeg"},
        headers=headers,
    ).get_json()["data"]
    stub_r2["put"](ticket["key"], content_type="image/jpeg")

    done = complete(client, headers, ticket["upload_id"])
    assert done.status_code == 201
    assert done.get_json()["data"]["event"]["poster_credit"] is None


# ── Housekeeping ───────────────────────────────────────────────────────────


def test_replacing_a_photo_deletes_the_previous_object(client, band, stub_r2):
    headers, artist = band

    def upload_photo():
        data = client.post(
            "/api/v1/uploads",
            json={"purpose": "artist_photo", "target_id": str(artist.id),
                  "content_type": "image/png"},
            headers=headers,
        ).get_json()["data"]
        stub_r2["put"](data["key"], content_type="image/png")
        complete(client, headers, data["upload_id"])
        return data["key"]

    first = upload_photo()
    upload_photo()
    assert first in stub_r2["deleted"], "the replaced photo must not linger in the bucket"


def test_sweeper_reclaims_expired_tickets(client, band, stub_r2, app):
    from app.services.upload_sweeper import sweep_abandoned_uploads

    headers, artist = band
    data = request_upload(client, headers, artist).get_json()["data"]
    key = data["key"]
    stub_r2["put"](key)

    import uuid

    ticket = db.session.get(MediaUpload, uuid.UUID(data["upload_id"]))
    ticket.expires_at = utcnow() - timedelta(hours=2)
    db.session.commit()

    result = sweep_abandoned_uploads()
    assert result["tickets"] == 1
    assert key in stub_r2["deleted"]

    db.session.refresh(ticket)
    assert ticket.status is UploadStatus.ABANDONED


def test_deleting_a_sample_removes_the_object(client, band, stub_r2):
    headers, artist = band
    data = request_upload(client, headers, artist).get_json()["data"]
    key = data["key"]
    stub_r2["put"](key)
    sample_id = complete(client, headers, data["upload_id"]).get_json()["data"]["sample"]["id"]

    response = client.delete(
        f"/api/v1/artists/{artist.id}/samples/{sample_id}", headers=headers
    )
    assert response.status_code == 200
    assert key in stub_r2["deleted"]
    assert db.session.query(AudioSample).count() == 0


def test_cannot_delete_another_bands_sample(client, band, auth, stub_r2, make_user,
                                            make_artist):
    headers, artist = band
    data = request_upload(client, headers, artist).get_json()["data"]
    stub_r2["put"](data["key"])
    sample_id = complete(client, headers, data["upload_id"]).get_json()["data"]["sample"]["id"]

    from app.models import User

    intruder_headers = auth(email="intruder@example.com")
    intruder_user = (
        db.session.query(User).filter_by(email="intruder@example.com").one()
    )
    intruder_band = make_artist(intruder_user, name="Kestrel")

    # Their own band id in the path, the victim's sample id in the tail.
    response = client.delete(
        f"/api/v1/artists/{intruder_band.id}/samples/{sample_id}", headers=intruder_headers
    )
    assert response.status_code == 404
    assert db.session.query(AudioSample).count() == 1
