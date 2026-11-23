"""MongoDB collections and indexes for the chat.

Collections (database CHAT_DB_NAME):
  users        _id = Acadza user id; name, role, coaching, batches, fcmTokens, strikes
  groups       one per chat; type "announcement" (only staff post) or "chat"; lastSeq, lastMessage
  members      one per (group, user); role student|teacher|admin, rollNo, lastReadSeq, muted
  messages     one per message; seq is a per-group counter, so "everything after seq N" is exact
  reports      messages students reported
  moderation   messages that were blocked, for admins to review
  chat_admins  extra admins: { _id: <acadza id> }
  settings     { _id: "moderation", bannedWords, competitors, ... } editable without a redeploy
"""
from __future__ import annotations

import logging
from typing import Optional

from pymongo import ASCENDING, DESCENDING, MongoClient, ReturnDocument
from pymongo.database import Database

from . import settings

log = logging.getLogger(__name__)

_client: Optional[MongoClient] = None
_db: Optional[Database] = None


def db() -> Database:
    global _client, _db
    if _db is None:
        _client = MongoClient(
            settings.MONGODB_URI,
            appname="acadza-chat",
            serverSelectionTimeoutMS=8000,
            connectTimeoutMS=8000,
            retryWrites=True,
            tz_aware=False,
            # A few connections kept open and ready: no new TLS handshake (several round trips)
            # in front of the first message after a quiet spell.
            minPoolSize=4,
            maxPoolSize=50,
        )
        _db = _client[settings.CHAT_DB_NAME]
    return _db


def warm() -> None:
    """Opens the connections at startup and keeps them used, so no message waits for one."""
    def loop() -> None:
        import time
        while True:
            try:
                db().command("ping")
            except Exception:  # noqa: BLE001
                log.warning("chat: MongoDB ping failed")
            time.sleep(120)
    from ..extensions import socketio
    socketio.start_background_task(loop)


def use_database(database: Database) -> None:
    """Tests: point the chat at another database (e.g. mongomock)."""
    global _db
    _db = database


def ensure_indexes() -> None:
    d = db()
    d.messages.create_index([("groupId", ASCENDING), ("seq", DESCENDING)], unique=True)
    # The same clientId twice (a resend after a dropped connection) never makes a second message.
    d.messages.create_index([("groupId", ASCENDING), ("clientId", ASCENDING)], unique=True)
    d.members.create_index([("groupId", ASCENDING), ("userId", ASCENDING)], unique=True)
    d.messages.create_index([("groupId", ASCENDING), ("reactedAt", ASCENDING)], sparse=True)
    d.media_pending.create_index([("at", ASCENDING)])
    d.members.create_index([("userId", ASCENDING), ("removed", ASCENDING)])
    d.groups.create_index([("autoJoin.coaching", ASCENDING), ("autoJoin.batch", ASCENDING)])
    d.groups.create_index([("coaching", ASCENDING)])
    # Admin "students of a batch": batch flags and coaching of everyone who opened the app.
    d.users.create_index([("batches", ASCENDING)])
    d.users.create_index([("coaching", ASCENDING), ("role", ASCENDING)])
    d.reports.create_index([("createdAt", DESCENDING)])
    d.moderation.create_index([("createdAt", DESCENDING)])
    log.info("chat: indexes ready")


def next_seq(group_id) -> int:
    """The group's next message number, atomically."""
    g = db().groups.find_one_and_update(
        {"_id": group_id}, {"$inc": {"lastSeq": 1}}, projection={"lastSeq": 1},
        return_document=ReturnDocument.AFTER,
    )
    if g is None:
        raise LookupError("group not found")
    return int(g["lastSeq"])
