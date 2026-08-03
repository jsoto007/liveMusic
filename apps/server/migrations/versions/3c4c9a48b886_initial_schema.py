"""initial schema

The whole Live Msc schema: accounts and sessions, bands, venues, listings,
saves/follows, sound samples, and the media-upload ledger.

Enum labels here are the lowercase `.value` strings, matching what the ORM
persists (see `app/models.py::pg_enum`). Raw SQL in any later revision must use
these same literals — there is no uppercase variant.

NOTE: once this revision has been applied to any real database its file is
frozen. Schema changes go in a NEW revision, never edited into this one — an
amended applied revision is a silent no-op on every existing database while a
from-scratch CI run still passes, so code and production drift apart.

Revision ID: 3c4c9a48b886
Revises:
Create Date: 2026-08-03

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = '3c4c9a48b886'
down_revision = None
branch_labels = None
depends_on = None


def upgrade():
    op.create_table('users',
    sa.Column('id', sa.Uuid(), nullable=False),
    sa.Column('email', sa.String(length=255), nullable=False),
    sa.Column('password_hash', sa.String(length=255), nullable=False),
    sa.Column('display_name', sa.String(length=80), nullable=False),
    sa.Column('role', sa.Enum('listener', 'artist', 'admin', name='user_role'), nullable=False),
    sa.Column('home_city', sa.String(length=120), nullable=True),
    sa.Column('is_active', sa.Boolean(), nullable=False),
    sa.Column('email_verified_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('failed_login_count', sa.Integer(), nullable=False),
    sa.Column('locked_until', sa.DateTime(timezone=True), nullable=True),
    sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
    sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False),
    sa.PrimaryKeyConstraint('id')
    )
    with op.batch_alter_table('users', schema=None) as batch_op:
        batch_op.create_index(batch_op.f('ix_users_email'), ['email'], unique=True)

    op.create_table('venues',
    sa.Column('id', sa.Uuid(), nullable=False),
    sa.Column('name', sa.String(length=160), nullable=False),
    sa.Column('slug', sa.String(length=180), nullable=False),
    sa.Column('address', sa.String(length=300), nullable=True),
    sa.Column('neighborhood', sa.String(length=120), nullable=True),
    sa.Column('city', sa.String(length=120), nullable=False),
    sa.Column('latitude', sa.Float(), nullable=True),
    sa.Column('longitude', sa.Float(), nullable=True),
    sa.Column('timezone_name', sa.String(length=64), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
    sa.PrimaryKeyConstraint('id')
    )
    with op.batch_alter_table('venues', schema=None) as batch_op:
        batch_op.create_index(batch_op.f('ix_venues_city'), ['city'], unique=False)
        batch_op.create_index('ix_venues_city_geo', ['city', 'latitude', 'longitude'], unique=False)
        batch_op.create_index(batch_op.f('ix_venues_slug'), ['slug'], unique=True)

    op.create_table('artists',
    sa.Column('id', sa.Uuid(), nullable=False),
    sa.Column('owner_user_id', sa.Uuid(), nullable=False),
    sa.Column('name', sa.String(length=120), nullable=False),
    sa.Column('slug', sa.String(length=140), nullable=False),
    sa.Column('city', sa.String(length=120), nullable=True),
    sa.Column('neighborhood', sa.String(length=120), nullable=True),
    sa.Column('one_liner', sa.String(length=300), nullable=True),
    sa.Column('bio', sa.Text(), nullable=True),
    sa.Column('sounds_like', sa.String(length=300), nullable=True),
    sa.Column('style_tags', sa.JSON(), nullable=False),
    sa.Column('available_for_hire', sa.Boolean(), nullable=False),
    sa.Column('photo_key', sa.String(length=400), nullable=True),
    sa.Column('verified_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
    sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False),
    sa.ForeignKeyConstraint(['owner_user_id'], ['users.id'], ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id')
    )
    with op.batch_alter_table('artists', schema=None) as batch_op:
        batch_op.create_index(batch_op.f('ix_artists_owner_user_id'), ['owner_user_id'], unique=False)
        batch_op.create_index(batch_op.f('ix_artists_slug'), ['slug'], unique=True)

    op.create_table('media_uploads',
    sa.Column('id', sa.Uuid(), nullable=False),
    sa.Column('user_id', sa.Uuid(), nullable=False),
    sa.Column('purpose', sa.Enum('artist_audio', 'artist_photo', 'event_poster', name='upload_purpose'), nullable=False),
    sa.Column('target_id', sa.Uuid(), nullable=True),
    sa.Column('object_key', sa.String(length=400), nullable=False),
    sa.Column('content_type', sa.String(length=100), nullable=False),
    sa.Column('max_bytes', sa.BigInteger(), nullable=False),
    sa.Column('declared_size_bytes', sa.BigInteger(), nullable=True),
    sa.Column('status', sa.Enum('pending', 'completed', 'abandoned', name='upload_status'), nullable=False),
    sa.Column('expires_at', sa.DateTime(timezone=True), nullable=False),
    sa.Column('completed_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
    sa.ForeignKeyConstraint(['user_id'], ['users.id'], ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('object_key')
    )
    with op.batch_alter_table('media_uploads', schema=None) as batch_op:
        batch_op.create_index(batch_op.f('ix_media_uploads_status'), ['status'], unique=False)
        batch_op.create_index('ix_media_uploads_status_expires', ['status', 'expires_at'], unique=False)
        batch_op.create_index(batch_op.f('ix_media_uploads_user_id'), ['user_id'], unique=False)

    op.create_table('refresh_tokens',
    sa.Column('id', sa.Uuid(), nullable=False),
    sa.Column('user_id', sa.Uuid(), nullable=False),
    sa.Column('token_hash', sa.String(length=64), nullable=False),
    sa.Column('family_id', sa.Uuid(), nullable=False),
    sa.Column('expires_at', sa.DateTime(timezone=True), nullable=False),
    sa.Column('revoked_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('rotated_to_id', sa.Uuid(), nullable=True),
    sa.Column('user_agent', sa.String(length=200), nullable=True),
    sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
    sa.ForeignKeyConstraint(['user_id'], ['users.id'], ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id')
    )
    with op.batch_alter_table('refresh_tokens', schema=None) as batch_op:
        batch_op.create_index(batch_op.f('ix_refresh_tokens_family_id'), ['family_id'], unique=False)
        batch_op.create_index(batch_op.f('ix_refresh_tokens_token_hash'), ['token_hash'], unique=True)
        batch_op.create_index('ix_refresh_tokens_user_active', ['user_id', 'revoked_at'], unique=False)

    op.create_table('artist_follows',
    sa.Column('user_id', sa.Uuid(), nullable=False),
    sa.Column('artist_id', sa.Uuid(), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
    sa.ForeignKeyConstraint(['artist_id'], ['artists.id'], ondelete='CASCADE'),
    sa.ForeignKeyConstraint(['user_id'], ['users.id'], ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('user_id', 'artist_id')
    )
    with op.batch_alter_table('artist_follows', schema=None) as batch_op:
        batch_op.create_index('ix_artist_follows_artist', ['artist_id'], unique=False)

    op.create_table('artist_members',
    sa.Column('id', sa.Uuid(), nullable=False),
    sa.Column('artist_id', sa.Uuid(), nullable=False),
    sa.Column('name', sa.String(length=120), nullable=False),
    sa.Column('instrument', sa.String(length=120), nullable=True),
    sa.Column('position', sa.Integer(), nullable=False),
    sa.ForeignKeyConstraint(['artist_id'], ['artists.id'], ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id')
    )
    with op.batch_alter_table('artist_members', schema=None) as batch_op:
        batch_op.create_index(batch_op.f('ix_artist_members_artist_id'), ['artist_id'], unique=False)

    op.create_table('audio_samples',
    sa.Column('id', sa.Uuid(), nullable=False),
    sa.Column('artist_id', sa.Uuid(), nullable=False),
    sa.Column('title', sa.String(length=140), nullable=False),
    sa.Column('object_key', sa.String(length=400), nullable=False),
    sa.Column('content_type', sa.String(length=100), nullable=False),
    sa.Column('size_bytes', sa.BigInteger(), nullable=False),
    sa.Column('duration_seconds', sa.Integer(), nullable=True),
    sa.Column('position', sa.Integer(), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
    sa.ForeignKeyConstraint(['artist_id'], ['artists.id'], ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('object_key')
    )
    with op.batch_alter_table('audio_samples', schema=None) as batch_op:
        batch_op.create_index(batch_op.f('ix_audio_samples_artist_id'), ['artist_id'], unique=False)

    op.create_table('events',
    sa.Column('id', sa.Uuid(), nullable=False),
    sa.Column('artist_id', sa.Uuid(), nullable=True),
    sa.Column('venue_id', sa.Uuid(), nullable=False),
    sa.Column('created_by_user_id', sa.Uuid(), nullable=True),
    sa.Column('headline', sa.String(length=160), nullable=False),
    sa.Column('support_line', sa.String(length=300), nullable=True),
    sa.Column('genre', sa.Enum('rock_punk', 'jazz', 'classical', 'electronic', 'folk_country', 'metal', 'hip_hop', 'gospel_soul', 'open_mic', 'festival', 'other', name='genre'), nullable=False),
    sa.Column('starts_at', sa.DateTime(timezone=True), nullable=False),
    sa.Column('doors_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('price_cents', sa.Integer(), nullable=True),
    sa.Column('age_restriction', sa.Enum('all_ages', '18_plus', '21_plus', name='age_restriction'), nullable=False),
    sa.Column('ticket_url', sa.String(length=500), nullable=True),
    sa.Column('short_line', sa.String(length=300), nullable=True),
    sa.Column('blurb', sa.Text(), nullable=True),
    sa.Column('poster_key', sa.String(length=400), nullable=True),
    sa.Column('status', sa.Enum('draft', 'published', 'cancelled', name='event_status'), nullable=False),
    sa.Column('published_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('cancelled_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
    sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False),
    sa.CheckConstraint('doors_at IS NULL OR doors_at <= starts_at', name='ck_events_doors_before_start'),
    sa.CheckConstraint('price_cents IS NULL OR price_cents >= 0', name='ck_events_price_non_negative'),
    sa.ForeignKeyConstraint(['artist_id'], ['artists.id'], ondelete='SET NULL'),
    sa.ForeignKeyConstraint(['created_by_user_id'], ['users.id'], ondelete='SET NULL'),
    sa.ForeignKeyConstraint(['venue_id'], ['venues.id'], ondelete='RESTRICT'),
    sa.PrimaryKeyConstraint('id')
    )
    with op.batch_alter_table('events', schema=None) as batch_op:
        batch_op.create_index(batch_op.f('ix_events_artist_id'), ['artist_id'], unique=False)
        batch_op.create_index(batch_op.f('ix_events_genre'), ['genre'], unique=False)
        batch_op.create_index(batch_op.f('ix_events_starts_at'), ['starts_at'], unique=False)
        batch_op.create_index(batch_op.f('ix_events_status'), ['status'], unique=False)
        batch_op.create_index('ix_events_status_starts_at', ['status', 'starts_at'], unique=False)
        batch_op.create_index(batch_op.f('ix_events_venue_id'), ['venue_id'], unique=False)

    op.create_table('event_interests',
    sa.Column('user_id', sa.Uuid(), nullable=False),
    sa.Column('event_id', sa.Uuid(), nullable=False),
    sa.Column('saved', sa.Boolean(), nullable=False),
    sa.Column('going', sa.Boolean(), nullable=False),
    sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False),
    sa.ForeignKeyConstraint(['event_id'], ['events.id'], ondelete='CASCADE'),
    sa.ForeignKeyConstraint(['user_id'], ['users.id'], ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('user_id', 'event_id')
    )
    with op.batch_alter_table('event_interests', schema=None) as batch_op:
        batch_op.create_index('ix_event_interests_event', ['event_id'], unique=False)

    op.create_table('event_lineup_slots',
    sa.Column('id', sa.Uuid(), nullable=False),
    sa.Column('event_id', sa.Uuid(), nullable=False),
    sa.Column('name', sa.String(length=160), nullable=False),
    sa.Column('note', sa.String(length=200), nullable=True),
    sa.Column('starts_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('position', sa.Integer(), nullable=False),
    sa.ForeignKeyConstraint(['event_id'], ['events.id'], ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id')
    )
    with op.batch_alter_table('event_lineup_slots', schema=None) as batch_op:
        batch_op.create_index(batch_op.f('ix_event_lineup_slots_event_id'), ['event_id'], unique=False)



def downgrade():
    with op.batch_alter_table('event_lineup_slots', schema=None) as batch_op:
        batch_op.drop_index(batch_op.f('ix_event_lineup_slots_event_id'))

    op.drop_table('event_lineup_slots')
    with op.batch_alter_table('event_interests', schema=None) as batch_op:
        batch_op.drop_index('ix_event_interests_event')

    op.drop_table('event_interests')
    with op.batch_alter_table('events', schema=None) as batch_op:
        batch_op.drop_index(batch_op.f('ix_events_venue_id'))
        batch_op.drop_index('ix_events_status_starts_at')
        batch_op.drop_index(batch_op.f('ix_events_status'))
        batch_op.drop_index(batch_op.f('ix_events_starts_at'))
        batch_op.drop_index(batch_op.f('ix_events_genre'))
        batch_op.drop_index(batch_op.f('ix_events_artist_id'))

    op.drop_table('events')
    with op.batch_alter_table('audio_samples', schema=None) as batch_op:
        batch_op.drop_index(batch_op.f('ix_audio_samples_artist_id'))

    op.drop_table('audio_samples')
    with op.batch_alter_table('artist_members', schema=None) as batch_op:
        batch_op.drop_index(batch_op.f('ix_artist_members_artist_id'))

    op.drop_table('artist_members')
    with op.batch_alter_table('artist_follows', schema=None) as batch_op:
        batch_op.drop_index('ix_artist_follows_artist')

    op.drop_table('artist_follows')
    with op.batch_alter_table('refresh_tokens', schema=None) as batch_op:
        batch_op.drop_index('ix_refresh_tokens_user_active')
        batch_op.drop_index(batch_op.f('ix_refresh_tokens_token_hash'))
        batch_op.drop_index(batch_op.f('ix_refresh_tokens_family_id'))

    op.drop_table('refresh_tokens')
    with op.batch_alter_table('media_uploads', schema=None) as batch_op:
        batch_op.drop_index(batch_op.f('ix_media_uploads_user_id'))
        batch_op.drop_index('ix_media_uploads_status_expires')
        batch_op.drop_index(batch_op.f('ix_media_uploads_status'))

    op.drop_table('media_uploads')
    with op.batch_alter_table('artists', schema=None) as batch_op:
        batch_op.drop_index(batch_op.f('ix_artists_slug'))
        batch_op.drop_index(batch_op.f('ix_artists_owner_user_id'))

    op.drop_table('artists')
    with op.batch_alter_table('venues', schema=None) as batch_op:
        batch_op.drop_index(batch_op.f('ix_venues_slug'))
        batch_op.drop_index('ix_venues_city_geo')
        batch_op.drop_index(batch_op.f('ix_venues_city'))

    op.drop_table('venues')
    with op.batch_alter_table('users', schema=None) as batch_op:
        batch_op.drop_index(batch_op.f('ix_users_email'))

    op.drop_table('users')
