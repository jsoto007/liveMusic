"""messages and image review

The hire desk's correspondence (one conversation per pair of readers, with
the artist or gig that opened it as the subject line) and the photo desk
(every completed image upload queues for editorial review; removal deletes
the object and notifies the uploader — ``notification_kind`` learns
``image_removed``).

Revision ID: e4a8b3c96d15
Revises: c9d2e51a7b43
Create Date: 2026-08-17 15:20:00.000000

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


# revision identifiers, used by Alembic.
revision = 'e4a8b3c96d15'
down_revision = 'c9d2e51a7b43'
branch_labels = None
depends_on = None


UPLOAD_PURPOSES = ('artist_audio', 'artist_photo', 'event_poster', 'user_avatar')


def _upload_purpose_type():
    """The existing ``upload_purpose`` type, reused by ``image_reviews``."""
    if op.get_bind().dialect.name == "postgresql":
        return postgresql.ENUM(name="upload_purpose", create_type=False)
    return sa.Enum(*UPLOAD_PURPOSES, name="upload_purpose")


def upgrade():
    bind = op.get_bind()

    if bind.dialect.name == "postgresql":
        op.execute(
            "ALTER TYPE notification_kind ADD VALUE IF NOT EXISTS 'image_removed'"
        )

    op.create_table(
        'conversations',
        sa.Column('id', sa.Uuid(), nullable=False),
        sa.Column('a_user_id', sa.Uuid(), nullable=False),
        sa.Column('b_user_id', sa.Uuid(), nullable=False),
        sa.Column('artist_id', sa.Uuid(), nullable=True),
        sa.Column('gig_id', sa.Uuid(), nullable=True),
        sa.Column('a_last_read_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('b_last_read_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('last_message_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint('a_user_id < b_user_id', name='ck_conversations_ordered_pair'),
        sa.ForeignKeyConstraint(['a_user_id'], ['users.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['artist_id'], ['artists.id'], ondelete='SET NULL'),
        sa.ForeignKeyConstraint(['b_user_id'], ['users.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['gig_id'], ['gigs.id'], ondelete='SET NULL'),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('a_user_id', 'b_user_id', name='uq_conversations_pair'),
    )
    with op.batch_alter_table('conversations', schema=None) as batch_op:
        batch_op.create_index(
            'ix_conversations_a_recent', ['a_user_id', 'last_message_at'], unique=False
        )
        batch_op.create_index(
            'ix_conversations_b_recent', ['b_user_id', 'last_message_at'], unique=False
        )

    op.create_table(
        'messages',
        sa.Column('id', sa.Uuid(), nullable=False),
        sa.Column('conversation_id', sa.Uuid(), nullable=False),
        sa.Column('sender_user_id', sa.Uuid(), nullable=False),
        sa.Column('body', sa.Text(), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(['conversation_id'], ['conversations.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['sender_user_id'], ['users.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
    )
    with op.batch_alter_table('messages', schema=None) as batch_op:
        batch_op.create_index(
            batch_op.f('ix_messages_conversation_id'), ['conversation_id'], unique=False
        )
        batch_op.create_index(
            'ix_messages_conversation_created', ['conversation_id', 'created_at'],
            unique=False,
        )

    op.create_table(
        'image_reviews',
        sa.Column('id', sa.Uuid(), nullable=False),
        sa.Column('uploader_user_id', sa.Uuid(), nullable=False),
        sa.Column('purpose', _upload_purpose_type(), nullable=False),
        sa.Column('target_id', sa.Uuid(), nullable=True),
        sa.Column('object_key', sa.String(length=400), nullable=False),
        sa.Column(
            'status',
            sa.Enum('pending', 'approved', 'removed', name='image_review_status'),
            nullable=False,
        ),
        sa.Column('reviewed_by_user_id', sa.Uuid(), nullable=True),
        sa.Column('reviewed_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(['reviewed_by_user_id'], ['users.id'], ondelete='SET NULL'),
        sa.ForeignKeyConstraint(['uploader_user_id'], ['users.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
    )
    with op.batch_alter_table('image_reviews', schema=None) as batch_op:
        batch_op.create_index(
            batch_op.f('ix_image_reviews_status'), ['status'], unique=False
        )
        batch_op.create_index(
            batch_op.f('ix_image_reviews_uploader_user_id'), ['uploader_user_id'],
            unique=False,
        )
        batch_op.create_index(
            'ix_image_reviews_status_created', ['status', 'created_at'], unique=False
        )


def downgrade():
    bind = op.get_bind()

    op.drop_table('image_reviews')
    op.drop_table('messages')
    op.drop_table('conversations')

    if bind.dialect.name == "postgresql":
        sa.Enum(name='image_review_status').drop(bind, checkfirst=True)
        # `notification_kind` keeps 'image_removed' — enum values cannot be
        # dropped on Postgres, and a stray label is harmless.
