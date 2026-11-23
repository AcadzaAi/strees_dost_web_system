"""Live chat over Socket.IO, namespace /chat (the stress test's default namespace is untouched).

Connect with auth: {"token": "<Acadza token>"}. The phone then joins a room per group it is in
plus its own user room.

App → server (all reply through the ack callback):
  send      {groupId, clientId, text, replyToSeq?}   → {ok, message} | {ok: false, error, message}
  read      {groupId, seq}
  delivered {groupId, seq}
  typing    {groupId, typing}
  viewing   {groupId | null}     the chat on screen: no notifications for it
Server → app:
  message, message_deleted, receipts, typing, group_added, group_removed, group_updated
"""
from __future__ import annotations

import logging

from flask import request
from flask_socketio import ConnectionRefusedError, emit, join_room

from ..extensions import socketio
from . import presence, service
from .auth import AuthError, verify_token
from .service import NS, ChatError

log = logging.getLogger(__name__)

_users: dict[str, object] = {}       # sid -> ChatUser


def _user():
    u = _users.get(request.sid)
    if u is None:
        raise ChatError("unauthorized", "Not signed in.", 401)
    return u


def _safe(fn):
    def wrapper(data=None):
        try:
            return fn(data or {})
        except ChatError as err:
            return err.to_dict()
        except Exception:  # noqa: BLE001
            log.exception("chat socket: %s failed", fn.__name__)
            return {"ok": False, "error": "server", "message": "Something went wrong. Try again."}
    wrapper.__name__ = fn.__name__
    return wrapper


@socketio.on("connect", namespace=NS)
def on_connect(auth=None):
    token = (auth or {}).get("token") if isinstance(auth, dict) else None
    token = token or request.args.get("token") or request.headers.get("Authorization", "")
    try:
        user = verify_token(token)
    except AuthError as exc:
        raise ConnectionRefusedError({"error": "unauthorized", "reason": str(exc)})
    _users[request.sid] = user
    presence.connected(request.sid, user.id)
    service.sync_auto_groups(user)
    join_room(service.user_room(user.id))
    for gid in service.group_ids_for(user.id):
        join_room(service.group_room(gid))
    emit("ready", {"userId": user.id})


@socketio.on("disconnect", namespace=NS)
def on_disconnect(*_args):
    _users.pop(request.sid, None)
    presence.disconnected(request.sid)


@socketio.on("send", namespace=NS)
@_safe
def on_send(data):
    msg = service.send_message(_user(), str(data.get("groupId", "")), str(data.get("clientId", "")),
                               str(data.get("text", "")), data.get("replyToSeq"), origin_sid=request.sid,
                               media_in=data.get("media"))
    return {"ok": True, "message": msg}


@socketio.on("edit", namespace=NS)
@_safe
def on_edit(data):
    msg = service.edit_message(_user(), str(data.get("groupId", "")), int(data.get("seq", 0)), str(data.get("text", "")))
    return {"ok": True, "message": msg}


@socketio.on("read", namespace=NS)
@_safe
def on_read(data):
    return {"ok": True, "readSeq": service.mark_read(_user(), str(data.get("groupId", "")), int(data.get("seq", 0)))}


@socketio.on("delivered", namespace=NS)
@_safe
def on_delivered(data):
    service.mark_delivered(_user(), str(data.get("groupId", "")), int(data.get("seq", 0)))
    return {"ok": True}


@socketio.on("typing", namespace=NS)
@_safe
def on_typing(data):
    user = _user()
    gid = str(data.get("groupId", ""))
    m = service.membership(gid, user.id)
    name = service.display_name(m.get("role", "student"), m.get("name") or user.name, m.get("rollNo"))
    emit("typing", {"groupId": gid, "userId": user.id, "name": name, "typing": bool(data.get("typing"))},
         to=service.group_room(gid), skip_sid=request.sid)
    return {"ok": True}


@socketio.on("viewing", namespace=NS)
@_safe
def on_viewing(data):
    user = _user()
    gid = data.get("groupId")
    if gid:
        service.membership(str(gid), user.id)
    presence.viewing(request.sid, str(gid) if gid else None)
    return {"ok": True}
