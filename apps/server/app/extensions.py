"""Flask extension singletons, created unbound and wired up in ``create_app``."""

from flask_cors import CORS
from flask_migrate import Migrate
from flask_sqlalchemy import SQLAlchemy
from sqlalchemy import event
from sqlalchemy.engine import Engine

cors = CORS()
db = SQLAlchemy()
migrate = Migrate()


@event.listens_for(Engine, "connect")
def _enforce_sqlite_foreign_keys(dbapi_connection, connection_record):  # noqa: ARG001
    """Turn on foreign-key enforcement for SQLite connections.

    SQLite ships with ``PRAGMA foreign_keys`` **off**, so it silently ignores
    every ``ON DELETE CASCADE`` and ``ON DELETE SET NULL`` in the schema. Prod
    is Postgres, which enforces them; the tests run on SQLite, which did not —
    so a whole class of behaviour (what happens to a reader's list, follows and
    comments when the account is deleted) was passing against a database that
    was not actually doing the work. Enabling the pragma makes the two agree.

    Registered on the base ``Engine`` class so it covers every engine, and
    guarded by dialect so it is a no-op on Postgres.
    """
    if dbapi_connection.__class__.__module__.split(".")[0] not in {"sqlite3", "pysqlite3"}:
        return
    cursor = dbapi_connection.cursor()
    try:
        cursor.execute("PRAGMA foreign_keys=ON")
    finally:
        cursor.close()

try:
    from flask_limiter import Limiter
    from flask_limiter.util import get_remote_address

    limiter = Limiter(key_func=get_remote_address)
except ImportError:  # pragma: no cover - optional dependency
    class _NoopLimiter:
        """Fallback used ONLY when flask-limiter is absent.

        The test suite does not need a real (Redis-backed) limiter, but a
        production process must never run with an unprotected rate-limit
        surface. ``create_app`` checks the sentinel below and refuses to boot a
        non-testing app on this shim, so the degradation cannot go unnoticed.
        """

        _is_noop_limiter = True

        def init_app(self, app):
            return None

        def limit(self, *args, **kwargs):
            def decorator(func):
                return func

            return decorator

        def exempt(self, func):
            return func

    limiter = _NoopLimiter()
