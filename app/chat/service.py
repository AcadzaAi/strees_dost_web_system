"""Chat rules in one place, used by both the socket events and the REST API.

Delivery model: every message gets the group's next `seq`. A phone that remembers the last seq it
has for a group asks for "everything after seq N" when it reconnects, so nothing is ever missed.
The app's own `clientId` makes resending safe: the same clientId never creates a second message.

Ticks: sent = the server stored it (ack); delivered / read = every other member's
lastDeliveredSeq / lastReadSeq has reached it, broadcast as one `receipts` event per group.
"""
from __future__ import annotations

import logging
import secrets
import threading
import time
from collections import deque
from typing import Any, Optional

from pymongo.errors import DuplicateKeyError

from . import moderation, presence, push, settings
from .auth import ChatUser
from .mongo import db, next_seq

log = logging.getLogger(__name__)

NS = "/chat"
GROUP_TYPES = ("announcement", "chat")
STAFF_MEMBER_ROLES = ("teacher", "admin")


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


def message_out(m: dict) -> dict:
    deleted = bool(m.get("deletedAt"))
    return {
        "id": m["_id"],
        "groupId": m["groupId"],
        "seq": m["seq"],
        "clientId": m.get("clientId"),
        "sender": {
            "id": m["senderId"],
            "name": m.get("senderName", ""),
            "role": m.get("senderRole", "student"),
            "rollNo": m.get("rollNo"),
            "label": sender_label(m.get("senderRole", "student"), m.get("rollNo")),
        },
        "type": m.get("type", "text"),
        "text": "" if deleted else m.get("text", ""),
        "replyTo": None if deleted else m.get("replyTo"),
        "createdAt": m["createdAt"],
        "deleted": deleted,
    }


def group_out(g: dict, member: Optional[dict] = None) -> dict:
    last_seq = int(g.get("lastSeq", 0))
    read = int((member or {}).get("lastReadSeq", 0))
    return {
        "id": g["_id"],
        "title": g.get("title", ""),
        "description": g.get("description", ""),
        "type": g.get("type", "chat"),
        "coaching": g.get("coaching"),
        "batch": g.get("batch"),
        "lastSeq": last_seq,
        "lastMessage": g.get("lastMessage"),
        "memberCount": int(g.get("memberCount", 0)),
        "myRole": (member or {}).get("role", "student"),
        "canPost": _can_post(g, member) if member else False,
        "muted": bool((member or {}).get("muted")),
        "unread": max(0, last_seq - read),
        "lastReadSeq": read,
        "receipts": {"deliveredSeq": int(g.get("deliveredSeq", 0)), "readSeq": int(g.get("readSeq", 0))},
        "autoJoin": bool(g.get("autoJoin")),
        "updatedAt": int((g.get("lastMessage") or {}).get("createdAt") or g.get("createdAt") or 0),
    }


# ── membership ───────────────────────────────────────────────────────────────────────────────

def _member_role_for(user: ChatUser) -> str:
    """A teacher shows as "Teacher" even when they are also a chat admin (admin rights come from
    the admin list, not from this label)."""
    if user.role.lower() == "student" and not user.is_admin:
        return "student"
    if user.role.lower() in ("teacher", "faculty", "mentor"):
        return "teacher"
    return "admin" if user.is_admin else "teacher"


def sync_auto_groups(user: ChatUser) -> None:
    """Puts the student in every auto-join group of their coaching and batch (once; an admin's
    removal sticks), and fills in their name where an admin added them by id only."""
    db().members.update_many({"userId": user.id, "name": {"$in": [None, ""]}}, {"$set": {"name": user.name}})
    query: dict = {"autoJoin.coaching": user.coaching}
    batches = list(user.batches) + ["*"]
    query["autoJoin.batch"] = {"$in": batches}
    for g in db().groups.find(query, projection={"_id": 1}):
        try:
            db().members.insert_one({
                "groupId": g["_id"], "userId": user.id, "role": _member_role_for(user),
                "name": user.name, "rollNo": None, "joinedAt": now_ms(), "lastReadSeq": 0,
                "lastDeliveredSeq": 0, "muted": False, "removed": False,
            })
            db().groups.update_one({"_id": g["_id"]}, {"$inc": {"memberCount": 1}})
        except DuplicateKeyError:
            pass


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


def _can_post(g: dict, member: Optional[dict]) -> bool:
    if not member:
        return False
    if (member.get("restrictedUntil") or 0) > now_ms():
        return False
    if g.get("type") == "announcement":
        return member.get("role") in STAFF_MEMBER_ROLES
    return True


def groups_for(user: ChatUser) -> list[dict]:
    sync_auto_groups(user)
    members = {m["groupId"]: m for m in db().members.find({"userId": user.id, "removed": {"$ne": True}})}
    if not members:
        return []
    groups = db().groups.find({"_id": {"$in": list(members)}})
    out = [group_out(g, members[g["_id"]]) for g in groups]
    return sorted(out, key=lambda x: x["updatedAt"], reverse=True)


def group_ids_for(user_id: str) -> list[str]:
    return [m["groupId"] for m in db().members.find({"userId": user_id, "removed": {"$ne": True}}, projection={"groupId": 1})]


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


def _strike(user: ChatUser, group_id: str) -> None:
    """Too many blocked messages in a short time: a short automatic mute in that group."""
    t = now_ms()
    since = t - settings.STRIKE_WINDOW_S * 1000
    db().users.update_one({"_id": user.id}, {"$push": {"strikes": {"$each": [t], "$slice": -20}}})
    doc = db().users.find_one({"_id": user.id}, projection={"strikes": 1}) or {}
    recent = [s for s in doc.get("strikes", []) if s >= since]
    if len(recent) >= settings.STRIKES_BEFORE_MUTE:
        until = t + settings.AUTO_MUTE_MIN * 60_000
        db().members.update_one({"groupId": group_id, "userId": user.id}, {"$set": {"restrictedUntil": until}})


def send_message(user: ChatUser, group_id: str, client_id: str, text: str,
                 reply_to_seq: Optional[int] = None, origin_sid: Optional[str] = None) -> dict:
    text = (text or "").strip()
    client_id = (client_id or "").strip()[:64] or secrets.token_hex(8)
    if not text:
        raise ChatError("empty", "Type a message first.")
    if len(text) > settings.MAX_TEXT_LENGTH:
        raise ChatError("too_long", f"Messages can be up to {settings.MAX_TEXT_LENGTH} characters.")

    g = group_or_404(group_id)
    member = membership(group_id, user.id)

    existing = db().messages.find_one({"groupId": group_id, "clientId": client_id})
    if existing:                                   # a resend: the same message, not a new one
        return message_out(existing)

    if not _can_post(g, member):
        if (member.get("restrictedUntil") or 0) > now_ms():
            raise ChatError("restricted", "You can't send messages in this group for a while.", 403)
        raise ChatError("read_only", "Only teachers can post in announcements.", 403)
    if not _rate_ok(user.id):
        raise ChatError("slow_down", "You're sending messages too fast.", 429)

    is_staff = member.get("role") in STAFF_MEMBER_ROLES or user.is_staff
    verdict = moderation.check(text, is_staff=is_staff)
    if not verdict.allowed:
        db().moderation.insert_one({
            "kind": "blocked", "groupId": group_id, "userId": user.id, "name": user.name,
            "text": text, "reasons": verdict.reasons, "createdAt": now_ms(),
        })
        _strike(user, group_id)
        raise ChatError("blocked", verdict.message, 422)

    reply = None
    if reply_to_seq:
        r = db().messages.find_one({"groupId": group_id, "seq": int(reply_to_seq)})
        if r and not r.get("deletedAt"):
            reply = {"seq": r["seq"], "senderName": r.get("senderName", ""), "text": (r.get("text") or "")[:160]}

    seq = next_seq(group_id)
    doc = {
        "_id": f"{group_id}-{seq}",
        "groupId": group_id, "seq": seq, "clientId": client_id,
        "senderId": user.id, "senderName": member.get("name") or user.name,
        "senderRole": member.get("role", "student"), "rollNo": member.get("rollNo"),
        "type": "text", "text": text, "replyTo": reply, "createdAt": now_ms(),
    }
    try:
        db().messages.insert_one(doc)
    except DuplicateKeyError:                      # two resends raced: return the one that won
        won = db().messages.find_one({"groupId": group_id, "clientId": client_id})
        if won:
            return message_out(won)
        raise

    shown = display_name(doc["senderRole"], doc["senderName"], doc.get("rollNo"))
    last = {"seq": seq, "text": text[:160], "senderName": shown, "senderId": user.id, "createdAt": doc["createdAt"]}
    db().groups.update_one({"_id": group_id}, {"$set": {"lastMessage": last}})
    db().members.update_one({"_id": member["_id"]}, {"$max": {"lastReadSeq": seq, "lastDeliveredSeq": seq}})

    out = message_out(doc)
    _emit("message", out, group_room(group_id))
    if verdict.alert:
        db().moderation.insert_one({"kind": "alert", "groupId": group_id, "userId": user.id, "name": user.name,
                                    "text": text, "reasons": ["self-harm"], "createdAt": now_ms(), "seq": seq})
    _notify(g, doc)
    return out


def _notify(g: dict, doc: dict) -> None:
    recipients = [
        m["userId"] for m in db().members.find(
            {"groupId": g["_id"], "removed": {"$ne": True}, "muted": {"$ne": True}, "userId": {"$ne": doc["senderId"]}},
            projection={"userId": 1},
        )
        if not presence.is_viewing(m["userId"], g["_id"])
    ]
    if not recipients:
        return
    label = sender_label(doc["senderRole"], doc.get("rollNo"))
    shown = display_name(doc["senderRole"], doc["senderName"], doc.get("rollNo"))
    push.send_to_users(recipients, {
        "type": "chat_message",
        "groupId": g["_id"],
        "groupTitle": g.get("title", ""),
        "groupType": g.get("type", "chat"),
        "seq": str(doc["seq"]),
        "messageId": doc["_id"],
        "senderId": doc["senderId"],
        "senderName": shown,
        "senderLabel": label,
        "text": doc["text"][:300],
        "createdAt": str(doc["createdAt"]),
        "title": g.get("title", ""),
        "body": f"{shown}: {doc['text'][:200]}",
    })


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
    return {"messages": [message_out(m) for m in items], "hasMore": has_more}


_receipt_at: dict[str, float] = {}


def _broadcast_receipts(group_id: str) -> None:
    """One summary per group, at most every 1.5 s: the lowest delivered / read seq of all members."""
    t = time.time()
    if t - _receipt_at.get(group_id, 0) < 1.5:
        return
    _receipt_at[group_id] = t
    agg = list(db().members.aggregate([
        {"$match": {"groupId": group_id, "removed": {"$ne": True}}},
        {"$group": {"_id": None, "d": {"$min": "$lastDeliveredSeq"}, "r": {"$min": "$lastReadSeq"}}},
    ]))
    if not agg:
        return
    d, r = int(agg[0].get("d") or 0), int(agg[0].get("r") or 0)
    db().groups.update_one({"_id": group_id}, {"$set": {"deliveredSeq": d, "readSeq": r}})
    _emit("receipts", {"groupId": group_id, "deliveredSeq": d, "readSeq": r}, group_room(group_id))


def mark_read(user: ChatUser, group_id: str, seq: int) -> int:
    m = membership(group_id, user.id)
    g = group_or_404(group_id)
    seq = max(0, min(int(seq), int(g.get("lastSeq", 0))))
    db().members.update_one({"_id": m["_id"]}, {"$max": {"lastReadSeq": seq, "lastDeliveredSeq": seq}})
    _broadcast_receipts(group_id)
    return seq


def mark_delivered(user: ChatUser, group_id: str, seq: int) -> None:
    m = membership(group_id, user.id)
    db().members.update_one({"_id": m["_id"]}, {"$max": {"lastDeliveredSeq": int(seq)}})
    _broadcast_receipts(group_id)


def delete_message(user: ChatUser, group_id: str, seq: int) -> dict:
    m = membership(group_id, user.id)
    msg = db().messages.find_one({"groupId": group_id, "seq": int(seq)})
    if not msg:
        raise ChatError("no_message", "That message is gone.", 404)
    own_in_time = msg["senderId"] == user.id and now_ms() - msg["createdAt"] <= settings.DELETE_WINDOW_MIN * 60_000
    if not (own_in_time or m.get("role") in STAFF_MEMBER_ROLES or user.is_admin):
        raise ChatError("forbidden", "You can't delete this message.", 403)
    db().messages.update_one({"_id": msg["_id"]}, {"$set": {"deletedAt": now_ms(), "deletedBy": user.id}})
    payload = {"groupId": group_id, "seq": int(seq), "id": msg["_id"]}
    _emit("message_deleted", payload, group_room(group_id))
    return payload


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


def register_device(user: ChatUser, token: str, platform: str) -> None:
    token = (token or "").strip()
    if not token:
        raise ChatError("no_token", "Missing FCM token.")
    # A phone that changed accounts sends its token to the new account only.
    db().users.update_many({"fcmTokens.token": token}, {"$pull": {"fcmTokens": {"token": token}}})
    db().users.update_one({"_id": user.id}, {"$push": {"fcmTokens": {
        "$each": [{"token": token, "platform": (platform or "android")[:16], "updatedAt": now_ms()}],
        "$slice": -5,                              # last 5 phones
    }}}, upsert=True)


def unregister_device(user: ChatUser, token: str) -> None:
    db().users.update_one({"_id": user.id}, {"$pull": {"fcmTokens": {"token": (token or "").strip()}}})


# ── admin ────────────────────────────────────────────────────────────────────────────────────

def _join_live(user_id: str, group_id: str, join: bool) -> None:
    """Adds / removes a connected user's phones to the group's live room right away."""
    from ..extensions import socketio
    from . import presence as p
    with p._lock:  # noqa: SLF001
        sids = list(p._user_sids.get(user_id, ()))  # noqa: SLF001
    for sid in sids:
        if join:
            socketio.server.enter_room(sid, group_room(group_id), namespace=NS)
        else:
            socketio.server.leave_room(sid, group_room(group_id), namespace=NS)


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
    batch = many if many else (single or None)
    gid = "g_" + secrets.token_hex(8)
    doc = {
        "_id": gid, "title": title[:80], "description": (body.get("description") or "")[:300],
        "type": gtype, "coaching": coaching, "batch": batch,
        # Auto-join: every student of this coaching (and batch, or "*" for all) joins on their own.
        "autoJoin": {"coaching": coaching, "batch": batch or "*"} if body.get("autoJoin") else None,
        "createdBy": admin.id, "createdAt": now_ms(), "lastSeq": 0, "lastMessage": None,
        "memberCount": 0, "deliveredSeq": 0, "readSeq": 0,
    }
    db().groups.insert_one(doc)
    add_members(gid, [{"userId": admin.id, "name": admin.name, "role": _member_role_for(admin)}])
    return group_out(db().groups.find_one({"_id": gid}))


def update_group(group_id: str, body: dict) -> dict:
    group_or_404(group_id)
    changes = {k: body[k] for k in ("title", "description") if isinstance(body.get(k), str)}
    if body.get("type") in GROUP_TYPES:
        changes["type"] = body["type"]
    if isinstance(body.get("autoJoin"), bool):
        g0 = group_or_404(group_id)
        changes["autoJoin"] = ({"coaching": g0.get("coaching"), "batch": g0.get("batch") or "*"}
                               if body["autoJoin"] else None)
    if changes:
        db().groups.update_one({"_id": group_id}, {"$set": changes})
    g = db().groups.find_one({"_id": group_id})
    _emit("group_updated", group_out(g), group_room(group_id))
    return group_out(g)


def add_members(group_id: str, members: list[dict]) -> int:
    group_or_404(group_id)
    added = 0
    for m in members:
        uid = str(m.get("userId") or "").strip()
        if not uid:
            continue
        role = m.get("role") if m.get("role") in ("student", "teacher", "admin") else "student"
        changes: dict = {"role": role, "removed": False}
        if (m.get("name") or "").strip():
            changes["name"] = m["name"].strip()
        if m.get("rollNo") not in (None, ""):
            changes["rollNo"] = str(m["rollNo"]).strip()
        res = db().members.update_one(
            {"groupId": group_id, "userId": uid},
            {"$set": changes,
             "$setOnInsert": {"joinedAt": now_ms(), "lastReadSeq": 0, "lastDeliveredSeq": 0, "muted": False}},
            upsert=True,
        )
        if res.upserted_id is not None:
            added += 1
        _join_live(uid, group_id, True)
        _emit("group_added", {"groupId": group_id}, user_room(uid))
    if added:
        db().groups.update_one({"_id": group_id}, {"$inc": {"memberCount": added}})
    return added


def remove_member(group_id: str, user_id: str) -> None:
    res = db().members.update_one({"groupId": group_id, "userId": user_id, "removed": {"$ne": True}},
                                  {"$set": {"removed": True}})
    if res.modified_count:
        db().groups.update_one({"_id": group_id}, {"$inc": {"memberCount": -1}})
    _emit("group_removed", {"groupId": group_id}, user_room(user_id))
    _join_live(user_id, group_id, False)


def restrict_member(group_id: str, user_id: str, minutes: int) -> None:
    until = now_ms() + max(0, int(minutes)) * 60_000 if minutes else 0
    db().members.update_one({"groupId": group_id, "userId": user_id}, {"$set": {"restrictedUntil": until}})


def list_members(group_id: str) -> list[dict]:
    out = []
    for m in db().members.find({"groupId": group_id, "removed": {"$ne": True}}).sort("role", 1):
        out.append({"userId": m["userId"], "name": m.get("name"), "role": m.get("role"),
                    "rollNo": m.get("rollNo"), "restrictedUntil": m.get("restrictedUntil") or 0,
                    "online": presence.is_online(m["userId"])})
    return out


def search_users(query: str, coaching: Optional[str] = None, role: Optional[str] = None, limit: int = 30) -> list[dict]:
    """People who have opened the chat at least once, by name or Acadza id (for adding to groups)."""
    import re
    q: dict = {}
    text = (query or "").strip()
    if text:
        q["$or"] = [{"_id": text}, {"name": {"$regex": re.escape(text), "$options": "i"}}]
    if coaching:
        q["coaching"] = coaching.strip().lower()
    if role == "staff":
        q["role"] = {"$in": ["teacher", "admin", "faculty", "mentor"]}
    elif role:
        q["role"] = role
    out = []
    for u in db().users.find(q, projection={"name": 1, "role": 1, "coaching": 1, "batches": 1}).sort("name", 1).limit(max(1, min(limit, 100))):
        out.append({"id": u["_id"], "name": u.get("name") or "", "role": u.get("role") or "student",
                    "coaching": u.get("coaching"), "batches": u.get("batches") or []})
    return out


def known_batches(coaching: Optional[str]) -> list[str]:
    """Batches seen among this coaching's chat users, to pick from when making a group."""
    q = {"coaching": coaching.strip().lower()} if coaching else {}
    return sorted(b for b in db().users.distinct("batches", q) if b)
