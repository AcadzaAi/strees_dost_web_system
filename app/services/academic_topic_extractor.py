"""Extract mentioned academic subjects/chapters/concepts from conversation."""
from __future__ import annotations

import json
import logging
import re
from typing import Any

from .openai_client import chat_json

logger = logging.getLogger(__name__)


SYSTEM_PROMPT_ACADEMIC_TOPICS = """
You extract ONLY explicitly mentioned academic study topics from a conversation.

Return STRICT JSON only:
{
  "academic_talk_detected": true,
  "subjects": ["..."],
  "chapters": ["..."],
  "concepts": ["..."],
  "sub_concepts": ["..."]
}

Rules:
- Only include what is directly mentioned or clearly named in the conversation.
- Do NOT infer a chapter or concept from a subject if it was not mentioned.
- If the conversation has no study/academic topic discussion, return:
  {
    "academic_talk_detected": false,
    "subjects": [],
    "chapters": [],
    "concepts": [],
    "sub_concepts": []
  }
- Prefer canonical academic labels:
  - subject: Physics, Chemistry, Mathematics, Biology
  - chapter: Kinematics, Organic Chemistry, Trigonometry
  - concept: Motion, Limits, Thermodynamics
  - sub_concept: Relative velocity, SN1 reaction, Binomial coefficient
- Keep arrays deduplicated.
"""


SUBJECT_PATTERNS = {
    "Physics": r"\bphysics\b",
    "Chemistry": r"\bchemistry\b",
    "Mathematics": r"\bmath(?:s|ematics)?\b",
    "Biology": r"\bbio(?:logy)?\b",
}


def _clean_list(values: Any) -> list[str]:
    if not isinstance(values, list):
        return []
    out: list[str] = []
    seen: set[str] = set()
    for item in values:
        text = " ".join(str(item or "").strip().split())
        if not text:
            continue
        lowered = text.lower()
        if lowered in seen:
            continue
        seen.add(lowered)
        out.append(text)
    return out


def _conversation_text(initial_text: str, conversation_history: list[dict[str, Any]] | None) -> str:
    parts: list[str] = []
    if initial_text:
        parts.append(str(initial_text).strip())
    for turn in conversation_history or []:
        if not isinstance(turn, dict):
            continue
        text = str(turn.get("text") or turn.get("content") or "").strip()
        if text:
            parts.append(text)
    return "\n".join(parts)


def _heuristic_fallback(text: str) -> dict[str, Any]:
    lowered = (text or "").lower()
    subjects = [name for name, pattern in SUBJECT_PATTERNS.items() if re.search(pattern, lowered)]
    return {
        "academic_talk_detected": bool(subjects),
        "subjects": subjects,
        "chapters": [],
        "concepts": [],
        "sub_concepts": [],
    }


def extract_academic_topics(
    initial_text: str,
    conversation_history: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    """Return only explicit academic topics mentioned across the conversation."""
    convo_text = _conversation_text(initial_text, conversation_history)
    empty = {
        "academic_talk_detected": False,
        "subjects": [],
        "chapters": [],
        "concepts": [],
        "sub_concepts": [],
    }
    if not convo_text.strip():
        return empty

    payload = {
        "conversation_text": convo_text[:6000],
        "conversation_history": (conversation_history or [])[-18:],
    }

    try:
        resp = chat_json(
            model="gpt-4o-mini",
            system=SYSTEM_PROMPT_ACADEMIC_TOPICS,
            user=json.dumps(payload, ensure_ascii=False),
            temperature=0.1,
            max_tokens=240,
        )
        raw = (resp.choices[0].message.content or "").strip()
        data = json.loads(raw)
        result = {
            "academic_talk_detected": bool(data.get("academic_talk_detected")),
            "subjects": _clean_list(data.get("subjects")),
            "chapters": _clean_list(data.get("chapters")),
            "concepts": _clean_list(data.get("concepts")),
            "sub_concepts": _clean_list(data.get("sub_concepts")),
        }
        if any(result[key] for key in ("subjects", "chapters", "concepts", "sub_concepts")):
            result["academic_talk_detected"] = True
        return result
    except Exception as exc:  # pragma: no cover - defensive
        logger.warning("extract_academic_topics failed: %s", exc)
        return _heuristic_fallback(convo_text)


__all__ = ["extract_academic_topics"]
