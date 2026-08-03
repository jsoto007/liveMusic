"""Cloudflare R2 access.

The server never handles file bytes. It mints presigned URLs and verifies, via
``HEAD``, that what landed in the bucket matches what it signed for. Everything
here degrades to ``None``/``False`` when R2 is unconfigured so the rest of the
app boots and tests run without credentials — callers must treat a ``None``
presign as "storage unavailable", not as success.
"""

import uuid
from urllib.parse import urlparse

import boto3
from botocore.config import Config as BotoConfig
from botocore.exceptions import BotoCoreError, ClientError
from flask import current_app

# What a client is allowed to upload, and what extension we store it under.
# The map is also the allowlist — a content type absent from it is rejected
# before anything is signed.
AUDIO_CONTENT_TYPES: dict[str, str] = {
    "audio/mpeg": "mp3",
    "audio/mp4": "m4a",
    "audio/aac": "aac",
    "audio/ogg": "ogg",
    "audio/opus": "opus",
    "audio/wav": "wav",
    "audio/x-wav": "wav",
    "audio/flac": "flac",
    "audio/webm": "weba",
}

IMAGE_CONTENT_TYPES: dict[str, str] = {
    "image/jpeg": "jpg",
    "image/png": "png",
    "image/webp": "webp",
    "image/avif": "avif",
}


def _config():
    return current_app.config


# Built once per (process, credential set) and reused. Constructing a boto3
# client is expensive — it parses service models and builds a signer — and
# `access_url` calls this once per object during serialization, so a page of
# 100 listings was building 100 clients on the hot path. boto3 clients are
# thread-safe for the calls made here.
_CLIENT_CACHE: dict[tuple, object] = {}


def build_client():
    config = _config()
    endpoint = config.get("R2_ENDPOINT_URL") or (
        f"https://{config['R2_ACCOUNT_ID']}.r2.cloudflarestorage.com"
        if config.get("R2_ACCOUNT_ID")
        else ""
    )
    access_key = config.get("R2_ACCESS_KEY_ID")
    secret_key = config.get("R2_SECRET_ACCESS_KEY")
    region = config.get("R2_REGION", "auto")

    if not endpoint or not access_key or not secret_key or not config.get("R2_BUCKET"):
        current_app.logger.warning("R2 is not configured; media operations are disabled.")
        return None

    # Keyed on the credentials themselves, so a config change (or a second app
    # in the same process, as in the test suite) gets its own client rather
    # than silently reusing another's.
    cache_key = (endpoint, access_key, secret_key, region)
    client = _CLIENT_CACHE.get(cache_key)
    if client is None:
        client = boto3.client(
            "s3",
            endpoint_url=endpoint,
            aws_access_key_id=access_key,
            aws_secret_access_key=secret_key,
            region_name=region,
            config=BotoConfig(signature_version="s3v4", retries={"max_attempts": 3}),
        )
        _CLIENT_CACHE[cache_key] = client
    return client


class R2Storage:
    # ── Keys ───────────────────────────────────────────────────────────────

    @staticmethod
    def build_key(prefix: str, owner_id, content_type: str, *, kind: str) -> str | None:
        """Mint an opaque object key.

        The client never proposes a key. If it did, a caller could sign an
        upload onto another band's prefix, or walk out of the namespace with
        ``../``. The only client-derived input here is the content type, and
        that has already been checked against an allowlist.
        """
        table = AUDIO_CONTENT_TYPES if kind == "audio" else IMAGE_CONTENT_TYPES
        extension = table.get(content_type)
        if extension is None:
            return None
        return f"{prefix}/{owner_id}/{uuid.uuid4().hex}.{extension}"

    # ── Upload ─────────────────────────────────────────────────────────────

    @staticmethod
    def generate_presigned_post(key: str, content_type: str, max_bytes: int,
                                expires_in: int | None = None) -> dict | None:
        """A presigned POST the client submits the file directly to.

        POST rather than PUT because only POST carries a
        ``content-length-range`` condition, so R2 itself rejects an oversized
        body. A presigned PUT cannot bound the size: a client could declare
        10 MB and push 10 GB, and the first the server would hear of it is the
        storage bill.

        The conditions also pin the exact key and content type, so a signature
        issued for one object cannot be replayed to write another.
        """
        client = build_client()
        if client is None:
            return None

        config = _config()
        ttl = expires_in or config["R2_SIGNED_URL_TTL_SECONDS"]
        try:
            return client.generate_presigned_post(
                Bucket=config["R2_BUCKET"],
                Key=key,
                Fields={"Content-Type": content_type},
                Conditions=[
                    {"Content-Type": content_type},
                    ["content-length-range", 1, max_bytes],
                ],
                ExpiresIn=ttl,
            )
        except (ClientError, BotoCoreError) as exc:
            current_app.logger.error("R2 presigned POST failed for %s: %s", key, exc)
            return None

    @staticmethod
    def head_object(key: str) -> dict | None:
        """Fetch an object's metadata, or ``None`` if it is not there.

        This is the completion gate: it is the only way the server learns what
        actually got uploaded, since it never saw the bytes.
        """
        client = build_client()
        if client is None:
            return None
        try:
            response = client.head_object(Bucket=_config()["R2_BUCKET"], Key=key)
        except ClientError as exc:
            code = exc.response.get("Error", {}).get("Code")
            if code in {"404", "NoSuchKey", "NotFound"}:
                return None
            current_app.logger.error("R2 HEAD failed for %s: %s", key, exc)
            return None
        except BotoCoreError as exc:
            current_app.logger.error("R2 HEAD failed for %s: %s", key, exc)
            return None

        return {
            "size_bytes": response.get("ContentLength"),
            "content_type": response.get("ContentType"),
            "etag": (response.get("ETag") or "").strip('"'),
        }

    @staticmethod
    def delete_object(key: str) -> bool:
        client = build_client()
        if client is None:
            return False
        try:
            client.delete_object(Bucket=_config()["R2_BUCKET"], Key=key)
            return True
        except (ClientError, BotoCoreError) as exc:
            current_app.logger.error("R2 delete failed for %s: %s", key, exc)
            return False

    # ── Read ───────────────────────────────────────────────────────────────

    @staticmethod
    def generate_presigned_get(key: str, expires_in: int | None = None) -> str | None:
        client = build_client()
        if client is None:
            return None
        config = _config()
        try:
            return client.generate_presigned_url(
                "get_object",
                Params={"Bucket": config["R2_BUCKET"], "Key": key},
                ExpiresIn=expires_in or config["R2_SIGNED_URL_TTL_SECONDS"],
            )
        except (ClientError, BotoCoreError) as exc:
            current_app.logger.error("R2 presign GET failed for %s: %s", key, exc)
            return None

    @staticmethod
    def access_url(key: str | None) -> str | None:
        """A URL a client can fetch this object from, or ``None``.

        Prefers the public CDN base when one is configured (cacheable, no
        signature to expire); otherwise mints a short-lived presigned GET.
        Either way the result is per-request and must never be written to the
        database.
        """
        if not key:
            return None
        base = (_config().get("R2_PUBLIC_BASE_URL") or "").rstrip("/")
        if base:
            return f"{base}/{key}"
        return R2Storage.generate_presigned_get(key)

    # ── Introspection ──────────────────────────────────────────────────────

    @staticmethod
    def is_configured() -> bool:
        config = _config()
        return bool(
            config.get("R2_BUCKET")
            and config.get("R2_ACCESS_KEY_ID")
            and config.get("R2_SECRET_ACCESS_KEY")
            and (config.get("R2_ENDPOINT_URL") or config.get("R2_ACCOUNT_ID"))
        )

    @staticmethod
    def upload_origin() -> str | None:
        """The origin a browser will POST uploads to — needed for CSP checks."""
        config = _config()
        raw = config.get("R2_ENDPOINT_URL") or (
            f"https://{config['R2_ACCOUNT_ID']}.r2.cloudflarestorage.com"
            if config.get("R2_ACCOUNT_ID")
            else ""
        )
        if not raw:
            return None
        parsed = urlparse(raw)
        if not parsed.scheme or not parsed.netloc:
            return None
        return f"{parsed.scheme}://{parsed.netloc}"
