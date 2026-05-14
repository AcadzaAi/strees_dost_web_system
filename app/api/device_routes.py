"""Device session endpoints."""
from __future__ import annotations

from flask import Blueprint, jsonify, request

from ..db.models import DeviceSession
from ..extensions import db

bp = Blueprint("device", __name__, url_prefix="/device")


@bp.post("/register")
def register_device():
    body = request.get_json(force=True, silent=True) or {}
    user_id = (body.get("user_id") or "").strip()
    device_id = (body.get("device_id") or "").strip()
    if not user_id or not device_id:
        return jsonify({"error": "user_id and device_id are required"}), 400

    record = DeviceSession.query.filter_by(user_id=user_id).first()
    if record:
        record.device_id = device_id
    else:
        record = DeviceSession(user_id=user_id, device_id=device_id)
        db.session.add(record)

    db.session.commit()
    return jsonify({"ok": True})


@bp.post("/verify")
def verify_device():
    body = request.get_json(force=True, silent=True) or {}
    user_id = (body.get("user_id") or "").strip()
    device_id = (body.get("device_id") or "").strip()
    if not user_id or not device_id:
        return jsonify({"error": "user_id and device_id are required"}), 400

    record = DeviceSession.query.filter_by(user_id=user_id).first()
    if not record:
        return jsonify({"valid": True})
    if record.device_id == device_id:
        return jsonify({"valid": True})
    return jsonify({"valid": False})
