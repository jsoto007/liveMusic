"""The migration must describe the same schema the models do.

Skipped unless TEST_DATABASE_URL points at Postgres: SQLite cannot express
native enums or several constraint kinds, so a comparison there would report
differences that do not exist on the real database.
"""

import os

import pytest
from alembic.autogenerate import compare_metadata
from alembic.migration import MigrationContext
from flask_migrate import upgrade as alembic_upgrade

from app import create_app
from app.extensions import db

TEST_DATABASE_URL = os.environ.get("TEST_DATABASE_URL", "")

pytestmark = pytest.mark.skipif(
    not TEST_DATABASE_URL.startswith("postgresql"),
    reason="migration parity is only meaningful against Postgres",
)


@pytest.fixture()
def migrated_app(tmp_path):
    from tests.conftest import TestConfig

    class MigrationConfig(TestConfig):
        SQLALCHEMY_DATABASE_URI = TEST_DATABASE_URL

    application = create_app(MigrationConfig)
    with application.app_context():
        # Start from nothing so the migration builds the schema itself, rather
        # than being compared against a create_all() shortcut.
        db.drop_all()
        with db.engine.begin() as connection:
            connection.exec_driver_sql("DROP TABLE IF EXISTS alembic_version")
            for enum_name in (
                "user_role", "event_status", "age_restriction", "genre",
                "upload_purpose", "upload_status",
            ):
                connection.exec_driver_sql(f"DROP TYPE IF EXISTS {enum_name} CASCADE")

        # Driven through Flask-Migrate so the run uses the same env.py the
        # deploy does, rather than a parallel Alembic configuration that could
        # pass here and fail in production.
        alembic_upgrade()
        yield application
        db.session.remove()


def test_migration_builds_the_schema_the_models_describe(migrated_app):
    with migrated_app.app_context(), db.engine.connect() as connection:
        context = MigrationContext.configure(connection)
        diff = compare_metadata(context, db.metadata)

    # Index/constraint reflection differences are noisy and not schema drift;
    # what matters is that no table or column is missing or of the wrong type.
    significant = [
        entry
        for entry in diff
        if entry[0] in {
            "add_table", "remove_table", "add_column", "remove_column",
            "modify_type", "modify_nullable",
        }
    ]
    assert significant == [], (
        "The models and the migration have drifted. Generate a NEW revision "
        "(never edit an applied one):\n"
        "  flask --app app db migrate -m 'describe the change'\n"
        f"Differences: {significant}"
    )
