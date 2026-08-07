"""Database models."""
from __future__ import annotations

import os
import uuid
from datetime import datetime

from sqlalchemy import JSON, func
from sqlalchemy.ext.mutable import MutableDict, MutableList

from ..extensions import db

USE_SQLITE = (
    (os.getenv("DATABASE_URL") or "").startswith("sqlite") or
    (os.getenv("SQLALCHEMY_DATABASE_URI") or "").startswith("sqlite") or
    not os.getenv("DATABASE_URL")  # Default to SQLite if no DATABASE_URL set
)

if USE_SQLITE:
    UUIDType = db.String(36)
    JSONType = JSON

    def _uuid_default() -> str:
        return str(uuid.uuid4())

else:
    from sqlalchemy.dialects.postgresql import JSONB, UUID

    UUIDType = UUID(as_uuid=True)
    JSONType = JSONB

    def _uuid_default() -> uuid.UUID:
        return uuid.uuid4()


class Session(db.Model):
    __tablename__ = "sessions"

    id = db.Column(UUIDType, primary_key=True, default=_uuid_default)
    user_id = db.Column(UUIDType, db.ForeignKey("users.id"), nullable=True)  # Link to user profile
    status = db.Column(db.String(20), nullable=False, default="active")

    raw_initial_text = db.Column(db.Text, nullable=True)

    history = db.Column(MutableList.as_mutable(JSONType), nullable=False, default=list)
    active_domains = db.Column(MutableList.as_mutable(JSONType), nullable=False, default=list)
    filled_slots = db.Column(MutableDict.as_mutable(JSONType), nullable=False, default=dict)
    meta = db.Column(MutableDict.as_mutable(JSONType), nullable=False, default=dict)
    popups = db.Column(MutableList.as_mutable(JSONType), nullable=False, default=list)
    
    # Academic topics extraction data
    academic_topics_raw = db.Column(MutableDict.as_mutable(JSONType), nullable=True)
    academic_topics_subject = db.Column(db.String(50), nullable=True)
    academic_topics_topics = db.Column(MutableList.as_mutable(JSONType), nullable=True)

    created_at = db.Column(
        db.DateTime, nullable=False, server_default=func.now(), default=datetime.utcnow
    )
    updated_at = db.Column(
        db.DateTime,
        nullable=False,
        server_default=func.now(),
        onupdate=func.now(),
        default=datetime.utcnow,
    )
    
    # Relationship
    user = db.relationship("User", back_populates="sessions")


class User(db.Model):
    __tablename__ = "users"

    id = db.Column(UUIDType, primary_key=True, default=_uuid_default)
    name = db.Column(db.String(100), nullable=False)
    
    # Session tracking
    total_sessions = db.Column(db.Integer, nullable=False, default=0)
    completed_sessions = db.Column(db.Integer, nullable=False, default=0)
    
    # Trigger history for future adaptive behavior
    trigger_history = db.Column(MutableList.as_mutable(JSONType), nullable=False, default=list)
    
    # User preferences and stats
    preferences = db.Column(MutableDict.as_mutable(JSONType), nullable=False, default=dict)
    stats = db.Column(MutableDict.as_mutable(JSONType), nullable=False, default=dict)
    
    created_at = db.Column(
        db.DateTime, nullable=False, server_default=func.now(), default=datetime.utcnow
    )
    last_seen_at = db.Column(
        db.DateTime, nullable=False, server_default=func.now(), default=datetime.utcnow
    )
    
    # Relationship
    sessions = db.relationship("Session", back_populates="user", lazy="dynamic")


__all__ = ["Session", "User"]