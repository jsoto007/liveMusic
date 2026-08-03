"""email tokens, deliveries and preferences

Adds the email surface: single-use tokens for verification and password reset,
a delivery ledger whose unique constraint makes notifications idempotent, and
the per-reader notification preferences.

The two preference booleans are NOT NULL, so they are added WITH a
`server_default` — otherwise the ALTER fails outright on any table that
already has users, and this migration would only ever have been tested against
an empty one. The default is dropped afterwards so the application layer stays
the single source of truth for what a new row gets.

Revision ID: 518b96758efa
Revises: a79309c89953
Create Date: 2026-08-03 13:45:56.683442

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = '518b96758efa'
down_revision = 'a79309c89953'
branch_labels = None
depends_on = None


def upgrade():
    op.create_table('email_deliveries',
    sa.Column('id', sa.Uuid(), nullable=False),
    sa.Column('user_id', sa.Uuid(), nullable=False),
    sa.Column('kind', sa.Enum('verify_email', 'reset_password', 'new_show_from_followed', 'show_reminder', name='email_kind'), nullable=False),
    sa.Column('subject_id', sa.Uuid(), nullable=True),
    sa.Column('sent_at', sa.DateTime(timezone=True), nullable=False),
    sa.ForeignKeyConstraint(['user_id'], ['users.id'], ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('user_id', 'kind', 'subject_id', name='uq_email_delivery_once')
    )
    with op.batch_alter_table('email_deliveries', schema=None) as batch_op:
        batch_op.create_index(batch_op.f('ix_email_deliveries_user_id'), ['user_id'], unique=False)

    op.create_table('email_tokens',
    sa.Column('id', sa.Uuid(), nullable=False),
    sa.Column('user_id', sa.Uuid(), nullable=False),
    sa.Column('purpose', sa.Enum('verify_email', 'reset_password', name='email_token_purpose'), nullable=False),
    sa.Column('token_hash', sa.String(length=64), nullable=False),
    sa.Column('expires_at', sa.DateTime(timezone=True), nullable=False),
    sa.Column('used_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
    sa.ForeignKeyConstraint(['user_id'], ['users.id'], ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id')
    )
    with op.batch_alter_table('email_tokens', schema=None) as batch_op:
        batch_op.create_index(batch_op.f('ix_email_tokens_token_hash'), ['token_hash'], unique=True)
        batch_op.create_index(batch_op.f('ix_email_tokens_user_id'), ['user_id'], unique=False)
        batch_op.create_index('ix_email_tokens_user_purpose', ['user_id', 'purpose', 'used_at'], unique=False)

    with op.batch_alter_table('users', schema=None) as batch_op:
        # server_default backfills existing rows; see the module docstring.
        batch_op.add_column(
            sa.Column(
                'notify_new_shows', sa.Boolean(), nullable=False,
                server_default=sa.true(),
            )
        )
        batch_op.add_column(
            sa.Column(
                'notify_show_reminders', sa.Boolean(), nullable=False,
                server_default=sa.true(),
            )
        )
        batch_op.add_column(
            sa.Column('unsubscribed_all_at', sa.DateTime(timezone=True), nullable=True)
        )

    # The backfill has happened; hand responsibility back to the ORM default.
    with op.batch_alter_table('users', schema=None) as batch_op:
        batch_op.alter_column('notify_new_shows', server_default=None)
        batch_op.alter_column('notify_show_reminders', server_default=None)



def downgrade():
    with op.batch_alter_table('users', schema=None) as batch_op:
        batch_op.drop_column('unsubscribed_all_at')
        batch_op.drop_column('notify_show_reminders')
        batch_op.drop_column('notify_new_shows')

    with op.batch_alter_table('email_tokens', schema=None) as batch_op:
        batch_op.drop_index('ix_email_tokens_user_purpose')
        batch_op.drop_index(batch_op.f('ix_email_tokens_user_id'))
        batch_op.drop_index(batch_op.f('ix_email_tokens_token_hash'))

    op.drop_table('email_tokens')
    with op.batch_alter_table('email_deliveries', schema=None) as batch_op:
        batch_op.drop_index(batch_op.f('ix_email_deliveries_user_id'))

    op.drop_table('email_deliveries')
