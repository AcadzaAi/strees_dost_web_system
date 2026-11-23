"""Chat limits that can be changed from Firebase without a redeploy or an app update.

Edit them in the Firebase Realtime Database at  chatConfig  (same project as the FCM service
account). Anything missing there uses the defaults below. The server re-reads it every 5 minutes,
enforces it, and sends it to the app (GET /api/chat/config and /me) so the app compresses and
warns with the same numbers.

Environment: FIREBASE_DATABASE_URL, e.g. https://<project>-default-rtdb.asia-southeast1.firebasedatabase.app
"""
from __future__ import annotations

import copy
import json
import logging
import os
import threading
import time
from typing import Any

import requests

from . import settings

log = logging.getLogger(__name__)

DEFAULTS: dict[str, Any] = {
    "media": {
        "enabled": True,
        # Files are removed from storage and chats after this many days.
        "retentionDays": 21,
        # Uploads stop when the files kept in storage reach this size (R2's free plan is 10 GB).
        "storageLimitGB": 9.0,
        # And no more than this much uploaded in one calendar month (India time), whatever expires.
        "monthlyUploadGB": 9.0,
        "image": {"maxSide": 1280, "quality": 70, "maxKB": 1500},
        "audio": {"bitrateKbps": 32, "maxSeconds": 300, "maxKB": 3000},
        "file": {"maxMB": 10, "compress": True},
        # Per person per day (India time). Teachers and admins use "teacher".
        "daily": {
            "student": {"count": 15, "mb": 15},
            "teacher": {"count": 100, "mb": 150},
        },
        # Students may send these kinds (teachers always may).
        "studentsCanSend": {"image": True, "audio": True, "file": True},
        # Nudity check after delivery, on our own server (photos, and the first pages of PDFs).
        # strictness: 1 = normal; higher catches more (and flags more by mistake), lower fewer.
        "scan": {"images": True, "documents": True, "documentPages": 5, "strictness": 1.0},
    },
    # Words admins add (or un-block) without a deploy: Firebase chatConfig/moderation.
    "moderation": {"extraWords": [], "extraHindiWords": [], "extraCompetitors": [], "allowWords": []},
    # AI check of students' messages a few seconds after delivery (Groq, free; needs GROQ_API_KEY).
    # batchSize: messages per request. waitSeconds: how long to gather a batch before checking.
    # models: Groq models in order of use (the next one takes over when one's daily allowance ends).
    "aiCheck": {"enabled": True, "batchSize": 25, "waitSeconds": 5,
                "models": ["openai/gpt-oss-safeguard-20b", "openai/gpt-oss-20b", "openai/gpt-oss-120b"]},
    "messages": {
        # Your own message can be edited for this long after sending.
        "editMinutes": 60,
        # Emoji reactions on messages and files (the author gets a notification).
        "reactions": True,
        # "online" / "last seen" in direct chats.
        "showOnline": True,
    },
}

_lock = threading.Lock()
_cache: dict[str, Any] = copy.deepcopy(DEFAULTS)
_loaded_at = 0.0
_REFRESH_S = 300
_creds = None


def _merge(base: dict, over: Any) -> dict:
    out = copy.deepcopy(base)
    if not isinstance(over, dict):
        return out
    for k, v in over.items():
        if k in out and isinstance(out[k], dict) and isinstance(v, dict):
            out[k] = _merge(out[k], v)
        elif k in out and v is not None:
            # Keep the type of the default (numbers from Firebase may arrive as strings).
            d = out[k]
            try:
                if isinstance(d, bool):
                    out[k] = v in (True, "true", "True", "1", 1)
                elif isinstance(d, (int, float)):
                    out[k] = type(d)(float(v)) if isinstance(d, float) else int(float(v))
                else:
                    out[k] = v
            except (TypeError, ValueError):
                pass
    return out


def _db_url() -> str:
    url = os.getenv("FIREBASE_DATABASE_URL", "").strip().rstrip("/")
    if url:
        return url
    try:
        pid = json.loads(settings.FIREBASE_SERVICE_ACCOUNT_JSON).get("project_id")
    except Exception:  # noqa: BLE001
        pid = None
    return f"https://{pid}-default-rtdb.firebaseio.com" if pid else ""


def _token() -> str | None:
    global _creds
    if not settings.FIREBASE_SERVICE_ACCOUNT_JSON:
        return None
    from google.auth.transport.requests import Request
    from google.oauth2 import service_account
    if _creds is None:
        _creds = service_account.Credentials.from_service_account_info(
            json.loads(settings.FIREBASE_SERVICE_ACCOUNT_JSON),
            scopes=["https://www.googleapis.com/auth/firebase.database", "https://www.googleapis.com/auth/userinfo.email"])
    if not _creds.valid:
        _creds.refresh(Request())
    return _creds.token


def refresh() -> None:
    """Reads chatConfig from Firebase; on any problem the last good values stay."""
    global _cache, _loaded_at
    url = _db_url()
    _loaded_at = time.time()
    if not url:
        return
    try:
        token = _token()
        if not token:
            return
        r = requests.get(f"{url}/chatConfig.json", headers={"Authorization": f"Bearer {token}"}, timeout=5)
        if r.status_code != 200:
            log.warning("chat config: Firebase answered %s", r.status_code)
            return
        merged = _merge(DEFAULTS, r.json() or {})
        with _lock:
            _cache = merged
    except Exception:  # noqa: BLE001
        log.warning("chat config: could not read Firebase, keeping the last values")


def get() -> dict[str, Any]:
    if time.time() - _loaded_at > _REFRESH_S:
        refresh()
    with _lock:
        return _cache


def set_for_tests(over: dict) -> None:
    global _cache, _loaded_at
    with _lock:
        _cache = _merge(DEFAULTS, over)
    _loaded_at = time.time() + 10 ** 9


def media() -> dict[str, Any]:
    return get()["media"]


def edit_minutes() -> int:
    return int(get()["messages"]["editMinutes"])


def show_online() -> bool:
    return bool(get()["messages"].get("showOnline", True))


def reactions_on() -> bool:
    return bool(get()["messages"].get("reactions", True))


def public() -> dict[str, Any]:
    """What the app needs (no secrets in here)."""
    c = get()
    return {"media": c["media"], "messages": c["messages"]}
