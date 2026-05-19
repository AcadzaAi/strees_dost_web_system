"""Academic topics and subject management routes."""
from __future__ import annotations

import logging
from typing import List

from flask import Blueprint, jsonify, request

from ..services.acadza_validator import acadza_validator

logger = logging.getLogger(__name__)

bp = Blueprint("academic", __name__, url_prefix="/api/academic")

@bp.get("/available-subjects")
def get_available_subjects():
    """Get list of available subjects from Acadza catalog."""
    try:
        # Initialize acadza validator to load catalog
        acadza_validator._initialize_from_acadza()
        
        subjects = list(acadza_validator._available_subjects)
        subjects.sort()  # Sort alphabetically
        
        return jsonify({
            "status": "success",
            "subjects": [subject.title() for subject in subjects]
        })
        
    except Exception as exc:
        logger.exception("get_available_subjects failed: %s", exc)
        return jsonify({"error": "internal error", "detail": str(exc)}), 500

def _build_subject_catalog_payload(subject: str) -> dict:
    chapters = acadza_validator.get_available_chapters(subject)
    concepts = acadza_validator.get_available_concepts(subject)
    subconcepts = acadza_validator.get_available_subconcepts(subject)

    chapters.sort()
    concepts.sort()
    subconcepts.sort()

    return {
        "status": "success",
        "subject": subject,
        "chapters": [chapter.title() for chapter in chapters],
        "concepts": [concept.title() for concept in concepts],
        "subconcepts": [subconcept.title() for subconcept in subconcepts],
    }


@bp.get("/available-chapters")
def get_available_chapters():
    """Get list of available chapters/concepts for a subject."""
    try:
        subject = request.args.get("subject", "").strip()
        if not subject:
            return jsonify({"error": "subject parameter required"}), 400
        
        # Initialize acadza validator to load catalog
        acadza_validator._initialize_from_acadza()

        return jsonify(_build_subject_catalog_payload(subject))
        
    except Exception as exc:
        logger.exception("get_available_chapters failed: %s", exc)
        return jsonify({"error": "internal error", "detail": str(exc)}), 500


@bp.get("/available-topics")
def get_available_topics():
    """Back-compat alias for chapters endpoint."""
    return get_available_chapters()

@bp.get("/subject-suggestions")
def get_subject_suggestions():
    """Get subject suggestions for partial input."""
    try:
        partial = request.args.get("partial", "").strip()
        if not partial:
            return jsonify({"error": "partial parameter required"}), 400
        
        # Initialize acadza validator
        acadza_validator._initialize_from_acadza()
        
        suggestions = acadza_validator.get_subject_suggestions(partial)
        
        return jsonify({
            "status": "success",
            "partial": partial,
            "suggestions": suggestions
        })
        
    except Exception as exc:
        logger.exception("get_subject_suggestions failed: %s", exc)
        return jsonify({"error": "internal error", "detail": str(exc)}), 500

@bp.get("/chapter-suggestions")
def get_chapter_suggestions():
    """Get chapter suggestions for a subject."""
    try:
        subject = request.args.get("subject", "").strip()
        partial = request.args.get("partial", "").strip()
        
        if not subject or not partial:
            return jsonify({"error": "subject and partial parameters required"}), 400
        
        # Initialize acadza validator
        acadza_validator._initialize_from_acadza()
        
        suggestions = acadza_validator.get_chapter_suggestions(subject, partial)
        
        return jsonify({
            "status": "success",
            "subject": subject,
            "partial": partial,
            "suggestions": suggestions
        })
        
    except Exception as exc:
        logger.exception("get_chapter_suggestions failed: %s", exc)
        return jsonify({"error": "internal error", "detail": str(exc)}), 500


@bp.get("/topic-suggestions")
def get_topic_suggestions():
    """Back-compat alias for chapter suggestions."""
    return get_chapter_suggestions()


__all__ = ["bp"]
