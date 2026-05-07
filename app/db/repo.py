"""Thin repository helpers."""
from __future__ import annotations

from ..extensions import db
from .models import Session


def create_session(raw_initial_text: str, user_id: str | None = None) -> Session:
    session = Session(
        user_id=user_id,
        raw_initial_text=raw_initial_text,
        history=[{"role": "user", "text": raw_initial_text}],
        active_domains=[],
        filled_slots={},
        meta={
            "total_questions_asked": 0,
            "domain_question_count": {},
            "clarifier_used": [],
            "current_question": None,
            "current_binary_question": None,
            "binary_answers": [],
            "emotion_signals": [],
            "combo_history": [],
            "trigger_feedback": {
                "recent_triggers": [],
                "effectiveness": {},
                "baseline_stats": {
                    "count": 0,
                    "sum_time": 0.0,
                    "sum_confidence": 0.0,
                    "sum_accuracy": 0.0,
                },
                "baseline_metrics": {
                    "time_spent": 0.0,
                    "confidence": 0.0,
                    "accuracy": 0.0,
                },
            },
        },
    )
    db.session.add(session)
    db.session.commit()
    db.session.refresh(session)
    return session


def get_session(session_id) -> Session | None:
    return Session.query.get(session_id)


def save_session(session: Session) -> None:
    db.session.add(session)
    db.session.commit()
    db.session.refresh(session)


__all__ = ["create_session", "get_session", "save_session"]
