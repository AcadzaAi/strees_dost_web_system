"""The whole student list of a coaching, with each student's batch flags (meta), so admins see
100% of a batch instantly, including students who haven't updated the app yet.

Acadza's user/by-coaching (the list the teacher notification screen loads) is read with the
admin's own token, page by page, in the background. Each student's true meta flags
(e.g. titanCourseMathEnrolled) go into the users collection, where "students of a batch" is
one indexed lookup. Students who open the app keep their own entry fresh anyway.
"""
from __future__ import annotations

import logging
import time

import requests
from pymongo import UpdateOne

from ..extensions import socketio
from . import settings
from .auth import _meta_batches, _strip_bearer, contact_of
from .mongo import db

log = logging.getLogger(__name__)

PAGE = 500
MAX_PAGES = 200            # 100,000 students per coaching
STALE_S = 6 * 3600


def _status_id(coaching: str) -> str:
    return f"roster:{coaching.strip().lower()}"


def status(coachings: list[str]) -> dict:
    out = {}
    for c in coachings:
        doc = db().settings.find_one({"_id": _status_id(c)}) or {}
        out[c] = {k: doc.get(k) for k in ("state", "students", "withMeta", "finishedAt", "error")}
    return out


def needs_sync(coaching: str) -> bool:
    doc = db().settings.find_one({"_id": _status_id(coaching)}) or {}
    if doc.get("state") == "running" and time.time() - (doc.get("startedAt") or 0) < 600:
        return False
    return time.time() - (doc.get("finishedAt") or 0) > STALE_S


def start(admin_token: str, coachings: list[str], force: bool = False) -> list[str]:
    """Starts a background sync for each coaching that needs one. Returns those started."""
    started = []
    for c in coachings:
        if not c.strip() or not (force or needs_sync(c)):
            continue
        db().settings.update_one({"_id": _status_id(c)},
                                 {"$set": {"state": "running", "startedAt": time.time(), "error": None}}, upsert=True)
        socketio.start_background_task(_sync, _strip_bearer(admin_token), c.strip())
        started.append(c)
    return started


def _sync(token: str, coaching: str) -> None:
    students = with_meta = 0
    try:
        for page in range(1, MAX_PAGES + 1):
            resp = requests.post(
                f"{settings.ACADZA_API_BASE}/user/by-coaching",
                params={"page": page, "limit": PAGE},
                json={"coaching": coaching},
                headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json"},
                timeout=30,
            )
            if resp.status_code != 200:
                raise RuntimeError(f"Acadza answered {resp.status_code}")
            body = resp.json() or {}
            data = body.get("data") if isinstance(body.get("data"), dict) else body
            users = data.get("users") or []
            ops = []
            for u in users:
                uid = str(u.get("_id") or "")
                if not uid:
                    continue
                students += 1
                fields = {
                    "name": (u.get("name") or u.get("username") or "").strip(),
                    "role": str(u.get("role") or "student"),
                    "coaching": str(u.get("reference") or coaching).strip().lower(),
                    "rosterAt": int(time.time() * 1000),
                    **contact_of(u),
                }
                if isinstance(u.get("meta"), dict) or u.get("coachingBatch"):
                    with_meta += 1
                    cb = u.get("coachingBatch") or []
                    cb = [cb] if isinstance(cb, str) else list(cb)
                    fields["batches"] = list(dict.fromkeys(str(b).strip() for b in cb + _meta_batches(u) if str(b).strip()))
                ops.append(UpdateOne({"_id": uid}, {"$set": fields,
                                                     "$setOnInsert": {"fcmTokens": [], "strikes": []}}, upsert=True))
            if ops:
                db().users.bulk_write(ops, ordered=False)
            total_pages = int(data.get("totalPages") or 0)
            if len(users) < PAGE or (total_pages and page >= total_pages):
                break
        db().settings.update_one({"_id": _status_id(coaching)}, {"$set": {
            "state": "done", "students": students, "withMeta": with_meta, "finishedAt": time.time()}})
        log.info("roster %s: %d students, %d with batch flags", coaching, students, with_meta)
    except Exception as exc:  # noqa: BLE001
        log.warning("roster %s failed: %s", coaching, exc)
        db().settings.update_one({"_id": _status_id(coaching)}, {"$set": {
            "state": "failed", "students": students, "withMeta": with_meta, "error": str(exc)[:200],
            "finishedAt": time.time()}})
