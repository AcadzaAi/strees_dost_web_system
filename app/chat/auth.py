"""Who is calling: verified with the student's own Acadza token.

The token is Acadza's JWT ({id, role, exp}). We read the id from the token itself (never from the
request) and ask Acadza's `user/details` with that same token: Acadza answers 401 for a forged or
expired token, so a 200 whose _id matches proves the caller. Results are cached for 15 minutes.
"""
from __future__ import annotations

import base64
import hashlib
import json
import logging
import threading
import time
from dataclasses import dataclass, field
from functools import wraps
from typing import Callable, Optional

import requests
from flask import g, jsonify, request

from . import settings
from .mongo import db

log = logging.getLogger(__name__)

CACHE_TTL_S = 15 * 60
STAFF_ROLES = {"teacher", "admin", "faculty", "mentor"}


@dataclass(frozen=True)
class ChatUser:
    id: str
    name: str
    role: str                      # Acadza role: student / teacher / ...
    coaching: str                  # Acadza "reference": the brand / coaching the student belongs to
    batches: tuple[str, ...] = field(default_factory=tuple)
    is_admin: bool = False

    @property
    def is_staff(self) -> bool:
        return self.is_admin or self.role.lower() in STAFF_ROLES


class AuthError(Exception):
    pass


_cache: dict[str, tuple[float, ChatUser]] = {}
_cache_lock = threading.Lock()


def _jwt_payload(token: str) -> dict:
    try:
        part = token.split(".")[1]
        part += "=" * (-len(part) % 4)
        return json.loads(base64.urlsafe_b64decode(part))
    except Exception as exc:  # noqa: BLE001
        raise AuthError("not an Acadza token") from exc


def _strip_bearer(raw: str) -> str:
    raw = (raw or "").strip()
    return raw[7:].strip() if raw.lower().startswith("bearer ") else raw


def is_admin_id(user_id: str) -> bool:
    if user_id in settings.CHAT_ADMIN_IDS:
        return True
    return db().chat_admins.find_one({"_id": user_id}, projection={"_id": 1}) is not None


def verify_token(raw_token: str) -> ChatUser:
    token = _strip_bearer(raw_token)
    if not token:
        raise AuthError("missing token")
    payload = _jwt_payload(token)
    user_id = str(payload.get("id") or "")
    exp = payload.get("exp")
    if not user_id:
        raise AuthError("token has no user")
    if isinstance(exp, (int, float)) and exp < time.time():
        raise AuthError("token expired")

    key = hashlib.sha256(token.encode()).hexdigest()
    now = time.time()
    with _cache_lock:
        hit = _cache.get(key)
        if hit and hit[0] > now:
            return hit[1]

    try:
        resp = requests.post(
            f"{settings.ACADZA_API_BASE}/user/details",
            json={"userid": user_id},
            headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json"},
            timeout=8,
        )
    except requests.RequestException as exc:
        raise AuthError("could not reach Acadza") from exc
    if resp.status_code in (401, 403):
        raise AuthError("token rejected")
    if resp.status_code != 200:
        raise AuthError(f"Acadza answered {resp.status_code}")
    body = resp.json() or {}
    data = body.get("data") if isinstance(body.get("data"), dict) else body
    if str(data.get("_id") or "") != user_id:
        raise AuthError("token and user don't match")

    batches = data.get("coachingBatch") or []
    if isinstance(batches, str):
        batches = [batches]
    batches = list(batches) + _meta_batches(data)
    role = str(data.get("role") or payload.get("role") or "student")
    user = ChatUser(
        id=user_id,
        name=(data.get("name") or data.get("username") or "Student").strip(),
        role=role,
        coaching=str(data.get("reference") or "acadza").strip().lower() or "acadza",
        batches=tuple(dict.fromkeys(str(b).strip() for b in batches if str(b).strip())),
        # Admins: only teachers, and only the ones on the admin list.
        is_admin=role.lower() in STAFF_ROLES and is_admin_id(user_id),
    )
    _remember(user)
    with _cache_lock:
        if len(_cache) > 20_000:
            _cache.clear()
        _cache[key] = (now + CACHE_TTL_S, user)
    return user


def _meta_batches(data: dict) -> list[str]:
    """Batches the way the notification screen sees them: every meta flag set to true
    (e.g. meta.spartansCourseMathEnrolled = true, the `value` of a batch in Firebase <brand>Batches)."""
    out: list[str] = []
    for key in ("meta", "userMeta"):
        meta = data.get(key)
        if isinstance(meta, dict):
            out += [str(k) for k, v in meta.items() if v is True or str(v).strip().lower() == "true"]
    return out


def _remember(user: ChatUser) -> None:
    """Keeps the users collection in step with Acadza (name, role, batches)."""
    db().users.update_one(
        {"_id": user.id},
        {
            "$set": {"name": user.name, "role": user.role, "coaching": user.coaching,
                     "batches": list(user.batches), "lastSeenAt": int(time.time() * 1000)},
            "$setOnInsert": {"fcmTokens": [], "strikes": []},
        },
        upsert=True,
    )


def require_user(fn: Callable) -> Callable:
    """REST: Authorization: Bearer <Acadza token>. Sets g.chat_user."""
    @wraps(fn)
    def wrapper(*args, **kwargs):
        try:
            g.chat_user = verify_token(request.headers.get("Authorization", ""))
        except AuthError as exc:
            return jsonify({"error": "unauthorized", "reason": str(exc)}), 401
        return fn(*args, **kwargs)
    return wrapper


def require_admin(fn: Callable) -> Callable:
    @wraps(fn)
    @require_user
    def wrapper(*args, **kwargs):
        if not g.chat_user.is_admin:
            return jsonify({"error": "forbidden"}), 403
        return fn(*args, **kwargs)
    return wrapper


def require_staff(fn: Callable) -> Callable:
    """Teachers (group admins who aren't on the chat-admin list still manage their groups)."""
    @wraps(fn)
    @require_user
    def wrapper(*args, **kwargs):
        if not g.chat_user.is_staff:
            return jsonify({"error": "forbidden"}), 403
        return fn(*args, **kwargs)
    return wrapper


def current_user() -> Optional[ChatUser]:
    return getattr(g, "chat_user", None)
