"""Socket.IO events."""
from __future__ import annotations

import json
import logging

from flask import request
from flask_socketio import emit, join_room

from ..extensions import socketio
from ..services import openai_client

logger = logging.getLogger(__name__)


@socketio.on("connect")
def on_connect():
    emit("server_hello", {"ok": True, "message": "Socket connected"})
    logger.info("socket: client connected sid=%s", request.sid)


@socketio.on("join_session")
def on_join_session(data):
    session_id = str((data or {}).get("session_id") or "")
    if session_id:
        logger.info("socket: join_session sid=%s session_id=%s", request.sid, session_id)
        join_room(session_id)
        emit("joined", {"ok": True, "session_id": session_id})


@socketio.on("suggest_request")
def on_suggest_request(data):
    """Return suggestions for initial text using OpenAI; falls back to local."""
    text = (data or {}).get("text") or ""
    cleaned = text.strip()
    logger.debug("socket: suggest_request sid=%s len=%s", request.sid, len(cleaned))

    # Basic guardrails to avoid noisy spam
    if len(cleaned) < 4:
        emit("suggestions", {"items": []}, to=request.sid)
        return

    suggestions: list[str] = []

    try:
        suggestions = _generate_ai_suggestions(cleaned)
    except Exception:  # pragma: no cover - defensive logging
        logger.exception("suggest_request ai fallback")
        suggestions = []

    if not suggestions:
        suggestions = _generate_local_suggestions(cleaned.lower())

    emit("suggestions", {"items": suggestions}, to=request.sid)


def _generate_local_suggestions(text: str) -> list[str]:
    """Keyword-based completions — returns CONTINUATIONS of what user typed, not full sentences."""
    bank: list[str] = []

    def add(*msgs: str) -> None:
        for msg in msgs:
            if msg not in bank:
                bank.append(msg)

    if any(word in text for word in ["exam", "test", "paper", "deadline", "time"]):
        add(
            "and I feel I have too little time to revise properly",
            "scores are inconsistent and it's stressing me out",
        )
    if any(word in text for word in ["phone", "scroll", "reel", "shorts", "game", "gaming"]):
        add(
            "and losing hours without realizing",
            "instead of studying and I can't stop",
        )
    if any(word in text for word in ["parent", "mom", "dad", "family"]):
        add(
            "expect a top score and I'm scared to disappoint them",
        )
    if any(word in text for word in ["compare", "friend", "topper", "rank"]):
        add(
            "and feel I'm always behind everyone else",
        )
    if any(word in text for word in ["motivation", "burnout", "tired", "drained"]):
        add(
            "and it's hard to stay motivated to study",
        )
    if any(word in text for word in ["backlog", "pending", "syllabus", "left"]):
        add(
            "and I don't know where to start",
        )
    if any(word in text for word in ["distract", "focus", "concentrat"]):
        add(
            "and can't focus for more than a few minutes",
        )
    if any(word in text for word in ["movie", "netflix", "series", "watch"]):
        add(
            "instead of studying and it's becoming a habit",
        )

    if not bank:
        add(
            "and I'm not sure how to manage it",
        )

    return bank[:1]


def _generate_ai_suggestions(text: str) -> list[str]:
    """Use OpenAI chat completion to propose concise continuations."""
    system = (
        "You complete a student's sentence. They are typing about their stress/focus issues.\n"
        "Return ONLY the CONTINUATION — the words that come AFTER what they already typed.\n"
        "Do NOT repeat what they typed. Do NOT return a full sentence from scratch.\n"
        "Return ONLY a JSON object: {\"suggestions\": [\"<continuation only>\"]}\n"
        "Max 60 chars. No markdown. No quotes around the continuation.\n"
        "Example: If they typed 'I keep watching' → return 'reels instead of studying'\n"
        "Example: If they typed 'My phone is' → return 'distracting me from focus'"
    )
    user = f"Student typed: \"{text[:300]}\"\nReturn only the continuation words:"
    resp = openai_client.chat_json_no_retry(
        model="gpt-4o-mini",
        system=system,
        user=user,
        max_tokens=40,
        temperature=0.4,
    )
    raw = (resp.choices[0].message.content or "").strip()
    data = json.loads(raw)
    suggestions = data.get("suggestions") if isinstance(data, dict) else None
    if not isinstance(suggestions, list):
        return []
    out: list[str] = []
    for item in suggestions:
        if isinstance(item, str):
            cleaned = item.strip()
            if cleaned:
                out.append(cleaned[:200])
        if len(out) >= 1:  # single best suggestion for inline ghost-text UX
            break
    return out


@socketio.on("disconnect")
def on_disconnect():
    return None
