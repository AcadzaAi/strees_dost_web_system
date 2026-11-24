"""Chat limits that can be changed from Firebase without a redeploy or an app update.

Edit them in the Firebase Realtime Database at  chatConfig  (same project as the FCM service
account). Anything missing there uses the defaults below. The server re-reads it every 5 minutes,
enforces it, and sends it to the app (GET /api/chat/config and /me) so the app compresses and
warns with the same numbers.

Live: watch() keeps one quiet connection open to Firebase (its REST streaming), which sends a
message only when something under chatConfig changes; the server then re-reads it at once. While
that connection is up, the 5-minute re-read becomes a 30-minute safety net. The app also listens
to chatConfig/media and chatConfig/messages itself, so phones update without asking the server.

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
        # The documents students may send (teachers any file). No videos, apps or zips.
        "studentFileTypes": ["pdf", "doc", "docx", "ppt", "pptx", "xls", "xlsx", "txt"],
        # Nudity check after delivery, on our own server (photos, and the first pages of PDFs).
        # strictness: 1 = normal; higher catches more (and flags more by mistake), lower fewer.
        "scan": {"images": True, "documents": True, "documentPages": 5, "strictness": 1.0},
    },
    # Words admins add (or un-block) without a deploy: Firebase chatConfig/moderation.
    # muteMinutes: an explicit message or photo (sexual, abusive) pauses that student in the group
    # for this long; group admins can lift it. Other blocked things (links, other coachings) never mute.
    "moderation": {"extraWords": [], "extraHindiWords": [], "extraCompetitors": [], "allowWords": [],
                   "extraEmojis": [], "muteMinutes": 20,
                   # links: "everyone" may send links, or only "admins" (group admins).
                   "links": "everyone"},
    # AI check of students' messages a few seconds after delivery (Groq, free; needs GROQ_API_KEY).
    # batchSize: messages per request. waitSeconds: how long to gather a batch before checking.
    # models: Groq models in order of use (the next one takes over when one's daily allowance ends).
    "aiCheck": {"enabled": True, "batchSize": 25, "waitSeconds": 5,
                "models": ["openai/gpt-oss-safeguard-20b", "openai/gpt-oss-20b", "openai/gpt-oss-120b"]},
    # Students verify their phone with an OTP the first time a teacher adds them from the app, and
    # on every new phone (not for groups filled from the coaching's batches). allowWithoutPhone:
    # an account with no phone number can't get an OTP, so it is let in (and logged).
    "security": {"phoneCheck": True, "allowWithoutPhone": True},
    # The whole chat, for everyone: open false = closed (students and teachers see closedMessage,
    # nothing is sent or received); minClientVersion: app builds whose chat is older than this are
    # asked to update (the app reports its chat version; 1 = the first release).
    "service": {"open": True, "closedMessage": "Chat is paused for a short while. Please check back soon.",
                "minClientVersion": 0},
    "messages": {
        # Your own message can be edited for this long after sending.
        "editMinutes": 60,
        # Emoji reactions on messages and files (the author gets a notification).
        "reactions": True,
        # "online" / "last seen" in direct chats.
        "showOnline": True,
        # Title and picture under a link (YouTube and other sites), fetched and checked by the server.
        "linkPreviews": True,
        # @mentions in groups (the person is notified even if they muted the group).
        # studentsMentionStudents false: students can mention only teachers.
        "mentions": True,
        "studentsMentionStudents": True,
        # The line at the top of every chat (under the group name). null: the app's own text;
        # "": no line; any text: that text.
        "rulesNote": None,
    },
}

_lock = threading.Lock()
_cache: dict[str, Any] = copy.deepcopy(DEFAULTS)
_loaded_at = 0.0
_REFRESH_S = 300
_REFRESH_WATCHED_S = 1800
_watching = False
_watch_started = False
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
    if time.time() - _loaded_at > (_REFRESH_WATCHED_S if _watching else _REFRESH_S):
        refresh()
    with _lock:
        return _cache


def _watch_once() -> None:
    """One streaming connection; returns when Firebase or the network closes it."""
    global _watching
    url, token = _db_url(), _token()
    if not url or not token:
        raise RuntimeError("no Firebase url or credentials")
    opened = time.time()
    # Firebase sends a keep-alive every ~30 s, so 90 s of silence means the line is dead.
    with requests.get(f"{url}/chatConfig.json", params={"access_token": token},
                      headers={"Accept": "text/event-stream"}, stream=True, timeout=(10, 90)) as r:
        if r.status_code != 200:
            raise RuntimeError(f"Firebase answered {r.status_code}")
        _watching = True
        event = ""
        for raw in r.iter_lines(decode_unicode=True):
            line = raw or ""
            if line.startswith("event:"):
                event = line[6:].strip()
            elif line.startswith("data:") and event in ("put", "patch"):
                refresh()                  # something changed: read the whole node once
            elif line.startswith("data:") and event in ("cancel", "auth_revoked"):
                return                     # rules changed or token expired: reconnect
            if time.time() - opened > 50 * 60:
                return                     # renew the token before its hour is up


def watch() -> None:
    """Runs for the life of the server (a background task); reconnects with a growing pause."""
    global _watching
    pause = 5
    while True:
        try:
            _watch_once()
            pause = 5
        except Exception as exc:  # noqa: BLE001
            log.warning("chat config: live updates paused (%s), retrying in %ss", exc, pause)
            pause = min(pause * 2, 300)
        finally:
            _watching = False
        time.sleep(pause)


def start_watch() -> None:
    global _watch_started
    if _watch_started or not settings.FIREBASE_SERVICE_ACCOUNT_JSON:
        return
    _watch_started = True
    from ..extensions import socketio
    socketio.start_background_task(watch)
    log.info("chat config: watching Firebase for live changes")


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
