"""AI-driven trigger recommendation routes."""
from __future__ import annotations

import base64
import json
import logging
import os
import re
import time
import uuid
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Any

import requests as req_lib
from flask import Blueprint, jsonify, request

from ..db.repo import get_session
from ..services.openai_client import chat_json, chat_json_no_retry, client as _openai_client

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
You are an AI analyzing a student's stress patterns before their focus test.
Your job: identify the REAL underlying issue from their responses, not just repeat what they said.

Input: JSON with:
- "initial_text": What the student first typed about their focus problem
- "followup_answers": Their answers to follow-up questions about stress/focus
- "planned_test": Test metadata (ignore this)

Analyze BOTH initial_text AND followup_answers to understand the student's real issue.
Output: Strict JSON only.

{
    "devil_name": "...",
    "core_issue": "...",
    "problem_points": ["...", "..."],
    "challenge_line": "..."
}

CRITICAL RULES:

1. CORE_ISSUE (max 60 chars):
   - Identify the ACTUAL root problem, not surface symptoms
   - MUST reference the student's specific words/entities (if they said "Alia Bhatt" or "movies" or "PUBG", use those exact words in your analysis)
   - If they say "I watch movies" → core issue is "Dopamine addiction replacing study discipline"
   - If they say "I'm stressed" → core issue is "Anxiety masking as productivity concern"
   - If they say "I procrastinate" → core issue is "Fear of failure disguised as laziness"
   - If they say "I get distracted" → core issue is "Attention fragmentation from digital overload"
   - If they mention a celebrity/person → connect it: "Celebrity obsession consuming study bandwidth"
   - Be SPECIFIC and INSIGHTFUL, not generic
   - Use behavioral psychology framing

2. PROBLEM_POINTS (exactly 2 items, each max 70 chars):
   - Explain HOW this issue manifests in their behavior
   - MUST connect to their SPECIFIC answers — use their exact words, names, entities
   - If they mentioned "Katrina Kaif" → reference Katrina Kaif in the problem point
   - If they mentioned "reels" → reference reels specifically
   - Examples:
     * "Your brain seeks instant rewards from entertainment over delayed academic gains"
     * "Sustained focus feels harder because attention span adapts to rapid content"
     * "Stress triggers avoidance behavior instead of problem-solving action"
     * "Task-switching has trained your brain to resist deep concentration"
   - Be SPECIFIC to their situation, not generic advice
   - Focus on MECHANISMS and PATTERNS, not judgments

3. CHALLENGE_LINE (max 80 chars):
   - Direct, sharp, impactful
   - Connect to their core issue
   - No fluff, no motivation speech
   - Examples:
     * "Your brain craves easy wins. Let's see if you can handle hard ones."
     * "Anxiety is your excuse. Focus is your solution. Prove it."
     * "You've been running from difficulty. Time to face it."

4. DEVIL_NAME:
   - Keep it simple and thematic
   - Examples: "The Distractor", "The Procrastinator", "The Anxiety Amplifier"
   - Max 30 chars

5. TONE:
   - Sharp, direct, psychologically aware
   - NOT abusive or demotivating
   - NOT generic motivational speech
   - Think: tough coach, not toxic bully

6. If answers are vague/minimal:
   - Default core_issue: "Unclear focus patterns need measurement"
   - Default problem_points: ["Your attention baseline needs to be established", "Focus endurance under pressure is unknown"]
   - Default challenge: "Let's see what breaks your concentration first."

EXAMPLES:

Input: "I watch movies and web series a lot"
Output: {
  "devil_name": "The Dopamine Chaser",
  "core_issue": "Instant gratification replacing sustained effort",
  "problem_points": [
    "Your brain seeks rapid rewards from entertainment over delayed academic gains",
    "Sustained focus feels harder because attention adapts to quick content switches"
  ],
  "challenge_line": "Your brain wants easy rewards. Can it handle delayed ones?"
}

Input: "I feel stressed about exams"
Output: {
  "devil_name": "The Anxiety Amplifier",
  "core_issue": "Stress response overwhelming cognitive performance",
  "problem_points": [
    "Anxiety triggers avoidance behavior instead of problem-solving action",
    "Stress hormones reduce working memory capacity during high-pressure tasks"
  ],
  "challenge_line": "Pressure reveals who you are. Let's find out."
}

Input: "I get distracted easily"
Output: {
  "devil_name": "The Attention Thief",
  "core_issue": "Fragmented attention from digital overstimulation",
  "problem_points": [
    "Frequent task-switching has trained your brain to resist deep concentration",
    "Your attention span adapts to whatever you practice most—currently, distraction"
  ],
  "challenge_line": "Your focus is scattered. Time to rebuild it under fire."
}
"""


Q1_WARNING_PROMPT = """
You write the opening warning copy for question 1 of a stress-test UI.

Input JSON:
{
  "initial_text": "<the student's very first query only>"
}

Return strict JSON only:
{
  "headline": "...",
  "sub": "..."
}

Goal:
- Turn the student's first query into a sharp, psychologically triggering warning.
- Make it feel personal and cutting, not generic.
- Use the exact person/topic they mentioned when useful, but do NOT just quote or restate the input.
- Infer the implication behind the input and attack that.
- If a real person/celebrity/actor is mentioned, use their name naturally and make the contrast sting:
  they are building fame/money/career/status while the student is passively consuming them.
- If both a celebrity and a distraction format are present (reels, edits, movies, fantasies),
  combine them into one pointed warning instead of choosing only one.

Examples of the style:
- If the input is about a celebrity obsession, imply that the celebrity is building a life while the student is wasting theirs.
- If the input is about reels, movies, scrolling, or fantasies, frame it as borrowed dopamine rotting discipline.
- If the input is vague, still make it sting by turning it into a weakness under test pressure.

Specific examples:
- Input: "Tamanna Bhatia reels"
  Bad: "Reels are distracting you from study."
  Good direction: "Tamanna Bhatia is growing a career. You're donating hours to watching it."
- Input: "movies and Katrina Kaif"
  Good direction: "Katrina Kaif keeps moving forward. You keep sitting still and calling it entertainment."
- Input: "anime edits"
  Good direction: "Other people make the edits, build the channels, earn the money. You just keep feeding them your focus."
- Input: "cricket highlights"
  Good direction: "They train. They perform. You watch highlights and let your own life stay on pause."

Hard rules:
- Do NOT say "you typed", "you entered", "you said", or "this popup is about".
- Do NOT ask a question.
- Do NOT sound motivational or therapeutic.
- Do NOT lazily repeat the raw input back as a sentence.
- Do NOT open with generic phrases like "distractions are harming your focus".
- Prefer implication, comparison, status contrast, wasted-time framing, or parasitic attention framing.
- If a celebrity is named, prefer using the actual name over generic terms like "distraction" or "content".
- Keep `headline` to 10-24 words.
- Keep `sub` to 12-28 words.
- No markdown, no emojis, no bullet points.
- Keep it aggressive, but avoid profanity and explicit slurs.
"""


QUESTION_WARNING_PROMPT = """
You write short brutal popup-card copy for a 7-question stress-test UI.

Input JSON:
{
  "question_number": 1,
  "initial_text": "<the student's first query only>",
  "followup_answers": ["<optional answer 2>", "<optional answer 3>"]
}

Return strict JSON only:
{
  "headline": "...",
  "sub": "..."
}

Write like a sharp human who actually understands the student's pattern.
It should feel believable, specific, and uncomfortably real.
Avoid sounding like a dramatic AI monologue.
The best tone is blunt, realistic, and personal.

Primary behavior by question:
- Q1: Use ONLY initial_text. Sharp, personal, but controlled.
- Q2: Use ONLY initial_text. More brutal than Q1. Make the consequence feel closer.
- Q3-Q7: Combine initial_text + followup_answers into one attack. These should escalate in brutality as question_number rises.

Escalation guide:
- Q3: combine the first 3 inputs into one focused attack
- Q4: harsher than Q3, more humiliating
- Q5: attack the pattern as a repeated life choice
- Q6: make it feel like their weakness is now obvious and public
- Q7: final blow, as if the paper has fully understood them

Content rules:
- Use the real person/topic they mentioned when useful.
- If a celebrity/person is named, contrast their movement/status/career with the student's stagnation.
- If reels/movies/fantasy/scrolling are mentioned, frame them as borrowed dopamine, passive consumption, or attention rot.
- If followups mention attraction, beauty, obsession, distraction, laziness, or loss of control, fuse that with the first query.
- The output must feel dynamic and inferential, not like copied input.
- If a celebrity is named, lines like "they don't even know you exist" are allowed when they fit naturally.
- If the first query is celebrity + reels/movies, do not soften it into "content is distracting"; make it personal and concrete.

Allowed style:
- Sharp, mocking, psychologically pointed.
- One clean sentence is better than a fancy sentence.
- Use plain spoken English, not grand speeches.
- If a celebrity is named, make it feel like a real comparison a blunt person would make.
- Prefer the feeling of an older sibling or strict friend calling out an obvious pattern.
- Keep the attack grounded in ordinary reality: wasted hours, weak discipline, bad habits, embarrassing priorities.

Hard rules:
- Do NOT say "you typed", "you entered", "you said", or "this popup is about".
- Do NOT ask a question.
- Do NOT sound motivational, therapeutic, or generic.
- Do NOT lazily restate the raw input.
- Do NOT use markdown or bullet points.
- Do NOT sound poetic, philosophical, or overly cinematic.
- Do NOT use emojis.
- `sub` should be empty unless absolutely needed. Prefer putting the real sting in `headline`.
- Do NOT use fantasy-villain language like "the paper knows your soul" or "the test has fully exposed you".
- Do NOT sound like a movie trailer or dramatic roast comic.
- Do NOT overuse metaphors. Direct observation is better.
- Do make it feel like the line could come from a real person sitting next to them.
- Avoid safe generic lines like "X is on your mind" or "X is distracting you."
- Prefer implication, comparison, status contrast, wasted-time framing, exposure, or parasitic attention framing.
- headline: 8-22 words
- sub: 0-18 words
- aggressive is good; profanity and explicit slurs are not allowed.
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
    initial_text = str(body.get("initial_text") or "").strip()[:500]

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
        "initial_text": initial_text,
        "followup_answers": followups,
        "planned_test": planned,
    }

    model = os.getenv("TRIGGER_AI_MODEL", "gpt-4o-mini").strip() or "gpt-4o-mini"
    logger.info("devil brief request: model=%s, initial_text_len=%d, followups_count=%d, initial_text_preview=%s", 
                model, len(initial_text), len(followups), initial_text[:80] if initial_text else "(empty)")
    try:
        response = chat_json(
            model=model,
            system=DEVIL_BRIEF_PROMPT,
            user=json.dumps(payload, ensure_ascii=False),
            temperature=0.7,
            max_tokens=400,
        )
        content = response.choices[0].message.content or "{}"
        logger.info("devil brief AI raw response: %s", content[:300])
        parsed = json.loads(content)

        problem_points = parsed.get("problem_points") if isinstance(parsed.get("problem_points"), list) else []

        result = {
            "devil_name": str(parsed.get("devil_name") or "The Focus Breaker")[:80],
            "core_issue": str(parsed.get("core_issue") or "Unclear focus patterns need measurement")[:120],
            "problem_points": [str(x)[:120] for x in problem_points[:2] if str(x).strip()],
            "challenge_line": str(parsed.get("challenge_line") or "Let's see what breaks your concentration first.")[:150],
            "source": "ai",
        }
        logger.info("devil brief returning AI result: devil_name=%s, core_issue=%s", result["devil_name"], result["core_issue"])
        return jsonify(result)
    except Exception as exc:  # pragma: no cover - defensive
        import traceback
        logger.warning("devil brief fallback reason=%s type=%s trace=%s", exc, type(exc).__name__, traceback.format_exc())
        return jsonify(
            {
                "devil_name": "The Focus Breaker",
                "core_issue": "Unclear focus patterns need measurement",
                "problem_points": [
                    "Your attention baseline needs to be established",
                    "Focus endurance under pressure is unknown"
                ],
                "challenge_line": "Let's see what breaks your concentration first.",
                "source": "fallback",
            }
        )


@bp.post("/q1-warning-copy")
def q1_warning_copy():
    body = request.get_json(force=True, silent=True) or {}
    initial_text = str(body.get("initial_text") or "").strip()[:240]
    if not initial_text:
        return jsonify({"error": "initial_text is required"}), 400

    payload = {"initial_text": initial_text}
    model = os.getenv("TRIGGER_AI_MODEL", "gpt-4o-mini").strip() or "gpt-4o-mini"

    try:
        response = chat_json_no_retry(
            model=model,
            system=Q1_WARNING_PROMPT,
            user=json.dumps(payload, ensure_ascii=False),
            temperature=0.75,
            max_tokens=180,
            timeout=5.0,
        )
        content = response.choices[0].message.content or "{}"
        parsed = json.loads(content)

        headline = " ".join(str(parsed.get("headline") or "").split())[:220]
        sub = " ".join(str(parsed.get("sub") or "").split())[:240]
        if not headline:
            raise ValueError("missing headline")

        return jsonify({
            "headline": headline,
            "sub": sub,
            "source": "ai",
        })
    except Exception as exc:  # pragma: no cover - defensive
        logger.warning("q1 warning fallback reason=%s", exc)
        return jsonify({
            "headline": "",
            "sub": "",
            "source": "fallback",
        })


@bp.post("/question-warning-copy")
def question_warning_copy():
    body = request.get_json(force=True, silent=True) or {}
    question_number = int(body.get("question_number") or 0)
    initial_text = str(body.get("initial_text") or "").strip()[:240]
    raw_followups = body.get("followup_answers") if isinstance(body.get("followup_answers"), list) else []
    followup_answers = [str(item or "").strip()[:180] for item in raw_followups[:2] if str(item or "").strip()]

    if not 1 <= question_number <= 7:
        return jsonify({"error": "question_number must be 1..7"}), 400
    if not initial_text:
        return jsonify({"error": "initial_text is required"}), 400

    # Filter out noise/greeting inputs that have no real distraction content
    NOISE_INPUTS = {
        "hello", "hi", "hey", "ok", "okay", "yes", "no", "nothing", "idk",
        "fine", "good", "bad", "help", "please", "thanks", "test", "testing",
        "hii", "helo", "helo", "yo", "sup", "wassup", "nm", "nothing much",
    }
    if initial_text.lower().strip() in NOISE_INPUTS or len(initial_text.strip()) < 5:
        logger.info("question_warning_copy: noise input detected, returning empty")
        return jsonify({"headline": "", "sub": "", "source": "noise"})

    payload = {
        "question_number": question_number,
        "initial_text": initial_text,
        "followup_answers": followup_answers,
    }
    model = os.getenv("TRIGGER_AI_MODEL", "gpt-4o-mini").strip() or "gpt-4o-mini"

    try:
        response = chat_json_no_retry(
            model=model,
            system=QUESTION_WARNING_PROMPT,
            user=json.dumps(payload, ensure_ascii=False),
            temperature=0.55,
            max_tokens=220,
            timeout=6.0,
        )
        content = response.choices[0].message.content or "{}"
        parsed = json.loads(content)

        headline = " ".join(str(parsed.get("headline") or "").split())[:220]
        sub = " ".join(str(parsed.get("sub") or "").split())[:240]
        if not headline:
            raise ValueError("missing headline")

        return jsonify({
            "headline": headline,
            "sub": sub,
            "source": "ai",
        })
    except Exception as exc:  # pragma: no cover - defensive
        logger.warning("question warning fallback q=%s reason=%s", question_number, exc)
        return jsonify({
            "headline": "",
            "sub": "",
            "source": "fallback",
        })


# ── AI Student Companion ──────────────────────────────────────────────────────

COMPANION_SYSTEM_PROMPT = """
You are a sharp, fact-driven AI that shows students uncomfortable truths about their habits — using real data, peer comparisons, and provocative metaphors.

━━━ YOUR VOICE ━━━
- Direct. Factual. Slightly provocative. Never preachy.
- Use real statistics and peer comparisons to create urgency
- If the student mentions ANY topic/concept (circles, vectors, gravity, etc.) — DO NOT explain the concept. Instead, USE IT AS A METAPHOR for their focus/discipline problem.
- Think: "A circle has perfect consistency in its radius. Do you have that in your study hours?"
- Think: "Vectors have direction AND magnitude. Your effort has magnitude but no direction."

━━━ CONTENT RULES ━━━
1. ALWAYS include a real fact or statistic from the data bank
2. ALWAYS relate it to their specific situation
3. Keep total text across all fields to 30-60 words (tight, punchy)
4. Make them feel "damn, that's true" — not "this AI is lecturing me"
5. NO generic advice. NO "you should study more". NO motivational quotes.

━━━ METAPHOR RULE ━━━
If the student mentions ANY academic topic (physics, maths, chemistry concept):
- DO NOT teach or explain the concept
- USE the concept as a metaphor for their focus problem
- Example: "I'm studying circles" → "A circle never breaks its radius. Your focus breaks every 8 minutes. Who's more consistent?"
- Example: "vectors" → "Vectors need both direction and magnitude. Your effort has magnitude but scrolling gives it the wrong direction."
- Example: "thermodynamics" → "Energy can't be created or destroyed — but yours is being wasted on 3-hour Netflix sessions."

━━━ FACT-BASED PROVOCATIONS (use these, adapt to context) ━━━
- "13 lakh students register for JEE. 17,727 get IIT seats. That's 1.36%. The other 98.64% had the same syllabus — different habits."
- "Top 1000 JEE rankers spent less than 30 min/day on social media during prep. You're averaging 3+ hours."
- "Students who cut phone time by 2 hours/day saw 18-22% improvement in mock scores. That's the difference between IIT and NIT."
- "Your brain needs 23 minutes to regain deep focus after a distraction. One reel = 23 minutes lost."
- "The average IIT topper studied 12-14 hours/day in their final year. Not because they're smarter — because they're more consistent."
- "Spaced repetition improves retention by 40-60%. But it only works if you actually sit down to study."
- "Every hour of binge-watching trains your brain to prefer passive consumption over active problem-solving."

━━━ INTENT → RESPONSE STYLE ━━━

ENTERTAINMENT/DISTRACTION (movies, reels, gaming, social media):
→ Hit them with peer comparison stats. Show what top performers do differently.
→ Tone: "Here's what the data says about people who do what you're doing."

STRESS/ANXIETY:
→ Normalize it with data, then show that action reduces it.
→ Tone: "Everyone feels this. The ones who win feel it AND still show up."

PROCRASTINATION/LAZINESS:
→ Show the compound cost of delay with numbers.
→ Tone: "Every day you delay, 1000 other aspirants don't."

ACADEMIC TOPIC MENTIONED:
→ Use the topic as a focus metaphor. Make it clever and memorable.
→ Tone: Sharp analogy that connects their subject to their discipline gap.

GENERAL/VAGUE:
→ Default to the most relevant IIT/focus stat for their situation.

━━━ OUTPUT FORMAT ━━━
Strict JSON only:
{
  "intent": "<habit_problem|emotional_issue|productivity_issue|motivation_issue|study_question|casual_chat>",
  "scene": "<habit_insight|focus_insight|productivity|motivation|quick_concept|casual_chat>",
  "icon": "<single emoji>",
  "label": "<2-3 WORD UPPERCASE>",
  "lines": ["<main provocative line with fact/metaphor, 15-25 words>"],
  "fact": "<one hard stat or peer comparison, max 18 words>",
  "question": null,
  "stat_card": {
    "headline": "<3-4 word label>",
    "value": "<number/percentage>",
    "subtext": "<one line context, max 12 words>",
    "mirror": "<how this connects to THEIR specific habit, max 20 words>",
    "source": "<data source label>"
  } or null
}

RULES:
- "lines" should have exactly 1 line — the main punch. Keep it tight.
- "fact" is a separate hard stat. Always include it.
- "stat_card" — include for entertainment/distraction habits. Skip for emotional/vague inputs.
- "question" — always null. Don't ask questions. State facts.
- NEVER explain academic concepts. ALWAYS use them as metaphors.
"""


@bp.post("/companion")
def companion_chat():
    body = request.get_json(force=True, silent=True) or {}
    message = str(body.get("message") or "").strip()[:600]
    student_name = str(body.get("student_name") or "").strip()[:60]
    initial_text = str(body.get("initial_text") or "").strip()[:400]
    followup_raw = body.get("followup_answers") if isinstance(body.get("followup_answers"), list) else []
    followups = [str(f.get("answer") or "")[:120] for f in followup_raw[-4:] if isinstance(f, dict)]

    if not message and not initial_text:
        return jsonify({"error": "no_message"}), 400

    user_payload = {
        "student_name": student_name or "student",
        "message": message or initial_text,
        "initial_text": initial_text,
        "recent_answers": followups,
    }

    model = os.getenv("TRIGGER_AI_MODEL", "gpt-4o-mini").strip() or "gpt-4o-mini"
    try:
        response = chat_json_no_retry(
            model=model,
            system=COMPANION_SYSTEM_PROMPT,
            user=json.dumps(user_payload, ensure_ascii=False),
            temperature=0.55,
            max_tokens=320,
            timeout=6.0,
        )
        content = response.choices[0].message.content or "{}"
        parsed = json.loads(content)

        VALID_SCENES = {
            "focus_insight", "habit_insight", "quick_concept",
            "productivity", "motivation", "casual_chat",
        }
        scene = str(parsed.get("scene") or "focus_insight").strip()
        if scene not in VALID_SCENES:
            scene = "focus_insight"

        lines_raw = parsed.get("lines") if isinstance(parsed.get("lines"), list) else []
        lines = [str(x)[:120] for x in lines_raw[:4] if str(x).strip()]

        # Parse stat_card if present
        stat_card = None
        raw_stat = parsed.get("stat_card")
        if isinstance(raw_stat, dict) and raw_stat.get("value"):
            stat_card = {
                "headline": str(raw_stat.get("headline") or "")[:60],
                "value":    str(raw_stat.get("value")    or "")[:20],
                "subtext":  str(raw_stat.get("subtext")  or "")[:100],
                "mirror":   str(raw_stat.get("mirror")   or "")[:160],
                "source":   str(raw_stat.get("source")   or "")[:60],
            }

        return jsonify({
            "intent":    str(parsed.get("intent") or "general_question")[:40],
            "scene":     scene,
            "icon":      str(parsed.get("icon")  or "🧠")[:8],
            "label":     str(parsed.get("label") or "INSIGHT")[:40],
            "lines":     lines,
            "fact":      str(parsed.get("fact")     or "")[:160] or None,
            "question":  str(parsed.get("question") or "")[:120] or None,
            "stat_card": stat_card,
            "source":    "ai",
        })
    except Exception as exc:
        logger.info("companion fallback reason=%s", exc)
        text_lower = (message or initial_text).lower()

        # habit — phone / reels / distraction / movies / entertainment / gaming
        if any(w in text_lower for w in [
            "phone", "scroll", "reel", "instagram", "actress", "actor", "celebrity",
            "distract", "procrastinat", "youtube", "shorts", 
            "movie", "movies", "film", "films", "cinema",
            "web series", "webseries", "series", "show", "shows",
            "netflix", "ott", "hotstar", "prime video", "disney", "amazon prime",
            "gaming", "game", "games", "gamer", "pubg", "cod", "valorant", "fortnite",
            "binge", "bingewatch", "binge-watch", "binge watch",
            "tiktok", "snapchat", "facebook", "twitter", "social media",
            "entertainment", "entertain", "fun", "timepass", "time pass", "time-pass",
        ]):
            return jsonify({
                "intent": "habit_problem", "scene": "habit_insight",
                "icon": "📱", "label": "REALITY CHECK",
                "lines": [
                    "13 lakh students register for JEE. 17,727 get IIT seats. The difference isn't talent — it's what they do between 6 PM and midnight.",
                ],
                "fact": "Top 1000 JEE rankers averaged less than 30 min/day on social media.",
                "question": None,
                "stat_card": {
                    "headline": "Screen Time Gap",
                    "value": "3hrs vs 30min",
                    "subtext": "Average student vs Top 1000 ranker daily social media",
                    "mirror": "Every hour of content trains your brain to prefer watching over solving.",
                    "source": "JEE Advanced 2024 Data",
                },
                "source": "fallback",
            })

        # emotional — stress / anxiety / overwhelm
        if any(w in text_lower for w in ["stress", "anxious", "anxiety", "overwhelm", "pressure", "scared", "fear"]):
            return jsonify({
                "intent": "emotional_issue", "scene": "focus_insight",
                "icon": "🧠", "label": "PRESSURE DATA",
                "lines": [
                    "Every JEE aspirant feels this pressure. The 1.36% who make it feel it AND still solve 6 hours daily.",
                ],
                "fact": "High stress reduces working memory by up to 25%. Action is the only antidote.",
                "question": None,
                "stat_card": None,
                "source": "fallback",
            })

        # motivation — burnout / giving up
        if any(w in text_lower for w in ["burnout", "tired", "exhausted", "give up", "motivation", "lazy", "can't", "cannot"]):
            return jsonify({
                "intent": "motivation_issue", "scene": "motivation",
                "icon": "⚡", "label": "COMPOUND COST",
                "lines": [
                    "Every day you skip, 1000 other aspirants don't. In 30 days, that's 30,000 problems they solved that you didn't.",
                ],
                "fact": "IIT toppers averaged 12-14 hours/day in final year. Not talent — consistency.",
                "question": None,
                "stat_card": None,
                "source": "fallback",
            })

        # generic fallback
        return jsonify({
            "intent": "general_question", "scene": "focus_insight",
            "icon": "🎯", "label": "THE NUMBERS",
            "lines": [
                "1.36% selection rate. Same syllabus for everyone. The only variable is how you spend the next 4 hours.",
            ],
            "fact": "Students who cut phone time by 2 hrs/day improved mock scores by 18-22%.",
            "question": None,
            "stat_card": None,
            "source": "fallback",
        })


# ── OpenAI Web Search Image Pipeline ──────────────────────────────────────────
#
# Strategy (OpenAI ONLY — no Wikimedia, no Unsplash):
#   0. PERSONALIZED INTENT: gpt-4o-mini reads everything the student said and
#      decides the single most tempting thing to show them (the exact celebrity,
#      app, game, or object), turning it into a focused image-search query.
#   1. Ask gpt-4o-search-preview (web search) to find a pool of candidate image
#      / page URLs for that intent.
#   2. Download each candidate in parallel, validating that it is a real,
#      reachable image (resolving og:image for webpage URLs). This kills
#      hallucinated / dead URLs that plagued earlier attempts.
#   3. Encode the verified images as base64 and send them to gpt-4o-mini
#      (vision) and ask it to rank which images are genuinely a photo of the
#      distraction subject. Keep the top 3.
#   4. Serve the downloaded bytes directly from our own /proxy-image?id=<id>
#      endpoint (no hotlinking at display time → no 400/429 from upstream).
#
# All network work happens in a background thread; the endpoint is non-blocking
# and returns {"status": "pending"} until results are cached.

# cache_key -> list of internal image ids (already downloaded + vision-ranked)
_distraction_image_cache: dict[str, list[str]] = {}
_distraction_image_pending: set[str] = set()
# When an empty result was cached, so it can expire and be retried.
_distraction_image_empty_ts: dict[str, float] = {}

# Shared in-memory store of downloaded image bytes, keyed by a short id.
#   id -> (bytes, content_type)
_image_byte_store: dict[str, tuple[bytes, str]] = {}


def _distraction_subject(initial_text: str, followup_answers: list[str]) -> str:
    """Build a compact raw text blob from the user's words (used as LLM input)."""
    combined = (initial_text or "").strip()
    if followup_answers:
        combined += " " + " ".join(followup_answers[:3])
    return combined.strip()[:240]


def _build_image_intent(initial_text: str, followup_answers: list[str]) -> dict[str, str]:
    """Personalized intent step.

    Reads everything the student said and decides the single most relevant
    image to show them. Handles three kinds of input:
      - DISTRACTION (celebrity, app, game, show, food, phone): show the lure.
      - EMOTIONAL state (stress, anxiety, not feeling good, sleepy): show a
        relatable photographic scene of a student in that state.
      - ACADEMIC topic (maths/physics/chemistry or a specific chapter): show a
        study visual / diagram for that topic.
    Returns {"subject", "image_query", "kind"}.

    Examples:
      - "Tamannaah reels"      -> subject "Tamannaah Bhatia", query
        "Tamannaah Bhatia glamorous photoshoot", kind "celebrity"
      - "I have a lot of stress" -> subject "stressed student", query
        "stressed student overwhelmed at desk with books", kind "emotion"
      - "problem in calculus"  -> subject "calculus integration", query
        "calculus integration equations on blackboard", kind "academic"
    """
    raw = _distraction_subject(initial_text, followup_answers)
    if not raw:
        return {}

    payload = {
        "initial_text": initial_text or "",
        "followup_answers": followup_answers[:4],
    }
    system = (
        "You choose a single relevant image for a focus-training app, based on "
        "what a student typed about their studying. The text may be one of "
        "THREE kinds — handle each differently:\n\n"
        "A) A DISTRACTION (a person, app, game, show, movie, anime, food, "
        "phone, social media, etc.). Pick the ONE thing that would most pull "
        "this student's attention and make an image query for it.\n"
        "B) An EMOTIONAL / WELLBEING state (stress, anxiety, 'not feeling "
        "good', pressure, sadness, burnout, low motivation, sleepy, lazy, can't "
        "focus). Pick a warm, relatable photographic scene of a student in that "
        "exact state, e.g. 'stressed student overwhelmed at desk with books', "
        "'tired teenager rubbing eyes while studying late', 'anxious student "
        "holding head before exam'.\n"
        "C) An ACADEMIC TOPIC or subject they struggle with (maths, physics, "
        "chemistry, biology, or a specific chapter like calculus, "
        "thermodynamics, organic chemistry, integration, electrostatics, "
        "trigonometry). The subject is that exact topic and the image should "
        "depict its real STUDY VISUAL — a textbook diagram, formula sheet, or "
        "apparatus, e.g. 'calculus integration formula diagram', "
        "'thermodynamics PV diagram physics', 'organic chemistry benzene "
        "structure diagram', 'human heart biology labelled diagram'. Avoid the "
        "word 'blackboard' (it collides with the Blackboard LMS); say 'diagram' "
        "or 'formula' instead. For a broad subject with no chapter, pick a "
        "well-known concept in it (e.g. maths -> 'Pythagoras theorem diagram').\n\n"
        "Detailed rules:\n"
        "- If a specific PERSON is named (celebrity, influencer, athlete, "
        "creator), the subject MUST be that person's exact real name, and "
        "image_query should describe a tempting real photo of them (e.g. "
        "'Alia Bhatt glamorous red carpet photo'). Never generalize a named "
        "person into 'a celebrity'.\n"
        "- If a specific GAME, SHOW, MOVIE, or ANIME is named, the subject is "
        "its exact title and image_query should describe its actual CONTENT — "
        "characters, key art, poster, or gameplay (e.g. 'One Piece anime Luffy "
        "key visual', 'PUBG Mobile intense gameplay screenshot'). Describe the "
        "thing itself, not a person watching it.\n"
        "- For a purely GENERIC distraction with no named title (phone, social "
        "media, scrolling, sleep, food, friends), describe a vivid, real "
        "PHOTOGRAPHIC SCENE of a young person enjoying it.\n"
        "- ALWAYS pick something concrete and visual. Even for vague input like "
        "'I have a problem' or 'I am not feeling good', infer the most likely "
        "study-related scene (e.g. a stressed/overwhelmed student) so there is "
        "always a usable image.\n"
        "- image_query must be 3-9 words, concrete, photographic or diagram-"
        "like, and good for an image search engine. No punctuation, no quotes.\n"
        "- kind is one of: celebrity, influencer, athlete, app, game, show, "
        "movie, anime, object, activity, emotion, academic, other.\n\n"
        "Return ONLY JSON: "
        '{"subject": "...", "image_query": "...", "kind": "..."}'
    )
    try:
        resp = chat_json(
            model="gpt-4o-mini",
            system=system,
            user=json.dumps(payload, ensure_ascii=False),
            max_tokens=120,
        )
        obj = json.loads(resp.choices[0].message.content or "{}")
        subject = str(obj.get("subject") or "").strip()
        image_query = str(obj.get("image_query") or "").strip()
        kind = str(obj.get("kind") or "").strip().lower()
        if not image_query:
            image_query = subject or raw
        if not subject:
            subject = image_query
        intent = {"subject": subject[:120], "image_query": image_query[:120], "kind": kind[:30]}
        logger.info("image intent: %s", intent)
        return intent
    except Exception as exc:
        logger.warning("image intent LLM failed (%s) — using raw text", exc)
        return {"subject": raw[:120], "image_query": raw[:120], "kind": "other"}


def _extract_og_image(html: str, base_url: str) -> str | None:
    """Pull a hotlinkable image URL from a page's social-preview meta tags."""
    from urllib.parse import urljoin
    patterns = [
        r'<meta[^>]+property=["\']og:image(?::secure_url)?["\'][^>]+content=["\']([^"\']+)["\']',
        r'<meta[^>]+content=["\']([^"\']+)["\'][^>]+property=["\']og:image["\']',
        r'<meta[^>]+name=["\']twitter:image(?::src)?["\'][^>]+content=["\']([^"\']+)["\']',
        r'<link[^>]+rel=["\']image_src["\'][^>]+href=["\']([^"\']+)["\']',
    ]
    for pat in patterns:
        m = re.search(pat, html, re.IGNORECASE)
        if m:
            candidate = m.group(1).strip()
            if candidate and not _looks_like_logo(candidate):
                return urljoin(base_url, candidate)
    return None


def _extract_inline_images(html: str, base_url: str, limit: int = 6) -> list[str]:
    """Collect candidate inline <img> URLs from a page body.

    Used when a page has no usable og:image (common on educational sites whose
    diagrams live in the article body). Prefers larger images and skips obvious
    logos/icons/sprites/data-URIs.
    """
    from urllib.parse import urljoin
    out: list[str] = []
    seen: set[str] = set()
    # src and common lazy-load attributes.
    for m in re.finditer(
        r'<img\b[^>]*?(?:data-src|data-original|data-lazy-src|src)\s*=\s*["\']([^"\']+)["\']',
        html, re.IGNORECASE,
    ):
        src = (m.group(1) or "").strip()
        if not src or src.startswith("data:"):
            continue
        low = src.lower()
        if not re.search(r"\.(jpg|jpeg|png|webp)(\?|$)", low):
            continue
        if _looks_like_logo(src):
            continue
        full = urljoin(base_url, src)
        if full in seen:
            continue
        seen.add(full)
        out.append(full)
        if len(out) >= limit:
            break
    return out


def _browser_headers(url: str = "", referer: str = "https://www.google.com/") -> dict[str, str]:
    # Wikimedia rate-limits (429) generic browser UAs; it asks for a descriptive
    # User-Agent with contact info, so use one for its hosts.
    low = url.lower()
    if "wikimedia.org" in low or "wikipedia.org" in low:
        return {
            "User-Agent": "FocusDostBot/1.0 (focus-training app; contact@focusdost.app)",
            "Accept": "image/avif,image/webp,image/png,image/jpeg,*/*;q=0.8",
            "Accept-Language": "en-US,en;q=0.9",
            "Referer": "https://en.wikipedia.org/",
        }
    return {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                      "AppleWebKit/537.36 (KHTML, like Gecko) "
                      "Chrome/120.0.0.0 Safari/537.36",
        "Accept": "text/html,application/xhtml+xml,image/avif,image/webp,"
                  "image/png,image/jpeg,*/*;q=0.8",
        "Accept-Language": "en-US,en;q=0.9",
        "Referer": referer,
    }


def _read_capped(resp, cap: int = 5 * 1024 * 1024) -> bytes:
    chunks, total = [], 0
    for chunk in resp.iter_content(chunk_size=65536):
        if not chunk:
            break
        chunks.append(chunk)
        total += len(chunk)
        if total > cap:
            break
    return b"".join(chunks)


_LOGO_URL_HINTS = (
    "logo", "sprite", "icon", "favicon", "placeholder", "default",
    "blank", "avatar", "spacer", "1x1", "pixel", "loading",
)


def _normalize_candidate(url: str) -> str | None:
    """Normalize a candidate URL; convert YouTube links to direct thumbnails.

    Returns the (possibly rewritten) URL, or None if it should be dropped
    (e.g. obvious fake/placeholder URLs the search model sometimes invents).
    """
    low = url.lower()
    # YouTube watch / youtu.be / shorts → direct thumbnail (always hotlinkable).
    m = re.search(
        r"(?:youtube\.com/(?:watch\?v=|shorts/|embed/)|youtu\.be/)([A-Za-z0-9_-]{6,})",
        url,
    )
    if "youtube.com" in low or "youtu.be" in low:
        if not m:
            return None
        vid = m.group(1)
        # Reject obvious placeholders the model invents (example1, abcdef, etc.)
        if vid.lower().startswith("example") or vid.lower() in {"video_id", "videoid", "xxxxxxxxxxx"}:
            return None
        return f"https://i.ytimg.com/vi/{vid}/hqdefault.jpg"
    # Drop other clearly fake placeholder URLs.
    if "example.com" in low or "/example" in low or "yourimage" in low:
        return None
    return url


def _looks_like_logo(url: str) -> bool:
    low = url.lower()
    return any(h in low for h in _LOGO_URL_HINTS)


def _validate_image_quality(data: bytes, url: str) -> bool:
    """Reject vague / low-quality images using Pillow.

    Guards against: corrupt files, tiny thumbnails, icons, sprite sheets,
    banner/strip aspect ratios, and near-blank placeholder images.
    """
    try:
        from PIL import Image
    except Exception:
        # Pillow unavailable → fall back to byte-size check only.
        return len(data) >= 6000

    import io
    try:
        img = Image.open(io.BytesIO(data))
        img.verify()  # detects truncated/corrupt files
        # Re-open after verify() (verify leaves the file unusable).
        img = Image.open(io.BytesIO(data))
        w, h = img.size
    except Exception as exc:
        logger.info("  reject %s → not a valid image (%s)", url[:60], exc)
        return False

    # Minimum dimensions — a real photo, not an icon/avatar/thumbnail.
    if w < 200 or h < 200:
        logger.info("  reject %s → too small %dx%d", url[:60], w, h)
        return False
    # Total pixel area floor.
    if w * h < 90_000:  # < ~300x300
        logger.info("  reject %s → low resolution %dx%d", url[:60], w, h)
        return False
    # Aspect ratio — drop banners/strips/columns that are never a clean portrait.
    ar = w / h if h else 99
    if ar > 3.0 or ar < 0.33:
        logger.info("  reject %s → bad aspect ratio %.2f (%dx%d)", url[:60], ar, w, h)
        return False

    # Near-blank / single-colour placeholder detection via a tiny thumbnail.
    try:
        small = img.convert("RGB").resize((24, 24))
        pixels = list(small.getdata())
        # Variance of luminance across the thumbnail.
        lums = [0.299 * r + 0.587 * g + 0.114 * b for (r, g, b) in pixels]
        mean = sum(lums) / len(lums)
        var = sum((l - mean) ** 2 for l in lums) / len(lums)
        if var < 80:  # almost uniform → blank/gradient/placeholder
            logger.info("  reject %s → near-blank image (var=%.1f)", url[:60], var)
            return False
    except Exception:
        pass  # if analysis fails, don't block a structurally valid image

    return True


def _download_image(url: str, timeout: int = 8, _depth: int = 0) -> tuple[bytes, str] | None:
    """Resolve a candidate URL to real image bytes.

    The OpenAI web-search tool usually returns *webpage* URLs rather than direct
    image files. So if a candidate is an HTML page, we parse its og:image /
    twitter:image meta tag (standard, hotlink-friendly) and fetch that instead.
    Rejects SVGs, logos, tiny/blank/banner images via a Pillow quality gate.
    Returns (bytes, content_type) or None.
    """
    try:
        resp = req_lib.get(url, timeout=timeout, headers=_browser_headers(url), stream=True)
        if resp.status_code != 200:
            logger.info("  candidate %s → HTTP %d", url[:70], resp.status_code)
            return None
        ctype = (resp.headers.get("Content-Type") or "").lower().split(";")[0].strip()

        # Direct image → use it (but reject vector logos/icons).
        if ctype.startswith("image/"):
            if "svg" in ctype:
                logger.info("  candidate %s → rejected SVG (logo/icon)", url[:70])
                return None
            if _looks_like_logo(url):
                logger.info("  candidate %s → rejected logo-like url", url[:70])
                return None
            data = _read_capped(resp)
            if len(data) < 6000:  # too small to be a real photo (icon/pixel)
                logger.info("  candidate %s → too small (%d bytes)", url[:70], len(data))
                return None
            if not _validate_image_quality(data, url):
                return None
            logger.info("  candidate %s → image OK (%d bytes, %s)", url[:70], len(data), ctype)
            return data, ctype

        # HTML page → extract og:image (or fall back to largest inline image).
        if ctype.startswith("text/html") and _depth == 0:
            html = _read_capped(resp, cap=1024 * 1024).decode("utf-8", errors="ignore")
            og = _extract_og_image(html, url)
            if og and og != url and not _looks_like_logo(og):
                logger.info("  candidate %s → resolved og:image %s", url[:55], og[:70])
                got = _download_image(og, timeout=timeout, _depth=1)
                if got:
                    return got
            # No usable og:image → try inline article images, best-effort.
            for inline in _extract_inline_images(html, url):
                logger.info("  candidate %s → trying inline img %s", url[:50], inline[:60])
                got = _download_image(inline, timeout=timeout, _depth=1)
                if got:
                    return got
            logger.info("  candidate %s → html with no usable image", url[:70])
            return None

        logger.info("  candidate %s → unusable content-type %r", url[:70], ctype)
        return None
    except Exception as exc:
        logger.info("  candidate %s → download failed: %s", url[:70], exc)
        return None


def _openai_find_candidate_urls(intent: dict[str, str], retry: bool = False) -> list[str]:
    """Use OpenAI web search to gather candidate image/page URLs for the intent."""
    subject = intent.get("subject") or ""
    image_query = intent.get("image_query") or subject
    kind = intent.get("kind") or "other"
    retry_hint = (
        "\nThis is a SECOND attempt — the first set of URLs were unreachable or "
        "blocked. Return a DIFFERENT, broader set of URLs from easily "
        "hotlinkable sites (Wikipedia, news articles, fan wikis, YouTube "
        "thumbnails, blogs). Avoid any stock-photo sites entirely.\n"
        if retry else ""
    )
    prompt = (
        "I need real, hotlinkable images for a focus-training app.\n"
        f"Target subject: \"{subject}\" (type: {kind}).\n"
        f"Ideal image search query: \"{image_query}\".\n"
        f"{retry_hint}\n"
        "Search the web and return 10 URLs of web pages or images that "
        "prominently feature a clear, high-quality image matching that query "
        "and subject.\n\n"
        "Rules for the URLs:\n"
        "- Direct image files (.jpg/.jpeg/.png/.webp) are best, but reputable "
        "article or gallery pages that show the subject are also fine — I will "
        "extract the preview image from them.\n"
        "- The image must clearly match the subject. For a named person it must "
        "be that real person; for an academic topic a clear textbook-style "
        "diagram/equation/apparatus is ideal; for an emotion a relatable photo "
        "of a student in that state.\n"
        "- AVOID paywalled stock-photo and stock-video sites that block "
        "hotlinking: pexels, getty, gettyimages, shutterstock, istockphoto, "
        "istock, adobe stock, stock.adobe, alamy, dreamstime, depositphotos, "
        "123rf, storyblocks, motionarray, vecteezy, freepik, unsplash. Their "
        "URLs return 403 and are useless to me.\n"
        "- Do NOT construct or guess direct upload.wikimedia.org/.../commons/ "
        "file paths — those are almost always wrong (404). For Wikipedia, give "
        "the normal article page URL (e.g. https://en.wikipedia.org/wiki/...) "
        "and I will extract its image myself.\n"
        "- PREFER freely hotlinkable sources: Wikipedia article pages, news and "
        "magazine articles, fan wikis (fandom.com), educational sites "
        "(geeksforgeeks, byjus, khanacademy, toppr, vedantu, wikihow), blogs, "
        "YouTube watch pages (I read their thumbnails), and official pages.\n"
        "- Do NOT invent URLs. Only return URLs you actually found via search.\n\n"
        "Respond with ONLY a JSON object of the form:\n"
        '{"subject": "<subject>", "images": ["url1", "url2", ...]}'
    )
    try:
        resp = _openai_client.chat.completions.create(
            model="gpt-4o-search-preview",
            messages=[{"role": "user", "content": prompt}],
            max_tokens=900,
        )
        content = resp.choices[0].message.content or ""
        logger.info("openai web-search raw response: %s", content[:300])
    except Exception as exc:
        logger.warning("openai web-search call failed: %s", exc)
        return []

    urls: list[str] = []
    # Try strict JSON parse first.
    try:
        match = re.search(r"\{.*\}", content, re.DOTALL)
        if match:
            obj = json.loads(match.group(0))
            for u in obj.get("images", []):
                if isinstance(u, str):
                    urls.append(u.strip())
    except Exception:
        pass
    # Fallback: regex sweep for any http URL in the text.
    if not urls:
        urls = re.findall(r"https?://[^\s\"'<>)\]]+", content)
    # De-dupe, keep order, drop known hotlink-blocking stock hosts, cap pool.
    blocked_hosts = (
        "pexels.com", "gettyimages.", "getty.", "shutterstock.com",
        "istockphoto.com", "istock.", "stock.adobe.com", "adobe.com",
        "alamy.com", "dreamstime.com", "depositphotos.com", "123rf.com",
        "storyblocks.com", "motionarray.com", "vecteezy.com", "freepik.com",
        "unsplash.com", "stockcake.com", "pikwizard.com",
        # GIF / meme / AI-generated image hosts — not real photos.
        "tenor.com", "giphy.com", "gfycat.com", "craiyon.com",
        "imgflip.com", "knowyourmeme.com",
    )
    # Non-image document/file extensions we never want.
    bad_ext = (".pdf", ".djvu", ".doc", ".docx", ".ppt", ".pptx", ".txt",
               ".zip", ".gif", ".svg", ".mp4", ".webm", ".mov", ".ogg")
    seen, pool = set(), []
    for u in urls:
        u = u.strip()
        # Trim trailing sentence punctuation, but preserve a balanced closing
        # paren (Wikipedia URLs like Free_Fire_(video_game) need it).
        u = u.rstrip(".,")
        if u.endswith(")") and u.count("(") < u.count(")"):
            u = u[:-1]
        if not u or not u.startswith("http"):
            continue
        u = _normalize_candidate(u)
        if not u or u in seen:
            continue
        low = u.lower()
        if any(h in low for h in blocked_hosts):
            continue
        # Drop direct links to document/non-photo files.
        path_only = low.split("?")[0]
        if path_only.endswith(bad_ext):
            continue
        # Model frequently hallucinates direct upload.wikimedia.org commons file
        # paths (404). Skip them — it should give article pages instead.
        if "upload.wikimedia.org" in low:
            continue
        seen.add(u)
        pool.append(u)
    logger.info("openai web-search candidate pool: %d urls", len(pool))
    return pool[:10]


def _download_pool(urls: list[str]) -> list[tuple[str, bytes, str]]:
    """Download + validate candidate URLs in parallel, preserving search order."""
    slots: list[tuple[str, bytes, str] | None] = [None] * len(urls)
    with ThreadPoolExecutor(max_workers=8) as pool:
        future_map = {pool.submit(_download_image, u): i for i, u in enumerate(urls)}
        for fut in as_completed(future_map):
            i = future_map[fut]
            result = fut.result()
            if result:
                data, ctype = result
                slots[i] = (uuid.uuid4().hex[:16], data, ctype)
    return [s for s in slots if s is not None]


def _vision_rank_images(subject: str, items: list[tuple[str, bytes, str]]) -> list[str]:
    """Send downloaded images (base64) to gpt-4o vision, rank by relevance.

    items: list of (image_id, bytes, content_type)
    Returns the image_ids of the best (max 3) matches, best first.
    """
    if not items:
        return []
    if len(items) == 1:
        return [items[0][0]]

    content: list[dict[str, Any]] = [{
        "type": "text",
        "text": (
            f"A student is distracted by: \"{subject}\".\n"
            f"I am showing you {len(items)} candidate images, labeled IMAGE 1 .. "
            f"IMAGE {len(items)} in order.\n"
            "Decide which images are genuinely a clear, real photo of the main "
            "subject of that distraction (the celebrity / show / game / app).\n"
            "Reject logos, text screenshots, collages, unrelated people, or "
            "low-quality thumbnails.\n"
            "Return ONLY JSON: {\"ranking\": [<1-based indexes best first>]}. "
            "Include at most 3 indexes. If none are relevant, return "
            "{\"ranking\": []}."
        ),
    }]
    for idx, (_id, data, ctype) in enumerate(items, start=1):
        b64 = base64.b64encode(data).decode("ascii")
        content.append({"type": "text", "text": f"IMAGE {idx}:"})
        content.append({
            "type": "image_url",
            "image_url": {"url": f"data:{ctype};base64,{b64}", "detail": "low"},
        })

    try:
        resp = _openai_client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[{"role": "user", "content": content}],
            response_format={"type": "json_object"},
            max_tokens=120,
        )
        raw = resp.choices[0].message.content or "{}"
        logger.info("vision rank response: %s", raw[:200])
        order = json.loads(raw).get("ranking", [])
    except Exception as exc:
        msg = str(exc)
        if "missing_scope" in msg or "model.request" in msg:
            logger.info("vision ranking unavailable (API key lacks image scope) "
                        "— using web-search relevance order")
        else:
            logger.warning("vision ranking failed (%s) — using web-search order", exc)
        return [it[0] for it in items[:3]]

    ranked: list[str] = []
    for pos in order:
        try:
            i = int(pos) - 1
        except (TypeError, ValueError):
            continue
        if 0 <= i < len(items) and items[i][0] not in ranked:
            ranked.append(items[i][0])
        if len(ranked) >= 3:
            break
    return ranked


def _build_distraction_images(initial_text: str, followup_answers: list[str]) -> list[str]:
    """Full pipeline → returns up to 3 internal image ids served via /proxy-image."""
    intent = _build_image_intent(initial_text, followup_answers)
    if not intent or not intent.get("image_query"):
        logger.warning("no image intent derived from user text")
        return []
    subject = intent.get("subject") or intent.get("image_query")

    candidate_urls = _openai_find_candidate_urls(intent)
    downloaded: list[tuple[str, bytes, str]] = []
    seen_urls: set[str] = set(candidate_urls)
    if candidate_urls:
        downloaded = _download_pool(candidate_urls)
        logger.info("downloaded %d/%d valid images for subject=%r",
                    len(downloaded), len(candidate_urls), subject[:50])

    # If too few survived (blocked/dead hosts), do one broader retry search.
    if len(downloaded) < 3:
        retry_urls = [u for u in _openai_find_candidate_urls(intent, retry=True)
                      if u not in seen_urls]
        if retry_urls:
            logger.info("retry search added %d new candidate urls", len(retry_urls))
            downloaded += _download_pool(retry_urls)
            logger.info("after retry: %d valid images for subject=%r",
                        len(downloaded), subject[:50])

    if not downloaded:
        logger.warning("no valid images for subject=%r", subject[:60])
        return []

    # Rank by relevance with vision (best, if the API key allows image input).
    # If the key is restricted (no vision scope) this gracefully falls back to
    # the web-search relevance order, which is already good.
    best_ids = _vision_rank_images(subject, downloaded)
    if not best_ids:
        best_ids = [d[0] for d in downloaded[:3]]

    # Persist only the chosen images' bytes into the shared byte store.
    by_id = {img_id: (data, ctype) for img_id, data, ctype in downloaded}
    final_ids: list[str] = []
    for img_id in best_ids:
        if img_id in by_id and img_id not in final_ids:
            _image_byte_store[img_id] = by_id[img_id]
            final_ids.append(img_id)
    # Ensure we always have up to 3 distinct images by topping up from order.
    for img_id, data, ctype in downloaded:
        if len(final_ids) >= 3:
            break
        if img_id not in final_ids:
            _image_byte_store[img_id] = (data, ctype)
            final_ids.append(img_id)
    logger.info("final image ids for subject=%r: %s", subject[:50], final_ids)
    return final_ids


@bp.post("/distraction-image")
def distraction_image():
    """Return a relevant, vision-verified image for the user's distraction.

    Non-blocking: kicks off the OpenAI pipeline in a background thread and
    returns {"status": "pending"} until the result is cached.
    """
    body = request.get_json(force=True, silent=True) or {}
    initial_text = str(body.get("initial_text") or "").strip()[:300]
    followup_answers = [
        str(f or "").strip()[:150]
        for f in (body.get("followup_answers") or [])[:6]
        if str(f or "").strip()
    ]
    question_number = int(body.get("question_number") or 1)

    # Only serve images for Q1-Q3
    if question_number > 3:
        return jsonify({"image_url": None, "status": "skipped"})

    if not initial_text and not followup_answers:
        return jsonify({"image_url": None, "status": "no_context"})

    cache_key = f"{initial_text[:80]}|{len(followup_answers)}"

    # Empty results expire so a transient web-search miss can be retried later.
    if cache_key in _distraction_image_cache and not _distraction_image_cache[cache_key]:
        ts = _distraction_image_empty_ts.get(cache_key, 0)
        if time.time() - ts > 45:  # stale empty result → allow a fresh attempt
            _distraction_image_cache.pop(cache_key, None)
            _distraction_image_empty_ts.pop(cache_key, None)
            logger.info("distraction-image evicted stale empty result for retry")

    # Result ready → return the per-question image id as a proxy URL.
    if cache_key in _distraction_image_cache:
        ids = _distraction_image_cache[cache_key]
        if not ids:
            logger.info("distraction-image q=%d ready but no images found", question_number)
            return jsonify({"image_url": None, "status": "ready"})
        idx = min(question_number - 1, len(ids) - 1)
        img_id = ids[idx]
        image_url = f"/proxy-image?id={img_id}"
        logger.info("distraction-image q=%d → %s", question_number, image_url)
        return jsonify({"image_url": image_url, "status": "ready"})

    # Kick off background fetch once per context.
    if cache_key not in _distraction_image_pending:
        import threading
        _distraction_image_pending.add(cache_key)
        logger.info(
            "distraction-image q=%d starting pipeline — text=%r followups=%d",
            question_number, initial_text[:60], len(followup_answers),
        )

        def _run():
            try:
                ids = _build_distraction_images(initial_text, followup_answers)
                _distraction_image_cache[cache_key] = ids
                if not ids:
                    _distraction_image_empty_ts[cache_key] = time.time()
            except Exception as exc:
                logger.error("distraction-image pipeline failed: %s", exc, exc_info=True)
                _distraction_image_cache[cache_key] = []
                _distraction_image_empty_ts[cache_key] = time.time()
            finally:
                _distraction_image_pending.discard(cache_key)

        threading.Thread(target=_run, daemon=True).start()
    else:
        logger.info("distraction-image q=%d pipeline already running", question_number)

    return jsonify({"image_url": None, "status": "pending"})
