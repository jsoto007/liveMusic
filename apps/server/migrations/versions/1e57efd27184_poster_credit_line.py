"""poster credit line

Adds `events.poster_credit`: an attribution line for a poster this app
attached itself from an openly-licensed source (CC BY / CC BY-SA require a
visible credit wherever the image is shown), as opposed to a band's own
upload, which carries none. Nullable, no backfill needed — existing posters
are all band-uploaded.

Revision ID: 1e57efd27184
Revises: 518b96758efa
Create Date: 2026-08-05 15:10:14.720619

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = '1e57efd27184'
down_revision = '518b96758efa'
branch_labels = None
depends_on = None


def upgrade():
    with op.batch_alter_table('events', schema=None) as batch_op:
        batch_op.add_column(sa.Column('poster_credit', sa.Text(), nullable=True))


def downgrade():
    with op.batch_alter_table('events', schema=None) as batch_op:
        batch_op.drop_column('poster_credit')
