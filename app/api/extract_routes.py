<<<<<<< HEAD
"""Academic topics extraction routes."""
from __future__ import annotations

import json
import logging
import re
from typing import Dict, List, Optional

from flask import Blueprint, jsonify, request

from ..services.openai_client import chat_json
from ..services.acadza_validator import acadza_validator

logger = logging.getLogger(__name__)

bp = Blueprint("extract", __name__, url_prefix="/api/extract")

# Subject normalization mapping (per product spec)
SUBJECT_NORMALIZATION = {
    "phy": "Physics",
    "phys": "Physics",
    "physics": "Physics",
    "chem": "Chemistry",
    "chemist": "Chemistry",
    "chemistry": "Chemistry",
    "math": "Maths",
    "maths": "Maths",
    "mathematics": "Maths",
    "bio": "Biology",
    "biology": "Biology",
    "biolog": "Biology",
}

# System prompt for academic topics extraction
SYSTEM_PROMPT_ACADEMIC_TOPICS = """
You are an academic topics extraction engine. Analyze the user's statement and conversation history to extract academic information.

Return JSON with exactly these fields:
{
  "academic_talk_detected": boolean,
  "subjects": array of strings,
  "chapters": array of strings, 
  "concepts": array of strings,
  "sub_concepts": array of strings
}

Rules:
- subjects: Main academic subjects mentioned (Physics, Chemistry, Mathematics, Biology, etc.)
- chapters: Specific chapter/topic names from curriculum (e.g., "Algebra", "Kinematics", "Organic Chemistry")
- concepts: Broad conceptual topics (e.g., "Force", "Equations", "Cell Structure")
- sub_concepts: Very specific topics (e.g., "Newton's Second Law", "Quadratic Equations", "Mitochondria")
- academic_talk_detected: true if any academic content is found, false otherwise

Consider conversation context - one-word replies like "circle" only make sense with the preceding question.
Extract from both the main text and conversation history.

Be precise but comprehensive. Return empty arrays if nothing found for a category.
"""

def normalize_subject(subject: str) -> Optional[str]:
    """Normalize subject name using pattern matching."""
    if not subject:
        return None
    
    subject_lower = subject.lower().strip()
    
    # Pattern matching for subject normalization
    for pattern, normalized in SUBJECT_NORMALIZATION.items():
        if subject_lower.startswith(pattern):
            return normalized
    
    # Exact match (case-insensitive) for already-normalized values
    normalized_values = {v.lower(): v for v in SUBJECT_NORMALIZATION.values()}
    if subject_lower in normalized_values:
        return normalized_values[subject_lower]
    
    return None

def extract_academic_topics(text: str, conversation_history: List[Dict]) -> Dict:
    """Extract academic topics using AI (no catalog dependency)."""
    try:
        # Build conversation context (preserve interleaved order)
        conversation_context: list[dict] = []
        for turn in conversation_history or []:
            if not isinstance(turn, dict):
                continue
            role = str(turn.get("role") or "").strip()
            content = str(turn.get("text") or turn.get("content") or "").strip()
            if role and content:
                conversation_context.append({"role": role, "content": content})
        
        payload = {
            "text": text,
            "conversation_history": conversation_context,
        }
        
        resp = chat_json(
            model="gpt-4o-mini",
            system=SYSTEM_PROMPT_ACADEMIC_TOPICS,
            user=json.dumps(payload, ensure_ascii=False),
            max_tokens=500,
            temperature=0.3,
        )
        
        raw = resp.choices[0].message.content or ""
        data = json.loads(raw)
        
        # Normalize subjects (keep only recognized ones)
        normalized_subjects: list[str] = []
        for subject in (data.get("subjects", []) or []):
            if not isinstance(subject, str):
                continue
            normalized = normalize_subject(subject)
            if normalized:
                normalized_subjects.append(normalized)
        
        return {
            "academic_talk_detected": data.get("academic_talk_detected", False),
            "subjects": normalized_subjects,
            "chapters": data.get("chapters", []) or [],
            "concepts": data.get("concepts", []) or [],
            "sub_concepts": data.get("sub_concepts", []) or [],
        }
        
    except Exception as exc:
        logger.warning("Academic topics extraction failed: %s", exc)
        return {
            "academic_talk_detected": False,
            "subjects": [],
            "chapters": [],
            "concepts": [],
            "sub_concepts": [],
        }

@bp.post("/academic-topics")
def extract_topics():
    """Extract academic topics from user text and conversation history."""
    try:
        body = request.get_json(force=True, silent=True) or {}
        
        text = body.get("text", "").strip()
        conversation_history = body.get("conversation_history", [])
        
        if not text:
            return jsonify({"error": "text is required"}), 400
        
        logger.info("Extracting academic topics from text: %r", text[:100])
        
        result = extract_academic_topics(text, conversation_history)
        
        # Per API contract: return the 5 fields at top-level.
        return jsonify(result)
        
    except Exception as exc:
        logger.exception("extract_topics endpoint failed: %s", exc)
        return jsonify({"error": "internal error", "detail": str(exc)}), 500


__all__ = ["bp"]
=======
"""Direct extraction routes for client apps."""
from __future__ import annotations

from flask import Blueprint, jsonify, request

from ..services.academic_topic_extractor import extract_academic_topics

bp = Blueprint("extract", __name__, url_prefix="/api/extract")


@bp.post("/academic-topics")
def extract_academic_topics_direct():
    body = request.get_json(force=True, silent=True) or {}
    initial_text = str(body.get("text") or body.get("initial_text") or "").strip()
    history_raw = body.get("conversation_history")
    conversation_history = history_raw if isinstance(history_raw, list) else []

    topics = extract_academic_topics(
        initial_text=initial_text,
        conversation_history=conversation_history,
    )
    return jsonify(topics)

>>>>>>> 9cf2445d80e1f3f3d18f0ed76d3f1177d5703a06
