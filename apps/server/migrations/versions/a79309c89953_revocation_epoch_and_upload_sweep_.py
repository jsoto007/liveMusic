"""revocation epoch and upload sweep tracking

Two columns, both closing gaps found in the 2026-08-03 adversarial review:

* ``users.sessions_invalidated_at`` — access tokens issued before this instant
  are refused, so "sign out everywhere" and account lockout take effect at
  once instead of after the token's remaining lifetime.
* ``media_uploads.swept_at`` — records that an object was confirmed deleted
  from R2, separately from the ticket's lifecycle status. The sweeper used to
  infer this from ``status``, so a failed delete still advanced the row and
  the object became permanently unreachable.

Both are nullable with no default, so this applies to a populated table
without a rewrite or a backfill.

Revision ID: a79309c89953
Revises: 3c4c9a48b886
Create Date: 2026-08-03 13:14:45.941876

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'a79309c89953'
down_revision = '3c4c9a48b886'
branch_labels = None
depends_on = None


def upgrade():
    with op.batch_alter_table('media_uploads', schema=None) as batch_op:
        batch_op.add_column(sa.Column('swept_at', sa.DateTime(timezone=True), nullable=True))
        batch_op.create_index('ix_media_uploads_unswept', ['swept_at', 'expires_at'], unique=False)

    with op.batch_alter_table('users', schema=None) as batch_op:
        batch_op.add_column(sa.Column('sessions_invalidated_at', sa.DateTime(timezone=True), nullable=True))



def downgrade():
    with op.batch_alter_table('users', schema=None) as batch_op:
        batch_op.drop_column('sessions_invalidated_at')

    with op.batch_alter_table('media_uploads', schema=None) as batch_op:
        batch_op.drop_index('ix_media_uploads_unswept')
        batch_op.drop_column('swept_at')

