"""Flask extension singletons, created unbound and wired up in ``create_app``."""

from flask_cors import CORS
from flask_migrate import Migrate
from flask_sqlalchemy import SQLAlchemy

cors = CORS()
db = SQLAlchemy()
migrate = Migrate()

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
