"""Structured JSON logging with a per-request correlation id.

Every line carries ``request_id`` so a single user action can be followed
across the log. Never log a token, a password, a presigned URL (it is a bearer
credential for the lifetime of its signature), or a full email address.
"""

import logging
import sys

from flask import g, has_request_context

try:
    from pythonjsonlogger import jsonlogger

    _HAS_JSON_LOGGER = True
except ImportError:  # pragma: no cover - optional dependency
    _HAS_JSON_LOGGER = False


class RequestIdFilter(logging.Filter):
    def filter(self, record: logging.LogRecord) -> bool:
        record.request_id = (
            getattr(g, "request_id", "-") if has_request_context() else "-"
        )
        return True


def configure_logging(app) -> None:
    level = getattr(logging, str(app.config.get("LOG_LEVEL", "INFO")).upper(), logging.INFO)

    handler = logging.StreamHandler(sys.stdout)
    if _HAS_JSON_LOGGER:
        handler.setFormatter(
            jsonlogger.JsonFormatter(
                "%(asctime)s %(levelname)s %(name)s %(request_id)s %(message)s",
                rename_fields={"asctime": "timestamp", "levelname": "level"},
            )
        )
    else:  # pragma: no cover - only when the optional dep is absent
        handler.setFormatter(
            logging.Formatter("%(asctime)s %(levelname)s [%(request_id)s] %(message)s")
        )
    handler.addFilter(RequestIdFilter())

    app.logger.handlers = [handler]
    app.logger.setLevel(level)
    app.logger.propagate = False

    root = logging.getLogger()
    root.handlers = [handler]
    root.setLevel(level)
