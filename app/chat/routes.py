"""Chat REST API under /api/chat. Every call needs `Authorization: Bearer <Acadza token>`.

The app uses REST for lists, history and catching up, and for sending when the socket is down
(the outbox, replies from a notification). Live traffic goes over the /chat socket.
"""
from __future__ import annotations

from flask import Blueprint, g, jsonify, request

from . import service
from .auth import require_admin, require_user
from .mongo import db
from .moderation import DEFAULT_RULES
from .service import ChatError

bp = Blueprint("chat", __name__, url_prefix="/api/chat")


@bp.errorhandler(ChatError)
def _chat_error(err: ChatError):
    return jsonify(err.to_dict()), err.status


def _int(name: str):
    v = request.args.get(name)
    return int(v) if v not in (None, "") else None


def _body() -> dict:
    return request.get_json(silent=True) or {}


# ── students and teachers ────────────────────────────────────────────────────────────────────

@bp.get("/me")
@require_user
def me():
    u = g.chat_user
    return jsonify({"id": u.id, "name": u.name, "role": u.role, "coaching": u.coaching,
                    "isAdmin": u.is_admin, "isStaff": u.is_staff})


@bp.get("/groups")
@require_user
def groups():
    return jsonify({"groups": service.groups_for(g.chat_user)})


@bp.get("/groups/<group_id>")
@require_user
def group(group_id):
    m = service.membership(group_id, g.chat_user.id)
    return jsonify(service.group_out(service.group_or_404(group_id), m))


@bp.get("/groups/<group_id>/messages")
@require_user
def messages(group_id):
    return jsonify(service.history(g.chat_user, group_id, before=_int("before"), after=_int("after"),
                                   limit=_int("limit") or 50))


@bp.post("/groups/<group_id>/messages")
@require_user
def send(group_id):
    b = _body()
    msg = service.send_message(g.chat_user, group_id, b.get("clientId", ""), b.get("text", ""), b.get("replyToSeq"))
    return jsonify({"ok": True, "message": msg})


@bp.post("/groups/<group_id>/read")
@require_user
def read(group_id):
    return jsonify({"ok": True, "readSeq": service.mark_read(g.chat_user, group_id, int(_body().get("seq", 0)))})


@bp.post("/groups/<group_id>/mute")
@require_user
def mute(group_id):
    service.set_muted(g.chat_user, group_id, bool(_body().get("muted")))
    return jsonify({"ok": True})


@bp.delete("/groups/<group_id>/messages/<int:seq>")
@require_user
def delete(group_id, seq):
    return jsonify({"ok": True, **service.delete_message(g.chat_user, group_id, seq)})


@bp.post("/groups/<group_id>/messages/<int:seq>/report")
@require_user
def report(group_id, seq):
    service.report_message(g.chat_user, group_id, seq, _body().get("reason", ""))
    return jsonify({"ok": True})


@bp.post("/devices")
@require_user
def add_device():
    b = _body()
    service.register_device(g.chat_user, b.get("token", ""), b.get("platform", "android"))
    return jsonify({"ok": True})


@bp.delete("/devices")
@require_user
def remove_device():
    service.unregister_device(g.chat_user, _body().get("token", ""))
    return jsonify({"ok": True})


# ── admin ────────────────────────────────────────────────────────────────────────────────────

@bp.get("/admin/groups")
@require_admin
def admin_groups():
    q = {"coaching": request.args["coaching"]} if request.args.get("coaching") else {}
    return jsonify({"groups": [service.group_out(x) for x in db().groups.find(q).sort("createdAt", -1)]})


@bp.post("/admin/groups")
@require_admin
def admin_create_group():
    return jsonify(service.create_group(g.chat_user, _body())), 201


@bp.patch("/admin/groups/<group_id>")
@require_admin
def admin_update_group(group_id):
    return jsonify(service.update_group(group_id, _body()))


@bp.get("/admin/groups/<group_id>/members")
@require_admin
def admin_members(group_id):
    return jsonify({"members": service.list_members(group_id)})


@bp.post("/admin/groups/<group_id>/members")
@require_admin
def admin_add_members(group_id):
    return jsonify({"ok": True, "added": service.add_members(group_id, _body().get("members") or [])})


@bp.delete("/admin/groups/<group_id>/members/<user_id>")
@require_admin
def admin_remove_member(group_id, user_id):
    service.remove_member(group_id, user_id)
    return jsonify({"ok": True})


@bp.post("/admin/groups/<group_id>/members/<user_id>/restrict")
@require_admin
def admin_restrict(group_id, user_id):
    service.restrict_member(group_id, user_id, int(_body().get("minutes", 0)))
    return jsonify({"ok": True})


@bp.get("/admin/users")
@require_admin
def admin_users():
    return jsonify({"users": service.search_users(request.args.get("q", ""), request.args.get("coaching"),
                                                  request.args.get("role"))})


@bp.get("/admin/batches")
@require_admin
def admin_batches():
    coaching = request.args.get("coaching") or g.chat_user.coaching
    return jsonify({"coaching": coaching, "batches": service.known_batches(coaching)})


@bp.get("/admin/moderation")
@require_admin
def admin_get_rules():
    doc = db().settings.find_one({"_id": "moderation"}) or {}
    return jsonify({**DEFAULT_RULES, **{k: v for k, v in doc.items() if k != "_id"}})


@bp.put("/admin/moderation")
@require_admin
def admin_put_rules():
    b = _body()
    allowed = {k: b[k] for k in DEFAULT_RULES if k in b}
    db().settings.update_one({"_id": "moderation"}, {"$set": allowed}, upsert=True)
    return jsonify({"ok": True})


@bp.get("/admin/reports")
@require_admin
def admin_reports():
    items = list(db().reports.find({}, {"_id": 0}).sort("createdAt", -1).limit(200))
    return jsonify({"reports": items})


@bp.get("/admin/moderation/log")
@require_admin
def admin_moderation_log():
    items = list(db().moderation.find({}, {"_id": 0}).sort("createdAt", -1).limit(200))
    return jsonify({"items": items})
