"""Chat REST API under /api/chat. Every call needs `Authorization: Bearer <Acadza token>`.

The app uses REST for lists, history and catching up, and for sending when the socket is down
(the outbox, replies from a notification). Live traffic goes over the /chat socket.
"""
from __future__ import annotations

from flask import Blueprint, g, jsonify, request

from . import chatconfig, service
from .auth import require_admin, require_staff, require_user
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
                    "isAdmin": u.is_admin, "isStaff": u.is_staff, "avatar": service.my_avatar(u),
                    "config": chatconfig.public()})


@bp.post("/me/avatar")
@require_user
def set_avatar():
    return jsonify({"ok": True, "avatar": service.set_avatar(g.chat_user, str(_body().get("avatar", "")))})


@bp.get("/contacts")
@require_user
def contacts():
    return jsonify({"contacts": service.contacts(g.chat_user)})


@bp.post("/direct")
@require_user
def open_direct():
    return jsonify(service.open_direct(g.chat_user, str(_body().get("userId", ""))))


@bp.get("/groups")
@require_user
def groups():
    return jsonify({"groups": service.groups_for(g.chat_user)})


@bp.get("/groups/<group_id>")
@require_user
def group(group_id):
    m = service.membership(group_id, g.chat_user.id)
    return jsonify(service.group_out(service.group_or_404(group_id), m, g.chat_user.id))


@bp.get("/groups/<group_id>/messages")
@require_user
def messages(group_id):
    return jsonify(service.history(g.chat_user, group_id, before=_int("before"), after=_int("after"),
                                   limit=_int("limit") or 50))


@bp.post("/groups/<group_id>/messages")
@require_user
def send(group_id):
    b = _body()
    msg = service.send_message(g.chat_user, group_id, b.get("clientId", ""), b.get("text", ""), b.get("replyToSeq"),
                               media_in=b.get("media"))
    return jsonify({"ok": True, "message": msg})


@bp.post("/groups/<group_id>/read")
@require_user
def read(group_id):
    return jsonify({"ok": True, "readSeq": service.mark_read(g.chat_user, group_id, int(_body().get("seq", 0)))})


@bp.patch("/groups/<group_id>/messages/<int:seq>")
@require_user
def edit(group_id, seq):
    msg = service.edit_message(g.chat_user, group_id, seq, str(_body().get("text", "")))
    return jsonify({"ok": True, "message": msg})


@bp.post("/groups/<group_id>/messages/<int:seq>/react")
@require_user
def react(group_id, seq):
    """{emoji}: my reaction on this message; "" takes it back."""
    return jsonify({"ok": True, **service.react(g.chat_user, group_id, seq, _body().get("emoji"))})


@bp.get("/groups/<group_id>/reactions")
@require_user
def reactions(group_id):
    """Reactions changed after ?since=<ms> (catch-up after being offline)."""
    return jsonify(service.reactions_since(g.chat_user, group_id, _int("since") or 0))


@bp.get("/groups/<group_id>/messages/<int:seq>/info")
@require_user
def message_info(group_id, seq):
    """My message: who read it, who has it (two ticks), who is still waiting."""
    return jsonify({"ok": True, **service.message_info(g.chat_user, group_id, seq)})


@bp.get("/groups/<group_id>/presence")
@require_user
def presence(group_id):
    """Direct chat: is the other person online, or when were they last."""
    return jsonify({"ok": True, **service.peer_presence(g.chat_user, group_id)})


@bp.get("/discover")
@require_user
def discover():
    """Groups I may ask to join (made for my batches, asking switched on, I'm not in them)."""
    return jsonify({"groups": service.discover_groups(g.chat_user)})


@bp.post("/groups/<group_id>/request")
@require_user
def request_join(group_id):
    return jsonify(service.request_join(g.chat_user, group_id))


@bp.delete("/groups/<group_id>/request")
@require_user
def cancel_request(group_id):
    return jsonify(service.cancel_request(g.chat_user, group_id))


@bp.get("/groups/<group_id>/manage/requests")
@require_user
def manage_requests(group_id):
    return jsonify({"requests": service.list_requests(g.chat_user, group_id)})


@bp.post("/groups/<group_id>/manage/requests")
@require_user
def manage_answer_requests(group_id):
    """{userIds: [...], approve: true|false}"""
    body = _body()
    n = service.answer_requests(g.chat_user, group_id, list(body.get("userIds") or []), bool(body.get("approve")))
    return jsonify({"ok": True, "count": n})


@bp.get("/config")
@require_user
def config():
    """Limits from Firebase chatConfig, so the app compresses and warns with the same numbers."""
    from . import chatconfig
    return jsonify(chatconfig.public())


@bp.post("/groups/<group_id>/media/upload")
@require_user
def media_upload(group_id):
    """A short-lived link to upload one photo / voice note / document straight to storage."""
    return jsonify(service.request_upload(g.chat_user, group_id, _body()))


@bp.get("/groups/<group_id>/media/link")
@require_user
def media_link(group_id):
    """A fresh download link for a file of this group (an old one has run out)."""
    from . import media
    key = request.args.get("key", "")
    service.membership(group_id, g.chat_user.id)
    if not media.enabled() or not media.belongs_to(key, group_id):
        return jsonify({"ok": False, "error": "no_media", "message": "That file is gone."}), 404
    return jsonify({"ok": True, "url": media.download_link(key)})


@bp.post("/groups/<group_id>/leave")
@require_user
def leave(group_id):
    service.leave_group(g.chat_user, group_id)
    return jsonify({"ok": True})


@bp.post("/groups/<group_id>/delivered")
@require_user
def delivered(group_id):
    """The phone got the message from a notification while the chat was closed."""
    service.mark_delivered(g.chat_user, group_id, int(_body().get("seq", 0)))
    return jsonify({"ok": True})


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
    return jsonify({"groups": [service.group_out(x) for x in db().groups.find({**q, "type": {"$ne": "direct"}}).sort("createdAt", -1)]})


@bp.post("/admin/groups")
@require_admin
def admin_create_group():
    return jsonify(service.create_group(g.chat_user, _body())), 201


# ── group admins: /groups/<id>/manage ────────────────────────────────────────────────────────

@bp.patch("/groups/<group_id>/manage")
@require_user
def manage_update(group_id):
    return jsonify(service.update_group(g.chat_user, group_id, _body()))


@bp.delete("/groups/<group_id>/manage")
@require_user
def manage_delete(group_id):
    service.delete_group(g.chat_user, group_id)
    return jsonify({"ok": True})


@bp.get("/groups/<group_id>/manage/members")
@require_user
def manage_members(group_id):
    return jsonify({"members": service.list_members(g.chat_user, group_id)})


@bp.post("/groups/<group_id>/manage/members")
@require_user
def manage_add(group_id):
    b = _body()
    added = service.admin_add_members(g.chat_user, group_id, b.get("members") or [], str(b.get("source") or "manual"))
    return jsonify({"ok": True, "added": added})


@bp.delete("/groups/<group_id>/manage/members/<user_id>")
@require_user
def manage_remove(group_id, user_id):
    service.remove_member(g.chat_user, group_id, user_id)
    return jsonify({"ok": True})


@bp.post("/groups/<group_id>/manage/members/<user_id>/restrict")
@require_user
def manage_restrict(group_id, user_id):
    b = _body()
    if b.get("everywhere"):                        # every group where I am an admin
        service.require_group_admin(g.chat_user, group_id)
        n = service.restrict_everywhere(g.chat_user, user_id, int(b.get("minutes", 0)))
        return jsonify({"ok": True, "groups": n})
    until = service.restrict_member(g.chat_user, group_id, user_id, int(b.get("minutes", 0)))
    return jsonify({"ok": True, "restrictedUntil": until})


@bp.post("/groups/<group_id>/manage/members/<user_id>/role")
@require_user
def manage_role(group_id, user_id):
    service.set_member_role(g.chat_user, group_id, user_id, str(_body().get("role", "")))
    return jsonify({"ok": True})


@bp.get("/groups/<group_id>/manage/left")
@require_user
def manage_left(group_id):
    return jsonify({"people": service.left_members(g.chat_user, group_id)})


@bp.get("/groups/<group_id>/manage/members/<user_id>")
@require_user
def manage_profile(group_id, user_id):
    return jsonify(service.member_profile(g.chat_user, group_id, user_id))


@bp.get("/groups/<group_id>/manage/sources")
@require_user
def manage_sources(group_id):
    return jsonify({"sources": service.sources(g.chat_user, group_id)})


@bp.post("/groups/<group_id>/manage/sources/remove")
@require_user
def manage_remove_source(group_id):
    return jsonify({"ok": True, **service.remove_source(g.chat_user, group_id, str(_body().get("source", "")))})


@bp.post("/groups/<group_id>/manage/import")
@require_user
def manage_import(group_id):
    return jsonify({"ok": True, "added": service.import_group(g.chat_user, group_id, str(_body().get("fromGroupId", "")))})


@bp.get("/groups/<group_id>/manage/candidates")
@require_user
def manage_candidates(group_id):
    return jsonify({"students": service.candidates(g.chat_user, group_id)})


@bp.get("/manage/my-groups")
@require_staff
def manage_my_groups():
    return jsonify({"groups": service.admin_groups_of(g.chat_user)})


@bp.get("/admin/users")
@require_staff
def admin_users():
    def _csv(name):
        return [x.strip() for x in (request.args.get(name) or "").split(",") if x.strip()]
    batches = _csv("batches")
    within = _csv("within") or [g.chat_user.coaching]        # the admin's coachings (from the app), else their own
    return jsonify({"users": service.search_users(
        request.args.get("q", ""), request.args.get("coaching"), request.args.get("role"),
        limit=2000 if batches else 30, batches=batches, coachings=_csv("coachings"),
        students_from=None if g.chat_user.is_admin and not _csv("within") else within)})


@bp.get("/admin/batches")
@require_staff
def admin_batches():
    coaching = request.args.get("coaching") or g.chat_user.coaching
    return jsonify({"coaching": coaching, "batches": service.known_batches(coaching)})


@bp.post("/admin/roster/sync")
@require_staff
def admin_roster_sync():
    from . import roster
    b = _body()
    coachings = [str(c) for c in (b.get("coachings") or [g.chat_user.coaching]) if str(c).strip()]
    started = roster.start(request.headers.get("Authorization", ""), coachings, force=bool(b.get("force")))
    return jsonify({"started": started, "status": roster.status(coachings)})


@bp.get("/admin/roster/status")
@require_staff
def admin_roster_status():
    from . import roster
    coachings = [c.strip() for c in (request.args.get("coachings") or g.chat_user.coaching).split(",") if c.strip()]
    return jsonify({"status": roster.status(coachings)})


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
