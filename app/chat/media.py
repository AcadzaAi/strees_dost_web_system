"""Photos, voice notes and documents in chats, stored in Cloudflare R2 (S3-compatible).

The phone never holds R2 keys. It asks the server for a short-lived upload link, uploads the
file straight to R2 (so media never passes through this server), then sends the message with
the file's key. Everyone in the group gets short-lived download links. The bucket stays private.

Files are stored as  g/<groupId>/<yyyy-mm>/<random>.<ext>  so a whole group can be cleaned up.

Environment (Render): R2_ENDPOINT, R2_ACCESS_KEY_ID, R2_SECRET_ACCESS_KEY, R2_BUCKET.
Without them media is off and text chat works exactly as before.
"""
from __future__ import annotations

import logging
import os
import secrets
import time
from typing import Optional

log = logging.getLogger(__name__)

R2_ENDPOINT = os.getenv("R2_ENDPOINT", "").strip().rstrip("/")
R2_ACCESS_KEY_ID = os.getenv("R2_ACCESS_KEY_ID", "").strip()
R2_SECRET_ACCESS_KEY = os.getenv("R2_SECRET_ACCESS_KEY", "").strip()
R2_BUCKET = os.getenv("R2_BUCKET", "").strip()

UPLOAD_LINK_S = 15 * 60                 # time to finish an upload
DOWNLOAD_LINK_S = 7 * 24 * 3600         # the longest R2 allows; the app keeps its own copy anyway

# What can be sent, and how big. Photos are compressed on the phone first (about 200 KB).
KINDS = {
    "image": {"max": 8 * 1024 * 1024, "mimes": ("image/jpeg", "image/png", "image/webp", "image/gif", "image/heic")},
    "audio": {"max": 16 * 1024 * 1024, "mimes": ("audio/mp4", "audio/m4a", "audio/aac", "audio/mpeg", "audio/ogg",
                                                  "audio/webm", "audio/x-m4a", "audio/3gpp", "audio/amr")},
    "file": {"max": 25 * 1024 * 1024, "mimes": ()},     # any type (PDF, Word, PowerPoint…)
}
EXT = {"image/jpeg": "jpg", "image/png": "png", "image/webp": "webp", "image/gif": "gif", "image/heic": "heic",
       "audio/mp4": "m4a", "audio/m4a": "m4a", "audio/x-m4a": "m4a", "audio/aac": "aac", "audio/mpeg": "mp3",
       "audio/ogg": "ogg", "audio/webm": "webm", "audio/3gpp": "3gp", "audio/amr": "amr", "application/pdf": "pdf"}

_client = None


def enabled() -> bool:
    return bool(R2_ENDPOINT and R2_ACCESS_KEY_ID and R2_SECRET_ACCESS_KEY and R2_BUCKET)


def _s3():
    global _client
    if _client is None:
        import boto3
        from botocore.config import Config
        _client = boto3.client(
            "s3",
            endpoint_url=R2_ENDPOINT,
            aws_access_key_id=R2_ACCESS_KEY_ID,
            aws_secret_access_key=R2_SECRET_ACCESS_KEY,
            region_name="auto",
            config=Config(signature_version="s3v4", retries={"max_attempts": 3, "mode": "standard"},
                          s3={"addressing_style": "path"}),
        )
    return _client


def key_for(group_id: str, mime: str, name: str = "") -> str:
    ext = EXT.get(mime) or (name.rsplit(".", 1)[-1].lower()[:8] if "." in name else "bin")
    ext = "".join(c for c in ext if c.isalnum()) or "bin"
    return f"g/{group_id}/{time.strftime('%Y-%m')}/{secrets.token_urlsafe(18)}.{ext}"


def belongs_to(key: str, group_id: str) -> bool:
    return isinstance(key, str) and key.startswith(f"g/{group_id}/") and ".." not in key and len(key) < 300


def upload_link(key: str, mime: str, size: int) -> str:
    """A PUT link the phone uploads to. Type and exact size are part of the signature, so a
    bigger file than the one allowed is refused by storage itself."""
    return _s3().generate_presigned_url(
        "put_object", Params={"Bucket": R2_BUCKET, "Key": key, "ContentType": mime, "ContentLength": int(size)},
        ExpiresIn=UPLOAD_LINK_S)


def delete_many(keys: list[str]) -> None:
    """Up to 1000 files per call."""
    for i in range(0, len(keys), 1000):
        chunk = [{"Key": k} for k in keys[i:i + 1000]]
        try:
            _s3().delete_objects(Bucket=R2_BUCKET, Delete={"Objects": chunk, "Quiet": True})
        except Exception:  # noqa: BLE001
            log.warning("media: could not delete %d files", len(chunk))


_link_cache: dict[str, tuple[str, float]] = {}


def download_link(key: str) -> str:
    """A GET link, reused for a day so the same message keeps the same link (phones cache by it)."""
    now = time.time()
    hit = _link_cache.get(key)
    if hit and hit[1] > now:
        return hit[0]
    url = _s3().generate_presigned_url("get_object", Params={"Bucket": R2_BUCKET, "Key": key}, ExpiresIn=DOWNLOAD_LINK_S)
    _link_cache[key] = (url, now + 24 * 3600)
    if len(_link_cache) > 20000:
        _link_cache.clear()
    return url


def read(key: str, max_bytes: int) -> Optional[bytes]:
    """The file's bytes (for the nudity check), or None when it is missing or too big."""
    try:
        obj = _s3().get_object(Bucket=R2_BUCKET, Key=key)
        if int(obj.get("ContentLength") or 0) > max_bytes:
            return None
        return obj["Body"].read(max_bytes + 1)[:max_bytes]
    except Exception:  # noqa: BLE001
        log.warning("chat: could not read %s from storage", key)
        return None


def delete(key: str) -> None:
    try:
        _s3().delete_object(Bucket=R2_BUCKET, Key=key)
    except Exception:  # noqa: BLE001
        log.warning("media: could not delete %s", key)


def delete_group(group_id: str) -> None:
    """Every file of a deleted group."""
    try:
        s3 = _s3()
        token: Optional[str] = None
        while True:
            kw = {"Bucket": R2_BUCKET, "Prefix": f"g/{group_id}/", "MaxKeys": 1000}
            if token:
                kw["ContinuationToken"] = token
            page = s3.list_objects_v2(**kw)
            keys = [{"Key": o["Key"]} for o in page.get("Contents", [])]
            if keys:
                s3.delete_objects(Bucket=R2_BUCKET, Delete={"Objects": keys, "Quiet": True})
            if not page.get("IsTruncated"):
                break
            token = page.get("NextContinuationToken")
    except Exception:  # noqa: BLE001
        log.warning("media: could not clean up group %s", group_id)


def label(media: Optional[dict]) -> str:
    """What the chat list and notifications show for a media message."""
    if not media:
        return ""
    kind = media.get("kind")
    if kind == "image":
        return "📷 Photo"
    if kind == "audio":
        secs = int((media.get("durationMs") or 0) / 1000)
        return f"🎤 Voice note ({secs // 60}:{secs % 60:02d})" if secs else "🎤 Voice note"
    return "📄 " + (media.get("name") or "Document")
