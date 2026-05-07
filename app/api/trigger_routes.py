"""AI-driven trigger recommendation routes."""
from __future__ import annotations

import json
import logging
import os
import time
from typing import Any

from flask import Blueprint, jsonify, request

from ..db.repo import get_session
from ..services.openai_client import chat_json, chat_json_no_retry

logger = logging.getLogger(__name__)

bp = Blueprint("triggers", __name__, url_prefix="/api/triggers")


ALLOWED_TRIGGERS = {
    "optionShuffle",
    "phantomCompetitor",
    "stressTimer",
    "confidenceBreaker",
    "mirageHighlight",
    "blurAttack",
    "screenFlip",
    "colorInversion",
    "heartbeatVibration",
    "waveDistortion",
    "fakeMentorCount",
    "chaosBackground",
    "shepardTone",
    "spatialTicking",
    "fakeLowBattery",
    "fakeCrashScreen",
    "blackout",
    "hesitationHeatmap",
}


EVENT_ALIASES = {
    "hover_hesitation": "interaction_hesitation",
}


EVENT_PRIORITY = {
    "wrong_answer": ["confidenceBreaker", "stressTimer", "phantomCompetitor"],
    "answer_changed": ["optionShuffle", "hesitationHeatmap", "mirageHighlight"],
    "interaction_hesitation": ["mirageHighlight", "hesitationHeatmap", "stressTimer"],
    "long_hesitation": ["phantomCompetitor", "stressTimer", "spatialTicking"],
    "idle_resumed": ["blurAttack", "chaosBackground"],
    "feedback_topic_selected": ["chaosBackground"],
    "time_pressure": ["heartbeatVibration", "stressTimer", "fakeLowBattery", "spatialTicking"],
    "question_loaded": ["fakeMentorCount", "phantomCompetitor"],
    "submit_attempt": ["spatialTicking", "stressTimer"],
    "context_switched": ["chaosBackground", "fakeMentorCount"],
    "device_agitation": ["spatialTicking", "shepardTone", "stressTimer"],
    "high_tap_intensity": ["confidenceBreaker", "stressTimer", "optionShuffle"],
}


PHASES = ("baseline", "escalation", "crucible", "final_sprint")
PHASE_TRIGGER_ALLOWLIST = {
    "baseline": {
        "mirageHighlight",
        "hesitationHeatmap",
        "optionShuffle",
        "phantomCompetitor",
        "fakeMentorCount",
        "stressTimer",
    },
    "escalation": {
        "mirageHighlight",
        "hesitationHeatmap",
        "phantomCompetitor",
        "fakeMentorCount",
        "stressTimer",
        "confidenceBreaker",
        "optionShuffle",
    },
    "crucible": {
        "mirageHighlight",
        "hesitationHeatmap",
        "phantomCompetitor",
        "fakeMentorCount",
        "stressTimer",
        "confidenceBreaker",
        "optionShuffle",
        "spatialTicking",
        "colorInversion",
        "blurAttack",
        "waveDistortion",
        "screenFlip",
        "chaosBackground",
        "shepardTone",
    },
    "final_sprint": ALLOWED_TRIGGERS,
}


TRIGGER_INTENSITY_HINTS = {
    "optionShuffle": "low",
    "mirageHighlight": "low",
    "hesitationHeatmap": "low",
    "confidenceBreaker": "medium",
    "phantomCompetitor": "medium",
    "stressTimer": "medium",
    "fakeMentorCount": "medium",
    "spatialTicking": "medium",
    "waveDistortion": "medium",
    "heartbeatVibration": "medium",
    "blurAttack": "high",
    "screenFlip": "high",
    "colorInversion": "high",
    "chaosBackground": "high",
    "shepardTone": "high",
    "fakeLowBattery": "high",
    "fakeCrashScreen": "high",
    "blackout": "high",
}


EMOTION_TRIGGER_PRIORITY = {
    "doubt": ["confidenceBreaker", "optionShuffle", "mirageHighlight"],
    "overload": ["chaosBackground", "shepardTone", "waveDistortion", "blurAttack"],
    "urgency": ["stressTimer", "heartbeatVibration", "spatialTicking", "fakeLowBattery"],
    "steady": [],
}


TRIGGER_COST_BY_INTENSITY = {
    "low": 8,
    "medium": 15,
    "high": 25,
}


ALLOWED_INTENSITIES = {"low", "medium", "high"}
ALLOWED_STATES = {"HIGH_PERFORMANCE", "HIGH_STRESS", "LOW_ENGAGEMENT", "NORMAL_STATE"}
ALLOWED_SPEED = {"fast", "normal", "slow"}
ALLOWED_CONFIDENCE_TREND = {"rising", "falling", "unstable", "unknown"}
ALLOWED_EFFECTIVENESS_DELTA = {"improved", "degraded", "unchanged", "unknown"}
ALLOWED_STRESS_RESPONSE = {"increased", "decreased", "unchanged", "unknown"}


SYSTEM_PROMPT = """
You are an AI Trigger Policy Engine for a real-time student assessment backend.
You are NOT a chatbot.
You MUST behave as a deterministic decision system.

Primary goal:
- Select at most one trigger from available_triggers.
- Improve engagement and decision quality without over-stimulation.

Hard requirements:
- Use ONLY trigger names present in available_triggers.
- If no intervention is needed, return trigger_name="" and timeout_ms=0.
- Output STRICT JSON only. No markdown. No extra text.
- Prefer stable decisions for similar inputs. Avoid randomness.

Input notes:
- recent_triggers may contain either strings or structured objects.
- context includes platform, test_phase, time_remaining_seconds, current_stress_budget.
- emotion_target is a precomputed target from backend heuristics.
- user_state.feedback_topic_preference and student_preferences.preferred_interest_topic indicate
    the student's chosen interest for future content.

Orchestration behavior:
- Respect test_phase pacing. In early phases, keep interventions subtle.
- Use emotion_target to bias selection:
  - doubt -> confidenceBreaker/optionShuffle style
  - overload -> chaos/shepard/wave style
  - urgency -> timer/ticking/haptic urgency style
- If conflicting signals or weak confidence, choose no trigger.
- If preferred interest topic exists, bias toward non-repetitive medium-intensity triggers
    for suitable events (especially context_switch/idle/distraction-style moments).

Safety:
- Never stack multiple triggers.
- Avoid immediate repeat behavior.
- Keep interventions conservative for high-stress/low-confidence situations.

Output STRICT JSON only with this schema:
{
    "trigger_name": "<name or empty>",
    "timeout_ms": <integer>,
    "reason": "<short machine-readable reason>",
    "intensity": "low|medium|high",
    "reason_code": "<machine_code>",
    "metrics": {
        "speed_state": "fast|normal|slow",
        "stress_score": <0..1>,
        "state": "HIGH_PERFORMANCE|HIGH_STRESS|LOW_ENGAGEMENT|NORMAL_STATE",
        "confidence_trend": "rising|falling|unstable|unknown"
    },
    "learning_update": {
        "effectiveness_delta": "improved|degraded|unchanged|unknown",
        "stress_response": "increased|decreased|unchanged|unknown"
    },
    "suggested_trigger": null | "<string>"
}

Output constraints:
- trigger_name MUST be empty or present in available_triggers.
- timeout_ms must be 0 when trigger_name is empty.
- timeout_ms must be 2500..12000 when trigger_name is non-empty.
- No keys outside this schema.
"""


DEVIL_BRIEF_PROMPT = """
You are writing a creative, dramatic pre-test briefing from a devil persona.
Use student follow-up answers and planned trigger policy context.

Output strict JSON only:
{
    "devil_name": "...",
    "intro": "...",
    "taunt": "...",
    "problems": ["...", "..."],
    "design_points": ["..."],
    "challenge_lines": ["..."]
}

Rules:
- Keep tone creative and dramatic, but not abusive.
- Problems: Maximum 2 items, each under 80 chars. These should be OBSERVATIONS about the user's actual situation/stress, NOT challenges or questions. State what you noticed from their answers (e.g., "You mentioned struggling with time management", "Your focus drops when multiple tasks pile up"). Do NOT ask questions or challenge them here.
- Design_points: Only 1 line, under 100 chars. Brief summary of what triggers/strategies we planned based on their problems.
- Challenge_lines: Only 1 line, under 100 chars. This is where you can be dramatic and challenging.
- Intro: One sentence under 120 chars, referencing their actual responses.
- Taunt: One sentence under 100 chars, connected to what they shared.
- Do not mention medical diagnosis.
- If user gave minimal/unclear answers, keep problems general but as observations, not questions.
- Problems = what you observed. Design_points = what we planned (1 line only). Challenge_lines = the dare.
"""


def _clamp_timeout(value: Any, default_value: int = 5200) -> int:
    try:
        num = int(value)
    except Exception:
        num = default_value
    return max(2500, min(12000, num))


def _safe_float(value: Any, default_value: float = 0.0) -> float:
    try:
        return float(value)
    except Exception:
        return default_value


def _clamp01(value: Any, default_value: float = 0.0) -> float:
    num = _safe_float(value, default_value)
    if num < 0:
        return 0.0
    if num > 1:
        return 1.0
    return num


def _safe_int(value: Any, default_value: int = 0) -> int:
    try:
        return int(float(value))
    except Exception:
        return default_value


def _canonical_event_name(raw: str) -> str:
    name = raw.strip().lower()
    if not name:
        return ""
    return EVENT_ALIASES.get(name, name)


def _phase_for_elapsed(elapsed_seconds: int) -> str:
    if elapsed_seconds <= 90:
        return "baseline"
    if elapsed_seconds <= 300:
        return "escalation"
    if elapsed_seconds <= 600:
        return "crucible"
    return "final_sprint"


def _phase_rank(phase: str) -> int:
    ranks = {
        "baseline": 0,
        "escalation": 1,
        "crucible": 2,
        "final_sprint": 3,
    }
    return ranks.get(phase, 0)


def _phase_by_rank(rank: int) -> str:
    if rank >= 3:
        return "final_sprint"
    if rank >= 2:
        return "crucible"
    if rank >= 1:
        return "escalation"
    return "baseline"


def _phase_for_submissions(total_submissions: int) -> str:
    count = max(0, int(total_submissions))
    if count <= 2:
        return "baseline"
    if count <= 8:
        return "escalation"
    if count <= 16:
        return "crucible"
    return "final_sprint"


def _normalize_context(
    raw_context: dict[str, Any],
    extra: dict[str, Any],
    user_state: dict[str, Any],
    telemetry: dict[str, Any],
    metrics: dict[str, Any],
) -> dict[str, Any]:
    platform = str(raw_context.get("platform") or extra.get("platform") or "web").strip().lower()
    if platform not in {"web", "android"}:
        platform = "web"

    elapsed_seconds = _safe_int(
        raw_context.get("elapsed_seconds"),
        _safe_int(extra.get("elapsed_seconds"), 0),
    )

    if elapsed_seconds <= 0:
        time_remaining_ms = _safe_int(
            user_state.get("time_remaining_ms"),
            _safe_int(raw_context.get("time_remaining_seconds"), 0) * 1000,
        )
        if time_remaining_ms > 0:
            elapsed_seconds = max(0, int((900000 - time_remaining_ms) / 1000))

    time_remaining_seconds = _safe_int(
        raw_context.get("time_remaining_seconds"),
        _safe_int(user_state.get("time_remaining_ms"), 0) // 1000,
    )
    if time_remaining_seconds <= 0 and elapsed_seconds > 0:
        time_remaining_seconds = max(0, 900 - elapsed_seconds)

    inferred_elapsed_phase = _phase_for_elapsed(elapsed_seconds)
    inferred_progress_phase = _phase_for_submissions(
        _safe_int(metrics.get("total_submissions"), 0)
    )
    inferred_phase = _phase_by_rank(
        max(_phase_rank(inferred_elapsed_phase), _phase_rank(inferred_progress_phase))
    )

    phase = str(raw_context.get("test_phase") or "").strip().lower()
    if phase in PHASES:
        phase = _phase_by_rank(max(_phase_rank(phase), _phase_rank(inferred_phase)))
    else:
        phase = inferred_phase

    budget_raw = raw_context.get("current_stress_budget")
    if budget_raw is None:
        budget_raw = telemetry.get("current_stress_budget")
    if budget_raw is None:
        budget_raw = extra.get("current_stress_budget")
    stress_budget = max(0, min(100, _safe_int(budget_raw, 100)))

    return {
        "platform": platform,
        "elapsed_seconds": max(0, elapsed_seconds),
        "time_remaining_seconds": max(0, time_remaining_seconds),
        "test_phase": phase,
        "current_stress_budget": stress_budget,
    }


def _phase_allowed_triggers(phase: str, available: list[str]) -> list[str]:
    allow = PHASE_TRIGGER_ALLOWLIST.get(phase) or ALLOWED_TRIGGERS
    return [name for name in available if name in allow]


def _classify_emotion_target(
    metrics: dict[str, Any],
    user_state: dict[str, Any],
    telemetry: dict[str, Any],
) -> str:
    recent_accuracy = _clamp01(
        telemetry.get("recent_accuracy"),
        _clamp01(metrics.get("recent_accuracy"), 0.5),
    )
    answer_latency_ms = _safe_int(
        user_state.get("answer_latency_ms"),
        _safe_int(telemetry.get("response_time_ms"), 0),
    )
    interaction_hesitation_ms = _safe_int(
        telemetry.get("interaction_hesitation_ms"),
        _safe_int(user_state.get("time_on_question_ms"), 0),
    )
    agitation = _safe_int(telemetry.get("device_movement_index"), 0)

    speed_fast = answer_latency_ms > 0 and answer_latency_ms <= 3500
    speed_slow = answer_latency_ms >= 9000 or interaction_hesitation_ms >= 1200

    if speed_fast and recent_accuracy >= 0.75:
        return "doubt"
    if (speed_fast and recent_accuracy <= 0.5) or (agitation >= 4 and recent_accuracy < 0.65):
        return "overload"
    if speed_slow and interaction_hesitation_ms >= 1000:
        return "urgency"
    return "steady"


def _normalize_recent_triggers(raw_recent: Any) -> list[Any]:
    if not isinstance(raw_recent, list):
        return []
    cleaned: list[Any] = []
    for item in raw_recent[-20:]:
        if isinstance(item, str):
            name = item.strip()
            if name:
                cleaned.append(name)
            continue
        if not isinstance(item, dict):
            continue
        entry: dict[str, Any] = {}
        trigger_name = str(item.get("trigger") or item.get("trigger_name") or "").strip()
        if trigger_name:
            entry["trigger"] = trigger_name
        intensity = str(item.get("intensity") or "").strip().lower()
        if intensity in ALLOWED_INTENSITIES:
            entry["intensity"] = intensity
        if isinstance(item.get("timestamp"), (int, float)):
            entry["timestamp"] = int(item["timestamp"])
        for key in ("pre_metrics", "post_metrics", "recovery_metrics"):
            raw_metrics = item.get(key)
            if not isinstance(raw_metrics, dict):
                continue
            entry[key] = {
                "time_spent": _safe_float(raw_metrics.get("time_spent"), 0.0),
                "confidence": _clamp01(raw_metrics.get("confidence"), 0.0),
                "accuracy": bool(raw_metrics.get("accuracy", False)),
            }
        if "recovery_score" in item:
            entry["recovery_score"] = _safe_float(item.get("recovery_score"), 1.0)
        if entry:
            cleaned.append(entry)
    return cleaned


def _load_session_feedback(session_id: str) -> tuple[list[Any], dict[str, Any]]:
    if not session_id:
        return ([], {})
    session = get_session(session_id)
    if not session:
        return ([], {})
    meta = dict(session.meta or {})
    feedback = meta.get("trigger_feedback") if isinstance(meta.get("trigger_feedback"), dict) else {}
    recent = _normalize_recent_triggers(feedback.get("recent_triggers"))
    effectiveness_raw = feedback.get("effectiveness") if isinstance(feedback.get("effectiveness"), dict) else {}
    effectiveness: dict[str, Any] = {}
    for name, data in effectiveness_raw.items():
        if not isinstance(name, str) or not isinstance(data, dict):
            continue
        level = str(data.get("level") or "medium").strip().lower()
        if level not in ALLOWED_INTENSITIES:
            level = "medium"
        effectiveness[name] = level
    return (recent, effectiveness)


def _normalize_ai_decision(parsed: dict[str, Any], available: list[str]) -> dict[str, Any]:
    trigger_name = str(parsed.get("trigger_name") or "").strip()
    if trigger_name and trigger_name not in available:
        trigger_name = ""

    timeout_ms = _clamp_timeout(parsed.get("timeout_ms"), 5200) if trigger_name else 0
    reason = str(parsed.get("reason") or "ai_decision")[:160]

    intensity = str(parsed.get("intensity") or "low").strip().lower()
    if intensity not in ALLOWED_INTENSITIES:
        intensity = "low"

    reason_code = str(parsed.get("reason_code") or "ai_decision")[:80]

    raw_metrics = parsed.get("metrics") if isinstance(parsed.get("metrics"), dict) else {}
    speed_state = str(raw_metrics.get("speed_state") or "normal").strip().lower()
    if speed_state not in ALLOWED_SPEED:
        speed_state = "normal"
    state = str(raw_metrics.get("state") or "NORMAL_STATE").strip().upper()
    if state not in ALLOWED_STATES:
        state = "NORMAL_STATE"
    confidence_trend = str(raw_metrics.get("confidence_trend") or "unknown").strip().lower()
    if confidence_trend not in ALLOWED_CONFIDENCE_TREND:
        confidence_trend = "unknown"
    stress_score = _clamp01(raw_metrics.get("stress_score"), 0.0)

    raw_learning = parsed.get("learning_update") if isinstance(parsed.get("learning_update"), dict) else {}
    effectiveness_delta = str(raw_learning.get("effectiveness_delta") or "unknown").strip().lower()
    if effectiveness_delta not in ALLOWED_EFFECTIVENESS_DELTA:
        effectiveness_delta = "unknown"
    stress_response = str(raw_learning.get("stress_response") or "unknown").strip().lower()
    if stress_response not in ALLOWED_STRESS_RESPONSE:
        stress_response = "unknown"

    suggested_trigger_raw = parsed.get("suggested_trigger")
    suggested_trigger: str | None = None
    if isinstance(suggested_trigger_raw, str):
        candidate = suggested_trigger_raw.strip()
        if candidate and candidate not in available:
            suggested_trigger = candidate[:80]

    return {
        "trigger_name": trigger_name,
        "timeout_ms": timeout_ms,
        "reason": reason,
        "intensity": intensity,
        "reason_code": reason_code,
        "metrics": {
            "speed_state": speed_state,
            "stress_score": stress_score,
            "state": state,
            "confidence_trend": confidence_trend,
        },
        "learning_update": {
            "effectiveness_delta": effectiveness_delta,
            "stress_response": stress_response,
        },
        "suggested_trigger": suggested_trigger,
    }


def _budget_cost_for_trigger(trigger_name: str, intensity: str) -> int:
    normalized_intensity = intensity if intensity in ALLOWED_INTENSITIES else TRIGGER_INTENSITY_HINTS.get(trigger_name, "medium")
    return TRIGGER_COST_BY_INTENSITY.get(normalized_intensity, 15)


def _policy_fallback_decision(
    *,
    available: list[str],
    phase: str,
    emotion_target: str,
    event_priority: list[str],
    emotion_priority: list[str],
    recent_triggers: list[Any],
    effectiveness: dict[str, Any],
    stress_budget: int,
    platform: str,
) -> dict[str, Any]:
    ranked: list[str] = []
    seen: set[str] = set()
    for name in event_priority + emotion_priority + available:
        if name in seen:
            continue
        seen.add(name)
        ranked.append(name)

    now_ms = int(time.time() * 1000)
    recent_window_ms = 120000
    recently_seen: set[str] = set()
    for item in recent_triggers[-30:]:
        if not isinstance(item, dict):
            continue
        name = str(item.get("trigger") or item.get("trigger_name") or "").strip()
        if not name:
            continue
        ts = _safe_int(item.get("timestamp"), 0)
        if ts > 0 and now_ms - ts <= recent_window_ms:
            recently_seen.add(name)

    level_rank = {"high": 3, "medium": 2, "low": 1}

    def sort_key(name: str) -> tuple[int, int, int]:
        recent_penalty = 1 if name in recently_seen else 0
        effect_level = str((effectiveness.get(name) or "")).strip().lower()
        return (recent_penalty, -level_rank.get(effect_level, 2), ranked.index(name))

    ranked = sorted(ranked, key=sort_key)

    for trigger_name in ranked:
        intensity = TRIGGER_INTENSITY_HINTS.get(trigger_name, "medium")
        cost = _budget_cost_for_trigger(trigger_name, intensity)
        if cost > stress_budget:
            continue

        base_timeout = {
            "low": 4200,
            "medium": 5600,
            "high": 6800,
        }.get(intensity, 5200)
        if phase == "baseline":
            base_timeout = min(base_timeout, 5000)
        elif phase == "final_sprint":
            base_timeout = min(7800, base_timeout + 500)

        return {
            "trigger_name": trigger_name,
            "timeout_ms": _clamp_timeout(base_timeout, 5200),
            "reason": "policy_fallback",
            "intensity": intensity,
            "reason_code": f"policy_fallback_{emotion_target}",
            "metrics": {
                "speed_state": "normal",
                "stress_score": 0.5,
                "state": "NORMAL_STATE",
                "confidence_trend": "unknown",
            },
            "learning_update": {
                "effectiveness_delta": "unknown",
                "stress_response": "unchanged",
            },
            "suggested_trigger": None,
            "phase": phase,
            "emotion_target": emotion_target,
            "budget_after": max(0, stress_budget - cost),
            "platform": platform,
            "source": "policy_fallback",
        }

    return _no_trigger_response(
        "policy_fallback_no_candidate",
        "policy_fallback",
        phase=phase,
        emotion_target=emotion_target,
        budget_after=stress_budget,
        platform=platform,
    )


def _no_trigger_response(
    reason: str,
    source: str = "server",
    *,
    phase: str = "baseline",
    emotion_target: str = "steady",
    budget_after: int = 100,
    platform: str = "web",
) -> dict[str, Any]:
    return {
        "trigger_name": "",
        "timeout_ms": 0,
        "reason": reason[:160],
        "intensity": "low",
        "reason_code": reason[:80],
        "metrics": {
            "speed_state": "normal",
            "stress_score": 0.0,
            "state": "NORMAL_STATE",
            "confidence_trend": "unknown",
        },
        "learning_update": {
            "effectiveness_delta": "unknown",
            "stress_response": "unchanged",
        },
        "suggested_trigger": None,
        "phase": phase,
        "emotion_target": emotion_target,
        "budget_after": max(0, min(100, int(budget_after))),
        "platform": platform,
        "source": source,
    }


@bp.post("/recommend")
def recommend_trigger():
    body = request.get_json(force=True, silent=True) or {}

    event_name = _canonical_event_name(str(body.get("event_name") or body.get("event_type") or ""))
    user_state = body.get("user_state") if isinstance(body.get("user_state"), dict) else {}
    student_preferences = body.get("student_preferences") if isinstance(body.get("student_preferences"), dict) else {}
    telemetry = body.get("telemetry") if isinstance(body.get("telemetry"), dict) else {}
    metrics = body.get("metrics") if isinstance(body.get("metrics"), dict) else {}
    context_raw = body.get("context") if isinstance(body.get("context"), dict) else {}
    extra_raw = body.get("extra") if isinstance(body.get("extra"), dict) else {}

    available_raw = body.get("available_triggers") if isinstance(body.get("available_triggers"), list) else []
    available_all = [name for name in available_raw if isinstance(name, str) and name in ALLOWED_TRIGGERS]

    session_id = str(extra_raw.get("session_id") or body.get("session_id") or "").strip()

    context = _normalize_context(context_raw, extra_raw, user_state, telemetry, metrics)
    phase = context["test_phase"]
    platform = context["platform"]
    stress_budget = context["current_stress_budget"]

    if not available_all:
        return jsonify(
            _no_trigger_response(
                "no_available_triggers",
                "server",
                phase=phase,
                budget_after=stress_budget,
                platform=platform,
            )
        )

    available = _phase_allowed_triggers(phase, available_all)
    if not available:
        return jsonify(
            _no_trigger_response(
                "phase_no_available_triggers",
                "server",
                phase=phase,
                budget_after=stress_budget,
                platform=platform,
            )
        )

    if stress_budget < min(TRIGGER_COST_BY_INTENSITY.values()):
        return jsonify(
            _no_trigger_response(
                "budget_exhausted",
                "server",
                phase=phase,
                budget_after=stress_budget,
                platform=platform,
            )
        )

    incoming_recent = _normalize_recent_triggers(body.get("recent_triggers"))
    stored_recent, stored_effectiveness = _load_session_feedback(session_id)
    recent_triggers = (stored_recent + incoming_recent)[-20:]

    emotion_target = _classify_emotion_target(metrics, user_state, telemetry)
    emotion_priority = EMOTION_TRIGGER_PRIORITY.get(emotion_target) or []
    event_priority = EVENT_PRIORITY.get(event_name, [])

    preferred_interest_topic = str(
        student_preferences.get("preferred_interest_topic")
        or user_state.get("feedback_topic_preference")
        or ""
    ).strip().lower()

    if preferred_interest_topic:
        event_priority = [*event_priority]

    payload = {
        "event_name": event_name,
        "event_type": event_name,
        "user_state": user_state,
        "metrics": metrics,
        "telemetry": telemetry,
        "context": context,
        "recent_triggers": recent_triggers,
        "followup_answers": body.get("followup_answers") if isinstance(body.get("followup_answers"), list) else [],
        "available_triggers": available,
        "event_priority": [name for name in event_priority if name in available],
        "emotion_target": emotion_target,
        "emotion_priority": [name for name in emotion_priority if name in available],
        "student_profile": {
            "trigger_effectiveness": stored_effectiveness,
            "preferred_interest_topic": preferred_interest_topic,
        },
        "student_preferences": student_preferences,
        "extra": extra_raw,
    }

    model = os.getenv("TRIGGER_AI_MODEL", "gpt-4o-mini").strip() or "gpt-4o-mini"
    ai_timeout_s_default = max(1.0, min(15.0, _safe_float(os.getenv("TRIGGER_AI_TIMEOUT_S", "5"), 5.0)))
    fast_events = {
        "enter_popups",
        "interaction_hesitation",
        "answer_changed",
        "wrong_answer",
        "time_pressure",
        "context_switched",
    }
    ai_timeout_s_fast = max(1.0, min(8.0, _safe_float(os.getenv("TRIGGER_AI_TIMEOUT_FAST_S", "3.5"), 3.5)))
    ai_timeout_s = ai_timeout_s_fast if event_name in fast_events else ai_timeout_s_default
    try:
        response = chat_json_no_retry(
            model=model,
            system=SYSTEM_PROMPT,
            user=json.dumps(payload, ensure_ascii=False),
            temperature=0.2,
            timeout=ai_timeout_s,
        )
        content = response.choices[0].message.content or "{}"
        parsed = json.loads(content)
        decision = _normalize_ai_decision(parsed if isinstance(parsed, dict) else {}, available)

        trigger_name = decision.get("trigger_name") or ""
        if trigger_name:
            trigger_cost = _budget_cost_for_trigger(trigger_name, str(decision.get("intensity") or "medium"))
            if trigger_cost > stress_budget:
                return jsonify(
                    _no_trigger_response(
                        "budget_gate",
                        "server",
                        phase=phase,
                        emotion_target=emotion_target,
                        budget_after=stress_budget,
                        platform=platform,
                    )
                )
            budget_after = max(0, stress_budget - trigger_cost)
        else:
            budget_after = stress_budget

        decision["phase"] = phase
        decision["emotion_target"] = emotion_target
        decision["budget_after"] = budget_after
        decision["platform"] = platform
        decision["source"] = "ai"
        return jsonify(decision)
    except Exception as exc:  # pragma: no cover - defensive
        logger.warning("trigger recommend policy fallback event=%s reason=%s", event_name, exc)
        return jsonify(
            _policy_fallback_decision(
                available=available,
                phase=phase,
                emotion_target=emotion_target,
                event_priority=[name for name in event_priority if name in available],
                emotion_priority=[name for name in emotion_priority if name in available],
                recent_triggers=recent_triggers,
                effectiveness=stored_effectiveness,
                stress_budget=stress_budget,
                platform=platform,
            )
        )


@bp.post("/devil-brief")
def devil_brief():
    body = request.get_json(force=True, silent=True) or {}
    followups_raw = body.get("followup_answers") if isinstance(body.get("followup_answers"), list) else []
    planned = body.get("planned_test") if isinstance(body.get("planned_test"), dict) else {}

    followups: list[dict[str, str]] = []
    for item in followups_raw[-14:]:
        if not isinstance(item, dict):
            continue
        followups.append(
            {
                "answer": str(item.get("answer") or "")[:280],
                "domain": str(item.get("domain") or "")[:80],
                "slot": str(item.get("slot") or "")[:80],
            }
        )

    payload = {
        "followup_answers": followups,
        "planned_test": planned,
    }

    model = os.getenv("TRIGGER_AI_MODEL", "gpt-4o-mini").strip() or "gpt-4o-mini"
    try:
        response = chat_json(
            model=model,
            system=DEVIL_BRIEF_PROMPT,
            user=json.dumps(payload, ensure_ascii=False),
            temperature=0.6,
        )
        content = response.choices[0].message.content or "{}"
        parsed = json.loads(content)

        problems = parsed.get("problems") if isinstance(parsed.get("problems"), list) else []
        design_points = parsed.get("design_points") if isinstance(parsed.get("design_points"), list) else []
        challenge_lines = parsed.get("challenge_lines") if isinstance(parsed.get("challenge_lines"), list) else []

        return jsonify(
            {
                "devil_name": str(parsed.get("devil_name") or "The Invigilator Devil")[:80],
                "intro": str(parsed.get("intro") or "I studied your responses and designed this test around your pressure points.")[:260],
                "taunt": str(parsed.get("taunt") or "Accept my challenge. I doubt you can beat me.")[:220],
                "problems": [str(x)[:80] for x in problems[:2] if str(x).strip()],
                "design_points": [str(x)[:100] for x in design_points[:1] if str(x).strip()],
                "challenge_lines": [str(x)[:100] for x in challenge_lines[:1] if str(x).strip()],
                "source": "ai",
            }
        )
    except Exception as exc:  # pragma: no cover - defensive
        logger.info("devil brief fallback reason=%s", exc)
        return jsonify(
            {
                "devil_name": "The Invigilator Devil",
                "intro": "I shaped this test from your answers: where you hesitate, where panic rises.",
                "taunt": "Accept my challenge. I know your weak moments; prove me wrong.",
                "problems": [
                    "Your speed drops when doubt creeps in.",
                    "Distractions pull your attention at critical moments.",
                ],
                "design_points": [
                    "Triggers activate on wrong answers, hesitation, and idle patterns.",
                ],
                "challenge_lines": [
                    "Accept this challenge and hold your focus.",
                ],
                "source": "fallback",
            }
        )
