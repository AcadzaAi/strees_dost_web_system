"""User profile API routes."""
from __future__ import annotations

from flask import Blueprint, jsonify, request

from ..db.models import User, Session
from ..extensions import db

bp = Blueprint("user", __name__, url_prefix="/api/user")


@bp.post("/login")
def login():
    """Login or create user profile."""
    data = request.get_json() or {}
    name = data.get("name", "").strip()
    
    if not name:
        return jsonify({"error": "Name is required"}), 400
    
    # Try to find existing user by name (case-insensitive)
    user = User.query.filter(db.func.lower(User.name) == name.lower()).first()
    
    if user:
        # Existing user - update last seen
        user.last_seen_at = db.func.now()
        db.session.commit()
        
        return jsonify({
            "user_id": str(user.id),
            "name": user.name,
            "total_sessions": user.total_sessions,
            "completed_sessions": user.completed_sessions,
            "is_new_user": False,
            "stats": user.stats,
            "preferences": user.preferences
        })
    else:
        # New user - create profile
        user = User(
            name=name,
            total_sessions=0,
            completed_sessions=0,
            trigger_history=[],
            preferences={},
            stats={}
        )
        db.session.add(user)
        db.session.commit()
        
        return jsonify({
            "user_id": str(user.id),
            "name": user.name,
            "total_sessions": 0,
            "completed_sessions": 0,
            "is_new_user": True,
            "stats": {},
            "preferences": {}
        })


@bp.get("/<user_id>")
def get_user(user_id):
    """Get user profile."""
    user = User.query.get(user_id)
    
    if not user:
        return jsonify({"error": "User not found"}), 404
    
    return jsonify({
        "user_id": str(user.id),
        "name": user.name,
        "total_sessions": user.total_sessions,
        "completed_sessions": user.completed_sessions,
        "stats": user.stats,
        "preferences": user.preferences,
        "created_at": user.created_at.isoformat(),
        "last_seen_at": user.last_seen_at.isoformat()
    })


@bp.post("/<user_id>/session-start")
def start_session(user_id):
    """Increment session count when user starts a new session."""
    user = User.query.get(user_id)
    
    if not user:
        return jsonify({"error": "User not found"}), 404
    
    user.total_sessions += 1
    user.last_seen_at = db.func.now()
    db.session.commit()
    
    return jsonify({
        "user_id": str(user.id),
        "total_sessions": user.total_sessions
    })


@bp.post("/<user_id>/session-complete")
def complete_session(user_id):
    """Increment completed session count."""
    user = User.query.get(user_id)
    
    if not user:
        return jsonify({"error": "User not found"}), 404
    
    user.completed_sessions += 1
    user.last_seen_at = db.func.now()
    db.session.commit()
    
    return jsonify({
        "user_id": str(user.id),
        "completed_sessions": user.completed_sessions
    })


@bp.post("/<user_id>/trigger-history")
def add_trigger_history(user_id):
    """Add trigger to user's history for future adaptive behavior."""
    user = User.query.get(user_id)
    
    if not user:
        return jsonify({"error": "User not found"}), 404
    
    data = request.get_json() or {}
    trigger_data = {
        "trigger_name": data.get("trigger_name"),
        "question_number": data.get("question_number"),
        "outcome": data.get("outcome"),
        "timestamp": db.func.now()
    }
    
    user.trigger_history.append(trigger_data)
    db.session.commit()
    
    return jsonify({"success": True})


@bp.put("/<user_id>/preferences")
def update_preferences(user_id):
    """Update user preferences."""
    user = User.query.get(user_id)
    
    if not user:
        return jsonify({"error": "User not found"}), 404
    
    data = request.get_json() or {}
    user.preferences.update(data)
    db.session.commit()
    
    return jsonify({"success": True, "preferences": user.preferences})


@bp.put("/<user_id>/stats")
def update_stats(user_id):
    """Update user stats."""
    user = User.query.get(user_id)
    
    if not user:
        return jsonify({"error": "User not found"}), 404
    
    data = request.get_json() or {}
    user.stats.update(data)
    db.session.commit()
    
    return jsonify({"success": True, "stats": user.stats})
