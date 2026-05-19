"""Session routes for academic topics extraction."""
from __future__ import annotations

import json
import logging
from typing import Dict, List, Optional

from flask import Blueprint, jsonify, request

from ..db.repo import get_session, save_session
from ..services.acadza_validator import acadza_validator

logger = logging.getLogger(__name__)

bp = Blueprint("session_academic", __name__, url_prefix="/api/session")

def normalize_subject(subject: str) -> Optional[str]:
    """Normalize subject name using pattern matching."""
    if not subject:
        return None
    
    subject_lower = subject.lower().strip()
    
    # Pattern matching for subject normalization (per product spec)
    subject_normalization = {
        "phy": "Physics",
        "phys": "Physics",
        "physics": "Physics",
        "chem": "Chemistry",
        "chemist": "Chemistry",
        "chemistry": "Chemistry",
        "math": "Mathematics",
        "maths": "Mathematics",
        "mathematics": "Mathematics",
    }
    
    for pattern, normalized in subject_normalization.items():
        if subject_lower.startswith(pattern):
            return normalized
    
    # Exact match (case-insensitive) for already-normalized values
    normalized_values = {v.lower(): v for v in subject_normalization.values()}
    if subject_lower in normalized_values:
        return normalized_values[subject_lower]
    
    return None

def get_auto_picked_topics(result: Dict) -> Optional[List[str]]:
    """Get auto-picked topics following hierarchy: sub_concepts > concepts > chapters."""
    if not result:
        return None
    
    # Follow hierarchy: sub_concepts > concepts > chapters
    if result.get("sub_concepts"):
        return result["sub_concepts"]
    elif result.get("concepts"):
        return result["concepts"]
    elif result.get("chapters"):
        return result["chapters"]
    
    return None


def _filter_acadza_items(items: list | None, available: list[str]) -> List[str]:
    if not items or not available:
        return []
    available_map = {item.lower(): item.title() for item in available}
    out: list[str] = []
    for item in items:
        if not isinstance(item, str):
            continue
        key = item.strip().lower()
        if key in available_map:
            out.append(available_map[key])
    return out

@bp.post("/<session_id>/academic-topics")
def save_academic_topics(session_id: str):
    """Save academic topics extraction results to session."""
    try:
        session = get_session(session_id)
        if not session:
            return jsonify({"error": "session not found"}), 404
        
        body = request.get_json(force=True, silent=True) or {}
        result = body.get("result", {})
        
        # Validate result structure
        if not isinstance(result, dict):
            logger.warning("Invalid result format: expected dict, got %s", type(result))
            return jsonify({"error": "invalid result format", "detail": "result must be a dictionary"}), 400
        
        # Store raw response as-is
        session.academic_topics_raw = result
        
        # Extract autoPickedSubject - normalize subjects[0]
        subjects = result.get("subjects", [])
        auto_picked_subject = None
        if subjects and isinstance(subjects, list) and isinstance(subjects[0], str):
            auto_picked_subject = normalize_subject(subjects[0])

        if auto_picked_subject and not acadza_validator.is_subject_available(auto_picked_subject):
            logger.info(
                "Auto-picked subject not available in Acadza catalog: %s",
                auto_picked_subject,
            )
            auto_picked_subject = None
        
        # Extract autoPickedTopics - only keep Acadza-backed chapters/concepts/subconcepts
        auto_picked_topics = None
        if auto_picked_subject:
            available_chapters = acadza_validator.get_available_chapters(auto_picked_subject)
            available_concepts = acadza_validator.get_available_concepts(auto_picked_subject)
            available_subconcepts = acadza_validator.get_available_subconcepts(auto_picked_subject)

            picked = _filter_acadza_items(result.get("sub_concepts"), available_subconcepts)
            if not picked:
                picked = _filter_acadza_items(result.get("concepts"), available_concepts)
            if not picked:
                picked = _filter_acadza_items(result.get("chapters"), available_chapters)

            auto_picked_topics = picked or None
        
        # Store in session
        session.academic_topics_subject = auto_picked_subject
        session.academic_topics_topics = auto_picked_topics
        
        # Save session
        save_session(session)
        
        logger.info(
            "Saved academic topics for session %s: subject=%s, topics_count=%d",
            session_id, 
            auto_picked_subject,
            len(auto_picked_topics) if auto_picked_topics else 0
        )
        
        return jsonify({
            "status": "success",
            "autoPickedSubject": auto_picked_subject,
            "autoPickedTopics": auto_picked_topics,
            "shouldSkipSubjectScreen": auto_picked_subject is not None,
            "shouldSkipTopicScreen": auto_picked_topics is not None
        })
        
    except Exception as exc:
        logger.exception("save_academic_topics failed: %s", exc)
        return jsonify({"error": "internal error", "detail": str(exc)}), 500

@bp.get("/<session_id>/academic-topics")
def get_academic_topics(session_id: str):
    """Get stored academic topics for a session."""
    try:
        session = get_session(session_id)
        if not session:
            return jsonify({"error": "session not found"}), 404
        
        return jsonify({
            "status": "success",
            "raw": session.academic_topics_raw,
            "autoPickedSubject": session.academic_topics_subject,
            "autoPickedTopics": session.academic_topics_topics,
            "shouldSkipSubjectScreen": session.academic_topics_subject is not None,
            "shouldSkipTopicScreen": session.academic_topics_topics is not None
        })
        
    except Exception as exc:
        logger.exception("get_academic_topics failed: %s", exc)
        return jsonify({"error": "internal error", "detail": str(exc)}), 500

@bp.delete("/<session_id>/academic-topics")
def reset_academic_topics(session_id: str):
    """Reset academic topics data (for retake functionality)."""
    try:
        session = get_session(session_id)
        if not session:
            return jsonify({"error": "session not found"}), 404
        
        session.academic_topics_raw = None
        session.academic_topics_subject = None
        session.academic_topics_topics = None
        
        save_session(session)
        
        logger.info("Reset academic topics for session %s", session_id)
        
        return jsonify({"status": "success"})
        
    except Exception as exc:
        logger.exception("reset_academic_topics failed: %s", exc)
        return jsonify({"error": "internal error", "detail": str(exc)}), 500


@bp.post("/<session_id>/meta")
def merge_session_meta(session_id: str):
    """Lightweight meta merge used by subject/topic selection UI."""
    try:
        session = get_session(session_id)
        if not session:
            return jsonify({"error": "session not found"}), 404

        body = request.get_json(force=True, silent=True) or {}
        selected_subject = body.get("selected_subject")
        selected_topics = body.get("selected_topics")

        meta = dict(session.meta or {})

        if isinstance(selected_subject, str):
            meta["selected_subject"] = selected_subject.strip()[:80] or None
        if isinstance(selected_topics, list):
            cleaned: list[str] = []
            for item in selected_topics:
                if isinstance(item, str):
                    val = item.strip()
                    if val:
                        cleaned.append(val[:120])
            meta["selected_topics"] = cleaned

        session.meta = meta
        save_session(session)
        return jsonify({"status": "success", "meta": session.meta})

    except Exception as exc:
        logger.exception("merge_session_meta failed: %s", exc)
        return jsonify({"error": "internal error", "detail": str(exc)}), 500


__all__ = ["bp"]
