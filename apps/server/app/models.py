"""Schema and invariants.

Conventions (see CLAUDE.md §5):

* UUID primary keys via ``sa.Uuid`` — native ``uuid`` on Postgres, CHAR(32) on
  SQLite, so the test suite and production share one model definition.
* Enums go through :func:`pg_enum`, which pins the stored label to the
  lowercase ``.value``. Raw SQL in a migration then uses the same literal the
  ORM does.
* Money is integer cents. ``NULL`` price means "not stated"; ``0`` means free.
* Timestamps are timezone-aware UTC, produced by :func:`utcnow`.
"""

import enum
import uuid
from datetime import datetime, timezone

import sqlalchemy as sa
from sqlalchemy.orm import relationship

from .extensions import db


def utcnow() -> datetime:
    """Aware UTC now.

    Never use ``datetime.utcnow()`` — it returns a *naive* datetime, which
    compares incorrectly (and silently) against the aware values these columns
    hold.
    """
    return datetime.now(timezone.utc)


def as_utc(value: datetime | None) -> datetime | None:
    """Force a datetime read back from the database to be aware.

    Postgres round-trips ``TIMESTAMPTZ`` as aware, but SQLite (the test
    backend) hands back a naive value for the same column. Comparing the two
    kinds raises ``TypeError`` at runtime, so every comparison against a stored
    timestamp goes through here. Values are stored UTC, so assuming UTC for a
    naive one is correct, not a guess.
    """
    if value is not None and value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value


def pg_enum(enum_cls, name: str):
    """A Postgres enum whose labels are the members' lowercase ``.value``.

    Without ``values_callable`` SQLAlchemy persists the member *name*
    (``PUBLISHED``) while Python code reads the value (``published``), which
    means every hand-written SQL literal has to remember to flip case. Pinning
    it here removes the trap entirely.
    """
    return sa.Enum(
        enum_cls,
        name=name,
        values_callable=lambda cls: [member.value for member in cls],
        native_enum=True,
    )


def _uuid_pk():
    return sa.Column(sa.Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4)


# ── Enums ──────────────────────────────────────────────────────────────────


class UserRole(str, enum.Enum):
    LISTENER = "listener"
    ARTIST = "artist"
    ADMIN = "admin"


class EventStatus(str, enum.Enum):
    DRAFT = "draft"
    PUBLISHED = "published"
    CANCELLED = "cancelled"


class AgeRestriction(str, enum.Enum):
    ALL_AGES = "all_ages"
    EIGHTEEN_PLUS = "18_plus"
    TWENTY_ONE_PLUS = "21_plus"


class Genre(str, enum.Enum):
    """The buckets the paper sets its listings in."""

    ROCK_PUNK = "rock_punk"
    JAZZ = "jazz"
    CLASSICAL = "classical"
    ELECTRONIC = "electronic"
    FOLK_COUNTRY = "folk_country"
    METAL = "metal"
    HIP_HOP = "hip_hop"
    GOSPEL_SOUL = "gospel_soul"
    OPEN_MIC = "open_mic"
    FESTIVAL = "festival"
    OTHER = "other"


GENRE_LABELS: dict[Genre, str] = {
    Genre.ROCK_PUNK: "Rock & punk",
    Genre.JAZZ: "Jazz",
    Genre.CLASSICAL: "Classical",
    Genre.ELECTRONIC: "Electronic",
    Genre.FOLK_COUNTRY: "Folk & country",
    Genre.METAL: "Metal",
    Genre.HIP_HOP: "Hip-hop",
    Genre.GOSPEL_SOUL: "Gospel & soul",
    Genre.OPEN_MIC: "Open mic",
    Genre.FESTIVAL: "Festival",
    Genre.OTHER: "Other",
}

AGE_LABELS: dict[AgeRestriction, str] = {
    AgeRestriction.ALL_AGES: "All ages",
    AgeRestriction.EIGHTEEN_PLUS: "18+",
    AgeRestriction.TWENTY_ONE_PLUS: "21+",
}


class EmailTokenPurpose(str, enum.Enum):
    VERIFY_EMAIL = "verify_email"
    RESET_PASSWORD = "reset_password"  # noqa: S105 - an enum label, not a secret


class EmailKind(str, enum.Enum):
    """Every kind of mail we send, and the switch a reader can turn off.

    Transactional kinds (verification, password reset, and anything about a
    show they have actually committed to) are deliberately NOT optional — a
    password reset that a preference could suppress is a support incident, and
    a reminder for a show you said you were going to is the thing you asked
    for. Only the discovery mail is opt-out.
    """

    VERIFY_EMAIL = "verify_email"
    RESET_PASSWORD = "reset_password"  # noqa: S105 - an enum label, not a secret
    NEW_SHOW_FROM_FOLLOWED = "new_show_from_followed"
    SHOW_REMINDER = "show_reminder"


#: Kinds a reader may switch off, and the preference column that governs each.
OPTIONAL_EMAIL_KINDS: dict[EmailKind, str] = {
    EmailKind.NEW_SHOW_FROM_FOLLOWED: "notify_new_shows",
    EmailKind.SHOW_REMINDER: "notify_show_reminders",
}


class UploadPurpose(str, enum.Enum):
    ARTIST_AUDIO = "artist_audio"
    ARTIST_PHOTO = "artist_photo"
    EVENT_POSTER = "event_poster"


class UploadStatus(str, enum.Enum):
    PENDING = "pending"
    COMPLETED = "completed"
    ABANDONED = "abandoned"


# ── Users and sessions ─────────────────────────────────────────────────────


class User(db.Model):
    __tablename__ = "users"

    id = _uuid_pk()
    # Stored lowercase; the unique index is on the stored value, so casing can
    # never create two accounts for one address.
    email = sa.Column(sa.String(255), nullable=False, unique=True, index=True)
    password_hash = sa.Column(sa.String(255), nullable=False)
    display_name = sa.Column(sa.String(80), nullable=False)
    role = sa.Column(
        pg_enum(UserRole, "user_role"), nullable=False, default=UserRole.LISTENER
    )
    home_city = sa.Column(sa.String(120), nullable=True)
    is_active = sa.Column(sa.Boolean, nullable=False, default=True)
    email_verified_at = sa.Column(sa.DateTime(timezone=True), nullable=True)
    failed_login_count = sa.Column(sa.Integer, nullable=False, default=0)
    locked_until = sa.Column(sa.DateTime(timezone=True), nullable=True)
    # Every access token issued before this instant is refused. Revoking
    # refresh tokens alone left already-issued access tokens working for their
    # full lifetime, so "sign out everywhere" — the control someone reaches for
    # when a device is stolen — did not actually sign anyone out. Set it on
    # sign-out-everywhere, on lockout, and on any future password change.
    sessions_invalidated_at = sa.Column(sa.DateTime(timezone=True), nullable=True)

    # ── Email preferences ─────────────────────────────────────────────────
    # Opt-out, not opt-in: someone who follows a band has asked to hear about
    # it. Only the discovery mail is governed here — see EmailKind.
    notify_new_shows = sa.Column(sa.Boolean, nullable=False, default=True)
    notify_show_reminders = sa.Column(sa.Boolean, nullable=False, default=True)
    # The master switch a one-click unsubscribe sets. Checked before every
    # optional kind, so honouring it can never be forgotten per-kind.
    unsubscribed_all_at = sa.Column(sa.DateTime(timezone=True), nullable=True)

    created_at = sa.Column(sa.DateTime(timezone=True), nullable=False, default=utcnow)
    updated_at = sa.Column(
        sa.DateTime(timezone=True), nullable=False, default=utcnow, onupdate=utcnow
    )

    artists = relationship("Artist", back_populates="owner", cascade="all, delete-orphan")
    refresh_tokens = relationship(
        "RefreshToken", back_populates="user", cascade="all, delete-orphan"
    )
    email_tokens = relationship(
        "EmailToken", back_populates="user", cascade="all, delete-orphan"
    )

    def accepts(self, kind: "EmailKind") -> bool:
        """Whether this reader should receive mail of ``kind``.

        Transactional kinds always pass. Optional ones require both the master
        switch and the per-kind switch — a reader who unsubscribed from
        everything must not keep receiving one category because a preference
        column happened to still be True.
        """
        column = OPTIONAL_EMAIL_KINDS.get(kind)
        if column is None:
            return True
        if self.unsubscribed_all_at is not None:
            return False
        return bool(getattr(self, column, False))

    @property
    def is_locked(self) -> bool:
        locked_until = as_utc(self.locked_until)
        return bool(locked_until and locked_until > utcnow())


class RefreshToken(db.Model):
    """One row per issued refresh token, so a token can be revoked server-side.

    Only the SHA-256 of the token is stored: a database read alone must not
    hand an attacker a working session. Rotation links each token to its
    predecessor through ``family_id``; presenting an already-rotated token
    means it leaked, and the whole family is revoked.
    """

    __tablename__ = "refresh_tokens"

    id = _uuid_pk()
    user_id = sa.Column(
        sa.Uuid(as_uuid=True), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    token_hash = sa.Column(sa.String(64), nullable=False, unique=True, index=True)
    family_id = sa.Column(sa.Uuid(as_uuid=True), nullable=False, index=True)
    expires_at = sa.Column(sa.DateTime(timezone=True), nullable=False)
    revoked_at = sa.Column(sa.DateTime(timezone=True), nullable=True)
    rotated_to_id = sa.Column(sa.Uuid(as_uuid=True), nullable=True)
    user_agent = sa.Column(sa.String(200), nullable=True)
    created_at = sa.Column(sa.DateTime(timezone=True), nullable=False, default=utcnow)

    user = relationship("User", back_populates="refresh_tokens")

    __table_args__ = (
        sa.Index("ix_refresh_tokens_user_active", "user_id", "revoked_at"),
    )

    @property
    def is_usable(self) -> bool:
        return self.revoked_at is None and as_utc(self.expires_at) > utcnow()


class EmailToken(db.Model):
    """A single-use, expiring token emailed to a reader.

    Only the SHA-256 is stored, exactly as for refresh tokens: the link lands
    in a mailbox and in server logs upstream of us, so a database read must
    not also hand over a working credential. Redeeming is a conditional UPDATE
    so a link cannot be used twice by two concurrent clicks — mail clients
    that prefetch links make that a real occurrence, not a theoretical one.
    """

    __tablename__ = "email_tokens"

    id = _uuid_pk()
    user_id = sa.Column(
        sa.Uuid(as_uuid=True), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False,
        index=True,
    )
    purpose = sa.Column(pg_enum(EmailTokenPurpose, "email_token_purpose"), nullable=False)
    token_hash = sa.Column(sa.String(64), nullable=False, unique=True, index=True)
    expires_at = sa.Column(sa.DateTime(timezone=True), nullable=False)
    used_at = sa.Column(sa.DateTime(timezone=True), nullable=True)
    created_at = sa.Column(sa.DateTime(timezone=True), nullable=False, default=utcnow)

    user = relationship("User", back_populates="email_tokens")

    __table_args__ = (
        sa.Index("ix_email_tokens_user_purpose", "user_id", "purpose", "used_at"),
    )

    @property
    def is_redeemable(self) -> bool:
        return self.used_at is None and as_utc(self.expires_at) > utcnow()


class EmailDelivery(db.Model):
    """One row per message actually handed to the transport.

    Two jobs. It is the audit trail for "did we email this person", which
    support will ask. And its unique constraint is what makes a notification
    idempotent — a scheduler that runs twice, or retries after a partial
    failure, must not mail the same reader about the same show again.
    """

    __tablename__ = "email_deliveries"

    id = _uuid_pk()
    user_id = sa.Column(
        sa.Uuid(as_uuid=True), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False,
        index=True,
    )
    kind = sa.Column(pg_enum(EmailKind, "email_kind"), nullable=False)
    # What the mail was about — an event id, an artist id. NULL for mail that
    # is not about a particular thing.
    subject_id = sa.Column(sa.Uuid(as_uuid=True), nullable=True)
    sent_at = sa.Column(sa.DateTime(timezone=True), nullable=False, default=utcnow)

    __table_args__ = (
        # The idempotency key. A partial unique index would be tidier but has
        # to hold across NULL subject_id too, so the tuple is used whole.
        sa.UniqueConstraint("user_id", "kind", "subject_id", name="uq_email_delivery_once"),
    )


# ── Artists ────────────────────────────────────────────────────────────────


class Artist(db.Model):
    __tablename__ = "artists"

    id = _uuid_pk()
    owner_user_id = sa.Column(
        sa.Uuid(as_uuid=True), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False,
        index=True,
    )
    name = sa.Column(sa.String(120), nullable=False)
    slug = sa.Column(sa.String(140), nullable=False, unique=True, index=True)
    city = sa.Column(sa.String(120), nullable=True)
    neighborhood = sa.Column(sa.String(120), nullable=True)
    one_liner = sa.Column(sa.String(300), nullable=True)
    bio = sa.Column(sa.Text, nullable=True)
    sounds_like = sa.Column(sa.String(300), nullable=True)
    # Free-form style tags ("Post-punk", "No wave"). JSON rather than ARRAY so
    # the same definition works on SQLite in tests.
    style_tags = sa.Column(sa.JSON, nullable=False, default=list)
    available_for_hire = sa.Column(sa.Boolean, nullable=False, default=False)
    photo_key = sa.Column(sa.String(400), nullable=True)
    verified_at = sa.Column(sa.DateTime(timezone=True), nullable=True)
    created_at = sa.Column(sa.DateTime(timezone=True), nullable=False, default=utcnow)
    updated_at = sa.Column(
        sa.DateTime(timezone=True), nullable=False, default=utcnow, onupdate=utcnow
    )

    owner = relationship("User", back_populates="artists")
    members = relationship(
        "ArtistMember",
        back_populates="artist",
        cascade="all, delete-orphan",
        order_by="ArtistMember.position",
    )
    samples = relationship(
        "AudioSample",
        back_populates="artist",
        cascade="all, delete-orphan",
        order_by="AudioSample.position",
    )
    events = relationship("Event", back_populates="artist")


class ArtistMember(db.Model):
    __tablename__ = "artist_members"

    id = _uuid_pk()
    artist_id = sa.Column(
        sa.Uuid(as_uuid=True), sa.ForeignKey("artists.id", ondelete="CASCADE"), nullable=False,
        index=True,
    )
    name = sa.Column(sa.String(120), nullable=False)
    instrument = sa.Column(sa.String(120), nullable=True)
    position = sa.Column(sa.Integer, nullable=False, default=0)

    artist = relationship("Artist", back_populates="members")


class ArtistFollow(db.Model):
    __tablename__ = "artist_follows"

    user_id = sa.Column(
        sa.Uuid(as_uuid=True), sa.ForeignKey("users.id", ondelete="CASCADE"), primary_key=True
    )
    artist_id = sa.Column(
        sa.Uuid(as_uuid=True), sa.ForeignKey("artists.id", ondelete="CASCADE"), primary_key=True
    )
    created_at = sa.Column(sa.DateTime(timezone=True), nullable=False, default=utcnow)

    __table_args__ = (sa.Index("ix_artist_follows_artist", "artist_id"),)


class AudioSample(db.Model):
    """A sound sample on an artist's profile.

    ``object_key`` is an R2 key, never a URL — a playable URL is a short-lived
    presigned GET minted at serialization time. Caching a signed URL in the
    database would mean handing out an expired link forever after.
    """

    __tablename__ = "audio_samples"

    id = _uuid_pk()
    artist_id = sa.Column(
        sa.Uuid(as_uuid=True), sa.ForeignKey("artists.id", ondelete="CASCADE"), nullable=False,
        index=True,
    )
    title = sa.Column(sa.String(140), nullable=False)
    object_key = sa.Column(sa.String(400), nullable=False, unique=True)
    content_type = sa.Column(sa.String(100), nullable=False)
    size_bytes = sa.Column(sa.BigInteger, nullable=False)
    duration_seconds = sa.Column(sa.Integer, nullable=True)
    position = sa.Column(sa.Integer, nullable=False, default=0)
    created_at = sa.Column(sa.DateTime(timezone=True), nullable=False, default=utcnow)

    artist = relationship("Artist", back_populates="samples")


# ── Venues and events ──────────────────────────────────────────────────────


class Venue(db.Model):
    __tablename__ = "venues"

    id = _uuid_pk()
    name = sa.Column(sa.String(160), nullable=False)
    slug = sa.Column(sa.String(180), nullable=False, unique=True, index=True)
    address = sa.Column(sa.String(300), nullable=True)
    neighborhood = sa.Column(sa.String(120), nullable=True)
    city = sa.Column(sa.String(120), nullable=False, index=True)
    latitude = sa.Column(sa.Float, nullable=True)
    longitude = sa.Column(sa.Float, nullable=True)
    # IANA zone. An event's wall-clock time is what a reader cares about
    # ("9:00 PM"), and that is only recoverable from the venue's own zone —
    # never the server's.
    timezone_name = sa.Column(sa.String(64), nullable=False, default="UTC")
    created_at = sa.Column(sa.DateTime(timezone=True), nullable=False, default=utcnow)

    events = relationship("Event", back_populates="venue")

    __table_args__ = (sa.Index("ix_venues_city_geo", "city", "latitude", "longitude"),)


class Event(db.Model):
    __tablename__ = "events"

    id = _uuid_pk()
    artist_id = sa.Column(
        sa.Uuid(as_uuid=True), sa.ForeignKey("artists.id", ondelete="SET NULL"), nullable=True,
        index=True,
    )
    venue_id = sa.Column(
        sa.Uuid(as_uuid=True), sa.ForeignKey("venues.id", ondelete="RESTRICT"), nullable=False,
        index=True,
    )
    created_by_user_id = sa.Column(
        sa.Uuid(as_uuid=True), sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )

    # Headline billing as it should read in the paper. Denormalised from the
    # artist on purpose: a listing may name an act that has no account, and an
    # artist renaming itself must not silently rewrite last year's listings.
    headline = sa.Column(sa.String(160), nullable=False)
    support_line = sa.Column(sa.String(300), nullable=True)
    genre = sa.Column(pg_enum(Genre, "genre"), nullable=False, default=Genre.OTHER, index=True)

    starts_at = sa.Column(sa.DateTime(timezone=True), nullable=False, index=True)
    doors_at = sa.Column(sa.DateTime(timezone=True), nullable=True)

    price_cents = sa.Column(sa.Integer, nullable=True)
    age_restriction = sa.Column(
        pg_enum(AgeRestriction, "age_restriction"),
        nullable=False,
        default=AgeRestriction.ALL_AGES,
    )
    ticket_url = sa.Column(sa.String(500), nullable=True)

    short_line = sa.Column(sa.String(300), nullable=True)
    blurb = sa.Column(sa.Text, nullable=True)
    poster_key = sa.Column(sa.String(400), nullable=True)

    status = sa.Column(
        pg_enum(EventStatus, "event_status"), nullable=False, default=EventStatus.DRAFT,
        index=True,
    )
    published_at = sa.Column(sa.DateTime(timezone=True), nullable=True)
    cancelled_at = sa.Column(sa.DateTime(timezone=True), nullable=True)
    created_at = sa.Column(sa.DateTime(timezone=True), nullable=False, default=utcnow)
    updated_at = sa.Column(
        sa.DateTime(timezone=True), nullable=False, default=utcnow, onupdate=utcnow
    )

    artist = relationship("Artist", back_populates="events")
    venue = relationship("Venue", back_populates="events")
    lineup = relationship(
        "EventLineupSlot",
        back_populates="event",
        cascade="all, delete-orphan",
        order_by="EventLineupSlot.position",
    )
    interests = relationship(
        "EventInterest", back_populates="event", cascade="all, delete-orphan"
    )

    __table_args__ = (
        # The listings feed is always "published, in this window, soonest
        # first" — this is the index that query rides.
        sa.Index("ix_events_status_starts_at", "status", "starts_at"),
        sa.CheckConstraint(
            "price_cents IS NULL OR price_cents >= 0", name="ck_events_price_non_negative"
        ),
        sa.CheckConstraint(
            "doors_at IS NULL OR doors_at <= starts_at", name="ck_events_doors_before_start"
        ),
    )

    @property
    def is_visible(self) -> bool:
        return self.status is EventStatus.PUBLISHED


class EventLineupSlot(db.Model):
    __tablename__ = "event_lineup_slots"

    id = _uuid_pk()
    event_id = sa.Column(
        sa.Uuid(as_uuid=True), sa.ForeignKey("events.id", ondelete="CASCADE"), nullable=False,
        index=True,
    )
    name = sa.Column(sa.String(160), nullable=False)
    note = sa.Column(sa.String(200), nullable=True)
    starts_at = sa.Column(sa.DateTime(timezone=True), nullable=True)
    position = sa.Column(sa.Integer, nullable=False, default=0)

    event = relationship("Event", back_populates="lineup")


class EventInterest(db.Model):
    """A reader's relationship to a listing.

    ``saved`` (kept for later) and ``going`` are independent — the prototype
    lists them as separate sections and a reader can hold both at once — so
    they are two flags on one row rather than a single status.
    """

    __tablename__ = "event_interests"

    user_id = sa.Column(
        sa.Uuid(as_uuid=True), sa.ForeignKey("users.id", ondelete="CASCADE"), primary_key=True
    )
    event_id = sa.Column(
        sa.Uuid(as_uuid=True), sa.ForeignKey("events.id", ondelete="CASCADE"), primary_key=True
    )
    saved = sa.Column(sa.Boolean, nullable=False, default=False)
    going = sa.Column(sa.Boolean, nullable=False, default=False)
    updated_at = sa.Column(
        sa.DateTime(timezone=True), nullable=False, default=utcnow, onupdate=utcnow
    )

    event = relationship("Event", back_populates="interests")

    __table_args__ = (sa.Index("ix_event_interests_event", "event_id"),)


# ── Media uploads ──────────────────────────────────────────────────────────


class MediaUpload(db.Model):
    """A one-shot ticket for a direct-to-R2 upload.

    The server mints the key (a client never chooses where its bytes land),
    records the exact content type and byte cap it signed for, and refuses to
    complete an upload whose object does not match. The row is the audit trail
    for a byte stream the API never sees.
    """

    __tablename__ = "media_uploads"

    id = _uuid_pk()
    user_id = sa.Column(
        sa.Uuid(as_uuid=True), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False,
        index=True,
    )
    purpose = sa.Column(pg_enum(UploadPurpose, "upload_purpose"), nullable=False)
    # The artist or event the finished object attaches to. Re-checked at
    # completion — a ticket cannot be redirected onto another owner's record.
    target_id = sa.Column(sa.Uuid(as_uuid=True), nullable=True)
    object_key = sa.Column(sa.String(400), nullable=False, unique=True)
    content_type = sa.Column(sa.String(100), nullable=False)
    max_bytes = sa.Column(sa.BigInteger, nullable=False)
    declared_size_bytes = sa.Column(sa.BigInteger, nullable=True)
    status = sa.Column(
        pg_enum(UploadStatus, "upload_status"), nullable=False, default=UploadStatus.PENDING,
        index=True,
    )
    expires_at = sa.Column(sa.DateTime(timezone=True), nullable=False)
    completed_at = sa.Column(sa.DateTime(timezone=True), nullable=True)
    # Set only once the object is confirmed gone from R2. The sweeper used to
    # infer this from ``status``, which meant a failed delete still flipped the
    # row to ABANDONED and the object became permanently unreachable — the
    # sweep query filtered on PENDING, so it was never revisited. Tracking the
    # reclaim separately from the lifecycle lets a failed delete retry.
    swept_at = sa.Column(sa.DateTime(timezone=True), nullable=True)
    created_at = sa.Column(sa.DateTime(timezone=True), nullable=False, default=utcnow)

    __table_args__ = (
        sa.Index("ix_media_uploads_status_expires", "status", "expires_at"),
        sa.Index("ix_media_uploads_unswept", "swept_at", "expires_at"),
    )

    @property
    def is_redeemable(self) -> bool:
        return self.status is UploadStatus.PENDING and as_utc(self.expires_at) > utcnow()

    def is_redeemable_now(self) -> bool:
        """Expiry only — the status check has already been made by the caller.

        Completion claims the ticket with an atomic status update, so by the
        time the expiry is checked the status is no longer PENDING and
        :attr:`is_redeemable` would always be False.
        """
        return as_utc(self.expires_at) > utcnow()
