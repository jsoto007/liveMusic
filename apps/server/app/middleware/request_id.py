"""Per-request correlation id, echoed back on the response.

An inbound ``X-Request-Id`` is honoured so a proxy or a client can stitch a
trace together, but it is never trusted verbatim: it is length-capped and
stripped of anything outside a conservative charset, because the value lands in
log lines and a response header.
"""

import re
import uuid

from flask import g, request

_HEADER = "X-Request-Id"
_SAFE = re.compile(r"[^A-Za-z0-9._\-]")
_MAX_LEN = 64


def _sanitize(raw: str | None) -> str | None:
    if not raw:
        return None
    cleaned = _SAFE.sub("", raw)[:_MAX_LEN]
    return cleaned or None


def init_request_id(app) -> None:
    @app.before_request
    def _assign_request_id():
        g.request_id = _sanitize(request.headers.get(_HEADER)) or uuid.uuid4().hex

    @app.after_request
    def _echo_request_id(response):
        request_id = getattr(g, "request_id", None)
        if request_id:
            response.headers[_HEADER] = request_id
        return response
