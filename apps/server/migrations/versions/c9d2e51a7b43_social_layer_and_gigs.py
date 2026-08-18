"""social layer and gigs

The social turn: public profiles (handle, bio, avatar), reader-to-reader
follows and blocks, named public/private event lists, flat comments with
likes and @mentions, post-show reviews, an in-app notification inbox,
content reports, and the classifieds board (gigs + applications).

Existing users are backfilled with a handle derived from their display name
(collisions broken with a slice of the row's own id), then the column goes
NOT NULL + unique. ``upload_purpose`` learns the ``user_avatar`` label —
enum values cannot be removed on Postgres, so the downgrade leaves that
label in place; a stray unused label is harmless, a type rebuild is not.

Revision ID: c9d2e51a7b43
Revises: 1e57efd27184
Create Date: 2026-08-17 11:40:00.000000

"""
import re
import unicodedata

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


# revision identifiers, used by Alembic.
revision = 'c9d2e51a7b43'
down_revision = '1e57efd27184'
branch_labels = None
depends_on = None


GENRES = (
    'rock_punk', 'jazz', 'classical', 'electronic', 'folk_country', 'metal',
    'hip_hop', 'gospel_soul', 'open_mic', 'festival', 'other',
)

# Inline copies of the handle helpers — a migration file is frozen once
# applied, so it must not import application code that keeps evolving.
_NON_HANDLE = re.compile(r"[^a-z0-9_]+")
_RESERVED = {
    "me", "you", "admin", "admins", "api", "search", "settings", "support",
    "moderator", "editor", "everyone", "livemsc", "live_msc", "themgmt",
}


def _handle_base(value, fallback="reader"):
    normalized = unicodedata.normalize("NFKD", value or "")
    ascii_only = normalized.encode("ascii", "ignore").decode("ascii").lower()
    base = _NON_HANDLE.sub("_", ascii_only).strip("_")[:24].strip("_")
    if len(base) < 3 or base in _RESERVED:
        return fallback
    return base


def _genre_type():
    """The existing ``genre`` type, reused by ``gigs``.

    On Postgres the type already exists (events created it), so it must be
    referenced without a CREATE TYPE; elsewhere sa.Enum degrades to VARCHAR
    and can simply be declared again.
    """
    if op.get_bind().dialect.name == "postgresql":
        return postgresql.ENUM(name="genre", create_type=False)
    return sa.Enum(*GENRES, name="genre")


def upgrade():
    bind = op.get_bind()

    # ── users: handle, bio, avatar ─────────────────────────────────────────
    with op.batch_alter_table('users', schema=None) as batch_op:
        batch_op.add_column(sa.Column('handle', sa.String(length=30), nullable=True))
        batch_op.add_column(sa.Column('bio', sa.Text(), nullable=True))
        batch_op.add_column(sa.Column('avatar_key', sa.String(length=400), nullable=True))

    # Backfill every existing account with a unique handle before the column
    # tightens to NOT NULL. Deterministic per row: the collision suffix is a
    # slice of the row's own id, so re-running against a partially-backfilled
    # database converges instead of reshuffling.
    rows = bind.execute(
        sa.text("SELECT id, display_name, email FROM users WHERE handle IS NULL")
    ).fetchall()
    taken = {
        row[0]
        for row in bind.execute(
            sa.text("SELECT handle FROM users WHERE handle IS NOT NULL")
        ).fetchall()
    }
    update = sa.text("UPDATE users SET handle = :handle WHERE id = :id")
    for row in rows:
        user_id, display_name, email = row[0], row[1], row[2]
        base = _handle_base(display_name or (email or "").split("@", 1)[0])
        id_hex = str(user_id).replace("-", "")
        candidate = base
        width = 4
        while candidate in taken:
            candidate = f"{base[:24]}_{id_hex[:width]}"
            width += 2
        taken.add(candidate)
        bind.execute(update, {"handle": candidate, "id": user_id})

    with op.batch_alter_table('users', schema=None) as batch_op:
        batch_op.alter_column('handle', existing_type=sa.String(length=30), nullable=False)
        batch_op.create_index(batch_op.f('ix_users_handle'), ['handle'], unique=True)

    # ── upload_purpose: user_avatar ────────────────────────────────────────
    if bind.dialect.name == "postgresql":
        op.execute("ALTER TYPE upload_purpose ADD VALUE IF NOT EXISTS 'user_avatar'")

    # ── social graph ───────────────────────────────────────────────────────
    op.create_table(
        'user_follows',
        sa.Column('follower_id', sa.Uuid(), nullable=False),
        sa.Column('followee_id', sa.Uuid(), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint('follower_id <> followee_id', name='ck_user_follows_not_self'),
        sa.ForeignKeyConstraint(['followee_id'], ['users.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['follower_id'], ['users.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('follower_id', 'followee_id'),
    )
    with op.batch_alter_table('user_follows', schema=None) as batch_op:
        batch_op.create_index('ix_user_follows_followee', ['followee_id'], unique=False)

    op.create_table(
        'user_blocks',
        sa.Column('blocker_id', sa.Uuid(), nullable=False),
        sa.Column('blocked_id', sa.Uuid(), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint('blocker_id <> blocked_id', name='ck_user_blocks_not_self'),
        sa.ForeignKeyConstraint(['blocked_id'], ['users.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['blocker_id'], ['users.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('blocker_id', 'blocked_id'),
    )
    with op.batch_alter_table('user_blocks', schema=None) as batch_op:
        batch_op.create_index('ix_user_blocks_blocked', ['blocked_id'], unique=False)

    # ── lists ──────────────────────────────────────────────────────────────
    op.create_table(
        'event_lists',
        sa.Column('id', sa.Uuid(), nullable=False),
        sa.Column('owner_user_id', sa.Uuid(), nullable=False),
        sa.Column('name', sa.String(length=80), nullable=False),
        sa.Column('description', sa.String(length=300), nullable=True),
        sa.Column('is_public', sa.Boolean(), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(['owner_user_id'], ['users.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('owner_user_id', 'name', name='uq_event_lists_owner_name'),
    )
    with op.batch_alter_table('event_lists', schema=None) as batch_op:
        batch_op.create_index(
            batch_op.f('ix_event_lists_owner_user_id'), ['owner_user_id'], unique=False
        )

    op.create_table(
        'event_list_items',
        sa.Column('list_id', sa.Uuid(), nullable=False),
        sa.Column('event_id', sa.Uuid(), nullable=False),
        sa.Column('note', sa.String(length=200), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(['event_id'], ['events.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['list_id'], ['event_lists.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('list_id', 'event_id'),
    )
    with op.batch_alter_table('event_list_items', schema=None) as batch_op:
        batch_op.create_index('ix_event_list_items_event', ['event_id'], unique=False)
        batch_op.create_index(
            'ix_event_list_items_created', ['list_id', 'created_at'], unique=False
        )

    # ── comments, likes, reviews ───────────────────────────────────────────
    op.create_table(
        'comments',
        sa.Column('id', sa.Uuid(), nullable=False),
        sa.Column('event_id', sa.Uuid(), nullable=False),
        sa.Column('author_user_id', sa.Uuid(), nullable=False),
        sa.Column('body', sa.Text(), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(['author_user_id'], ['users.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['event_id'], ['events.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
    )
    with op.batch_alter_table('comments', schema=None) as batch_op:
        batch_op.create_index(
            batch_op.f('ix_comments_author_user_id'), ['author_user_id'], unique=False
        )
        batch_op.create_index(batch_op.f('ix_comments_event_id'), ['event_id'], unique=False)
        batch_op.create_index('ix_comments_event_created', ['event_id', 'created_at'],
                              unique=False)

    op.create_table(
        'comment_likes',
        sa.Column('comment_id', sa.Uuid(), nullable=False),
        sa.Column('user_id', sa.Uuid(), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(['comment_id'], ['comments.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['user_id'], ['users.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('comment_id', 'user_id'),
    )
    with op.batch_alter_table('comment_likes', schema=None) as batch_op:
        batch_op.create_index('ix_comment_likes_user', ['user_id'], unique=False)

    op.create_table(
        'reviews',
        sa.Column('id', sa.Uuid(), nullable=False),
        sa.Column('event_id', sa.Uuid(), nullable=False),
        sa.Column('author_user_id', sa.Uuid(), nullable=False),
        sa.Column('rating', sa.SmallInteger(), nullable=False),
        sa.Column('body', sa.Text(), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint('rating >= 1 AND rating <= 5', name='ck_reviews_rating_range'),
        sa.ForeignKeyConstraint(['author_user_id'], ['users.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['event_id'], ['events.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('event_id', 'author_user_id', name='uq_reviews_event_author'),
    )
    with op.batch_alter_table('reviews', schema=None) as batch_op:
        batch_op.create_index(
            batch_op.f('ix_reviews_author_user_id'), ['author_user_id'], unique=False
        )
        batch_op.create_index(batch_op.f('ix_reviews_event_id'), ['event_id'], unique=False)

    # ── gigs ───────────────────────────────────────────────────────────────
    op.create_table(
        'gigs',
        sa.Column('id', sa.Uuid(), nullable=False),
        sa.Column('posted_by_user_id', sa.Uuid(), nullable=False),
        sa.Column('title', sa.String(length=160), nullable=False),
        sa.Column('description', sa.Text(), nullable=False),
        sa.Column('city', sa.String(length=120), nullable=False),
        sa.Column('neighborhood', sa.String(length=120), nullable=True),
        sa.Column('venue_name', sa.String(length=160), nullable=True),
        sa.Column('starts_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('timezone_name', sa.String(length=64), nullable=False),
        sa.Column('pay_cents', sa.Integer(), nullable=True),
        sa.Column('pay_note', sa.String(length=140), nullable=True),
        sa.Column('genre', _genre_type(), nullable=True),
        sa.Column(
            'status', sa.Enum('open', 'closed', name='gig_status'), nullable=False
        ),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint('pay_cents IS NULL OR pay_cents >= 0',
                           name='ck_gigs_pay_non_negative'),
        sa.ForeignKeyConstraint(['posted_by_user_id'], ['users.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
    )
    with op.batch_alter_table('gigs', schema=None) as batch_op:
        batch_op.create_index(batch_op.f('ix_gigs_city'), ['city'], unique=False)
        batch_op.create_index(
            batch_op.f('ix_gigs_posted_by_user_id'), ['posted_by_user_id'], unique=False
        )
        batch_op.create_index(batch_op.f('ix_gigs_status'), ['status'], unique=False)
        batch_op.create_index('ix_gigs_status_created', ['status', 'created_at'], unique=False)

    op.create_table(
        'gig_applications',
        sa.Column('id', sa.Uuid(), nullable=False),
        sa.Column('gig_id', sa.Uuid(), nullable=False),
        sa.Column('artist_id', sa.Uuid(), nullable=False),
        sa.Column('applicant_user_id', sa.Uuid(), nullable=False),
        sa.Column('message', sa.String(length=1000), nullable=True),
        sa.Column(
            'status',
            sa.Enum('pending', 'accepted', 'declined', name='gig_application_status'),
            nullable=False,
        ),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(['applicant_user_id'], ['users.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['artist_id'], ['artists.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['gig_id'], ['gigs.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('gig_id', 'artist_id', name='uq_gig_applications_gig_artist'),
    )
    with op.batch_alter_table('gig_applications', schema=None) as batch_op:
        batch_op.create_index(
            batch_op.f('ix_gig_applications_artist_id'), ['artist_id'], unique=False
        )
        batch_op.create_index(batch_op.f('ix_gig_applications_gig_id'), ['gig_id'],
                              unique=False)

    # ── notifications and reports ──────────────────────────────────────────
    op.create_table(
        'notifications',
        sa.Column('id', sa.Uuid(), nullable=False),
        sa.Column('user_id', sa.Uuid(), nullable=False),
        sa.Column(
            'kind',
            sa.Enum(
                'new_follower', 'event_comment', 'comment_like', 'mention',
                'event_review', 'gig_application', 'gig_accepted', 'gig_declined',
                name='notification_kind',
            ),
            nullable=False,
        ),
        sa.Column('actor_user_id', sa.Uuid(), nullable=True),
        sa.Column('event_id', sa.Uuid(), nullable=True),
        sa.Column('comment_id', sa.Uuid(), nullable=True),
        sa.Column('gig_id', sa.Uuid(), nullable=True),
        sa.Column('read_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(['actor_user_id'], ['users.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['comment_id'], ['comments.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['event_id'], ['events.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['gig_id'], ['gigs.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['user_id'], ['users.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
    )
    with op.batch_alter_table('notifications', schema=None) as batch_op:
        batch_op.create_index(batch_op.f('ix_notifications_user_id'), ['user_id'],
                              unique=False)
        batch_op.create_index('ix_notifications_user_created', ['user_id', 'created_at'],
                              unique=False)
        batch_op.create_index('ix_notifications_user_unread', ['user_id', 'read_at'],
                              unique=False)

    op.create_table(
        'content_reports',
        sa.Column('id', sa.Uuid(), nullable=False),
        sa.Column('reporter_user_id', sa.Uuid(), nullable=False),
        sa.Column('comment_id', sa.Uuid(), nullable=True),
        sa.Column('review_id', sa.Uuid(), nullable=True),
        sa.Column('reported_user_id', sa.Uuid(), nullable=True),
        sa.Column(
            'reason',
            sa.Enum('spam', 'harassment', 'inappropriate', 'other', name='report_reason'),
            nullable=False,
        ),
        sa.Column('detail', sa.String(length=500), nullable=True),
        sa.Column(
            'status',
            sa.Enum('open', 'resolved', 'dismissed', name='report_status'),
            nullable=False,
        ),
        sa.Column('resolved_by_user_id', sa.Uuid(), nullable=True),
        sa.Column('resolved_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            '(CASE WHEN comment_id IS NOT NULL THEN 1 ELSE 0 END'
            ' + CASE WHEN review_id IS NOT NULL THEN 1 ELSE 0 END'
            ' + CASE WHEN reported_user_id IS NOT NULL THEN 1 ELSE 0 END) <= 1',
            name='ck_content_reports_one_subject',
        ),
        sa.ForeignKeyConstraint(['comment_id'], ['comments.id'], ondelete='SET NULL'),
        sa.ForeignKeyConstraint(['reported_user_id'], ['users.id'], ondelete='SET NULL'),
        sa.ForeignKeyConstraint(['reporter_user_id'], ['users.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['resolved_by_user_id'], ['users.id'], ondelete='SET NULL'),
        sa.ForeignKeyConstraint(['review_id'], ['reviews.id'], ondelete='SET NULL'),
        sa.PrimaryKeyConstraint('id'),
    )
    with op.batch_alter_table('content_reports', schema=None) as batch_op:
        batch_op.create_index(
            batch_op.f('ix_content_reports_reporter_user_id'), ['reporter_user_id'],
            unique=False,
        )
        batch_op.create_index(batch_op.f('ix_content_reports_status'), ['status'],
                              unique=False)
        batch_op.create_index('ix_content_reports_status_created', ['status', 'created_at'],
                              unique=False)


def downgrade():
    bind = op.get_bind()

    op.drop_table('content_reports')
    op.drop_table('notifications')
    op.drop_table('gig_applications')
    op.drop_table('gigs')
    op.drop_table('reviews')
    op.drop_table('comment_likes')
    op.drop_table('comments')
    op.drop_table('event_list_items')
    op.drop_table('event_lists')
    op.drop_table('user_blocks')
    op.drop_table('user_follows')

    if bind.dialect.name == "postgresql":
        for enum_name in (
            'notification_kind', 'report_reason', 'report_status', 'gig_status',
            'gig_application_status',
        ):
            sa.Enum(name=enum_name).drop(bind, checkfirst=True)
        # `upload_purpose` keeps the 'user_avatar' label: Postgres cannot drop
        # an enum value, and a rebuild of a type in active use is riskier than
        # a stray label nothing writes any more.

    with op.batch_alter_table('users', schema=None) as batch_op:
        batch_op.drop_index(batch_op.f('ix_users_handle'))
        batch_op.drop_column('avatar_key')
        batch_op.drop_column('bio')
        batch_op.drop_column('handle')
