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
    """Keyword-based completions to keep UX fast and offline."""
    bank: list[str] = []

    def add(*msgs: str) -> None:
        for msg in msgs:
            if msg not in bank:
                bank.append(msg)

    if any(word in text for word in ["exam", "test", "paper", "deadline", "time"]):
        add(
            "Exams are close and I feel I have too little time to revise properly.",
            "My mock tests are inconsistent and it's stressing me out.",
        )
    if any(word in text for word in ["phone", "scroll", "reel", "shorts", "game", "gaming"]):
        add(
            "I keep picking up my phone and losing hours on reels.",
            "Gaming sessions at night are killing my sleep and study rhythm.",
        )
    if any(word in text for word in ["parent", "mom", "dad", "family"]):
        add(
            "My parents expect a top score and I'm scared to disappoint them.",
        )
    if any(word in text for word in ["compare", "friend", "topper", "rank"]):
        add(
            "I keep comparing myself with friends and feel I'm always behind.",
        )
    if any(word in text for word in ["motivation", "burnout", "tired", "drained"]):
        add(
            "I'm feeling burnt out and it's hard to stay motivated.",
        )
    if any(word in text for word in ["backlog", "pending", "syllabus", "left"]):
        add(
            "There's a backlog of chapters piling up and I don't know where to start.",
        )

    if not bank:
        add(
            "I'm overwhelmed and not sure how to manage everything right now.",
            "I feel stuck and need a clear plan to get back on track.",
        )

    return bank[:1]  # single best suggestion for inline ghost-text UX


def _generate_ai_suggestions(text: str) -> list[str]:
    """Use OpenAI chat completion to propose concise suggestions."""
    system = (
        "You suggest a single completion for a student stress vent.\n"
        "Return ONLY a JSON object: {\"suggestions\": [\"<one short sentence>\"]}\n"
        "Max 100 chars. No markdown."
    )
    user = f"Partial: {text[:300]}\nComplete their thought in 1 natural first-person sentence."
    resp = openai_client.chat_json_no_retry(
        model="gpt-4o-mini",
        system=system,
        user=user,
        max_tokens=60,
        temperature=0.5,
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
