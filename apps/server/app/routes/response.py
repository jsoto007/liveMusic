"""The one response envelope every route returns.

Success is ``{"data": ..., "error": null}``; failure is
``{"data": null, "error": {"code", "message", "details"}}``. Clients branch on
``error.code`` (a stable SCREAMING_SNAKE string) and show ``error.message``
directly, so a message must always be safe for a user to read — no SQL, no
stack, no internal identifiers.
"""

from typing import Any

from flask import jsonify


def ok(data: Any, status: int = 200, headers: dict | None = None):
    response = jsonify({"data": data, "error": None})
    response.status_code = status
    if headers:
        for key, value in headers.items():
            response.headers[key] = value
    return response


def error(code: str, message: str, details: dict | None = None, status: int = 400):
    payload = {"code": code, "message": message, "details": details or {}}
    response = jsonify({"data": None, "error": payload})
    response.status_code = status
    return response
