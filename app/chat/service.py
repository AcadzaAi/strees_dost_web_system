"""Chat rules in one place, used by both the socket events and the REST API.

Delivery model: every message gets the group's next `seq`. A phone that remembers the last seq it
has for a group asks for "everything after seq N" when it reconnects, so nothing is ever missed.
The app's own `clientId` makes resending safe: the same clientId never creates a second message.

Ticks: sent = the server stored it (ack); delivered / read = every other member's
lastDeliveredSeq / lastReadSeq has reached it, broadcast as one `receipts` event per group.

Who may do what
  - Chat admins (teachers on CHAT_ADMIN_IDS) create groups; they are the group's creator.
  - Group admins (the creator, and teachers the admins promote) rename, switch "admins only",
    add / remove anyone, mute students, delete any message, add another group's students.
  - Only the creator deletes the group. Only teachers can be admins.
  - Everyone deletes their own messages at any time, for everyone.
  - Direct chats: a student can message the teachers of their groups, never another student;
    teachers can message anyone they share a group with.
"""
from __future__ import annotations

import logging
import re
import secrets
import threading
import time
from collections import deque
from typing import Any, Optional

from pymongo import ReturnDocument
from pymongo.errors import DuplicateKeyError

from . import ai_review, chatconfig, media, media_scan, moderation, presence, push, settings
from .auth import STAFF_ROLES, ChatUser
from .mongo import db, next_seq

log = logging.getLogger(__name__)

NS = "/chat"
GROUP_TYPES = ("announcement", "chat")
MEMBER_ROLES = ("student", "teacher", "admin")
STAFF_MEMBER_ROLES = ("teacher", "admin")
STUDENT_AVATARS = ("g1", "g2", "g3", "b1", "b2", "b3")
TEACHER_AVATAR = "teacher"
ADMIN_NOTICE_EVERY_S = 30 * 60


class ChatError(Exception):
    def __init__(self, code: str, message: str, status: int = 400):
        super().__init__(message)
        self.code, self.message, self.status = code, message, status

    def to_dict(self) -> dict:
        return {"ok": False, "error": self.code, "message": self.message}


def now_ms() -> int:
    return int(time.time() * 1000)


def group_room(group_id: str) -> str:
    return f"g:{group_id}"


def user_room(user_id: str) -> str:
    return f"u:{user_id}"


def _emit(event: str, payload: Any, room: str, skip_sid: Optional[str] = None) -> None:
    from ..extensions import socketio
    socketio.emit(event, payload, to=room, namespace=NS, skip_sid=skip_sid)


# ── avatars ──────────────────────────────────────────────────────────────────────────────────

def is_photo(avatar: Optional[str]) -> bool:
    return isinstance(avatar, str) and avatar.startswith("https://") and "/api/chat/avatar/" in avatar


def avatar_of(role: Optional[str], chosen: Optional[str]) -> str:
    """Teachers and admins: their own photo if they set one, else the teacher picture. Students
    only ever have one of the drawn characters (never a photo)."""
    if (role or "student") != "student":
        return chosen if is_photo(chosen) else TEACHER_AVATAR
    return chosen if chosen in STUDENT_AVATARS else ""


def _contact_cards(user_ids) -> dict[str, dict]:
    """Name and phone from the users collection, for lists admins see (a member saved without a
    name still shows who they are). One query."""
    ids = list({u for u in user_ids if u and u != "system"})
    if not ids:
        return {}
    return {u["_id"]: {"name": u.get("name") or "", "phone": u.get("phone") or ""}
            for u in db().users.find({"_id": {"$in": ids}}, projection={"name": 1, "phone": 1})}


def _avatars(user_ids) -> dict[str, str]:
    ids = list({u for u in user_ids if u and u != "system"})
    if not ids:
        return {}
    return {u["_id"]: u.get("avatar") or "" for u in db().users.find({"_id": {"$in": ids}}, projection={"avatar": 1})}


def set_avatar(user: ChatUser, avatar: str) -> str:
    if user.is_staff:
        raise ChatError("teacher_avatar", "Teachers always have the teacher picture.", 403)
    if avatar not in STUDENT_AVATARS:
        raise ChatError("bad_avatar", "Pick one of the characters.")
    db().users.update_one({"_id": user.id}, {"$set": {"avatar": avatar}}, upsert=True)
    _avatar_cache[user.id] = avatar
    return avatar


_avatar_cache: dict[str, str] = {}     # user id -> chosen character (saves a lookup per message)


def my_avatar(user: ChatUser) -> str:
    if user.id not in _avatar_cache:
        doc = db().users.find_one({"_id": user.id}, projection={"avatar": 1}) or {}
        _avatar_cache[user.id] = doc.get("avatar") or ""
    return avatar_of("teacher" if user.is_staff else "student", _avatar_cache[user.id])


# ── a teacher's own photo ────────────────────────────────────────────────────────────────────

AVATAR_MAX_BYTES = 600 * 1024


def request_avatar_upload(user: ChatUser, body: dict) -> dict:
    """Teachers and admins only: a link to upload their photo (a small JPEG the app made)."""
    if not user.is_staff:
        raise ChatError("forbidden", "Only teachers can use their own photo.", 403)
    if not media.enabled():
        raise ChatError("media_off", "Photos can't be uploaded right now.", 503)
    size = int(body.get("size") or 0)
    if size <= 0 or size > AVATAR_MAX_BYTES:
        raise ChatError("too_big", "This photo is too big.", 400)
    key = f"a/{user.id}/{secrets.token_urlsafe(12)}.jpg"
    db().media_pending.insert_one({"_id": key, "size": size, "userId": user.id, "groupId": "avatar", "at": now_ms()})
    return {"key": key, "uploadUrl": media.upload_link(key, "image/jpeg", size), "method": "PUT",
            "headers": {"Content-Type": "image/jpeg"}, "expiresIn": media.UPLOAD_LINK_S}


def set_avatar_photo(user: ChatUser, key: str, base_url: str) -> str:
    """The uploaded photo is checked (nudity) and becomes the teacher's picture everywhere."""
    if not user.is_staff:
        raise ChatError("forbidden", "Only teachers can use their own photo.", 403)
    if not isinstance(key, str) or not key.startswith(f"a/{user.id}/") or ".." in key:
        raise ChatError("bad_photo", "That photo could not be used.")
    if not db().media_pending.find_one({"_id": key}):
        raise ChatError("bad_photo", "That photo could not be used.")
    data = media.read(key, AVATAR_MAX_BYTES + 1024)
    scan = media_scan.check_image(data) if data else None
    if scan is None or not scan.checked or not scan.allowed:
        media.delete(key)
        db().media_pending.delete_one({"_id": key})
        raise ChatError("bad_photo", "This photo can't be used. Please pick another one.", 422)
    old = (db().users.find_one({"_id": user.id}, projection={"avatarKey": 1}) or {}).get("avatarKey")
    token = key.rsplit("/", 1)[-1].split(".")[0]
    url = f"{base_url.rstrip('/')}/api/chat/avatar/{user.id}/{token}"
    db().users.update_one({"_id": user.id}, {"$set": {"avatar": url, "avatarKey": key}}, upsert=True)
    db().media_pending.delete_one({"_id": key})
    if old and old != key:
        media.delete(old)
    _avatar_cache[user.id] = url
    return url


def remove_avatar_photo(user: ChatUser) -> str:
    if not user.is_staff:
        raise ChatError("forbidden", "Only teachers can use their own photo.", 403)
    old = (db().users.find_one({"_id": user.id}, projection={"avatarKey": 1}) or {}).get("avatarKey")
    db().users.update_one({"_id": user.id}, {"$set": {"avatar": TEACHER_AVATAR}, "$unset": {"avatarKey": ""}})
    if old:
        media.delete(old)
    _avatar_cache[user.id] = TEACHER_AVATAR
    return TEACHER_AVATAR


def avatar_link(user_id: str) -> Optional[str]:
    """Where a teacher's current photo is (a storage link), for /api/chat/avatar/<id>/..."""
    key = (db().users.find_one({"_id": user_id}, projection={"avatarKey": 1}) or {}).get("avatarKey")
    return media.download_link(key) if key and media.enabled() else None


# ── how teachers are addressed: "Anshul Sir", "Neha Ma'am" ──────────────────────────────────

HONORIFICS = {"sir": "Sir", "maam": "Ma'am"}
_HONORIFIC_IN_NAME = re.compile(r"\b(sir|ma'?am|mam|madam|maa?m)\.?$", re.I)


def with_honorific(name: str, honorific: Optional[str]) -> str:
    title = HONORIFICS.get(honorific or "")
    if not title or not name or _HONORIFIC_IN_NAME.search(name.strip()):
        return name
    return f"{name.strip()} {title}"


_honorific_cache: dict[str, str] = {}


def honorific_of(user_id: str) -> str:
    if user_id not in _honorific_cache:
        doc = db().users.find_one({"_id": user_id}, projection={"honorific": 1}) or {}
        _honorific_cache[user_id] = doc.get("honorific") or ""
    return _honorific_cache[user_id]


def set_honorific(user: ChatUser, value: str) -> str:
    """Teachers choose Sir or Ma'am once; students then see "Anshul Sir" on their messages."""
    if not user.is_staff:
        raise ChatError("forbidden", "Only teachers choose this.", 403)
    value = (value or "").strip().lower().replace("'", "")
    if value not in ("sir", "maam", ""):
        raise ChatError("bad_value", "Pick Sir or Ma'am.")
    db().users.update_one({"_id": user.id}, {"$set": {"honorific": value}}, upsert=True)
    _honorific_cache[user.id] = value
    for m in db().members.find({"userId": user.id, "removed": {"$ne": True}}, projection={"groupId": 1}):
        _emit("group_updated", {"groupId": m["groupId"]}, group_room(m["groupId"]))
    return value


def has_saved_name(user_id: str) -> bool:
    """The student already added their name here (Acadza may still be catching up)."""
    return bool((db().users.find_one({"_id": user_id}, projection={"named": 1}) or {}).get("named"))


def refresh_my_name(user: ChatUser, name: str) -> str:
    """A student saved their name on their account: the chat uses it straight away."""
    name = re.sub(r"\s+", " ", (name or "").strip())[:60]
    if len(name) < 2:
        raise ChatError("bad_name", "Please type your full name.")
    if not moderation.check(name, is_staff=user.is_staff, ai=False).allowed:
        raise ChatError("bad_name", "Please type your real name.")
    db().users.update_one({"_id": user.id}, {"$set": {"name": name, "named": True}})
    db().members.update_many({"userId": user.id}, {"$set": {"name": name}})
    return name


# ── shapes sent to the app ───────────────────────────────────────────────────────────────────

def sender_label(role: str, roll_no: Optional[str]) -> str:
    """What shows under a name: "Teacher", "Admin" or "Roll 23"."""
    if role == "teacher":
        return "Teacher"
    if role == "admin":
        return "Admin"
    return f"Roll {roll_no}" if roll_no else ""


def display_name(role: str, name: str, roll_no: Optional[str]) -> str:
    """How a person shows to others: students by roll number, teachers and admins by name."""
    if role == "student" and roll_no:
        return f"Roll {roll_no}"
    return name or "Member"


def message_out(m: dict, avatars: Optional[dict] = None) -> dict:
    deleted = bool(m.get("deletedAt"))
    role = m.get("senderRole", "student")
    chosen = (avatars or {}).get(m["senderId"], m.get("senderAvatar"))
    return {
        "id": m["_id"],
        "groupId": m["groupId"],
        "seq": m["seq"],
        "clientId": m.get("clientId"),
        "sender": {
            "id": m["senderId"],
            "name": m.get("senderName", ""),
            "role": role,
            "rollNo": m.get("rollNo"),
            "label": sender_label(role, m.get("rollNo")),
            "avatar": avatar_of(role, chosen) if role != "system" else "",
        },
        "type": m.get("type", "text"),
        "text": "" if deleted else m.get("text", ""),
        "replyTo": None if deleted else m.get("replyTo"),
        "createdAt": m["createdAt"],
        "deleted": deleted,
        "deletedByAdmin": deleted and m.get("deletedBy") not in (None, m["senderId"]),
        "media": None if deleted else _media_out(m.get("media"), m.get("createdAt") or 0),
        "editedAt": int(m.get("editedAt") or 0) if not deleted else 0,
        "reactions": [] if deleted else reactions_out(m),
        "reactedAt": int(m.get("reactedAt") or 0),
        "mentions": [] if deleted else [{"userId": x.get("u", ""), "name": x.get("n", "")} for x in m.get("mentions") or []],
        "mentionAll": bool(m.get("mentionAll")) and not deleted,
    }


def reactions_out(m: dict) -> list[dict]:
    """Who reacted with what, oldest first: [{userId, name, emoji}]."""
    rs = [v for v in (m.get("reactions") or {}).values() if isinstance(v, dict) and v.get("e")]
    rs.sort(key=lambda v: int(v.get("at") or 0))
    return [{"userId": v.get("u", ""), "name": v.get("n", ""), "emoji": v["e"]} for v in rs]


def _media_out(md: Optional[dict], created_at: int = 0) -> Optional[dict]:
    if not md or not md.get("key"):
        return None
    out = {k: md.get(k) for k in ("kind", "key", "mime", "size", "name", "width", "height", "durationMs")}
    out["gzip"] = bool(md.get("gzip"))
    days = int(chatconfig.media()["retentionDays"])
    out["expiresAt"] = int(created_at) + days * 86_400_000 if created_at and days > 0 else 0
    out["expired"] = bool(md.get("expired")) or (out["expiresAt"] > 0 and out["expiresAt"] < now_ms())
    out["url"] = "" if out["expired"] or not media.enabled() else media.download_link(md["key"])
    return out


def _limit_bytes(kind: str) -> int:
    """The size limit for one file of this kind, from chatConfig (never above the hard ceiling)."""
    c = chatconfig.media()
    by_kind = {"image": int(c["image"]["maxKB"]) * 1024, "audio": int(c["audio"]["maxKB"]) * 1024,
               "file": int(float(c["file"]["maxMB"]) * 1024 * 1024)}
    return min(by_kind.get(kind, 0), media.KINDS[kind]["max"])


def _size_text(n: int) -> str:
    return f"{n // 1024} KB" if n < 1024 * 1024 else f"{n / (1024 * 1024):.0f} MB"


def _day_key(user_id: str) -> str:
    # Days run on India time, so "today's limit" resets at midnight IST.
    return f"{user_id}:{time.strftime('%Y-%m-%d', time.gmtime(time.time() + 5.5 * 3600))}"


def _usage_today(user_id: str) -> dict:
    return db().media_usage.find_one({"_id": _day_key(user_id)}) or {}


def _stored_bytes() -> int:
    return int((db().media_stats.find_one({"_id": "storage"}) or {}).get("bytes") or 0)


def _add_stored(delta: int) -> None:
    if delta:
        db().media_stats.update_one({"_id": "storage"}, {"$inc": {"bytes": int(delta)}}, upsert=True)


def _month_key() -> str:
    return "month:" + time.strftime("%Y-%m", time.gmtime(time.time() + 5.5 * 3600))


def _uploaded_this_month() -> int:
    return int((db().media_stats.find_one({"_id": _month_key()}) or {}).get("bytes") or 0)


def _pending_bytes(exclude_key: Optional[str] = None) -> int:
    """Files uploaded (or being uploaded) but not sent yet: they take space too."""
    q = {"_id": {"$ne": exclude_key}} if exclude_key else {}
    return sum(int(d.get("size") or 0) for d in db().media_pending.find(q, projection={"size": 1}))


def _check_media_allowed(user: ChatUser, member: dict, kind: str, size: int, key: Optional[str] = None) -> None:
    """Every rule from chatConfig, with a reason the person can understand."""
    c = chatconfig.media()
    if not c["enabled"] or not media.enabled():
        raise ChatError("media_off", "Sending photos and files is switched off right now.", 503)
    rule = media.KINDS.get(kind)
    if not rule:
        raise ChatError("bad_media", "Pick a photo, a voice note or a document.")
    staff = member.get("role") in STAFF_MEMBER_ROLES or user.is_staff
    if not staff and not c["studentsCanSend"].get(kind, True):
        what = {"image": "photos", "audio": "voice notes", "file": "documents"}[kind]
        raise ChatError("not_allowed", f"Students can't send {what} right now.", 403)
    top = _limit_bytes(kind)
    if size <= 0 or size > top:
        raise ChatError("too_big", f"This file is too big. The limit is {_size_text(top)}.", 400)
    cap = c["daily"]["teacher" if staff else "student"]
    used = _usage_today(user.id)
    if int(used.get("count") or 0) + 1 > int(cap["count"]):
        raise ChatError("daily_limit", f"You can send {int(cap['count'])} files a day. Try again tomorrow.", 429)
    if int(used.get("bytes") or 0) + size > int(float(cap["mb"]) * 1024 * 1024):
        raise ChatError("daily_limit", f"You can send {cap['mb']} MB of files a day. Try again tomorrow.", 429)
    # Two hard ceilings so the bucket never goes past R2's free 10 GB: what is kept right now
    # (sent files + uploads not sent yet), and what was uploaded this month.
    gb = 1024 ** 3
    if _stored_bytes() + _pending_bytes(exclude_key=key) + size > float(c["storageLimitGB"]) * gb:
        raise ChatError("storage_full", "File storage is full for now. Older files are cleared every day; try later.", 507)
    if key is None and _uploaded_this_month() + size > float(c["monthlyUploadGB"]) * gb:
        raise ChatError("storage_full", "This month's file limit is used up. Text messages still work.", 507)


def _clean_media(user: ChatUser, member: dict, group_id: str, raw) -> Optional[dict]:
    """The file a message points at, checked: right group, allowed kind, within every limit."""
    if not raw:
        return None
    if not isinstance(raw, dict):
        raise ChatError("bad_media", "That file could not be sent.")
    kind = raw.get("kind")
    key = raw.get("key")
    if kind not in media.KINDS or not media.belongs_to(key, group_id):
        raise ChatError("bad_media", "That file could not be sent.")
    size = int(raw.get("size") or 0)
    pending = db().media_pending.find_one({"_id": key}, projection={"size": 1})
    if pending and int(pending.get("size") or 0) > 0:
        size = int(pending["size"])                # the size the upload was signed for, not what the app says
    _check_media_allowed(user, member, kind, size, key=key)

    def num(name, top):
        try:
            v = int(raw.get(name) or 0)
        except (TypeError, ValueError):
            v = 0
        return max(0, min(v, top))
    return {"kind": kind, "key": key, "mime": str(raw.get("mime") or "")[:80], "size": size,
            "name": str(raw.get("name") or "")[:120], "width": num("width", 20000), "height": num("height", 20000),
            "durationMs": num("durationMs", 3 * 3600 * 1000), "gzip": bool(raw.get("gzip")) and kind == "file"}


def _as_list(v) -> list:
    """A list from Firebase, which may arrive as {"0": a, "1": b} or as one comma-separated text."""
    if isinstance(v, dict):
        return list(v.values())
    if isinstance(v, str):
        return [x for x in v.split(",") if x.strip()]
    return list(v or [])


def request_upload(user: ChatUser, group_id: str, body: dict) -> dict:
    """A short-lived link to upload one file to R2 for this group (only if I may post here)."""
    if not media.enabled():
        raise ChatError("media_off", "Sending photos and files is switched off right now.", 503)
    g = group_or_404(group_id)
    member = membership(group_id, user.id)
    if not _can_post(g, member):
        if (member.get("restrictedUntil") or 0) > now_ms():
            raise ChatError("restricted", "A teacher has paused your messages in this group for a while.", 403)
        raise ChatError("read_only", "Only admins can send messages in this group.", 403)
    kind = body.get("kind")
    rule = media.KINDS.get(kind)
    if not rule:
        raise ChatError("bad_media", "Pick a photo, a voice note or a document.")
    mime = str(body.get("mime") or "application/octet-stream").lower()[:80]
    if rule["mimes"] and mime not in rule["mimes"]:
        raise ChatError("bad_media", "That kind of file can't be sent here.")
    size = int(body.get("size") or 0)
    _check_media_allowed(user, member, kind, size)
    name = str(body.get("name") or "")
    staff = member.get("role") in STAFF_MEMBER_ROLES or user.is_staff
    if kind == "file" and not staff:
        # Students: documents only (no videos, apps, zips). chatConfig media/studentFileTypes.
        allowed = {str(t).lower().strip(". ") for t in _as_list(chatconfig.media().get("studentFileTypes"))}
        ext = name.rsplit(".", 1)[-1].lower() if "." in name else ""
        if ext not in allowed or mime.startswith(("video/", "application/vnd.android")):
            raise ChatError("not_allowed", "Students can send PDF, Word, PowerPoint and Excel files only.", 403)
    key = media.key_for(group_id, mime, name)
    # Remembered until the message is sent; an upload never sent is removed after a few days.
    db().media_pending.insert_one({"_id": key, "size": size, "userId": user.id, "groupId": group_id, "at": now_ms()})
    return {"key": key, "uploadUrl": media.upload_link(key, mime, size), "method": "PUT",
            "headers": {"Content-Type": mime}, "expiresIn": media.UPLOAD_LINK_S}


def _match(g: dict) -> Optional[dict]:
    """Which students the group is for: {coaching: [...], batch: [...] or ["*"]} (old groups too)."""
    if g.get("match"):
        return g["match"]
    aj = g.get("autoJoin")
    if isinstance(aj, dict):                      # groups made before "match" existed
        return {"coaching": aj.get("coaching"), "batch": aj.get("batch")}
    return None


def _auto(g: dict) -> bool:
    return g.get("autoJoin") is True or isinstance(g.get("autoJoin"), dict)


def _as_list(v) -> list:
    if v is None:
        return []
    return list(v) if isinstance(v, (list, tuple)) else [v]


def group_out(g: dict, member: Optional[dict] = None, viewer: Optional[str] = None) -> dict:
    last_seq = int(g.get("lastSeq", 0))
    m = member or {}
    read = int(m.get("lastReadSeq", 0))
    match = _match(g) or {}
    out = {
        "id": g["_id"],
        "title": g.get("title", ""),
        "description": g.get("description", ""),
        "type": g.get("type", "chat"),
        "coaching": g.get("coaching"),
        "batches": [b for b in _as_list(match.get("batch")) if b and b != "*"],
        "wholeCoaching": "*" in _as_list(match.get("batch")),
        "lastSeq": last_seq,
        "lastMessage": g.get("lastMessage"),
        "memberCount": int(g.get("memberCount", 0)),
        "myRole": m.get("role", "student"),
        "isAdmin": m.get("role") == "admin",
        "isCreator": bool(viewer) and g.get("createdBy") == viewer,
        "canPost": _can_post(g, member) if member else False,
        "restrictedUntil": int(m.get("restrictedUntil") or 0),
        "muted": bool(m.get("muted")),
        "unread": max(0, last_seq - read),
        "lastReadSeq": read,
        "receipts": {"deliveredSeq": int(g.get("deliveredSeq", 0)), "readSeq": int(g.get("readSeq", 0))},
        "autoJoin": _auto(g),
        "joinRequests": bool(g.get("joinRequests")),
        # Admins see how many students are waiting for an answer.
        "requestCount": int(g.get("pendingRequests") or 0) if m.get("role") == "admin" else 0,
        "updatedAt": int((g.get("lastMessage") or {}).get("createdAt") or g.get("createdAt") or 0),
        "peer": None,
    }
    if g.get("type") == "direct" and viewer:
        other = db().members.find_one({"groupId": g["_id"], "userId": {"$ne": viewer}}) or {}
        if other:
            av = _avatars([other["userId"]]).get(other["userId"])
            out["peer"] = {"id": other["userId"], "name": other.get("name") or "", "role": other.get("role", "student"),
                           "rollNo": other.get("rollNo"), "avatar": avatar_of(other.get("role"), av)}
            out["title"] = other.get("name") or "Chat"
    return out


# ── membership ───────────────────────────────────────────────────────────────────────────────

def _member_role_for(user: ChatUser) -> str:
    """Teachers join as teachers (admin is a group right given by the group's admins)."""
    return "teacher" if user.is_staff else "student"


def _groups_matching(user: ChatUser) -> list[dict]:
    """Groups made for this user's coaching and batches (old and new group shapes)."""
    batches = list(user.batches) + ["*"]
    ors = [{"match.coaching": user.coaching, "match.batch": {"$in": batches}},
           {"autoJoin.coaching": user.coaching, "autoJoin.batch": {"$in": batches}}]
    return list(db().groups.find({"$or": ors}, projection={"_id": 1, "title": 1, "autoJoin": 1, "match": 1}))


def sync_auto_groups(user: ChatUser) -> None:
    """Puts the student in every auto-join group made for their coaching and batches (once; an
    admin's removal sticks), and tells the group's admins about new students: joined, or waiting
    to be added where auto-add is off."""
    db().members.update_many({"userId": user.id, "name": {"$in": [None, ""]}}, {"$set": {"name": user.name}})
    if user.is_staff:
        return
    for g in _groups_matching(user):
        exists = db().members.find_one({"groupId": g["_id"], "userId": user.id}, projection={"_id": 1})
        if exists:
            continue
        if _auto(g):
            try:
                db().members.insert_one({
                    "groupId": g["_id"], "userId": user.id, "role": "student",
                    "name": user.name, "rollNo": None, "joinedAt": now_ms(), "lastReadSeq": 0,
                    "lastDeliveredSeq": 0, "muted": False, "removed": False, "sources": ["auto"],
                })
                db().groups.update_one({"_id": g["_id"]}, {"$inc": {"memberCount": 1}})
                _close_requests(g["_id"], [user.id])
                _admin_notice(g["_id"], "joined")
            except DuplicateKeyError:
                pass
        else:
            # Auto-add is off: the admins see the student under "New students" in Group settings.
            # No notification for this: every student who merely opens the chat would send one.
            # Admins are told when a student actually asks to join (join requests).
            try:
                db().candidates_seen.insert_one({"_id": f"{g['_id']}:{user.id}", "at": now_ms()})
            except DuplicateKeyError:
                pass


# ── asking to join ───────────────────────────────────────────────────────────────────────────
# A group with "Let students ask to join" on shows up for the students it is made for (its
# coaching and batches) who aren't in it, under "Groups you can join". A request goes to the
# group's admins as a notification; they approve or decline it in Group settings, Requests to join.

REQUEST_AGAIN_AFTER_MS = 24 * 3600 * 1000      # after a "no", a student can ask again a day later


def _request_id(group_id: str, user_id: str) -> str:
    return f"{group_id}:{user_id}"


def discover_groups(user: ChatUser) -> list[dict]:
    """Groups this student may ask to join: made for their coaching and batches, asking switched
    on, and they aren't in it (people who left or were removed can ask to come back)."""
    if user.is_staff:
        return []
    found = [g for g in _groups_matching(user)]
    ids = [g["_id"] for g in found]
    if not ids:
        return []
    groups = list(db().groups.find({"_id": {"$in": ids}, "joinRequests": True, "type": {"$ne": "direct"}},
                                   projection={"title": 1, "description": 1, "memberCount": 1, "type": 1}))
    if not groups:
        return []
    inside = {m["groupId"] for m in db().members.find(
        {"userId": user.id, "groupId": {"$in": [g["_id"] for g in groups]}, "removed": {"$ne": True}}, projection={"groupId": 1})}
    asked = {r["groupId"]: r for r in db().join_requests.find(
        {"userId": user.id, "groupId": {"$in": [g["_id"] for g in groups]}}, projection={"groupId": 1, "status": 1})}
    out = []
    for g in groups:
        if g["_id"] in inside:
            continue
        r = asked.get(g["_id"]) or {}
        out.append({"id": g["_id"], "title": g.get("title", ""), "description": g.get("description", ""),
                    "type": g.get("type", "chat"), "memberCount": int(g.get("memberCount") or 0),
                    "requested": r.get("status") == "pending"})
    return sorted(out, key=lambda x: x["title"].lower())


def request_join(user: ChatUser, group_id: str) -> dict:
    g = group_or_404(group_id)
    if not g.get("joinRequests") or g.get("type") == "direct":
        raise ChatError("closed", "This group isn't taking requests right now.", 403)
    if user.is_staff or group_id not in {x["_id"] for x in _groups_matching(user)}:
        raise ChatError("not_for_you", "This group is for other batches.", 403)
    if db().members.find_one({"groupId": group_id, "userId": user.id, "removed": {"$ne": True}}, projection={"_id": 1}):
        raise ChatError("already_in", "You're already in this group.", 409)
    rid = _request_id(group_id, user.id)
    old = db().join_requests.find_one({"_id": rid}) or {}
    if old.get("status") == "pending":
        return {"ok": True, "requested": True}
    if old.get("status") == "rejected" and now_ms() - int(old.get("answeredAt") or 0) < REQUEST_AGAIN_AFTER_MS:
        raise ChatError("wait", "An admin said no to your last request. You can ask again tomorrow.", 429)
    before = db().members.find_one({"groupId": group_id, "userId": user.id}, projection={"left": 1, "removed": 1, "rollNo": 1}) or {}
    note = "left" if before.get("left") else ("removed" if before.get("removed") else "")
    db().join_requests.update_one({"_id": rid}, {"$set": {
        "groupId": group_id, "userId": user.id, "name": user.name, "rollNo": before.get("rollNo"),
        "batches": list(user.batches)[:5], "note": note, "status": "pending", "at": now_ms(),
    }}, upsert=True)
    db().groups.update_one({"_id": group_id}, {"$inc": {"pendingRequests": 1}})
    _tell_admins_about_requests(g, f"{user.name or 'A student'} asked to join {g.get('title', '')}. Tap to see the request.")
    return {"ok": True, "requested": True}


def cancel_request(user: ChatUser, group_id: str) -> dict:
    res = db().join_requests.delete_one({"_id": _request_id(group_id, user.id), "status": "pending"})
    if res.deleted_count:
        db().groups.update_one({"_id": group_id}, {"$inc": {"pendingRequests": -1}})
        g = db().groups.find_one({"_id": group_id})
        if g:
            _tell_admins_about_requests(g, None)
    return {"ok": True, "requested": False}


def _close_requests(group_id: str, user_ids: list[str]) -> None:
    res = db().join_requests.update_many({"groupId": group_id, "userId": {"$in": list(user_ids)}, "status": "pending"},
                                         {"$set": {"status": "approved", "answeredAt": now_ms()}})
    if res.modified_count:
        db().groups.update_one({"_id": group_id}, {"$inc": {"pendingRequests": -res.modified_count}})


def _tell_admins_about_requests(g: dict, body: Optional[str]) -> None:
    """The admins' screens update at once; with [body], their phones get a notification that
    opens the requests."""
    admins = [m["userId"] for m in db().members.find({"groupId": g["_id"], "role": "admin", "removed": {"$ne": True}},
                                                     projection={"userId": 1})]
    for uid in admins:
        _emit("group_updated", {"groupId": g["_id"]}, user_room(uid))
    if body and admins:
        title = g.get("title", "")
        push.send_to_users(admins, {"type": "chat_admin", "kind": "join_request", "groupId": g["_id"], "groupTitle": title,
                                    "title": title, "body": body, "text": body})


def list_requests(user: ChatUser, group_id: str) -> list[dict]:
    require_group_admin(user, group_id)
    docs = list(db().join_requests.find({"groupId": group_id, "status": "pending"}).sort("at", 1))
    avatars = _avatars(d["userId"] for d in docs)
    cards = _contact_cards(d["userId"] for d in docs)
    return [{"userId": d["userId"], "name": d.get("name") or (cards.get(d["userId"]) or {}).get("name") or "",
             "phone": (cards.get(d["userId"]) or {}).get("phone", ""),
             "rollNo": d.get("rollNo"), "at": int(d.get("at") or 0),
             "note": d.get("note") or "", "batches": d.get("batches") or [],
             "avatar": avatar_of("student", avatars.get(d["userId"]))} for d in docs]


def answer_requests(user: ChatUser, group_id: str, user_ids: list[str], approve: bool) -> int:
    """Approve (they're added and told "X added you") or decline (they can ask again tomorrow)."""
    require_group_admin(user, group_id)
    ids = [str(u) for u in user_ids if str(u).strip()]
    docs = list(db().join_requests.find({"groupId": group_id, "userId": {"$in": ids}, "status": "pending"}))
    if not docs:
        return 0
    if approve:
        admin_add_members(user, group_id, [{"userId": d["userId"], "name": d.get("name") or "", "role": "student",
                                            "rollNo": d.get("rollNo")} for d in docs], source="request")
    db().join_requests.update_many({"_id": {"$in": [d["_id"] for d in docs]}},
                                   {"$set": {"status": "approved" if approve else "rejected", "answeredAt": now_ms(),
                                             "answeredBy": user.id}})
    db().groups.update_one({"_id": group_id}, {"$inc": {"pendingRequests": -len(docs)}})
    g = db().groups.find_one({"_id": group_id})
    if g:
        _tell_admins_about_requests(g, None)
    for d in docs:                                  # their "Groups you can join" list updates too
        _emit("group_updated", {"groupId": group_id}, user_room(d["userId"]))
    return len(docs)


def _admin_notice(group_id: str, kind: str) -> None:
    """Counts new students per group and pushes one short summary to its admins at most every
    30 minutes: "3 new students joined Titan Maths" / "2 new students of Titan Maths are waiting"."""
    field_ = "pendingJoined" if kind == "joined" else "pendingWaiting"
    g = db().groups.find_one_and_update({"_id": group_id}, {"$inc": {field_: 1}},
                                        return_document=ReturnDocument.AFTER)
    if not g:
        return
    t = time.time()
    if t - float(g.get("adminNoticeAt") or 0) < ADMIN_NOTICE_EVERY_S:
        return
    joined, waiting = int(g.get("pendingJoined") or 0), int(g.get("pendingWaiting") or 0)
    db().groups.update_one({"_id": group_id}, {"$set": {"adminNoticeAt": t, "pendingJoined": 0, "pendingWaiting": 0}})
    title = g.get("title", "")
    parts = []
    if joined:
        parts.append(f"{joined} new student{'s' if joined > 1 else ''} joined {title}.")
    if waiting:
        parts.append(f"{waiting} new student{'s' if waiting > 1 else ''} of {title} "
                     f"{'are' if waiting > 1 else 'is'} not in the group yet. Open Group settings, New students, to add them.")
    if not parts:
        return
    admins = [m["userId"] for m in db().members.find({"groupId": group_id, "role": "admin", "removed": {"$ne": True}},
                                                     projection={"userId": 1})]
    push.send_to_users(admins, {"type": "chat_admin", "groupId": group_id, "groupTitle": title,
                                "title": title, "body": " ".join(parts), "text": " ".join(parts)})


def membership(group_id: str, user_id: str) -> dict:
    m = db().members.find_one({"groupId": group_id, "userId": user_id, "removed": {"$ne": True}})
    if not m:
        raise ChatError("not_member", "You're not in this group.", 403)
    return m


def group_or_404(group_id: str) -> dict:
    g = db().groups.find_one({"_id": group_id})
    if not g:
        raise ChatError("no_group", "This group doesn't exist.", 404)
    return g


def _should_be_admin(user: ChatUser, g: dict, m: dict) -> bool:
    """The creator, and teachers on CHAT_ADMIN_IDS, always run the groups they are in
    (also fixes groups made before group admins existed)."""
    return g.get("createdBy") == user.id or (user.is_admin and m.get("role") in ("teacher", "admin"))


def require_group_admin(user: ChatUser, group_id: str) -> tuple[dict, dict]:
    g = group_or_404(group_id)
    if g.get("type") == "direct":
        raise ChatError("forbidden", "Direct chats have no admins.", 403)
    m = membership(group_id, user.id)
    if m.get("role") != "admin" and _should_be_admin(user, g, m):
        db().members.update_one({"_id": m["_id"]}, {"$set": {"role": "admin"}})
        m["role"] = "admin"
    if m.get("role") != "admin":
        raise ChatError("forbidden", "Only the group's admins can do this.", 403)
    return g, m


def _can_post(g: dict, member: Optional[dict]) -> bool:
    if not member:
        return False
    if (member.get("restrictedUntil") or 0) > now_ms():
        return False
    if g.get("type") == "announcement":
        return member.get("role") == "admin"
    return True


def groups_for(user: ChatUser) -> list[dict]:
    sync_auto_groups(user)
    members = {m["groupId"]: m for m in db().members.find({"userId": user.id, "removed": {"$ne": True}})}
    if not members:
        return []
    groups = [g for g in db().groups.find({"_id": {"$in": list(members)}})
              # an opened but empty direct chat is only the opener's (the app hides it too)
              if not (g.get("type") == "direct" and not g.get("lastSeq") and g.get("createdBy") != user.id)]
    for g in groups:                               # groups made before group admins existed
        m = members[g["_id"]]
        if g.get("type") != "direct" and m.get("role") != "admin" and _should_be_admin(user, g, m):
            db().members.update_one({"_id": m["_id"]}, {"$set": {"role": "admin"}})
            m["role"] = "admin"
    out = [group_out(g, members[g["_id"]], user.id) for g in groups]
    return sorted(out, key=lambda x: x["updatedAt"], reverse=True)


def group_ids_for(user_id: str) -> list[str]:
    return [m["groupId"] for m in db().members.find({"userId": user_id, "removed": {"$ne": True}}, projection={"groupId": 1})]


# ── system lines in the chat ("Anshul Sir added 34 students from Spartans") ─────────────────

def system_message(group_id: str, text: str) -> None:
    """A short centred note in the chat so everyone knows what changed. No notification."""
    if not db().groups.find_one({"_id": group_id}, projection={"_id": 1}):
        return
    seq = next_seq(group_id)
    doc = {"_id": f"{group_id}-{seq}", "groupId": group_id, "seq": seq, "clientId": f"sys-{seq}",
           "senderId": "system", "senderName": "", "senderRole": "system", "rollNo": None,
           "type": "system", "text": text[:300], "replyTo": None, "createdAt": now_ms()}
    db().messages.insert_one(doc)
    db().groups.update_one({"_id": group_id}, {"$set": {"lastMessage": {
        "seq": seq, "text": text[:160], "senderName": "", "senderId": "system", "createdAt": doc["createdAt"]}}})
    _emit("message", message_out(doc), group_room(group_id))


def _who(user: ChatUser, member: Optional[dict] = None) -> str:
    return (member or {}).get("name") or user.name or "An admin"


def _person(m: Optional[dict], fallback: str = "Someone") -> str:
    if not m:
        return fallback
    return display_name(m.get("role", "student"), m.get("name") or "", m.get("rollNo")) or fallback


# ── sending ──────────────────────────────────────────────────────────────────────────────────

_rate: dict[str, deque] = {}
_rate_lock = threading.Lock()


def _rate_ok(user_id: str) -> bool:
    t = time.time()
    with _rate_lock:
        q = _rate.setdefault(user_id, deque())
        while q and t - q[0] > settings.RATE_LIMIT_WINDOW_S:
            q.popleft()
        if len(q) >= settings.RATE_LIMIT_COUNT:
            return False
        q.append(t)
        return True


def _strike(user: ChatUser, group_id: str, reasons) -> None:
    """Something explicit (a sexual or abusive message, a nude photo): the student is paused in
    that group for chatconfig moderation.muteMinutes (20), and the group's admins are told so they
    can lift it. Links, phone numbers and other coachings' names are only stopped, never punished.
    Teachers and admins are never paused."""
    if user.is_staff or not moderation.is_explicit(reasons):
        return
    t = now_ms()
    db().users.update_one({"_id": user.id}, {"$push": {"strikes": {"$each": [t], "$slice": -20}}})
    try:
        minutes = int((chatconfig.get().get("moderation") or {}).get("muteMinutes", 20))
    except (TypeError, ValueError):
        minutes = 20
    if minutes <= 0:
        return
    until = t + minutes * 60_000
    # $max: a longer pause a teacher already set stays.
    res = db().members.update_one({"groupId": group_id, "userId": user.id, "role": "student", "removed": {"$ne": True}},
                                  {"$max": {"restrictedUntil": until}})
    if not res.matched_count:
        return
    _emit("group_updated", {"groupId": group_id}, user_room(user.id))
    g = db().groups.find_one({"_id": group_id}, projection={"title": 1}) or {}
    title = g.get("title", "")
    body = f"Your messages in {title} are paused for {minutes} minutes because a message broke the group rules."
    push.send_to_users([user.id], {"type": "chat_admin", "kind": "paused", "groupId": group_id, "groupTitle": title,
                                   "title": title, "body": body, "text": body})
    admins = [m["userId"] for m in db().members.find({"groupId": group_id, "role": "admin", "removed": {"$ne": True}},
                                                     projection={"userId": 1})]
    if admins:
        note = (f"{user.name or 'A student'} was paused for {minutes} minutes in {title} for an explicit message. "
                f"You can lift it from the member's profile.")
        push.send_to_users(admins, {"type": "chat_admin", "kind": "auto_paused", "groupId": group_id, "userId": user.id,
                                    "groupTitle": title, "title": title, "body": note, "text": note})


def send_message(user: ChatUser, group_id: str, client_id: str, text: str,
                 reply_to_seq: Optional[int] = None, origin_sid: Optional[str] = None,
                 media_in: Optional[dict] = None, mentions_in=None) -> dict:
    started = time.time()
    text = (text or "").strip()
    client_id = (client_id or "").strip()[:64] or secrets.token_hex(8)
    if not text and not media_in:
        raise ChatError("empty", "Type a message first.")
    if len(text) > settings.MAX_TEXT_LENGTH:
        raise ChatError("too_long", f"Messages can be up to {settings.MAX_TEXT_LENGTH} characters.")

    # The lookups don't depend on each other: one trip to the database instead of four in a row.
    g, member, existing, reply_doc, avatar = _together(
        lambda: group_or_404(group_id),
        lambda: membership(group_id, user.id),
        lambda: db().messages.find_one({"groupId": group_id, "clientId": client_id}, projection={"_id": 1}),
        lambda: db().messages.find_one({"groupId": group_id, "seq": int(reply_to_seq)}) if reply_to_seq else None,
        lambda: my_avatar(user),
    )
    looked = time.time()
    if existing:                                   # a resend: the same message, not a new one
        return message_out(db().messages.find_one({"_id": existing["_id"]}))
    attached = _clean_media(user, member, group_id, media_in)

    if not _can_post(g, member):
        if (member.get("restrictedUntil") or 0) > now_ms():
            raise ChatError("restricted", "A teacher has paused your messages in this group for a while.", 403)
        raise ChatError("read_only", "Only admins can send messages in this group.", 403)
    if not _rate_ok(user.id):
        raise ChatError("slow_down", "You're sending messages too fast.", 429)

    is_staff = member.get("role") in STAFF_MEMBER_ROLES or user.is_staff
    # Word lists, links, phone numbers: checked here, instantly. The AI check runs right after
    # delivery (it is a call to OpenAI) and takes the message down if it finds abuse.
    can_link = _can_send_links(user, member) if text and moderation.has_link(text) else None
    verdict = moderation.check(text, is_staff=is_staff, ai=False, can_link=can_link) if text else moderation.Verdict(allowed=True)
    if not verdict.allowed:
        db().moderation.insert_one({
            "kind": "blocked", "groupId": group_id, "userId": user.id, "name": user.name,
            "text": text, "reasons": verdict.reasons, "createdAt": now_ms(),
        })
        _strike(user, group_id, verdict.reasons)
        raise ChatError("blocked", verdict.message, 422)

    reply = None
    if reply_doc:
        r = reply_doc
        if not r.get("deletedAt") and r.get("type") != "system":
            reply = {"seq": r["seq"],
                     "senderName": display_name(r.get("senderRole", "student"), r.get("senderName", ""), r.get("rollNo")),
                     "text": ((r.get("text") or "") or media.label(r.get("media")))[:160]}

    seq = next_seq(group_id)
    numbered = time.time()
    doc = {
        "_id": f"{group_id}-{seq}",
        "groupId": group_id, "seq": seq, "clientId": client_id,
        "senderId": user.id, "senderName": with_honorific(member.get("name") or user.name, honorific_of(user.id))
        if is_staff else (member.get("name") or user.name),
        "senderRole": member.get("role", "student"), "rollNo": member.get("rollNo"), "senderAvatar": avatar,
        "type": "text", "text": text, "replyTo": reply, "createdAt": now_ms(),
    }
    mentioned, everyone = _clean_mentions(user, g, member, mentions_in)
    if mentioned:
        doc["mentions"] = mentioned
    if everyone:
        doc["mentionAll"] = True
    if attached:
        doc["media"] = attached
        # Counts towards today's limit and the storage total.
        db().media_usage.update_one({"_id": _day_key(user.id)},
                                    {"$inc": {"count": 1, "bytes": attached["size"]}, "$set": {"at": now_ms()}}, upsert=True)
        _add_stored(attached["size"])
        db().media_pending.delete_one({"_id": attached["key"]})
        db().media_stats.update_one({"_id": _month_key()}, {"$inc": {"bytes": attached["size"]}}, upsert=True)

    out = message_out(doc)
    if g.get("type") == "direct" and seq == 1:     # the first message: the chat appears for the other person
        for other in db().members.find({"groupId": group_id, "userId": {"$ne": user.id}}, projection={"userId": 1}):
            _join_live(other["userId"], group_id, True)
            _emit("group_added", {"groupId": group_id}, user_room(other["userId"]))
    # Everyone else gets it now, while it is being saved: they don't wait for the write.
    _emit("message", out, group_room(group_id), skip_sid=origin_sid)
    try:
        db().messages.insert_one(doc)
    except Exception as exc:
        # Not saved: take back what was shown under this number (a retry comes with a new one,
        # and phones keep one copy per clientId, so nothing doubles).
        _emit("message_deleted", {"groupId": group_id, "seq": seq, "id": doc["_id"], "byAdmin": False}, group_room(group_id))
        if isinstance(exc, DuplicateKeyError):     # two resends raced: return the one that won
            won = db().messages.find_one({"groupId": group_id, "clientId": client_id})
            if won:
                return message_out(won)
        raise
    saved = time.time()

    def notify_now() -> None:
        # The notification goes out first and on its own, so nothing else can hold it back or
        # stop it (it used to wait for the AI check and was lost when anything before it failed).
        try:
            _notify(g, doc)
        except Exception:  # noqa: BLE001
            log.exception("chat: notification failed for %s", doc["_id"])

    def after() -> None:
        try:
            shown = display_name(doc["senderRole"], doc["senderName"], doc.get("rollNo"))
            preview = (media.label(attached) + (" " + text if text else "")) if attached else text
            last = {"seq": seq, "text": preview[:160], "senderName": shown, "senderId": user.id, "createdAt": doc["createdAt"]}
            db().groups.update_one({"_id": group_id}, {"$set": {"lastMessage": last}})
            db().members.update_one({"_id": member["_id"]}, {"$max": {"lastReadSeq": seq, "lastDeliveredSeq": seq}})
            if verdict.alert:
                db().moderation.insert_one({"kind": "alert", "groupId": group_id, "userId": user.id, "name": user.name,
                                            "text": text, "reasons": ["self-harm"], "createdAt": now_ms(), "seq": seq})
                _alert_admins(g, user, shown)
        except Exception:  # noqa: BLE001
            log.exception("chat: after-send bookkeeping failed for %s", doc["_id"])
        if text and not is_staff:
            try:
                ai_review.submit(text, _on_ai_verdict(user, g, doc, already_alerted=verdict.alert))
            except Exception:  # noqa: BLE001
                log.exception("chat: AI check failed for %s", doc["_id"])
        # Photos and PDFs from anyone: checked for nudity on this server; gone in a second or two if so.
        if attached:
            try:
                scan = media_scan.check_media(attached, strict=not is_staff)
                if not scan.allowed:
                    log.warning("chat: %s taken down by the media check (%s)", doc["_id"], ", ".join(scan.reasons))
                    _take_down(user, group_id, doc, scan.reasons)
            except Exception:  # noqa: BLE001
                log.exception("chat: media check failed for %s", doc["_id"])

    _background(notify_now)
    _background(after)
    took = int((time.time() - started) * 1000)
    if took > 300:
        # Where the time went, so a slow database (or one far from the server) shows in the logs.
        log.warning("chat: send took %d ms (lookups %d, number %d, save %d) - is MongoDB in the same region as the server?",
                    took, int((looked - started) * 1000), int((numbered - looked) * 1000), int((saved - numbered) * 1000))
    return out


def _together(*fns):
    """Runs independent database lookups at the same time (green threads on the server), so they
    cost one round trip instead of one each. Results in order; the first error is raised."""
    if not _SYNC_BACKGROUND:
        try:
            import eventlet
            from eventlet import patcher
            if patcher.is_monkey_patched("socket"):
                def guarded(fn):
                    # Errors come back as values: raised here, not printed by eventlet as crashes.
                    def run():
                        try:
                            return True, fn()
                        except Exception as exc:  # noqa: BLE001
                            return False, exc
                    return run
                pile = eventlet.GreenPile(len(fns))
                for fn in fns:
                    pile.spawn(guarded(fn))
                results = list(pile)
                for ok, value in results:
                    if not ok:
                        raise value
                return [value for _, value in results]
        except ImportError:
            pass
    return [fn() for fn in fns]


def _can_send_links(user: ChatUser, member: dict) -> bool:
    """Links are for admins: an admin of this group, anyone on the chat admin list, or a teacher
    who runs any group, so a Meet link also works in their private chats with students."""
    if member.get("role") == "admin" or user.is_admin:
        return True
    if not user.is_staff:
        return False
    return db().members.find_one({"userId": user.id, "role": "admin", "removed": {"$ne": True}}, projection={"_id": 1}) is not None


def _background(fn) -> None:
    """Runs fn after the current request has answered (a green thread on the server)."""
    if _SYNC_BACKGROUND:
        fn()
        return
    from ..extensions import socketio
    socketio.start_background_task(fn)


_SYNC_BACKGROUND = False       # tests flip this so they can check the results right away


def _alert_admins(g: dict, user: ChatUser, shown: str) -> None:
    """A student wrote something that sounds like self-harm: the group's admins (not the group)
    get a notification that opens the chat, so a person notices quickly."""
    if user.is_staff:
        return
    admins = [m["userId"] for m in db().members.find({"groupId": g["_id"], "role": "admin", "removed": {"$ne": True}},
                                                     projection={"userId": 1}) if m["userId"] != user.id]
    if not admins:
        return
    title = g.get("title", "")
    body = f"{shown or 'A student'} may need help. Please look at their message in {title}."
    push.send_to_users(admins, {"type": "chat_admin", "kind": "alert", "groupId": g["_id"], "groupTitle": title,
                                "title": title, "body": body, "text": body})


def _on_ai_verdict(user: ChatUser, g: dict, doc: dict, *, already_alerted: bool = False):
    """What happens when the AI check (a few seconds after delivery) has looked at a message."""
    def done(v: "moderation.Verdict", terms: list) -> None:
        if not v.allowed:
            current = db().messages.find_one({"_id": doc["_id"]}, projection={"deletedAt": 1, "text": 1}) or {}
            if current.get("deletedAt") or (current.get("text") or "") != (doc.get("text") or ""):
                return                            # already deleted, or edited since (the edit is checked on its own)
            log.warning("chat: %s taken down by the AI check (%s)", doc["_id"], ", ".join(v.reasons))
            _take_down(user, g["_id"], doc, v.reasons)    # also pulls the notification back
            ai_review.learn(terms, v.reasons[0].replace("ai:", ""), doc.get("text") or "")
        elif v.alert and not already_alerted:
            db().moderation.insert_one({"kind": "alert", "groupId": g["_id"], "userId": user.id, "name": user.name,
                                        "text": doc.get("text", ""), "reasons": ["self-harm", "ai"], "createdAt": now_ms(),
                                        "seq": doc.get("seq")})
            _alert_admins(g, user, display_name(doc.get("senderRole"), doc.get("senderName"), doc.get("rollNo")))
    return done


def _take_down(user: ChatUser, group_id: str, doc: dict, reasons: list) -> None:
    """The AI check flagged a delivered message: gone for everyone, logged, and a strike."""
    db().messages.update_one({"_id": doc["_id"]}, {"$set": {"deletedAt": now_ms(), "deletedBy": "moderation"}})
    md = doc.get("media") or {}
    if md.get("key") and not md.get("expired"):
        _add_stored(-int(md.get("size") or 0))
        if media.enabled():
            media.delete(md["key"])
    g = db().groups.find_one({"_id": group_id}, projection={"lastMessage": 1}) or {}
    if (g.get("lastMessage") or {}).get("seq") == doc["seq"]:
        db().groups.update_one({"_id": group_id}, {"$set": {"lastMessage.text": "This message was deleted", "lastMessage.deleted": True}})
    _emit("message_deleted", {"groupId": group_id, "seq": doc["seq"], "id": doc["_id"], "byAdmin": True}, group_room(group_id))
    others = [m["userId"] for m in db().members.find({"groupId": group_id, "userId": {"$ne": user.id}, "removed": {"$ne": True}},
                                                     projection={"userId": 1})]
    # High priority: the phone must wake now and remove the notification, not when Android gets to it.
    push.send_to_users(others, {"type": "chat_retract", "groupId": group_id, "seq": str(doc["seq"])}, priority="high")
    db().moderation.insert_one({"kind": "blocked", "groupId": group_id, "userId": user.id, "name": user.name,
                                "text": doc.get("text", ""), "reasons": reasons, "createdAt": now_ms(), "after": True})
    _strike(user, group_id, reasons)


def _push_text(doc: dict) -> str:
    if doc.get("media"):
        return media.label(doc["media"]) + (" " + doc["text"] if doc.get("text") else "")
    return doc.get("text", "")


MAX_MENTIONS = 5


def _can_mention_all(user: ChatUser, member: dict) -> bool:
    return member.get("role") == "admin" or user.is_admin


def _clean_mentions(user: ChatUser, g: dict, member: dict, raw) -> tuple[list[dict], bool]:
    """@mentions in a group: up to 5 people who are in it (students and teachers alike), plus
    "everyone" for admins. Ids that aren't members, or myself, are dropped quietly."""
    cfg = chatconfig.get()["messages"]
    if not raw or not isinstance(raw, (list, tuple)) or g.get("type") == "direct" or not cfg.get("mentions", True):
        return [], False
    asked = [str(x).strip() for x in raw if str(x or "").strip()]
    everyone = "everyone" in asked and _can_mention_all(user, member)
    ids = [i for i in dict.fromkeys(asked) if i not in ("everyone", user.id)][:MAX_MENTIONS]
    if not ids:
        return [], everyone
    staff = member.get("role") in STAFF_MEMBER_ROLES or user.is_staff
    rows = {r["userId"]: r for r in db().members.find(
        {"groupId": g["_id"], "userId": {"$in": ids}, "removed": {"$ne": True}},
        projection={"userId": 1, "name": 1, "role": 1, "rollNo": 1})}
    out = []
    for uid in ids:
        r = rows.get(uid)
        if not r:
            continue
        if not staff and r.get("role", "student") == "student" and not cfg.get("studentsMentionStudents", True):
            continue
        out.append({"u": uid, "n": display_name(r.get("role", "student"), r.get("name") or "", r.get("rollNo"))})
    return out, everyone


def mentionable(user: ChatUser, group_id: str) -> dict:
    """Who I can @mention here: teachers first, then students (as everyone in the group sees them)."""
    g = group_or_404(group_id)
    me = membership(group_id, user.id)
    cfg = chatconfig.get()["messages"]
    if g.get("type") == "direct" or not cfg.get("mentions", True):
        return {"people": [], "everyone": False}
    staff = me.get("role") in STAFF_MEMBER_ROLES or user.is_staff
    docs = list(db().members.find({"groupId": group_id, "removed": {"$ne": True}, "userId": {"$ne": user.id}},
                                  projection={"userId": 1, "name": 1, "role": 1, "rollNo": 1}))
    if not staff and not cfg.get("studentsMentionStudents", True):
        docs = [d for d in docs if d.get("role", "student") != "student"]
    avatars = _avatars(d["userId"] for d in docs)
    people = [{"userId": d["userId"], "name": display_name(d.get("role", "student"), d.get("name") or "", d.get("rollNo")),
               "role": d.get("role", "student"), "avatar": avatar_of(d.get("role"), avatars.get(d["userId"]))}
              for d in docs]
    people.sort(key=lambda x: (x["role"] == "student", x["name"].lower()))
    return {"people": people[:500], "everyone": _can_mention_all(user, me)}


def _notify(g: dict, doc: dict) -> None:
    named = {x.get("u") for x in doc.get("mentions") or []}
    everyone = bool(doc.get("mentionAll"))
    recipients, mentioned, muted, viewing = [], [], 0, 0
    for m in db().members.find({"groupId": g["_id"], "removed": {"$ne": True}, "userId": {"$ne": doc["senderId"]}},
                               projection={"userId": 1, "muted": 1}):
        called = everyone or m["userId"] in named
        if presence.is_viewing(m["userId"], g["_id"]):
            viewing += 1                           # the chat is open on their phone: no notification
        elif called:
            mentioned.append(m["userId"])          # a mention gets through even when the group is muted
        elif m.get("muted"):
            muted += 1
        else:
            recipients.append(m["userId"])
    if muted or viewing:
        log.info("chat push %s: skipped %d muted, %d with the chat open", g["_id"], muted, viewing)
    if not recipients and not mentioned:
        return
    label = sender_label(doc["senderRole"], doc.get("rollNo"))
    shown = display_name(doc["senderRole"], doc["senderName"], doc.get("rollNo"))
    direct = g.get("type") == "direct"
    # A direct message shows the sender's real name (the teacher knows who wrote).
    title = doc["senderName"] if direct else g.get("title", "")
    data = {
        "type": "chat_message",
        "groupId": g["_id"],
        "groupTitle": title,
        "groupType": g.get("type", "chat"),
        "seq": str(doc["seq"]),
        "messageId": doc["_id"],
        "senderId": doc["senderId"],
        "senderName": doc["senderName"] if direct else shown,
        "senderLabel": "" if direct else label,
        "senderAvatar": doc.get("senderAvatar") or "",
        "senderRole": doc.get("senderRole") or "student",
        "text": _push_text(doc)[:300],
        "createdAt": str(doc["createdAt"]),
        "title": title,
        "body": _push_text(doc)[:200] if direct else f"{shown}: {_push_text(doc)[:200]}",
    }
    if recipients:
        push.send_to_users(recipients, data)
    if mentioned:
        push.send_to_users(mentioned, {**data, "mentioned": "1",
                                       "body": f"{shown} mentioned you: {_push_text(doc)[:180]}"})


# ── reading ──────────────────────────────────────────────────────────────────────────────────

def history(user: ChatUser, group_id: str, before: Optional[int] = None, after: Optional[int] = None,
            limit: int = settings.PAGE_SIZE) -> dict:
    membership(group_id, user.id)
    limit = max(1, min(int(limit or settings.PAGE_SIZE), settings.MAX_PAGE_SIZE))
    q: dict = {"groupId": group_id}
    if after is not None:
        q["seq"] = {"$gt": int(after)}
        items = list(db().messages.find(q).sort("seq", 1).limit(limit + 1))
        has_more = len(items) > limit
        items = items[:limit]
    else:
        if before is not None:
            q["seq"] = {"$lt": int(before)}
        items = list(db().messages.find(q).sort("seq", -1).limit(limit + 1))
        has_more = len(items) > limit
        items = list(reversed(items[:limit]))
    avatars = _avatars(m["senderId"] for m in items)
    return {"messages": [message_out(m, avatars) for m in items], "hasMore": has_more}


_receipt_at: dict[str, float] = {}
_receipt_pending: set[str] = set()
_RECEIPT_GAP_S = 0.7


def _broadcast_receipts(group_id: str) -> None:
    """At most one summary per group every 0.7 s, and never a dropped one: a change inside the
    gap goes out at its end."""
    wait = _RECEIPT_GAP_S - (time.time() - _receipt_at.get(group_id, 0))
    if wait <= 0 or _SYNC_BACKGROUND:
        _send_receipts(group_id)
        return
    if group_id in _receipt_pending:
        return
    _receipt_pending.add(group_id)

    def later() -> None:
        time.sleep(wait)
        _receipt_pending.discard(group_id)
        _send_receipts(group_id)

    _background(later)


def _send_receipts(group_id: str) -> None:
    """The lowest delivered / read seq over members who have the chat app (people who never
    opened it would keep a message at one tick for ever)."""
    _receipt_at[group_id] = time.time()
    try:
        rows = list(db().members.find({"groupId": group_id, "removed": {"$ne": True}},
                                      projection={"userId": 1, "lastDeliveredSeq": 1, "lastReadSeq": 1}))
        if not rows:
            return
        with_app = {u["_id"] for u in db().users.find(
            {"_id": {"$in": [m["userId"] for m in rows]}, "fcmTokens.0": {"$exists": True}}, projection={"_id": 1})}
        counted = [m for m in rows if m["userId"] in with_app] or rows
        d = min(int(m.get("lastDeliveredSeq") or 0) for m in counted)
        r = min(int(m.get("lastReadSeq") or 0) for m in counted)
        db().groups.update_one({"_id": group_id}, {"$set": {"deliveredSeq": d, "readSeq": r}})
        _emit("receipts", {"groupId": group_id, "deliveredSeq": d, "readSeq": r}, group_room(group_id))
    except Exception:  # noqa: BLE001
        log.exception("chat: receipts failed for %s", group_id)


RECEIPT_LOG = 300        # how many steps of "delivered / read up to N at time T" each member keeps


def _advance(member_id, field: str, seq: int, at: int) -> bool:
    """Moves lastDeliveredSeq / lastReadSeq forward and notes when, so "Message info" can say
    exactly when each person got and read each message. False when it was already there."""
    log_field = "deliveredLog" if field == "lastDeliveredSeq" else "readLog"
    r = db().members.update_one(
        {"_id": member_id, "$or": [{field: {"$lt": seq}}, {field: {"$exists": False}}]},
        {"$set": {field: seq}, "$push": {log_field: {"$each": [[seq, at]], "$slice": -RECEIPT_LOG}}})
    return r.modified_count > 0


def mark_read(user: ChatUser, group_id: str, seq: int) -> int:
    m, g = _together(lambda: membership(group_id, user.id), lambda: group_or_404(group_id))
    seq = max(0, min(int(seq), int(g.get("lastSeq", 0))))
    at = now_ms()
    moved = _advance(m["_id"], "lastDeliveredSeq", seq, at)       # read means it arrived too
    moved = _advance(m["_id"], "lastReadSeq", seq, at) or moved
    if moved:
        _broadcast_receipts(group_id)
    return seq


def mark_delivered(user: ChatUser, group_id: str, seq: int) -> None:
    m = membership(group_id, user.id)
    if _advance(m["_id"], "lastDeliveredSeq", int(seq), now_ms()):
        _broadcast_receipts(group_id)


def mark_all_delivered(user_id: str) -> int:
    """The phone just connected and synced its chats: everything sent to it so far has arrived
    (WhatsApp's second tick, even for messages that came while it was offline and the
    notification never got through). Returns how many chats moved on."""
    rows = list(db().members.find({"userId": user_id, "removed": {"$ne": True}},
                                  projection={"groupId": 1, "lastDeliveredSeq": 1}))
    if not rows:
        return 0
    last = {g["_id"]: int(g.get("lastSeq") or 0) for g in db().groups.find(
        {"_id": {"$in": [r["groupId"] for r in rows]}}, projection={"lastSeq": 1})}
    at, moved = now_ms(), 0
    for r in rows:
        top = last.get(r["groupId"], 0)
        if top > int(r.get("lastDeliveredSeq") or 0) and _advance(r["_id"], "lastDeliveredSeq", top, at):
            moved += 1
            _broadcast_receipts(r["groupId"])
    return moved


def _when(log_rows, seq: int) -> int:
    """When a member's delivered / read mark first reached seq (0 = not known)."""
    for entry in log_rows or []:
        try:
            s_, at = int(entry[0]), int(entry[1])
        except (TypeError, ValueError, IndexError):
            continue
        if s_ >= seq:
            return at
    return 0


def message_info(user: ChatUser, group_id: str, seq: int) -> dict:
    """My message's "Message info", like WhatsApp: who read it and when, who has it on their
    phone (ticked twice) and when, and who hasn't got it yet (phone off or no internet, or no app)."""
    membership(group_id, user.id)
    msg = db().messages.find_one({"groupId": group_id, "seq": int(seq)})
    if not msg or msg.get("type") == "system" or msg.get("deletedAt"):
        raise ChatError("no_message", "That message is gone.", 404)
    if msg["senderId"] != user.id:
        raise ChatError("forbidden", "Only the sender can see who got a message.", 403)
    rows = list(db().members.find(
        {"groupId": group_id, "removed": {"$ne": True}, "userId": {"$ne": user.id}},
        projection={"userId": 1, "name": 1, "role": 1, "rollNo": 1, "joinedAt": 1, "lastDeliveredSeq": 1,
                    "lastReadSeq": 1, "deliveredLog": 1, "readLog": 1}))
    # People who joined after it was sent never got it: not "waiting".
    rows = [m for m in rows if int(m.get("joinedAt") or 0) <= int(msg["createdAt"]) + 1000]
    with_app = {u["_id"] for u in db().users.find(
        {"_id": {"$in": [m["userId"] for m in rows]}, "fcmTokens.0": {"$exists": True}}, projection={"_id": 1})}
    read, delivered, waiting = [], [], []
    for m in rows:
        person = {"userId": m["userId"], "name": display_name(m.get("role", "student"), m.get("name") or "", m.get("rollNo"))}
        if int(m.get("lastReadSeq") or 0) >= seq:
            read.append({**person, "at": _when(m.get("readLog"), seq)})
        elif int(m.get("lastDeliveredSeq") or 0) >= seq:
            delivered.append({**person, "at": _when(m.get("deliveredLog"), seq)})
        else:
            waiting.append({**person, "hasApp": m["userId"] in with_app, "online": presence.is_online(m["userId"])})
    read.sort(key=lambda x: x["at"] or 0, reverse=True)
    delivered.sort(key=lambda x: x["at"] or 0, reverse=True)
    waiting.sort(key=lambda x: (not x["hasApp"], x["name"]))
    return {"groupId": group_id, "seq": int(seq), "sentAt": int(msg["createdAt"]),
            "read": read, "delivered": delivered, "waiting": waiting}


# ── online / last seen (direct chats) ────────────────────────────────────────────────────────

def _direct_groups_of(user_id: str) -> list[str]:
    ids = [m["groupId"] for m in db().members.find({"userId": user_id, "removed": {"$ne": True}}, projection={"groupId": 1})]
    if not ids:
        return []
    return [g["_id"] for g in db().groups.find({"_id": {"$in": ids}, "type": "direct"}, projection={"_id": 1})]


def presence_changed(user_id: str, online: bool) -> None:
    """Came online (app opened) or went offline: the people they chat with directly see it at once."""
    if not chatconfig.show_online():
        return
    at = now_ms()
    if not online:
        db().users.update_one({"_id": user_id}, {"$set": {"lastSeenAt": at}}, upsert=True)
    payload = {"userId": user_id, "online": online, "lastSeen": 0 if online else at}
    for gid in _direct_groups_of(user_id):
        _emit("presence", {**payload, "groupId": gid}, group_room(gid))


def peer_presence(user: ChatUser, group_id: str) -> dict:
    """For a direct chat: is the other person here right now, and if not, when they last were."""
    membership(group_id, user.id)
    g = group_or_404(group_id)
    if g.get("type") != "direct" or not chatconfig.show_online():
        return {"userId": "", "online": False, "lastSeen": 0}
    other = db().members.find_one({"groupId": group_id, "userId": {"$ne": user.id}}, projection={"userId": 1})
    if not other:
        return {"userId": "", "online": False, "lastSeen": 0}
    uid = other["userId"]
    if presence.is_online(uid):
        return {"userId": uid, "online": True, "lastSeen": 0}
    doc = db().users.find_one({"_id": uid}, projection={"lastSeenAt": 1}) or {}
    return {"userId": uid, "online": False, "lastSeen": int(doc.get("lastSeenAt") or 0)}


def delete_message(user: ChatUser, group_id: str, seq: int) -> dict:
    """Your own message: any time. Group admins: anyone's. Gone for everyone."""
    m = membership(group_id, user.id)
    msg = db().messages.find_one({"groupId": group_id, "seq": int(seq)})
    if not msg or msg.get("type") == "system":
        raise ChatError("no_message", "That message is gone.", 404)
    if not (msg["senderId"] == user.id or m.get("role") == "admin"):
        raise ChatError("forbidden", "You can only delete your own messages.", 403)
    db().messages.update_one({"_id": msg["_id"]}, {"$set": {"deletedAt": now_ms(), "deletedBy": user.id}})
    g = db().groups.find_one({"_id": group_id}, projection={"lastMessage": 1}) or {}
    if (g.get("lastMessage") or {}).get("seq") == int(seq):
        db().groups.update_one({"_id": group_id}, {"$set": {"lastMessage.text": "This message was deleted", "lastMessage.deleted": True}})
    payload = {"groupId": group_id, "seq": int(seq), "id": msg["_id"], "byAdmin": msg["senderId"] != user.id}
    _emit("message_deleted", payload, group_room(group_id))
    md = msg.get("media") or {}
    key = md.get("key")
    if key and not md.get("expired"):
        _add_stored(-int(md.get("size") or 0))
        if media.enabled():                        # the photo / voice note goes too, not just the bubble
            _background(lambda: media.delete(key))
    return payload


def edit_message(user: ChatUser, group_id: str, seq: int, text: str) -> dict:
    """Your own message (or a file's caption), within chatConfig.messages.editMinutes. Everyone
    sees the new text with "edited"."""
    member = membership(group_id, user.id)
    text = (text or "").strip()
    msg = db().messages.find_one({"groupId": group_id, "seq": int(seq)})
    if not msg or msg.get("type") == "system" or msg.get("deletedAt"):
        raise ChatError("no_message", "That message is gone.", 404)
    if msg["senderId"] != user.id:
        raise ChatError("forbidden", "You can only edit your own messages.", 403)
    window = chatconfig.edit_minutes()
    if now_ms() - int(msg["createdAt"]) > window * 60_000:
        span = f"{window // 60} hour{'s' if window // 60 != 1 else ''}" if window % 60 == 0 else f"{window} minutes"
        raise ChatError("edit_window", f"Messages can only be edited within {span} of sending.", 403)
    if not text and not msg.get("media"):
        raise ChatError("empty", "A message can't be empty. Delete it instead.")
    if len(text) > settings.MAX_TEXT_LENGTH:
        raise ChatError("too_long", f"Messages can be up to {settings.MAX_TEXT_LENGTH} characters.")
    if text == (msg.get("text") or ""):
        return message_out(msg)
    g = group_or_404(group_id)
    if not _can_post(g, member):
        raise ChatError("read_only", "You can't send messages here right now.", 403)
    is_staff = member.get("role") in STAFF_MEMBER_ROLES or user.is_staff
    can_link = _can_send_links(user, member) if text and moderation.has_link(text) else None
    verdict = moderation.check(text, is_staff=is_staff, ai=False, can_link=can_link) if text else moderation.Verdict(allowed=True)
    if not verdict.allowed:
        _strike(user, group_id, verdict.reasons)
        raise ChatError("blocked", verdict.message, 422)
    at = now_ms()
    db().messages.update_one({"_id": msg["_id"]}, {"$set": {"text": text, "editedAt": at}, "$push": {
        "edits": {"$each": [{"text": msg.get("text") or "", "at": at}], "$slice": -10}}})
    msg.update({"text": text, "editedAt": at})
    last = (db().groups.find_one({"_id": group_id}, projection={"lastMessage": 1}) or {}).get("lastMessage") or {}
    if last.get("seq") == int(seq):
        preview = (media.label(msg.get("media")) + (" " + text if text else "")) if msg.get("media") else text
        db().groups.update_one({"_id": group_id}, {"$set": {"lastMessage.text": preview[:160]}})
    out = message_out(msg)
    _emit("message_edited", {"groupId": group_id, "seq": int(seq), "text": text, "editedAt": at}, group_room(group_id))
    if text and not is_staff:
        _background(lambda: ai_review.submit(text, _on_ai_verdict(user, g, msg, already_alerted=verdict.alert)))
    return out


def sweep_expired_media(limit: int = 500) -> int:
    """Removes files older than chatConfig.media.retentionDays from storage; their messages then
    show "expired". Runs every few hours. Returns how many were removed."""
    days = int(chatconfig.media()["retentionDays"])
    if days <= 0:
        return 0
    cutoff = now_ms() - days * 86_400_000
    docs = list(db().messages.find(
        {"media.key": {"$exists": True}, "media.expired": {"$ne": True}, "createdAt": {"$lt": cutoff}},
        projection={"media": 1, "deletedAt": 1}).limit(limit))
    if not docs:
        return 0
    if media.enabled():
        media.delete_many([d["media"]["key"] for d in docs])
    freed = sum(int(d["media"].get("size") or 0) for d in docs if not d.get("deletedAt"))
    db().messages.update_many({"_id": {"$in": [d["_id"] for d in docs]}}, {"$set": {"media.expired": True}})
    _add_stored(-freed)
    log.info("chat: removed %d expired files (%d MB)", len(docs), freed // (1024 * 1024))
    return len(docs)


PENDING_KEEP_MS = 3 * 86_400_000


def sweep_unsent_uploads() -> int:
    """Uploads whose message was never sent (app closed, sending cancelled): removed after 3 days."""
    cutoff = now_ms() - PENDING_KEEP_MS
    docs = list(db().media_pending.find({"at": {"$lt": cutoff}}, projection={"_id": 1}).limit(500))
    if not docs:
        return 0
    keys = [d["_id"] for d in docs]
    if media.enabled():
        media.delete_many(keys)
    db().media_pending.delete_many({"_id": {"$in": keys}})
    log.info("chat: removed %d uploads that were never sent", len(keys))
    return len(keys)


def recount_storage() -> int:
    """Recounts the bytes kept in storage from the messages themselves, so the running total can
    never drift away from the truth (and let the bucket grow past the limit)."""
    total = 0
    for d in db().messages.find({"media.key": {"$exists": True}, "media.expired": {"$ne": True},
                                 "deletedAt": {"$exists": False}}, projection={"media.size": 1}):
        total += int((d.get("media") or {}).get("size") or 0)
    db().media_stats.update_one({"_id": "storage"}, {"$set": {"bytes": total, "countedAt": now_ms()}}, upsert=True)
    return total


def start_media_sweeper() -> None:
    def loop() -> None:
        while True:
            try:
                while sweep_expired_media() >= 500:       # a big backlog: keep going
                    pass
                sweep_unsent_uploads()
                recount_storage()
            except Exception:  # noqa: BLE001
                log.exception("chat: expired-file sweep failed")
            time.sleep(3 * 3600)
    from ..extensions import socketio
    socketio.start_background_task(loop)


# ── reactions ────────────────────────────────────────────────────────────────────────────────

_REACT_WINDOW_S = 60
_REACT_MAX = 40
_react_times: dict[str, deque] = {}
_react_lock = threading.Lock()


def _react_rate_ok(user_id: str) -> bool:
    t = time.time()
    with _react_lock:
        q = _react_times.setdefault(user_id, deque())
        while q and t - q[0] > _REACT_WINDOW_S:
            q.popleft()
        if len(q) >= _REACT_MAX:
            return False
        q.append(t)
        return True


def _clean_emoji(raw) -> str:
    e = str(raw or "").strip()
    if not e:
        return ""
    if len(e) > 8 or any(ch.isascii() for ch in e):
        raise ChatError("bad_reaction", "Pick an emoji to react with.")
    if moderation.emoji_hit(e, reaction=True):
        raise ChatError("bad_reaction", "That emoji isn't allowed here.")
    return e


def react(user: ChatUser, group_id: str, seq: int, emoji) -> dict:
    """One reaction per person per message: a new emoji replaces mine, an empty one removes it.
    Everyone in the chat sees it at once; the message's author gets a notification."""
    if not chatconfig.reactions_on():
        raise ChatError("reactions_off", "Reactions are switched off right now.", 503)
    emoji = _clean_emoji(emoji)
    g = group_or_404(group_id)
    member = membership(group_id, user.id)
    if (member.get("restrictedUntil") or 0) > now_ms():
        raise ChatError("restricted", "A teacher has paused your messages in this group for a while.", 403)
    msg = db().messages.find_one({"groupId": group_id, "seq": int(seq)})
    if not msg or msg.get("type") == "system" or msg.get("deletedAt"):
        raise ChatError("no_message", "That message is gone.", 404)
    slot = user.id.replace(".", "_").replace("$", "_")
    before = (msg.get("reactions") or {}).get(slot) or {}
    if (before.get("e") or "") == emoji:
        return {"groupId": group_id, "seq": int(seq), "reactions": reactions_out(msg), "reactedAt": int(msg.get("reactedAt") or 0)}
    if not _react_rate_ok(user.id):
        raise ChatError("slow_down", "You're reacting too fast.", 429)
    at = now_ms()
    name = display_name(member.get("role", "student"), member.get("name") or user.name, member.get("rollNo"))
    if emoji:
        change = {"$set": {f"reactions.{slot}": {"u": user.id, "n": name, "e": emoji, "at": at}, "reactedAt": at}}
    else:
        change = {"$unset": {f"reactions.{slot}": ""}, "$set": {"reactedAt": at}}
    fresh = db().messages.find_one_and_update({"_id": msg["_id"]}, change, return_document=ReturnDocument.AFTER)
    payload = {"groupId": group_id, "seq": int(seq), "reactions": reactions_out(fresh), "reactedAt": at}
    _emit("reaction", payload, group_room(group_id))
    if msg["senderId"] != user.id and (emoji or before.get("e")):
        def notify() -> None:
            try:
                _notify_reaction(g, msg, user, name, emoji)
            except Exception:  # noqa: BLE001
                log.exception("chat: reaction notification failed for %s", msg["_id"])
        _background(notify)
    return payload


def _notify_reaction(g: dict, msg: dict, reactor: ChatUser, name: str, emoji: str) -> None:
    author = db().members.find_one({"groupId": g["_id"], "userId": msg["senderId"], "removed": {"$ne": True}},
                                   projection={"muted": 1})
    if not author or author.get("muted"):
        return
    if emoji and presence.is_viewing(msg["senderId"], g["_id"]):
        return                                     # they are looking at the chat: they see it there
    direct = g.get("type") == "direct"
    title = reactor.name if direct else g.get("title", "")
    shown = reactor.name if direct else name
    preview = _push_text(msg)[:80] or "your message"
    push.send_to_users([msg["senderId"]], {
        "type": "chat_reaction",
        "groupId": g["_id"],
        "groupTitle": title,
        "groupType": g.get("type", "chat"),
        "seq": str(msg["seq"]),
        "senderId": reactor.id,
        "senderName": shown,
        "emoji": emoji,                            # empty: the reaction was taken back, pull the line
        "text": preview,
        "title": title,
        "body": f"{shown} reacted {emoji} to: \u201c{preview}\u201d" if emoji else "",
        "createdAt": str(now_ms()),
    }, priority="high" if emoji else "normal")


def reactions_since(user: ChatUser, group_id: str, since: int) -> dict:
    """Reactions that changed after `since` (ms), for a phone that was offline when they came."""
    membership(group_id, user.id)
    docs = list(db().messages.find({"groupId": group_id, "reactedAt": {"$gt": int(since or 0)}},
                                   projection={"seq": 1, "reactions": 1, "reactedAt": 1, "deletedAt": 1})
                .sort("reactedAt", 1).limit(300))
    items = [{"seq": d["seq"], "reactions": [] if d.get("deletedAt") else reactions_out(d)} for d in docs]
    until = max([int(d["reactedAt"]) for d in docs], default=int(since or 0))
    return {"items": items, "until": until, "more": len(docs) == 300}


def report_message(user: ChatUser, group_id: str, seq: int, reason: str) -> None:
    membership(group_id, user.id)
    msg = db().messages.find_one({"groupId": group_id, "seq": int(seq)})
    if not msg:
        raise ChatError("no_message", "That message is gone.", 404)
    db().reports.insert_one({
        "groupId": group_id, "seq": int(seq), "messageId": msg["_id"], "text": msg.get("text", ""),
        "senderId": msg["senderId"], "reporterId": user.id, "reason": (reason or "")[:300], "createdAt": now_ms(),
    })


def set_muted(user: ChatUser, group_id: str, muted: bool) -> None:
    m = membership(group_id, user.id)
    db().members.update_one({"_id": m["_id"]}, {"$set": {"muted": bool(muted)}})


def register_device(user: ChatUser, token: str, platform: str, device: str = "") -> None:
    token = (token or "").strip()
    if not token:
        raise ChatError("no_token", "Missing FCM token.")
    # A phone that changed accounts sends its token to the new account only.
    db().users.update_many({"fcmTokens.token": token}, {"$pull": {"fcmTokens": {"token": token}}})
    db().users.update_one({"_id": user.id}, {"$push": {"fcmTokens": {
        "$each": [{"token": token, "platform": (platform or "android")[:16], "updatedAt": now_ms(),
                   **({"device": device} if device else {})}],
        "$slice": -5,                              # last 5 phones
    }}}, upsert=True)


def unregister_device(user: ChatUser, token: str) -> None:
    db().users.update_one({"_id": user.id}, {"$pull": {"fcmTokens": {"token": (token or "").strip()}}})


# ── direct chats ─────────────────────────────────────────────────────────────────────────────

def _shared_groups(a: str, b: str) -> list[dict]:
    """Groups (not direct chats) both people are in, with b's membership in each."""
    mine = {m["groupId"] for m in db().members.find({"userId": a, "removed": {"$ne": True}}, projection={"groupId": 1})}
    if not mine:
        return []
    theirs = list(db().members.find({"userId": b, "groupId": {"$in": list(mine)}, "removed": {"$ne": True}}))
    gids = [m["groupId"] for m in theirs]
    real = {g["_id"] for g in db().groups.find({"_id": {"$in": gids}, "type": {"$ne": "direct"}}, projection={"_id": 1})}
    return [m for m in theirs if m["groupId"] in real]


def contacts(user: ChatUser) -> list[dict]:
    """Students: the teachers of their groups. Teachers: everyone in their groups."""
    gids = [m["groupId"] for m in db().members.find({"userId": user.id, "removed": {"$ne": True}}, projection={"groupId": 1})]
    real = {g["_id"]: g.get("title", "") for g in db().groups.find({"_id": {"$in": gids}, "type": {"$ne": "direct"}},
                                                                 projection={"title": 1})}
    q: dict = {"groupId": {"$in": list(real)}, "userId": {"$ne": user.id}, "removed": {"$ne": True}}
    if not user.is_staff:
        q["role"] = {"$in": list(STAFF_MEMBER_ROLES)}
    people: dict[str, dict] = {}
    for m in db().members.find(q):
        p = people.setdefault(m["userId"], {"id": m["userId"], "name": m.get("name") or "", "role": m.get("role", "student"),
                                            "rollNo": m.get("rollNo"), "groups": []})
        if m.get("role") == "admin":
            p["role"] = "admin"
        elif m.get("role") == "teacher" and p["role"] == "student":
            p["role"] = "teacher"
        title = real.get(m["groupId"], "")
        if title and title not in p["groups"]:
            p["groups"].append(title)
    avatars = _avatars(people)
    for p in people.values():
        p["avatar"] = avatar_of(p["role"], avatars.get(p["id"]))
    ordered = sorted(people.values(), key=lambda p: (p["role"] == "student", (p["name"] or "").lower()))
    return ordered[:500]


def open_direct(user: ChatUser, other_id: str) -> dict:
    other_id = (other_id or "").strip()
    if not other_id or other_id == user.id:
        raise ChatError("bad_person", "Pick someone to message.")
    shared = _shared_groups(user.id, other_id)
    if not shared:
        raise ChatError("forbidden", "You can only message people from your groups.", 403)
    other_staff = any(m.get("role") in STAFF_MEMBER_ROLES for m in shared)
    if not user.is_staff and not other_staff:
        raise ChatError("forbidden", "Students can message their teachers, not other students.", 403)
    a, b = sorted([user.id, other_id])
    gid = f"dm_{a}_{b}"
    if not db().groups.find_one({"_id": gid}, projection={"_id": 1}):
        try:
            db().groups.insert_one({"_id": gid, "title": "", "description": "", "type": "direct",
                                    "createdBy": user.id, "createdAt": now_ms(), "lastSeq": 0, "lastMessage": None,
                                    "memberCount": 2, "deliveredSeq": 0, "readSeq": 0})
        except DuplicateKeyError:
            pass
        other = shared[0]
        mine = db().members.find_one({"userId": user.id, "groupId": other["groupId"]}) or {}
        for uid, name, role, roll in ((user.id, mine.get("name") or user.name, _member_role_for(user), mine.get("rollNo")),
                                      (other_id, other.get("name") or "", "teacher" if other_staff else "student",
                                       other.get("rollNo"))):
            db().members.update_one(
                {"groupId": gid, "userId": uid},
                {"$setOnInsert": {"role": role, "name": name, "rollNo": roll, "joinedAt": now_ms(), "lastReadSeq": 0,
                                  "lastDeliveredSeq": 0, "muted": False, "removed": False}},
                upsert=True)
            _join_live(uid, gid, True)
        # The other person hears about it with the first message, not when the chat is opened.
    m = membership(gid, user.id)
    return group_out(group_or_404(gid), m, user.id)


# ── managing groups (group admins) ───────────────────────────────────────────────────────────

def _join_live(user_id: str, group_id: str, join: bool) -> None:
    """Adds / removes a connected user's phones to the group's live room right away."""
    from ..extensions import socketio
    from . import presence as p
    with p._lock:  # noqa: SLF001
        sids = list(p._user_sids.get(user_id, ()))  # noqa: SLF001
    for sid in sids:
        try:
            if join:
                socketio.server.enter_room(sid, group_room(group_id), namespace=NS)
            else:
                socketio.server.leave_room(sid, group_room(group_id), namespace=NS)
        except Exception:  # noqa: BLE001
            pass


def create_group(admin: ChatUser, body: dict) -> dict:
    title = (body.get("title") or "").strip()
    gtype = body.get("type") or "chat"
    if not title:
        raise ChatError("no_title", "Give the group a name.")
    if gtype not in GROUP_TYPES:
        raise ChatError("bad_type", "type is 'announcement' or 'chat'.")
    coaching = (body.get("coaching") or admin.coaching).strip().lower()
    # One batch ("batch") or several ("batches", e.g. Spartans Physics + Chemistry + Math).
    many = [str(b).strip() for b in (body.get("batches") or []) if str(b).strip()]
    single = (body.get("batch") or "").strip()
    batch = many if many else ([single] if single else [])
    # Every reference this admin's notifications reach (e.g. ANSHUL + 99+JEE): students of all of
    # them can join, like a notification goes to all of them.
    coachings = list(dict.fromkeys(
        [coaching] + [str(c).strip().lower() for c in (body.get("coachings") or []) if str(c).strip()]))
    gid = "g_" + secrets.token_hex(8)
    doc = {
        "_id": gid, "title": title[:80], "description": (body.get("description") or "")[:300],
        "type": gtype, "coaching": coaching, "coachings": coachings, "batch": batch or None,
        "match": {"coaching": coachings, "batch": batch or ["*"]},
        "autoJoin": bool(body.get("autoJoin")),
        "joinRequests": bool(body.get("joinRequests")),
        "createdBy": admin.id, "createdAt": now_ms(), "lastSeq": 0, "lastMessage": None,
        "memberCount": 0, "deliveredSeq": 0, "readSeq": 0,
    }
    db().groups.insert_one(doc)
    add_members(gid, [{"userId": admin.id, "name": admin.name, "role": "admin"}], source="creator")
    system_message(gid, f"{admin.name} created the group")
    m = membership(gid, admin.id)
    return group_out(db().groups.find_one({"_id": gid}), m, admin.id)


def update_group(user: ChatUser, group_id: str, body: dict) -> dict:
    g, me = require_group_admin(user, group_id)
    changes: dict = {}
    who = _who(user, me)
    if isinstance(body.get("title"), str) and body["title"].strip() and body["title"].strip() != g.get("title"):
        changes["title"] = body["title"].strip()[:80]
    if isinstance(body.get("description"), str) and body["description"] != g.get("description", ""):
        changes["description"] = body["description"][:300]
    if body.get("type") in GROUP_TYPES and body["type"] != g.get("type"):
        changes["type"] = body["type"]
    if isinstance(body.get("autoJoin"), bool) and body["autoJoin"] != _auto(g):
        changes["autoJoin"] = body["autoJoin"]
        if not g.get("match"):
            changes["match"] = _match(g) or {"coaching": [g.get("coaching")], "batch": ["*"]}
    if isinstance(body.get("joinRequests"), bool) and body["joinRequests"] != bool(g.get("joinRequests")):
        changes["joinRequests"] = body["joinRequests"]
        if not g.get("match") and "match" not in changes:
            changes["match"] = _match(g) or {"coaching": [g.get("coaching")], "batch": ["*"]}
    if changes:
        db().groups.update_one({"_id": group_id}, {"$set": changes})
    if "title" in changes:
        system_message(group_id, f"{who} renamed the group to “{changes['title']}”")
    if "type" in changes:
        system_message(group_id, f"{who} changed the group: only admins can send messages"
                       if changes["type"] == "announcement" else f"{who} changed the group: everyone can send messages")
    g = db().groups.find_one({"_id": group_id})
    _emit("group_updated", {"groupId": group_id}, group_room(group_id))
    return group_out(g, membership(group_id, user.id), user.id)


def delete_group(user: ChatUser, group_id: str) -> None:
    g = group_or_404(group_id)
    if g.get("type") == "direct" or g.get("createdBy") != user.id:
        raise ChatError("forbidden", "Only the person who created the group can delete it.", 403)
    ids = [m["userId"] for m in db().members.find({"groupId": group_id}, projection={"userId": 1})]
    kept = sum(int((m.get("media") or {}).get("size") or 0) for m in db().messages.find(
        {"groupId": group_id, "media.key": {"$exists": True}, "media.expired": {"$ne": True}, "deletedAt": {"$exists": False}},
        projection={"media.size": 1}))
    _add_stored(-kept)
    db().messages.delete_many({"groupId": group_id})
    db().members.delete_many({"groupId": group_id})
    db().groups.delete_one({"_id": group_id})
    for uid in ids:
        _emit("group_removed", {"groupId": group_id}, user_room(uid))
        _join_live(uid, group_id, False)
    if media.enabled():
        _background(lambda: media.delete_group(group_id))


def _is_teacher(user_id: str) -> bool:
    u = db().users.find_one({"_id": user_id}, projection={"role": 1}) or {}
    if str(u.get("role") or "").lower() in STAFF_ROLES:
        return True
    return db().members.find_one({"userId": user_id, "role": {"$in": list(STAFF_MEMBER_ROLES)},
                                  "removed": {"$ne": True}}, projection={"_id": 1}) is not None


def add_members(group_id: str, members: list[dict], source: str = "manual", added_by: Optional[str] = None) -> int:
    """Adds people (or changes the role / roll number of people already in). `source` records how
    they came in (manual, batch:<value>, group:<id>, auto, creator) so admins can see and undo it."""
    g = group_or_404(group_id)
    added = 0
    newly: list[str] = []
    for m in members:
        uid = str(m.get("userId") or "").strip()
        if not uid:
            continue
        role = m.get("role") if m.get("role") in MEMBER_ROLES else "student"
        changes: dict = {"role": role, "removed": False}
        if (m.get("name") or "").strip():
            changes["name"] = m["name"].strip()
        if m.get("rollNo") not in (None, ""):
            changes["rollNo"] = str(m["rollNo"]).strip()
        before = db().members.find_one({"groupId": group_id, "userId": uid}, projection={"removed": 1, "role": 1, "left": 1})
        if before and before.get("left") and source not in ("manual", "request"):
            continue                                    # left by themselves: only "Add back" (or their own request) brings them in
        changes["left"] = False
        if before and not before.get("removed") and before.get("role") == "admin" and role != "admin":
            changes["role"] = "admin"                   # adding again never demotes an admin
        db().members.update_one(
            {"groupId": group_id, "userId": uid},
            {"$set": changes, "$addToSet": {"sources": source},
             "$setOnInsert": {"joinedAt": now_ms(), "lastReadSeq": 0, "lastDeliveredSeq": 0, "muted": False}},
            upsert=True,
        )
        if before is None or before.get("removed"):
            added += 1
            newly.append(uid)
            _join_live(uid, group_id, True)
            _emit("group_added", {"groupId": group_id}, user_room(uid))
    if added:
        db().groups.update_one({"_id": group_id}, {"$inc": {"memberCount": added}})
    if newly and source != "request":
        _close_requests(group_id, newly)            # in by another way: nothing left to answer
    if newly and added_by and g.get("type") != "direct":
        # "Anshul Sir added you to Titan": everyone just added hears it on their phone.
        title = g.get("title", "")
        body = f"{added_by} added you to {title}. Tap to open the group."
        push.send_to_users(newly, {"type": "chat_admin", "kind": "added", "groupId": group_id, "groupTitle": title,
                                   "title": title, "body": body, "text": body})
    return added


def admin_add_members(user: ChatUser, group_id: str, members: list[dict], source: str = "manual") -> int:
    g, me = require_group_admin(user, group_id)
    clean = []
    for m in members:                                  # promoting is a separate, checked action
        m = dict(m)
        if m.get("role") in ("admin", "teacher") and not _is_teacher(str(m.get("userId") or "")):
            m["role"] = "student"
        elif m.get("role") == "admin":
            m["role"] = "teacher"
        clean.append(m)
    added = add_members(group_id, clean, source=source or "manual", added_by=_who(user, me))
    if added:
        label = _source_label(source)
        system_message(group_id, f"{_who(user, me)} added {added} {'person' if added == 1 else 'people'}"
                                 + (f" {label}" if label else ""))
    return added


def _source_label(source: str) -> str:
    if source.startswith("group:"):
        src = db().groups.find_one({"_id": source[6:]}, projection={"title": 1}) or {}
        return f"from {src.get('title') or 'another group'}"
    if source.startswith("batch:"):
        return "from a batch"
    if source == "request":
        return "who asked to join"
    return ""


def remove_member(user: ChatUser, group_id: str, user_id: str) -> None:
    g, me = require_group_admin(user, group_id)
    if user_id == g.get("createdBy"):
        raise ChatError("forbidden", "The group's creator can't be removed.", 403)
    target = membership(group_id, user_id)
    _remove(group_id, user_id)
    system_message(group_id, f"{_who(user, me)} removed {_person(target)}")


def _remove(group_id: str, user_id: str) -> bool:
    res = db().members.update_one({"groupId": group_id, "userId": user_id, "removed": {"$ne": True}},
                                  {"$set": {"removed": True}})
    if res.modified_count:
        db().groups.update_one({"_id": group_id}, {"$inc": {"memberCount": -1}})
        _emit("group_removed", {"groupId": group_id}, user_room(user_id))
        _join_live(user_id, group_id, False)
        return True
    return False


def leave_group(user: ChatUser, group_id: str) -> None:
    """Anyone but the creator can leave whenever they like. Only an admin can add them back."""
    g = group_or_404(group_id)
    if g.get("type") == "direct":
        raise ChatError("forbidden", "This is a private chat, not a group.", 403)
    m = membership(group_id, user.id)
    if g.get("createdBy") == user.id:
        raise ChatError("creator", "You created this group. Delete it instead of leaving.", 403)
    db().members.update_one({"_id": m["_id"]}, {"$set": {"left": True, "leftAt": now_ms()}})
    _remove(group_id, user.id)
    system_message(group_id, f"{_person(m, user.name or 'A student')} left the group")


def left_members(user: ChatUser, group_id: str) -> list[dict]:
    """People who left by themselves, newest first, for the admins' "Left the group" list."""
    require_group_admin(user, group_id)
    docs = list(db().members.find({"groupId": group_id, "left": True, "removed": True}).sort("leftAt", -1))
    avatars = _avatars(m["userId"] for m in docs)
    cards = _contact_cards(m["userId"] for m in docs)
    return [{"userId": m["userId"], "name": m.get("name") or (cards.get(m["userId"]) or {}).get("name") or "",
             "phone": (cards.get(m["userId"]) or {}).get("phone", "") if (m.get("role") or "student") == "student" else "",
             "role": m.get("role") or "student",
             "rollNo": m.get("rollNo"), "leftAt": int(m.get("leftAt") or 0),
             "avatar": avatar_of(m.get("role"), avatars.get(m["userId"]))} for m in docs]


def member_profile(user: ChatUser, group_id: str, user_id: str) -> dict:
    """What a teacher or admin sees on tapping a member: who they are, a student's phone numbers
    (to copy), which groups they are in, how they came in, and whether they are paused. Only the
    group's admins get the actions (canManage)."""
    g = group_or_404(group_id)
    me = membership(group_id, user.id)
    can_manage = me.get("role") == "admin" or _should_be_admin(user, g, me)
    if not (can_manage or me.get("role") in STAFF_MEMBER_ROLES or user.is_staff):
        raise ChatError("forbidden", "Only teachers and admins can see member details.", 403)
    m = db().members.find_one({"groupId": group_id, "userId": user_id})
    if not m:
        raise ChatError("not_member", "That person isn't in this group.", 404)
    person = db().users.find_one({"_id": user_id}) or {}
    mine = {x["groupId"]: x for x in db().members.find({"userId": user.id, "removed": {"$ne": True}},
                                                         projection={"groupId": 1, "role": 1})}
    groups = []
    theirs = list(db().members.find({"userId": user_id, "removed": {"$ne": True}},
                                    projection={"groupId": 1, "role": 1, "restrictedUntil": 1}))
    titles = {x["_id"]: x for x in db().groups.find({"_id": {"$in": [t["groupId"] for t in theirs]}, "type": {"$ne": "direct"}},
                                                    projection={"title": 1, "type": 1, "memberCount": 1})}
    for t in theirs:
        gd = titles.get(t["groupId"])
        if not gd:
            continue
        groups.append({"id": gd["_id"], "title": gd.get("title") or "", "type": gd.get("type", "chat"),
                       "memberCount": int(gd.get("memberCount") or 0), "role": t.get("role", "student"),
                       "iAmIn": gd["_id"] in mine, "iAmAdmin": (mine.get(gd["_id"]) or {}).get("role") == "admin",
                       "pausedUntil": int(t.get("restrictedUntil") or 0)})
    groups.sort(key=lambda x: (x["id"] != group_id, x["title"].lower()))
    last = db().messages.find_one({"groupId": group_id, "senderId": user_id, "type": {"$ne": "system"}},
                                  sort=[("seq", -1)], projection={"createdAt": 1})
    return {
        "userId": user_id, "name": m.get("name") or person.get("name") or "", "role": m.get("role", "student"),
        "rollNo": m.get("rollNo"), "avatar": avatar_of(m.get("role"), person.get("avatar")),
        "coaching": person.get("coaching") or "", "batches": person.get("batches") or [],
        "usesApp": bool(person.get("fcmTokens")), "online": presence.is_online(user_id),
        "joinedAt": int(m.get("joinedAt") or 0), "sources": m.get("sources") or [],
        "isCreator": user_id == g.get("createdBy"), "removed": bool(m.get("removed")), "left": bool(m.get("left")),
        "restrictedUntil": int(m.get("restrictedUntil") or 0),
        "messageCount": db().messages.count_documents({"groupId": group_id, "senderId": user_id, "type": {"$ne": "system"},
                                                       "deletedAt": {"$exists": False}}),
        "lastMessageAt": int((last or {}).get("createdAt") or 0),
        "groups": groups,
        "canManage": can_manage,
        # A student's numbers, for their teachers and admins (never a teacher's own number).
        "phone": (person.get("phone") or "") if m.get("role", "student") == "student" else "",
        "parentPhone": (person.get("parentPhone") or "") if m.get("role", "student") == "student" else "",
    }


def restrict_everywhere(user: ChatUser, user_id: str, minutes: int) -> int:
    """Pauses a student in every group where I am an admin and they are a member. Returns how many."""
    mine = [m["groupId"] for m in db().members.find({"userId": user.id, "role": "admin", "removed": {"$ne": True}},
                                                     projection={"groupId": 1})]
    theirs = [m["groupId"] for m in db().members.find({"userId": user_id, "groupId": {"$in": mine}, "role": "student",
                                                       "removed": {"$ne": True}}, projection={"groupId": 1})]
    for gid in theirs:
        restrict_member(user, gid, user_id, minutes)
    return len(theirs)


def set_member_role(user: ChatUser, group_id: str, user_id: str, role: str) -> None:
    g, me = require_group_admin(user, group_id)
    if role not in MEMBER_ROLES:
        raise ChatError("bad_role", "Role is student, teacher or admin.")
    target = membership(group_id, user_id)
    if user_id == g.get("createdBy") and role != "admin":
        raise ChatError("forbidden", "The group's creator stays an admin.", 403)
    if role in STAFF_MEMBER_ROLES and not _is_teacher(user_id):
        raise ChatError("teachers_only", "Only teachers can be admins.", 403)
    if target.get("role") == role:
        return
    db().members.update_one({"_id": target["_id"]}, {"$set": {"role": role}})
    _emit("group_updated", {"groupId": group_id}, user_room(user_id))
    who = _who(user, me)
    if role == "admin":
        system_message(group_id, f"{who} made {target.get('name') or 'a teacher'} an admin")
    elif target.get("role") == "admin":
        system_message(group_id, f"{target.get('name') or 'A teacher'} is no longer an admin")


def restrict_member(user: ChatUser, group_id: str, user_id: str, minutes: int) -> int:
    """Pauses a student's messages in this group; the student is told why and for how long."""
    g, _ = require_group_admin(user, group_id)
    target = membership(group_id, user_id)
    if target.get("role") != "student":
        raise ChatError("forbidden", "Only students can be muted.", 403)
    minutes = max(0, min(int(minutes or 0), 7 * 24 * 60))
    until = now_ms() + minutes * 60_000 if minutes else 0
    db().members.update_one({"_id": target["_id"]}, {"$set": {"restrictedUntil": until}})
    _emit("group_updated", {"groupId": group_id}, user_room(user_id))
    title = g.get("title", "")
    if minutes:
        hours = minutes // 60
        span = f"{hours} hour{'s' if hours != 1 else ''}" if minutes % 60 == 0 else f"{minutes} minutes"
        body = f"A teacher paused your messages in {title} for {span}. You can still read the group."
    else:
        body = f"You can send messages in {title} again."
    push.send_to_users([user_id], {"type": "chat_admin", "groupId": group_id, "groupTitle": title,
                                   "title": title, "body": body, "text": body})
    return until


def list_members(user: ChatUser, group_id: str) -> list[dict]:
    g, _ = require_group_admin(user, group_id)
    docs = list(db().members.find({"groupId": group_id, "removed": {"$ne": True}}))
    avatars = _avatars(m["userId"] for m in docs)
    cards = _contact_cards(m["userId"] for m in docs)
    out = []
    for m in docs:
        card = cards.get(m["userId"]) or {}
        out.append({"userId": m["userId"], "name": m.get("name") or card.get("name") or "", "role": m.get("role"),
                    "phone": card.get("phone", "") if m.get("role", "student") == "student" else "",
                    "rollNo": m.get("rollNo"), "restrictedUntil": m.get("restrictedUntil") or 0,
                    "online": presence.is_online(m["userId"]), "sources": m.get("sources") or [],
                    "isCreator": m["userId"] == g.get("createdBy"),
                    "avatar": avatar_of(m.get("role"), avatars.get(m["userId"]))})
    order = {"admin": 0, "teacher": 1, "student": 2}
    out.sort(key=lambda x: (order.get(x["role"], 3), (x["name"] or "").lower()))
    return out


def sources(user: ChatUser, group_id: str) -> list[dict]:
    """How the students came in, with counts: "From Spartans (34)", "Batch Titan Maths (20)"."""
    require_group_admin(user, group_id)
    counts: dict[str, int] = {}
    for m in db().members.find({"groupId": group_id, "removed": {"$ne": True}, "role": "student"},
                               projection={"sources": 1}):
        for s in (m.get("sources") or ["manual"]):
            counts[s] = counts.get(s, 0) + 1
    out = []
    for s, n in counts.items():
        item = {"source": s, "count": n, "kind": s.split(":", 1)[0], "value": s.split(":", 1)[1] if ":" in s else "",
                "title": ""}
        if s.startswith("group:"):
            src = db().groups.find_one({"_id": s[6:]}, projection={"title": 1}) or {}
            item["title"] = src.get("title") or "A deleted group"
        out.append(item)
    out.sort(key=lambda x: -x["count"])
    return out


def remove_source(user: ChatUser, group_id: str, source: str) -> dict:
    """Undo one way of adding: students who came only that way leave; others stay."""
    _, me = require_group_admin(user, group_id)
    removed = kept = 0
    for m in list(db().members.find({"groupId": group_id, "removed": {"$ne": True}, "role": "student",
                                     "sources": source})):
        rest = [s for s in (m.get("sources") or []) if s != source]
        db().members.update_one({"_id": m["_id"]}, {"$pull": {"sources": source}})
        if rest:
            kept += 1
        elif _remove(group_id, m["userId"]):
            removed += 1
    if removed:
        label = _source_label(source)
        system_message(group_id, f"{_who(user, me)} removed {removed} student{'s' if removed != 1 else ''}"
                                 + (f" added {label}" if label else ""))
    return {"removed": removed, "kept": kept}


def import_group(user: ChatUser, group_id: str, from_group_id: str) -> int:
    """Adds every student of another group (e.g. Spartans into Titan), marked as "from Spartans"."""
    _, me = require_group_admin(user, group_id)
    if from_group_id == group_id:
        raise ChatError("same_group", "Pick a different group.")
    src = group_or_404(from_group_id)
    if src.get("type") == "direct":
        raise ChatError("bad_group", "Pick a group, not a direct chat.")
    membership(from_group_id, user.id)                 # only from groups you are in yourself
    students = [{"userId": m["userId"], "name": m.get("name") or "", "role": "student", "rollNo": m.get("rollNo")}
                for m in db().members.find({"groupId": from_group_id, "removed": {"$ne": True}, "role": "student"})]
    added = add_members(group_id, students, source=f"group:{from_group_id}", added_by=_who(user, me))
    system_message(group_id, f"{_who(user, me)} added {added} student{'s' if added != 1 else ''} "
                             f"from {src.get('title', 'another group')}")
    return added


def candidates(user: ChatUser, group_id: str) -> list[dict]:
    """Students the group is made for who are not in it (new admissions, auto-add off, or not yet
    added): the "New students" list. People an admin removed are left out."""
    g, _ = require_group_admin(user, group_id)
    match = _match(g)
    if not match:
        return []
    coachings = [c for c in _as_list(match.get("coaching")) if c]
    batches = [b for b in _as_list(match.get("batch")) if b]
    q: dict = {"role": "student"}
    if coachings:
        q["coaching"] = {"$in": coachings}
    if batches and "*" not in batches:
        q["batches"] = {"$in": batches}
    in_group = {m["userId"] for m in db().members.find({"groupId": group_id}, projection={"userId": 1})}
    out = []
    for u in db().users.find(q, projection={"name": 1, "avatar": 1, "lastSeenAt": 1, "phone": 1}).limit(5000):
        if u["_id"] in in_group:
            continue
        out.append({"id": u["_id"], "name": u.get("name") or "", "role": "student", "phone": u.get("phone") or "",
                    "avatar": avatar_of("student", u.get("avatar")), "usesApp": bool(u.get("lastSeenAt"))})
    out.sort(key=lambda x: (not x["usesApp"], not x["name"], (x["name"] or "").lower()))   # nameless last
    return out


def admin_groups_of(user: ChatUser) -> list[dict]:
    """Groups where this person is an admin (to pick from when adding another group's students)."""
    gids = [m["groupId"] for m in db().members.find({"userId": user.id, "removed": {"$ne": True}}, projection={"groupId": 1})]
    out = []
    for g in db().groups.find({"_id": {"$in": gids}, "type": {"$ne": "direct"}}):
        students = db().members.count_documents({"groupId": g["_id"], "removed": {"$ne": True}, "role": "student"})
        out.append({"id": g["_id"], "title": g.get("title", ""), "students": students})
    out.sort(key=lambda x: x["title"].lower())
    return out


# ── people search (teachers) ─────────────────────────────────────────────────────────────────

def search_users(query: str, coaching: Optional[str] = None, role: Optional[str] = None, limit: int = 30,
                 batches: Optional[list[str]] = None, coachings: Optional[list[str]] = None,
                 students_from: Optional[list[str]] = None) -> list[dict]:
    """People who have opened the app since the chat came, or are in a copied coaching list
    (with the batch flags from their meta), by name / id, batch and coaching. Indexed."""
    q: dict = {}
    text = (query or "").strip()
    if text:
        q["$or"] = [{"_id": text}, {"name": {"$regex": re.escape(text), "$options": "i"}}]
        digits = re.sub(r"\D", "", text)
        if len(digits) >= 4:                           # a phone number (or part of one), typed any way
            key = re.escape(digits[-10:])
            q["$or"] += [{"phoneDigits": {"$regex": key}}, {"parentDigits": {"$regex": key}}, {"phone": {"$regex": key}}]
    wanted = [c.strip().lower() for c in (coachings or []) if c and c.strip()]
    if coaching:
        wanted.append(coaching.strip().lower())
    if wanted:
        q["coaching"] = {"$in": list(dict.fromkeys(wanted))}
    if batches:
        q["batches"] = {"$in": [b for b in batches if b]}
    if students_from and not wanted:
        # Searching by name / phone / id: students only from the admin's own coachings (their
        # numbers are in the results); teachers from anywhere, to add a visiting teacher.
        allowed = list(dict.fromkeys(c.strip().lower() for c in students_from if c and c.strip()))
        q["$and"] = [{"$or": [{"role": {"$in": ["teacher", "admin", "faculty", "mentor"]}}, {"coaching": {"$in": allowed}}]}]
    if role == "staff":
        q["role"] = {"$in": ["teacher", "admin", "faculty", "mentor"]}
    elif role:
        q["role"] = role
    out = []
    for u in db().users.find(q, projection={"name": 1, "role": 1, "coaching": 1, "batches": 1, "avatar": 1, "phone": 1}) \
            .sort("name", 1).limit(max(1, min(limit, 2000))):
        r = u.get("role") or "student"
        out.append({"id": u["_id"], "name": u.get("name") or "", "role": r,
                    "phone": (u.get("phone") or "") if r.lower() not in STAFF_ROLES else "",
                    "coaching": u.get("coaching"), "batches": u.get("batches") or [],
                    "avatar": avatar_of("teacher" if r.lower() in STAFF_ROLES else "student", u.get("avatar"))})
    out.sort(key=lambda x: (not x["name"], x["name"].lower()))           # people without a name last
    return out


def known_batches(coaching: Optional[str]) -> list[str]:
    """Batches seen among this coaching's chat users, to pick from when making a group."""
    q = {"coaching": coaching.strip().lower()} if coaching else {}
    return sorted(b for b in db().users.distinct("batches", q) if b)
