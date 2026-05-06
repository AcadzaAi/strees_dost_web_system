"""Session routes."""
from __future__ import annotations

from datetime import datetime, timezone
import re

from flask import Blueprint, current_app, jsonify, request

from ..db.repo import create_session, get_session, save_session
from ..extensions import socketio
from ..realtime.scheduler import start_popup_simulation
from ..services.combo_answer_parser import PARSERS as COMBO_PARSERS
from ..services.combo_question_generator import generate_combo_question
from ..services.combo_specs import COMBO_SPECS
from ..services.fallbacks import CLARIFIER_QUESTION
from ..services.gpt_client import detect_causes, extract_components
from ..services.openai_client import transcribe_audio
from ..services.planner import (
    activate_domains_from_causes,
    pick_next_slot,
)
from ..services.popup_generator import generate_popups
from ..services.question_generator import (
    ai_ready_to_complete,
    generate_initial_clarifiers,
    generate_next_followup,
    generate_question,
    get_generic_domain_question,
    get_followup_count,
    increment_followup_count,
    reset_followup_count,
    should_show_skip_button,
    followup_limit_reached,
)
from ..services.slot_manager import (
    add_negated_slots,
    get_missing_slots,
    infer_emotion_signals,
    is_slot_allowed,
    set_slot_value,
)
from ..services.slot_prefill_llm import prefill_slots_with_llm, update_state_with_user_reply
from ..services.slot_prefill_schema import SessionState
from ..services.relevance import combo_relevant, domain_relevant
from ..services.stop_engine import should_stop
from ..services.user_summary import generate_user_summary

bp = Blueprint("session", __name__, url_prefix="/session")


def _mentions_person_text(text: str) -> bool:
    lowered = (text or "").lower()
    return bool(
        re.search(
            r"\b(friend|friends|teacher|sir|maam|mam|parent|parents|mother|father|mom|dad|brother|sister|classmate|roommate|boyfriend|girlfriend|partner|cousin|person|someone)\b",
            lowered,
        )
    )


def _has_explicit_person_name_text(text: str) -> bool:
    """Return True when user text already includes explicit related-person identity."""
    raw_text = (text or "")
    lowered = raw_text.lower()
    relation = r"(?:friend|friends|teacher|sir|maam|mam|parent|parents|mother|father|mom|dad|brother|sister|classmate|roommate|boyfriend|girlfriend|partner|cousin|person|someone)"

    direct_patterns = [
        rf"\b{relation}\b[^.?!\n]{{0,40}}\b(?:name\s+is|named|called)\s+[a-z][a-z'\-]{{1,30}}\b",
    ]
    if any(re.search(pattern, lowered) for pattern in direct_patterns):
        return True

    relation_tokens = {
        "friend", "friends", "teacher", "sir", "maam", "mam", "parent", "parents",
        "mother", "father", "mom", "dad", "brother", "sister", "classmate", "roommate",
        "boyfriend", "girlfriend", "partner", "cousin", "person", "someone",
    }
    stop_tokens = {
        "is", "am", "are", "was", "were", "be", "been", "being", "the", "a", "an",
        "my", "your", "our", "his", "her", "their", "this", "that", "these", "those",
        "very", "too", "so", "bad", "good", "nice", "mean", "strict", "rude", "compare",
        "compares", "comparing", "keeps", "keep", "karta", "karti", "karte", "hai", "ho",
        "with", "and", "or", "to", "of", "for", "in", "on",
    }
    tokens = re.findall(r"[A-Za-z][A-Za-z'\-]*", lowered)
    for idx in range(len(tokens) - 1):
        if tokens[idx] in relation_tokens:
            nxt = tokens[idx + 1]
            if nxt not in stop_tokens and len(nxt) >= 3:
                return True
    return False


def _asks_for_name_text(question: str) -> bool:
    return bool(re.search(r"\bname\b", (question or "").lower()))


def _forced_name_question(text: str) -> str:
    lowered = (text or "").lower()
    if re.search(r"\bteacher\b|\bsir\b|\bmaam\b|\bmam\b", lowered):
        return "Which teacher exactly are you talking about and what is their name?"
    if re.search(r"\bfriends?\b", lowered):
        return "Which friend exactly are you talking about and what is their name?"
    if re.search(r"\bmother\b|\bfather\b|\bmom\b|\bdad\b|\bparent\b|\bparents\b|\bbrother\b|\bsister\b|\bcousin\b", lowered):
        return "Which family member are you talking about and what is their name?"
    return "Who exactly are you talking about and what is this person's name?"


def _append_name_to_followup(existing_followup: str, latest_text: str) -> str:
    """Preserve contextual follow-up and append person-name requirement."""
    question = " ".join((existing_followup or "").strip().split())
    if not question:
        return _forced_name_question(latest_text)
    if _asks_for_name_text(question):
        return question

    if question.endswith("?"):
        question = question[:-1].rstrip()

    name_part = _forced_name_question(latest_text)
    if name_part.endswith("?"):
        name_part = name_part[:-1].rstrip()

    return f"{question}, and {name_part.lower()}?"


def _safe_float(value, default: float = 0.0) -> float:
    try:
        return float(value)
    except Exception:
        return default


def _clamp01(value, default: float = 0.0) -> float:
    num = _safe_float(value, default)
    if num < 0:
        return 0.0
    if num > 1:
        return 1.0
    return num


def _normalize_feedback_metric(raw: dict | None) -> dict:
    raw = raw if isinstance(raw, dict) else {}
    return {
        "time_spent": _safe_float(raw.get("time_spent"), 0.0),
        "confidence": _clamp01(raw.get("confidence"), 0.0),
        "accuracy": bool(raw.get("accuracy", False)),
    }


def _impact_from_metrics(pre: dict, post: dict) -> str:
    # Lower time_spent is better; higher confidence and accuracy are better.
    degrade_count = 0
    improve_count = 0

    if post.get("time_spent", 0.0) > pre.get("time_spent", 0.0):
        degrade_count += 1
    elif post.get("time_spent", 0.0) < pre.get("time_spent", 0.0):
        improve_count += 1

    if post.get("confidence", 0.0) < pre.get("confidence", 0.0):
        degrade_count += 1
    elif post.get("confidence", 0.0) > pre.get("confidence", 0.0):
        improve_count += 1

    if bool(post.get("accuracy", False)) != bool(pre.get("accuracy", False)):
        if bool(post.get("accuracy", False)):
            improve_count += 1
        else:
            degrade_count += 1

    if degrade_count == 3:
        return "STRONG_NEGATIVE"
    if degrade_count >= 2:
        return "NEGATIVE"
    if improve_count >= 2:
        return "POSITIVE"
    return "NEUTRAL"


def _score_from_impact(impact: str) -> float:
    if impact == "STRONG_NEGATIVE":
        return -2.0
    if impact == "NEGATIVE":
        return -1.0
    if impact == "POSITIVE":
        return 1.0
    return 0.0


def _effectiveness_level(avg_score: float) -> str:
    if avg_score <= -0.5:
        return "low"
    if avg_score >= 0.5:
        return "high"
    return "medium"


def _safe_metric_ratio(numerator: float, denominator: float, default: float = 1.0) -> float:
    if denominator <= 0:
        return default
    return max(0.0, numerator / denominator)


def _build_baseline_metrics(stats: dict | None) -> dict:
    stats = stats if isinstance(stats, dict) else {}
    count = max(1, int(stats.get("count") or 0))
    avg_time = _safe_float(stats.get("sum_time"), 0.0) / count
    avg_confidence = _clamp01(_safe_float(stats.get("sum_confidence"), 0.0) / count, 0.0)
    avg_accuracy = _clamp01(_safe_float(stats.get("sum_accuracy"), 0.0) / count, 0.0)
    return {
        "time_spent": avg_time,
        "confidence": avg_confidence,
        "accuracy": avg_accuracy,
    }


def _recovery_band(recovery_score: float) -> str:
    if recovery_score >= 0.95:
        return "fast"
    if recovery_score >= 0.80:
        return "moderate"
    return "slow"


def _recovery_effectiveness_score(recovery_score: float) -> float:
    if recovery_score >= 0.95:
        return -0.5
    if recovery_score >= 0.80:
        return 0.5
    return 1.0


def _compute_recovery_score(baseline_metrics: dict, recovery_metrics: dict) -> float:
    baseline_time = max(1.0, _safe_float(baseline_metrics.get("time_spent"), 1.0))
    baseline_accuracy = _clamp01(baseline_metrics.get("accuracy"), 0.5)

    recovery_time = max(1.0, _safe_float(recovery_metrics.get("time_spent"), baseline_time))
    recovery_accuracy = _clamp01(recovery_metrics.get("accuracy"), baseline_accuracy)

    accuracy_ratio = _safe_metric_ratio(recovery_accuracy, max(0.01, baseline_accuracy), 1.0)
    speed_ratio = _safe_metric_ratio(baseline_time, recovery_time, 1.0)
    score = (0.6 * accuracy_ratio) + (0.4 * speed_ratio)
    return max(0.0, min(1.5, score))


@bp.post("/transcribe")
def transcribe_session_audio():
    try:
        audio = request.files.get("audio")
        if not audio:
            return jsonify({"error": "audio file is required"}), 400

        transcript = transcribe_audio(audio)
        current_app.logger.info("transcribe_session_audio: transcript len=%s", len(transcript))
        if not transcript:
            return jsonify({"error": "could not transcribe audio"}), 400

        return jsonify({"text": transcript})
    except Exception as exc:  # pragma: no cover - defensive logging
        current_app.logger.exception("transcribe_session_audio failed: %s", exc)
        return jsonify({"error": "transcription failed", "detail": str(exc)}), 500


@bp.post("/start")
def start_session():
    try:
        body = request.get_json(force=True, silent=True) or {}
        text = (body.get("text") or "").strip()
        current_app.logger.info("start_session: incoming text len=%s", len(text))
        if not text:
            return jsonify({"error": "text is required"}), 400

        session = create_session(text)
        current_app.logger.info("start_session: created session_id=%s", session.id)

        prefill = prefill_slots_with_llm(text)
        current_app.logger.debug("start_session: prefill=%s", prefill)

        causes = detect_causes(text)
        current_app.logger.debug("start_session: causes=%s", causes)
        meta = dict(session.meta or {})
        meta["causes"] = causes
        meta["clarifier_queue"] = []
        if getattr(prefill, "extracted_state", None):
            meta["extracted_state"] = prefill.extracted_state.model_dump()
        raw_client = body.get("client_user")
        if isinstance(raw_client, dict):
            safe_user = {}
            for key in ("user_id", "display_name", "email", "mood"):
                val = raw_client.get(key)
                if isinstance(val, str):
                    val = val.strip()[:240]
                    if val:
                        safe_user[key] = val
            if safe_user:
                meta["client_user"] = safe_user
        session.meta = meta

        session.active_domains = prefill.active_domains or activate_domains_from_causes(causes)
        current_app.logger.debug("start_session: active_domains=%s", session.active_domains)

        for domain, slots in (prefill.prefill or {}).items():
            for slot, value in slots.items():
                set_slot_value(session.filled_slots, domain, slot, value)
        add_negated_slots(session.filled_slots, prefill.negated_slots or [])

        if not session.active_domains:
            session.active_domains = ["time_pressure", "distractions", "academic_confidence"]

        # Reset the runtime follow-up counter for this new session
        reset_followup_count(str(session.id))

        save_session(session)
        current_app.logger.info("start_session: saved session_id=%s", session.id)

        return jsonify(
            {
                "session_id": str(session.id),
                "status": session.status,
                "active_domains": session.active_domains,
                "prefilled": session.filled_slots,
            }
        )
    except Exception as exc:  # pragma: no cover - defensive logging
        current_app.logger.exception("start_session failed: %s", exc)
        return jsonify({"error": "internal error", "detail": str(exc)}), 500


@bp.post("/<session_id>/answer")
def answer(session_id: str):
    session = get_session(session_id)
    current_app.logger.info("answer: session_id=%s", session_id)
    if not session:
        return jsonify({"error": "session not found"}), 404
    if session.status != "active":
        return jsonify({"error": "session is not active"}), 400

    body = request.get_json(force=True, silent=True) or {}
    answer_text = (body.get("answer") or "").strip()

    meta = dict(session.meta or {})

    def _update_extracted_state(new_text: str) -> None:
        raw = meta.get("extracted_state") or {}
        try:
            current_state = SessionState(**raw)
        except Exception:
            current_state = SessionState()
        updated = update_state_with_user_reply(current_state, new_text)
        meta["extracted_state"] = updated.model_dump()

    current_question = meta.get("current_question") or {}
    if current_question.get("type") == "clarifier":
        clarifier_answers = list(meta.get("clarifier_answers") or [])
        clarifier_answers.append({"question": current_question.get("question"), "answer": answer_text})
        meta["clarifier_answers"] = clarifier_answers
        meta["current_question"] = None
        _update_extracted_state(answer_text)
        session.meta = meta
        session.history.append({"role": "user", "text": answer_text})
        save_session(session)
        return jsonify({"ok": True, "clarifier": True, "meta": session.meta})

    if current_question.get("type") == "combo":
        combo_id = current_question.get("combo_id")
        parser = COMBO_PARSERS.get(combo_id)
        if parser:
            parsed = parser(answer_text)
            if not parsed:
                hint = COMBO_SPECS.get(combo_id, {}).get("hint", "")
                return jsonify(
                    {
                        "need_clarification": True,
                        "question": f"Please follow the format:\n{hint}",
                    }
                )

            for key, value in parsed["slots"].items():
                domain_key, slot_key = key.split(".", 1)
                set_slot_value(session.filled_slots, domain_key, slot_key, value)

            emotion = parsed.get("emotion")
            if emotion:
                signals = list(meta.get("emotion_signals") or [])
                signals.append(emotion)
                meta["emotion_signals"] = signals

            meta["current_question"] = None
            _update_extracted_state(answer_text)
            session.meta = meta
            session.history.append({"role": "user", "text": answer_text})
            save_session(session)
            return jsonify({"ok": True, "filled_slots": session.filled_slots, "meta": session.meta})

    domain = body.get("domain")
    slot = body.get("slot")
    domain = domain or current_question.get("domain")
    slot = slot or current_question.get("slot")
    current_app.logger.debug("answer: domain=%s slot=%s", domain, slot)

    if not (domain and slot):
        return jsonify({"error": "domain/slot missing (no current_question found)"}), 400

    if not is_slot_allowed(domain, slot):
        return jsonify({"error": "invalid domain/slot"}), 400

    if not answer_text:
        return jsonify({"error": "answer is required"}), 400

    clarifier_used = list(meta.get("clarifier_used") or [])
    key = f"{domain}.{slot}"
    if len(answer_text.split()) < 2 and key not in clarifier_used:
        clarifier_used.append(key)
        meta["clarifier_used"] = clarifier_used
        meta["current_question"] = {
            "domain": domain,
            "slot": slot,
            "question": CLARIFIER_QUESTION,
        }
        session.meta = meta

        session.history.append({"role": "user", "text": answer_text})
        session.history.append({"role": "assistant", "text": CLARIFIER_QUESTION})
        save_session(session)
        return jsonify(
            {
                "need_clarification": True,
                "domain": domain,
                "slot": slot,
                "question": CLARIFIER_QUESTION,
            }
        )

    session.history.append({"role": "user", "text": answer_text})
    set_slot_value(session.filled_slots, domain, slot, answer_text)
    meta["current_question"] = None
    _update_extracted_state(answer_text)
    session.meta = meta

    save_session(session)
    return jsonify({"ok": True, "filled_slots": session.filled_slots, "meta": session.meta})


@bp.post("/<session_id>/next-question")
def next_question(session_id: str):
    session = get_session(session_id)
    current_app.logger.info("next_question: session_id=%s", session_id)
    if not session or session.status != "active":
        return jsonify({"error": "invalid session"}), 400

    meta = dict(session.meta or {})
    current_q = meta.get("current_question")
    if current_q:
        return jsonify(
            {
                "done": False,
                "domain": current_q.get("domain"),
                "slot": current_q.get("slot"),
                "question": current_q.get("question"),
                "meta": session.meta,
                "pending": True,
                "message": "Answer the current question first",
            }
        )

    asked_questions = [
        item.get("text", "")
        for item in (session.history or [])
        if isinstance(item, dict) and item.get("role") == "assistant"
    ]
    total_questions = int(meta.get("total_questions_asked", 0))
    min_required_questions = max(3, int(current_app.config.get("MIN_QUESTIONS", 3)))

    # Follow-up phase
    body = request.get_json(force=True, silent=True) or {}
    client_followups_done = bool(body.get("followups_done", False))
    followup_count = get_followup_count(session_id)
    followups_exhausted = bool(meta.get("followups_exhausted", False))

    user_texts = [
        str(item.get("text") or item.get("content") or "").strip()
        for item in (session.history or [])
        if isinstance(item, dict) and item.get("role") == "user"
    ]
    user_texts = [text for text in user_texts if text]

    latest_user_text = user_texts[-1] if user_texts else ""
    if not latest_user_text:
        latest_user_text = session.raw_initial_text or ""

    name_already_known = any(_has_explicit_person_name_text(text) for text in user_texts)

    if not client_followups_done and not followups_exhausted and not followup_limit_reached(followup_count):
        followup = generate_next_followup(
            user_text=latest_user_text,
            asked_questions=asked_questions,
            conversation_history=session.history or [],
            followup_count=followup_count,
            initial_text=session.raw_initial_text or "",
            session_id=session_id,
        )

        if (
            followup
            and _mentions_person_text(latest_user_text)
            and not name_already_known
            and not _asks_for_name_text(followup)
        ):
            current_app.logger.info("next_question: appending name requirement at route-level session=%s", session_id)
            followup = _append_name_to_followup(followup, latest_user_text)

        if followup:
            new_count = increment_followup_count(session_id)
            show_skip = should_show_skip_button(new_count)

            meta["current_question"] = {"type": "clarifier", "question": followup}
            meta["total_questions_asked"] = total_questions + 1
            session.meta = meta
            session.history.append({"role": "assistant", "text": followup})
            save_session(session)

            current_app.logger.info(
                "next_question: serving followup count=%d show_skip=%s session=%s",
                new_count, show_skip, session_id,
            )

            return jsonify(
                {
                    "done": False,
                    "is_followup": True,
                    "clarifier": True,
                    "question": followup,
                    "followup_count": new_count,
                    "show_skip_button": show_skip,
                    "meta": session.meta,
                }
            )
        else:
            current_app.logger.info(
                "next_question: followup generator returned None (count=%d), moving to slot phase session=%s",
                followup_count, session_id,
            )
            meta["followups_exhausted"] = True
            session.meta = meta

    elif not followups_exhausted and (client_followups_done or followup_limit_reached(followup_count)):
        current_app.logger.info(
            "next_question: followups done/skipped (client_done=%s count=%d) session=%s",
            client_followups_done, followup_count, session_id,
        )
        meta["followups_exhausted"] = True
        session.meta = meta

    # Slot-filling phase

    if not session.active_domains:
        session.active_domains = extract_components(session.raw_initial_text or "")

    if not session.active_domains:
        causes = meta.get("causes")
        if not causes:
            causes = detect_causes(session.raw_initial_text or "")
            meta["causes"] = causes
            session.meta = meta
        session.active_domains = activate_domains_from_causes(causes)

    if not session.active_domains:
        session.active_domains = ["time_pressure", "distractions", "academic_confidence"]

    missing = get_missing_slots(session.active_domains, session.filled_slots)

    def _is_missing(domain: str, slot: str) -> bool:
        return not session.filled_slots.get(domain, {}).get(slot)

    domain_counts = dict(meta.get("domain_question_count") or {})
    combo_history = set(meta.get("combo_history") or [])
    raw_text = session.raw_initial_text or ""

    combo_spec_id = None
    combo_spec = None

    if total_questions <= 2:
        if (
            "friend_compare_emotion" not in combo_history
            and combo_relevant("friend_compare_emotion", raw_text)
            and domain_relevant("social_comparison", raw_text)
            and (
                _is_missing("distractions", "friend_name")
                or _is_missing("social_comparison", "comparison_person")
                or _is_missing("social_comparison", "comparison_gap")
            )
        ):
            combo_spec_id = "friend_compare_emotion"
        elif (
            "distraction_time_combo" not in combo_history
            and combo_relevant("distraction_time_combo", raw_text)
            and domain_relevant("distractions", raw_text)
            and domain_relevant("time_pressure", raw_text)
            and (
                _is_missing("distractions", "gaming_app")
                or _is_missing("distractions", "gaming_time")
                or _is_missing("time_pressure", "timetable_breaker")
            )
        ):
            combo_spec_id = "distraction_time_combo"

    if combo_spec_id:
        combo_spec = COMBO_SPECS[combo_spec_id]
        question = generate_combo_question(combo_spec_id, session, session.raw_initial_text or "")
    if combo_spec_id and combo_spec and question:
        current_app.logger.info("next_question: serving combo %s", combo_spec_id)
        meta["total_questions_asked"] = total_questions + 1
        meta["current_question"] = {
            "type": "combo",
            "combo_id": combo_spec_id,
            "question": question,
        }
        history = list(combo_history)
        history.append(combo_spec_id)
        meta["combo_history"] = history
        session.meta = meta
        session.history.append({"role": "assistant", "text": question})
        save_session(session)
        return jsonify(
            {
                "done": False,
                "combo": True,
                "followups_complete": True,  # inform client followups are done
                "question": question,
                "hint": combo_spec["hint"],
                "meta": session.meta,
            }
        )
    elif combo_spec_id and not question:
        combo_spec_id = None

    if should_stop(
        total_questions_asked=total_questions,
        missing_slots_count=len(missing),
        min_questions=min_required_questions,
        max_questions=current_app.config["MAX_QUESTIONS"],
    ):
        return _complete_session(session)

    question = None
    domain = slot = None
    attempts = 0
    max_attempts = len(missing) + 3

    while attempts < max_attempts:
        missing = get_missing_slots(session.active_domains, session.filled_slots)
        next_slot = pick_next_slot(
            session.active_domains,
            missing,
            domain_counts,
            current_app.config["MAX_DOMAIN_QUESTIONS"],
            session.raw_initial_text or "",
            session.filled_slots,
            meta.get("causes") or {},
        )
        if not next_slot:
            return _complete_session(session)

        domain, slot = next_slot
        current_app.logger.debug("next_question: picked domain=%s slot=%s", domain, slot)
        profile = session.filled_slots or {}
        domain_profile = profile.get(domain) or {}

        excerpt = None
        if domain == "academic_confidence":
            weak = domain_profile.get("weak_subject") or ""
            last = domain_profile.get("last_test_experience") or ""
            if weak or last:
                excerpt = f"Weak in {weak}. Last test felt {last}."
        elif domain == "family_pressure":
            expect = domain_profile.get("expectation_type") or ""
            member = domain_profile.get("family_member") or ""
            if expect or member:
                excerpt = f"Family member {member} expects {expect}."
        elif domain == "distractions":
            friend = domain_profile.get("friend_name") or ""
            app = domain_profile.get("phone_app") or ""
            if friend or app:
                excerpt = f"Distractions include {friend} and app {app}."

        last_question = (meta.get("last_question") or "").strip()
        context = {
            "user_text": session.raw_initial_text or "",
            "filled_slots": session.filled_slots,
            "domain": domain,
            "slot": slot,
            "causes": meta.get("causes") or {},
        }
        context["meta"] = {
            "last_question": last_question,
            "clarifier_answers": meta.get("clarifier_answers") or [],
        }

        if slot == "__generic__":
            generic = get_generic_domain_question(domain)
            if generic:
                next_slot, generic_question = generic
                if generic_question == last_question:
                    add_negated_slots(session.filled_slots, [next_slot])
                    attempts += 1
                    continue
                slot, question = next_slot, generic_question
                break
            attempts += 1
            continue

        question = generate_question(domain, slot, excerpt=excerpt, context=context)
        if question:
            break

        generic = get_generic_domain_question(domain)
        if generic:
            next_slot, generic_question = generic
            if generic_question == last_question:
                add_negated_slots(session.filled_slots, [next_slot])
                attempts += 1
                continue
            slot, question = next_slot, generic_question
            break

        add_negated_slots(session.filled_slots, [slot])
        attempts += 1

    if not question:
        return _complete_session(session)

    session.history.append({"role": "assistant", "text": question})
    meta["total_questions_asked"] = total_questions + 1
    domain_counts[domain] = int(domain_counts.get(domain, 0)) + 1
    meta["domain_question_count"] = domain_counts
    meta["current_question"] = {"domain": domain, "slot": slot, "question": question}
    meta["last_question"] = question
    session.meta = meta

    save_session(session)

    return jsonify(
        {
            "done": False,
            "followups_complete": True,
            "domain": domain,
            "slot": slot,
            "question": question,
            "meta": session.meta,
        }
    )


@bp.get("/<session_id>/status")
def status(session_id: str):
    session = get_session(session_id)
    if not session:
        return jsonify({"error": "session not found"}), 404
    return jsonify(
        {
            "session_id": str(session.id),
            "status": session.status,
            "active_domains": session.active_domains,
            "filled_slots": session.filled_slots,
            "meta": session.meta,
        }
    )


@bp.get("/<session_id>/debug")
def debug_session(session_id: str):
    session = get_session(session_id)
    if not session:
        return jsonify({"error": "session not found"}), 404
    return jsonify(
        {
            "id": str(session.id),
            "status": session.status,
            "popups_count": len(session.popups or []),
            "popups": session.popups or [],
            "filled_slots": session.filled_slots,
            "meta": session.meta,
            "raw_initial_text": session.raw_initial_text,
            "history": session.history,
        }
    )


@bp.get("/<session_id>/summary")
def session_summary(session_id: str):
    session = get_session(session_id)
    if not session:
        return jsonify({"error": "session not found"}), 404
    meta = dict(session.meta or {})
    return jsonify(
        {
            "session_id": str(session.id),
            "status": session.status,
            "user_summary": meta.get("user_summary") or {},
        }
    )
@bp.post("/<session_id>/complete")
def complete_session_early(session_id: str):
    """Mark session as completed early when user skips remaining questions."""
    session = get_session(session_id)
    if not session:
        return jsonify({"error": "session not found"}), 404

    if session.status == "completed":
        return jsonify(
            {
                "ok": True,
                "already_completed": True,
                "popups_count": len(session.popups or []),
            }
        )

    return _complete_session(session)


@bp.post("/<session_id>/skip-followups")
def skip_followups(session_id: str):
    """
    Called by the frontend when the student presses 'Skip to test →'.

    Marks followups as exhausted in session meta so the next call to
    next-question jumps straight to slot-filling (and then completion).
    Also resets the runtime follow-up counter for this session.
    """
    session = get_session(session_id)
    if not session:
        return jsonify({"error": "session not found"}), 404

    meta = dict(session.meta or {})
    meta["followups_exhausted"] = True
    session.meta = meta
    save_session(session)

    # Reset the runtime counter — session is moving on
    reset_followup_count(session_id)

    current_app.logger.info("skip_followups: student skipped followups session=%s", session_id)
    return jsonify({"ok": True, "followups_exhausted": True})


@bp.post("/<session_id>/start-simulation")
def start_simulation(session_id: str):
    session = get_session(session_id)
    if not session or session.status != "completed":
        return jsonify({"error": "session not completed"}), 400

    popups = list(session.popups or [])
    if not popups:
        meta = dict(session.meta or {})
        stress_profile = session.filled_slots or {}
        stress_profile["__raw_text__"] = session.raw_initial_text or ""
        clarifier_answers = meta.get("clarifier_answers")
        if clarifier_answers:
            stress_profile["__clarifiers__"] = clarifier_answers

        inferred_signals = infer_emotion_signals(stress_profile)
        stored_signals = meta.get("emotion_signals") or []
        emotion_signals = list(dict.fromkeys(stored_signals + inferred_signals))

        popups = generate_popups(stress_profile, emotion_signals)
        session.popups = popups
        meta["popups_ready"] = True
        session.meta = meta
        save_session(session)

    max_popups = max(1, min(200, int(current_app.config.get("SIM_MAX_POPUPS", 18))))
    scheduled = popups[:max_popups]

    start_popup_simulation(session_id, scheduled)
    return jsonify(
        {
            "ok": True,
            "popups_scheduled": len(scheduled),
            "popups_total": len(popups),
        }
    )


@bp.post("/<session_id>/test-popup")
def test_popup(session_id: str):
    session = get_session(session_id)
    if not session:
        return jsonify({"error": "session not found"}), 404

    payload = {
        "type": "distraction",
        "message": "Test popup ✅\nIf you see this, WS works.",
        "ttl": 8000,
    }
    socketio.emit("popup", payload, room=str(session_id))
    return jsonify({"ok": True, "sent": True, "payload": payload})


@bp.post("/<session_id>/trigger-feedback")
def persist_trigger_feedback(session_id: str):
    session = get_session(session_id)
    if not session:
        return jsonify({"error": "session not found"}), 404

    body = request.get_json(force=True, silent=True) or {}
    trigger_name = str(body.get("trigger") or body.get("trigger_name") or "").strip()
    if not trigger_name:
        return jsonify({"error": "trigger is required"}), 400

    intensity = str(body.get("intensity") or "low").strip().lower()
    if intensity not in {"low", "medium", "high"}:
        intensity = "low"

    ts_raw = body.get("timestamp")
    ts = int(ts_raw) if isinstance(ts_raw, (int, float)) else int(datetime.now(tz=timezone.utc).timestamp() * 1000)

    pre_metrics = _normalize_feedback_metric(body.get("pre_metrics"))
    post_metrics = _normalize_feedback_metric(body.get("post_metrics"))
    recovery_metrics = _normalize_feedback_metric(body.get("recovery_metrics") or body.get("post_60s_metrics"))
    impact = _impact_from_metrics(pre_metrics, post_metrics)
    impact_score = _score_from_impact(impact)

    meta = dict(session.meta or {})
    feedback = meta.get("trigger_feedback") if isinstance(meta.get("trigger_feedback"), dict) else {}
    recent = [item for item in (feedback.get("recent_triggers") or []) if isinstance(item, dict)]
    effectiveness = feedback.get("effectiveness") if isinstance(feedback.get("effectiveness"), dict) else {}

    baseline_stats = feedback.get("baseline_stats") if isinstance(feedback.get("baseline_stats"), dict) else {}
    baseline_count = int(baseline_stats.get("count") or 0) + 1
    baseline_stats["count"] = baseline_count
    baseline_stats["sum_time"] = _safe_float(baseline_stats.get("sum_time"), 0.0) + _safe_float(pre_metrics.get("time_spent"), 0.0)
    baseline_stats["sum_confidence"] = _safe_float(baseline_stats.get("sum_confidence"), 0.0) + _clamp01(pre_metrics.get("confidence"), 0.0)
    baseline_stats["sum_accuracy"] = _safe_float(baseline_stats.get("sum_accuracy"), 0.0) + (1.0 if bool(pre_metrics.get("accuracy")) else 0.0)

    baseline_metrics = _build_baseline_metrics(baseline_stats)
    if body.get("baseline_metrics") and isinstance(body.get("baseline_metrics"), dict):
        incoming_baseline = body.get("baseline_metrics")
        baseline_metrics = {
            "time_spent": _safe_float(incoming_baseline.get("time_spent"), baseline_metrics.get("time_spent", 0.0)),
            "confidence": _clamp01(incoming_baseline.get("confidence"), baseline_metrics.get("confidence", 0.0)),
            "accuracy": _clamp01(incoming_baseline.get("accuracy"), baseline_metrics.get("accuracy", 0.0)),
        }

    recovery_source = recovery_metrics if body.get("recovery_metrics") or body.get("post_60s_metrics") else post_metrics
    recovery_score = _compute_recovery_score(baseline_metrics, recovery_source)
    recovery_band = _recovery_band(recovery_score)
    impact_score += _recovery_effectiveness_score(recovery_score)

    stored = {
        "trigger": trigger_name,
        "intensity": intensity,
        "timestamp": ts,
        "pre_metrics": pre_metrics,
        "post_metrics": post_metrics,
        "recovery_metrics": recovery_source,
        "baseline_metrics": baseline_metrics,
        "recovery_score": recovery_score,
        "recovery_band": recovery_band,
        "impact": impact,
    }
    recent.append(stored)
    feedback["recent_triggers"] = recent[-30:]
    feedback["baseline_stats"] = baseline_stats
    feedback["baseline_metrics"] = baseline_metrics

    trigger_stats = effectiveness.get(trigger_name) if isinstance(effectiveness.get(trigger_name), dict) else {}
    count = int(trigger_stats.get("count") or 0) + 1
    total_score = _safe_float(trigger_stats.get("total_score"), 0.0) + impact_score
    avg_score = total_score / max(1, count)
    avg_recovery = (
        (_safe_float(trigger_stats.get("avg_recovery"), recovery_score) * max(0, count - 1)) + recovery_score
    ) / max(1, count)
    effectiveness[trigger_name] = {
        "count": count,
        "total_score": total_score,
        "avg_score": avg_score,
        "avg_recovery": avg_recovery,
        "last_recovery_score": recovery_score,
        "last_recovery_band": recovery_band,
        "level": _effectiveness_level(avg_score),
        "last_impact": impact,
        "last_intensity": intensity,
        "last_timestamp": ts,
    }
    feedback["effectiveness"] = effectiveness

    meta["trigger_feedback"] = feedback
    session.meta = meta
    save_session(session)

    return jsonify(
        {
            "ok": True,
            "stored": stored,
            "trigger_effectiveness": effectiveness.get(trigger_name) or {},
            "recent_count": len(feedback.get("recent_triggers") or []),
        }
    )


@bp.get("/<session_id>/trigger-feedback")
def get_trigger_feedback(session_id: str):
    session = get_session(session_id)
    if not session:
        return jsonify({"error": "session not found"}), 404

    meta = dict(session.meta or {})
    feedback = meta.get("trigger_feedback") if isinstance(meta.get("trigger_feedback"), dict) else {}
    return jsonify(
        {
            "ok": True,
            "session_id": str(session.id),
            "recent_triggers": feedback.get("recent_triggers") or [],
            "effectiveness": feedback.get("effectiveness") or {},
        }
    )




def _complete_session(session):
    session.status = "completed"
    stress_profile = session.filled_slots or {}
    stress_profile["__raw_text__"] = session.raw_initial_text or ""
    # pass clarifier answers to popup generator for personalization
    meta = dict(session.meta or {})
    clarifier_answers = meta.get("clarifier_answers")
    if clarifier_answers:
        stress_profile["__clarifiers__"] = clarifier_answers
    inferred_signals = infer_emotion_signals(stress_profile)
    stored_signals = (session.meta or {}).get("emotion_signals") or []
    emotion_signals = list(dict.fromkeys(stored_signals + inferred_signals))
    meta["user_summary"] = generate_user_summary(
        session.raw_initial_text or "",
        filled_slots=session.filled_slots or {},
        conversation_history=session.history or [],
        emotion_signals=emotion_signals,
    )
    meta["popups_ready"] = False
    session.meta = meta
    # Popups are generated lazily in /start-simulation so test-question
    # generation is not contending with popup generation.
    session.popups = []

    # Clean up runtime follow-up counter
    reset_followup_count(str(session.id))

    save_session(session)
    return jsonify(
        {
            "done": True,
            "status": session.status,
            "popups_ready": False,
            "popups_count": len(session.popups or []),
            "filled_slots": session.filled_slots,
        }
    )