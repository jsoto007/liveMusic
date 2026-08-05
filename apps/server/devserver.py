"""A throwaway local stack for end-to-end checks. NOT part of the app.

Serves the real Flask API and the built SPA from one origin, on SQLite, with
R2 replaced by an in-memory bucket reachable over HTTP. That last part matters:
the browser really does PUT the file to a presigned-style URL and the server
really does HEAD it back before writing the row, so the full upload path runs
exactly as it does in production — only the storage is local.

Run:  python devserver.py [port]
"""

import os
import sys

os.environ.setdefault("TESTING", "true")
os.environ.setdefault("FLASK_ENV", "development")
os.environ.setdefault("DATABASE_URL", "sqlite+pysqlite:////tmp/livemsc-e2e.db")

from flask import request, send_from_directory  # noqa: E402

from app import create_app  # noqa: E402
from app.config import Config  # noqa: E402
from app.extensions import db  # noqa: E402
from app.services import r2_storage  # noqa: E402

PORT = int(sys.argv[1]) if len(sys.argv) > 1 else 5055
DIST = os.path.abspath(os.path.join(os.path.dirname(__file__), "../web/dist"))


class DevConfig(Config):
    TESTING = True
    IS_DEVELOPMENT = True
    SQLALCHEMY_DATABASE_URI = os.environ["DATABASE_URL"]
    SECRET_KEY = "e2e-secret"
    JWT_SECRET = "e2e-jwt-secret-that-is-long-enough-32"
    SESSION_COOKIE_SECURE = False
    RATELIMIT_ENABLED = False
    EMAIL_RESPONSE_FLOOR_SECONDS = 0.0
    R2_BUCKET = "e2e-bucket"
    R2_ENDPOINT_URL = f"http://localhost:{PORT}"
    R2_ACCESS_KEY_ID = "e2e-key"
    R2_SECRET_ACCESS_KEY = "e2e-secret-key"
    R2_PUBLIC_BASE_URL = ""


BUCKET: dict[str, dict] = {}

# Flipped by the test to simulate a deployment with no R2 credentials — which
# is precisely the state the production API is in right now.
STORAGE = {"configured": True}


def _presigned_put(key, content_type, expires_in=None):
    return f"http://localhost:{PORT}/__storage/{key}"


def _head(key):
    return BUCKET.get(key)


def _delete(key):
    BUCKET.pop(key, None)
    return True


def _presigned_get(key, expires_in=None):
    return f"http://localhost:{PORT}/__storage/{key}"


def _is_configured():
    return STORAGE["configured"]


r2_storage.R2Storage.generate_presigned_put = staticmethod(_presigned_put)
r2_storage.R2Storage.head_object = staticmethod(_head)
r2_storage.R2Storage.delete_object = staticmethod(_delete)
r2_storage.R2Storage.generate_presigned_get = staticmethod(_presigned_get)
r2_storage.R2Storage.is_configured = staticmethod(_is_configured)

app = create_app(DevConfig)


@app.put("/__storage/<path:key>")
def storage_put(key):
    """Stand-in for R2's presigned-PUT endpoint."""
    body = request.get_data()
    # Same shape R2Storage.head_object normalises to, not boto3's raw keys.
    BUCKET[key] = {
        "size_bytes": len(body),
        "content_type": request.content_type or "",
        "etag": "stub",
        "body": body,
    }
    return "", 200


@app.get("/__storage/<path:key>")
def storage_get(key):
    obj = BUCKET.get(key)
    if obj is None:
        return "", 404
    return obj["body"], 200, {"Content-Type": obj["content_type"] or "application/octet-stream"}


@app.post("/__control/storage")
def storage_control():
    STORAGE["configured"] = bool(request.get_json().get("configured"))
    return {"configured": STORAGE["configured"]}


@app.get("/", defaults={"path": ""})
@app.get("/<path:path>")
def spa(path):
    full = os.path.join(DIST, path)
    if path and os.path.isfile(full):
        return send_from_directory(DIST, path)
    return send_from_directory(DIST, "index.html")


if __name__ == "__main__":
    if os.path.exists("/tmp/livemsc-e2e.db"):
        os.remove("/tmp/livemsc-e2e.db")
    with app.app_context():
        db.create_all()
    app.run(port=PORT, threaded=True)
