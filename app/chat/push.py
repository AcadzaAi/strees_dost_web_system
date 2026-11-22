"""Notifications through FCM HTTP v1, sent from the server for every new message.

High-priority data messages: the app builds the notification itself (one conversation-style
notification per group, reply from the notification, default sound on the "Chats" channel) and
can skip it while that chat is open. Tokens FCM reports as dead are removed.
"""
from __future__ import annotations

import json
import logging
import threading
import time
from typing import Iterable, Optional

import requests
from concurrent.futures import ThreadPoolExecutor

from . import settings
from .mongo import db

log = logging.getLogger(__name__)

_SCOPE = "https://www.googleapis.com/auth/firebase.messaging"
_lock = threading.Lock()
_creds = None
_project_id: Optional[str] = None

# One kept-alive HTTPS connection pool to FCM: no new TLS handshake per phone (saves ~200 ms each).
_session = requests.Session()
_session.mount("https://", requests.adapters.HTTPAdapter(pool_connections=4, pool_maxsize=64))
# Phones are sent to side by side, not one after another (green threads on the server).
_pool = ThreadPoolExecutor(max_workers=48)


def enabled() -> bool:
    return bool(settings.FIREBASE_SERVICE_ACCOUNT_JSON)


def _access_token() -> Optional[str]:
    global _creds, _project_id
    if not enabled():
        return None
    from google.auth.transport.requests import Request
    from google.oauth2 import service_account

    with _lock:
        if _creds is None:
            info = json.loads(settings.FIREBASE_SERVICE_ACCOUNT_JSON)
            _project_id = info["project_id"]
            _creds = service_account.Credentials.from_service_account_info(info, scopes=[_SCOPE])
        if not _creds.valid or _creds.expiry is None or (_creds.expiry.timestamp() - time.time()) < 300:
            _creds.refresh(Request())
        return _creds.token


def _send_one(token: str, data: dict[str, str], access: str) -> str:
    """'ok', 'dead' (remove the token) or 'error'."""
    body = {
        "message": {
            "token": token,
            "data": data,
            # High priority: delivered at once, even when the phone is dozing.
            "android": {"priority": "high", "ttl": "86400s"},
            "apns": {"headers": {"apns-priority": "10"},
                     "payload": {"aps": {"sound": "default", "mutable-content": 1,
                                         "alert": {"title": data.get("title", ""), "body": data.get("body", "")},
                                         "thread-id": data.get("groupId", "")}}},
        }
    }
    try:
        r = _session.post(
            f"https://fcm.googleapis.com/v1/projects/{_project_id}/messages:send",
            headers={"Authorization": f"Bearer {access}", "Content-Type": "application/json"},
            data=json.dumps(body), timeout=10,
        )
    except requests.RequestException:
        return "error"
    if r.status_code == 200:
        return "ok"
    text = r.text
    if r.status_code in (404, 400) and ("UNREGISTERED" in text or "INVALID_ARGUMENT" in text and "token" in text.lower()):
        return "dead"
    log.warning("fcm: %s %s", r.status_code, text[:200])
    return "error"


def send_to_users(user_ids: Iterable[str], data: dict[str, str]) -> None:
    """Fire-and-forget: runs in the background so sending a message never waits for FCM."""
    ids = list(dict.fromkeys(user_ids))
    if not ids or not enabled():
        return

    def run() -> None:
        try:
            started = time.time()
            access = _access_token()
            if not access:
                return
            targets: list[tuple[str, str]] = []
            found = set()
            for user in db().users.find({"_id": {"$in": ids}}, projection={"fcmTokens": 1}):
                for entry in user.get("fcmTokens") or []:
                    tok = entry.get("token") if isinstance(entry, dict) else entry
                    if tok:
                        targets.append((user["_id"], tok))
                        found.add(user["_id"])
            results = list(_pool.map(lambda t: _send_one(t[1], data, access), targets)) if targets else []
            dead = [t for t, r in zip(targets, results) if r == "dead"]
            for uid, tok in dead:
                db().users.update_one({"_id": uid}, {"$pull": {"fcmTokens": {"token": tok}}})
            log.info("fcm %s %s: %d people, %d phones, %d sent, %d dead, %d without the app, %d ms",
                     data.get("type"), data.get("groupId"), len(ids), len(targets), results.count("ok"), len(dead),
                     len(ids) - len(found), int((time.time() - started) * 1000))
        except Exception:  # noqa: BLE001
            log.exception("fcm: send failed")

    from ..extensions import socketio
    socketio.start_background_task(run)


def warm_up() -> None:
    """Fetches the FCM access token at start-up and keeps it fresh, so no message waits for it."""
    if not enabled():
        return

    def loop() -> None:
        while True:
            try:
                _access_token()
            except Exception:  # noqa: BLE001
                log.warning("fcm: could not refresh the access token")
            time.sleep(1200)

    from ..extensions import socketio
    socketio.start_background_task(loop)

