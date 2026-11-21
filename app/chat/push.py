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

from . import settings
from .mongo import db

log = logging.getLogger(__name__)

_SCOPE = "https://www.googleapis.com/auth/firebase.messaging"
_lock = threading.Lock()
_creds = None
_project_id: Optional[str] = None


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
            "android": {"priority": "high", "ttl": "86400s"},
            "apns": {"headers": {"apns-priority": "10"},
                     "payload": {"aps": {"sound": "default", "mutable-content": 1,
                                         "alert": {"title": data.get("title", ""), "body": data.get("body", "")},
                                         "thread-id": data.get("groupId", "")}}},
        }
    }
    try:
        r = requests.post(
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
            access = _access_token()
            if not access:
                return
            dead: list[tuple[str, str]] = []
            for user in db().users.find({"_id": {"$in": ids}}, projection={"fcmTokens": 1}):
                for entry in user.get("fcmTokens") or []:
                    tok = entry.get("token") if isinstance(entry, dict) else entry
                    if tok and _send_one(tok, data, access) == "dead":
                        dead.append((user["_id"], tok))
            for uid, tok in dead:
                db().users.update_one({"_id": uid}, {"$pull": {"fcmTokens": {"token": tok}}})
        except Exception:  # noqa: BLE001
            log.exception("fcm: send failed")

    from ..extensions import socketio
    socketio.start_background_task(run)
