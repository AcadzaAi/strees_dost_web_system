"""Persistence model for the standalone Acadza leaderboard API."""
from __future__ import annotations

from ..extensions import db


class LeaderboardEntry(db.Model):
    """One subject/chapter result from a submitted practice."""

    __tablename__ = "leaderboard_entries"

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.String(64), index=True, nullable=False)
    name = db.Column(db.String(120))
    reference = db.Column(db.String(64), index=True)
    practice_id = db.Column(db.String(64), nullable=False)
    level = db.Column(db.String(10))
    subject = db.Column(db.String(40), index=True)
    chapter = db.Column(db.String(160), index=True)
    correct = db.Column(db.Integer, default=0)
    incorrect = db.Column(db.Integer, default=0)
    points = db.Column(db.Integer, default=0)
    attempted_at = db.Column(db.DateTime, index=True, nullable=False)

    __table_args__ = (
        db.UniqueConstraint(
            "user_id",
            "practice_id",
            "subject",
            "chapter",
            name="uq_leaderboard_user_practice_scope",
        ),
        db.Index(
            "ix_leaderboard_query",
            "reference",
            "subject",
            "chapter",
            "attempted_at",
        ),
    )


__all__ = ["LeaderboardEntry"]
