"""Test fixtures.

Each test gets a fresh in-memory schema, so nothing leaks between them and
order never matters. R2 is stubbed by default — the suite must not need
credentials, and a test that reaches the network is a flaky test.
"""

import os

import pytest

os.environ.setdefault("TESTING", "true")
os.environ.setdefault("FLASK_ENV", "testing")
os.environ.setdefault("DATABASE_URL", "sqlite+pysqlite:///:memory:")

from app import create_app  # noqa: E402
from app.config import Config  # noqa: E402
from app.extensions import db as _db  # noqa: E402
from app.models import Artist, User, UserRole, Venue  # noqa: E402
from app.utils.handles import handle_base, unique_handle  # noqa: E402
from app.utils.passwords import hash_password  # noqa: E402
from app.utils.slugs import unique_slug  # noqa: E402

# SQLite by default so the suite runs anywhere with no setup. Point
# TEST_DATABASE_URL at a scratch Postgres to run the same tests against the
# real dialect — enums, TIMESTAMPTZ and native UUID all behave differently
# there, and a green SQLite run is not proof the Postgres one passes.
TEST_DATABASE_URL = os.environ.get("TEST_DATABASE_URL", "sqlite+pysqlite:///:memory:")


class TestConfig(Config):
    TESTING = True
    IS_DEVELOPMENT = True
    SQLALCHEMY_DATABASE_URI = TEST_DATABASE_URL
    # A single connection so an in-memory SQLite database is visible to every
    # session in the test, not recreated empty per checkout.
    SQLALCHEMY_ENGINE_OPTIONS = (
        {"poolclass": None} if TEST_DATABASE_URL.startswith("sqlite") else {}
    )
    SECRET_KEY = "test-secret"
    JWT_SECRET = "test-jwt-secret-that-is-long-enough-32"
    SESSION_COOKIE_SECURE = False
    RATELIMIT_ENABLED = False
    # The timing floor is a real defence in production; in tests it would add
    # half a second to every "send me a link" case for no benefit.
    EMAIL_RESPONSE_FLOOR_SECONDS = 0.0
    R2_BUCKET = "test-bucket"
    R2_ENDPOINT_URL = "https://accountid.r2.cloudflarestorage.com"
    R2_ACCESS_KEY_ID = "test-access-key"
    R2_SECRET_ACCESS_KEY = "test-secret-key"
    R2_PUBLIC_BASE_URL = ""


@pytest.fixture(autouse=True)
def _reset_process_state():
    """Clear the process-wide budgets and caches between tests.

    The per-recipient email budget and the geocoding cache/budget are module
    level by design — they bound spend across a whole worker. That makes them
    shared mutable state for a test suite, so one test's sends would otherwise
    exhaust the next test's allowance.
    """
    from app.services.email_service import reset_recipient_budget
    from app.services.geocoding import clear_cache, reset_budget

    reset_recipient_budget()
    clear_cache()
    reset_budget()
    yield


@pytest.fixture()
def app():
    application = create_app(TestConfig)
    with application.app_context():
        _db.create_all()
        yield application
        _db.session.remove()
        _db.drop_all()


@pytest.fixture()
def db(app):  # noqa: ARG001 - app must be built first
    return _db


@pytest.fixture()
def client(app):
    return app.test_client()


# ── Factories ──────────────────────────────────────────────────────────────


@pytest.fixture()
def make_user(db):
    def _make(email="reader@example.com", password="correct-horse-battery",
              role=UserRole.LISTENER, display_name="Reader", handle=None):
        user = User(
            email=email.lower(),
            password_hash=hash_password(password),
            display_name=display_name,
            handle=handle or unique_handle(
                db.session, handle_base(email.split("@", 1)[0], fallback="reader")
            ),
            role=role,
        )
        db.session.add(user)
        db.session.commit()
        return user

    return _make


@pytest.fixture()
def make_artist(db):
    def _make(owner, name="Bloodroot Choir", **kwargs):
        artist = Artist(
            owner_user_id=owner.id,
            name=name,
            slug=unique_slug(db.session, Artist, name),
            city=kwargs.pop("city", "Providence"),
            **kwargs,
        )
        db.session.add(artist)
        db.session.commit()
        return artist

    return _make


@pytest.fixture()
def make_venue(db):
    def _make(name="Dusk", city="Providence", latitude=41.8180, longitude=-71.4460,
              timezone_name="America/New_York", **kwargs):
        venue = Venue(
            name=name,
            slug=unique_slug(db.session, Venue, f"{name}-{city}"),
            city=city,
            latitude=latitude,
            longitude=longitude,
            timezone_name=timezone_name,
            **kwargs,
        )
        db.session.add(venue)
        db.session.commit()
        return venue

    return _make


@pytest.fixture()
def make_event(db, make_venue):
    """Shared event factory — the social suites all need listings to hang
    comments, reviews and lists off."""
    from datetime import timedelta

    from app.models import AgeRestriction, Event, EventStatus, Genre, utcnow

    def _make(artist=None, venue=None, hours_ahead=3, status=EventStatus.PUBLISHED,
              headline="Bloodroot Choir", genre=Genre.ROCK_PUNK, price_cents=1200,
              created_by=None, **kwargs):
        venue = venue or make_venue()
        event = Event(
            artist_id=artist.id if artist else None,
            venue_id=venue.id,
            created_by_user_id=created_by.id if created_by else None,
            headline=headline,
            genre=genre,
            starts_at=utcnow() + timedelta(hours=hours_ahead),
            price_cents=price_cents,
            age_restriction=AgeRestriction.TWENTY_ONE_PLUS,
            status=status,
            published_at=utcnow() if status is EventStatus.PUBLISHED else None,
            **kwargs,
        )
        db.session.add(event)
        db.session.commit()
        return event

    return _make


@pytest.fixture()
def auth(client):
    """Register a user through the real endpoint and return its bearer header.

    Going through the API rather than inserting rows means the token, the
    cookies and the password policy are all exercised on every test that needs
    a signed-in caller.
    """

    def _auth(email="reader@example.com", password="correct-horse-battery",
              display_name="Reader"):
        response = client.post(
            "/api/v1/auth/register",
            json={"email": email, "password": password, "display_name": display_name},
        )
        assert response.status_code == 201, response.get_json()
        token = response.get_json()["data"]["access_token"]
        return {"Authorization": f"Bearer {token}"}

    return _auth


@pytest.fixture()
def stub_r2(monkeypatch):
    """Replace R2 with an in-memory bucket.

    Records what was signed and what 'exists', so completion tests can assert
    on the real code path without a network call.
    """
    from app.services import r2_storage

    state = {"objects": {}, "signed": [], "deleted": []}

    def _presigned_put(key, content_type, expires_in=None):  # noqa: ARG001
        state["signed"].append({"key": key, "content_type": content_type})
        return f"https://accountid.r2.cloudflarestorage.com/test-bucket/{key}"

    def _head(key):
        return state["objects"].get(key)

    def _delete(key):
        state["deleted"].append(key)
        state["objects"].pop(key, None)
        return True

    def _presigned_get(key, expires_in=None):  # noqa: ARG001
        return f"https://signed.example/{key}?sig=stub"

    monkeypatch.setattr(
        r2_storage.R2Storage, "generate_presigned_put", staticmethod(_presigned_put)
    )
    monkeypatch.setattr(r2_storage.R2Storage, "head_object", staticmethod(_head))
    monkeypatch.setattr(r2_storage.R2Storage, "delete_object", staticmethod(_delete))
    monkeypatch.setattr(
        r2_storage.R2Storage, "generate_presigned_get", staticmethod(_presigned_get)
    )
    monkeypatch.setattr(r2_storage.R2Storage, "is_configured", staticmethod(lambda: True))

    def put(key, *, size_bytes=1024, content_type="audio/mpeg"):
        """Simulate the client's direct upload landing in the bucket."""
        state["objects"][key] = {"size_bytes": size_bytes, "content_type": content_type,
                                 "etag": "stub"}

    state["put"] = put
    return state
