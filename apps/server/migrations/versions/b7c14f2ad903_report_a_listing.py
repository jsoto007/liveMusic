"""a listing can be reported

`content_reports` could point at a comment, a review or a person — but not at
an event. A listing is the paper's primary user-written surface (headline,
support line, note, and an uploaded poster), and it was the one place a reader
could see something objectionable with no way to flag it. App Store Review
Guideline 1.2 requires a report mechanism on user-generated content, so this
adds `event_id` alongside the other three subjects and widens the
one-subject check constraint to count it.

`ON DELETE SET NULL`, like every other subject column here: removing the
reported listing must not shred the report, because the report row is the
audit line saying moderation happened.

Revision ID: b7c14f2ad903
Revises: e4a8b3c96d15
Create Date: 2026-09-02 13:05:00.000000

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'b7c14f2ad903'
down_revision = 'e4a8b3c96d15'
branch_labels = None
depends_on = None


CHECK_NAME = 'ck_content_reports_one_subject'

OLD_CHECK = (
    "(CASE WHEN comment_id IS NOT NULL THEN 1 ELSE 0 END"
    " + CASE WHEN review_id IS NOT NULL THEN 1 ELSE 0 END"
    " + CASE WHEN reported_user_id IS NOT NULL THEN 1 ELSE 0 END) <= 1"
)

NEW_CHECK = (
    "(CASE WHEN comment_id IS NOT NULL THEN 1 ELSE 0 END"
    " + CASE WHEN review_id IS NOT NULL THEN 1 ELSE 0 END"
    " + CASE WHEN reported_user_id IS NOT NULL THEN 1 ELSE 0 END"
    " + CASE WHEN event_id IS NOT NULL THEN 1 ELSE 0 END) <= 1"
)


def upgrade():
    # batch_alter_table so the same revision runs on SQLite, which cannot ALTER
    # a constraint in place and has to rebuild the table.
    with op.batch_alter_table('content_reports') as batch:
        batch.add_column(sa.Column('event_id', sa.Uuid(), nullable=True))
        batch.drop_constraint(CHECK_NAME, type_='check')
        batch.create_check_constraint(CHECK_NAME, NEW_CHECK)
        batch.create_foreign_key(
            'fk_content_reports_event_id_events',
            'events',
            ['event_id'],
            ['id'],
            ondelete='SET NULL',
        )
    op.create_index(
        'ix_content_reports_event', 'content_reports', ['event_id'], unique=False
    )


def downgrade():
    op.drop_index('ix_content_reports_event', table_name='content_reports')
    # Any report that pointed at a listing loses its subject rather than the
    # whole row — the same shape a removed comment leaves behind.
    with op.batch_alter_table('content_reports') as batch:
        batch.drop_constraint('fk_content_reports_event_id_events', type_='foreignkey')
        batch.drop_constraint(CHECK_NAME, type_='check')
        batch.create_check_constraint(CHECK_NAME, OLD_CHECK)
        batch.drop_column('event_id')
