"""LLM-powered slot prefilling."""
from __future__ import annotations

import json
import logging
from collections import OrderedDict

from pydantic import ValidationError

from ..constants import SLOT_SCHEMA
from .slot_prefill_schema import Event, Person, SessionState, SlotPrefillResponse
from .openai_client import chat_json

logger = logging.getLogger(__name__)


SYSTEM_PROMPT_PREFILL = """
You are a slot extractor for a student stress-test system.

Return ONLY JSON (no markdown). Use the provided SLOT_SCHEMA.
Rules:
- Only use domains and slots that exist in SLOT_SCHEMA.
- If a value is not clearly stated/implied, do not guess.
- Values should be short (1–8 words). No long sentences.
- You may correct spelling/casing (e.g., "instragram" -> "Instagram").
- active_domains should include the stress domains present in the user's text.
- If the user explicitly says a slot does NOT apply (e.g., "not distracted by phone"),
  add that slot name to negated_slots.

Output format:
{
  "active_domains": ["distractions", "time_pressure"],
  "negated_slots": ["phone_app"],
  "prefill": {
    "distractions": {"phone_app": "Instagram"}
  }
}
"""


SYSTEM_PROMPT_EXTRACT_STATE = """
You are an information extraction engine for a student stress conversation.

Return JSON only with exactly these keys:
- people: array of objects {"role": string, "name": string or null}
- events: array of objects {"description": string, "known": boolean}
- emotions: array of strings
- missing_information: array of strings
- ignored_information: array of strings

Rules:
1. Do not hallucinate names, people, events, or emotions.
2. If a person role is mentioned without a name, set name to null.
3. If a person has name null, add role_name to missing_information.
4. If an event is referenced vaguely, add event_detail to missing_information.
5. Be aggressive in identifying missing_information needed for a specific follow-up question.
6. Allowed missing labels only:
   friend_name, boss_name, mother_name, father_name, partner_name, teacher_name,
   event_detail, timeline_detail, trigger_detail
7. If user explicitly denies something (for example not distracted by phone),
   add a short canonical label to ignored_information.
8. No extra keys. No markdown. No explanation text.

Output format:
{
  "people": [],
  "events": [],
  "emotions": [],
  "missing_information": [],
  "ignored_information": []
}
"""


SYSTEM_PROMPT_UPDATE_STATE = """
You update an existing structured conversation state using new user text.

Return JSON only with exactly these keys:
- people
- events
- emotions
- missing_information
- ignored_information

You are given:
1) previous_state
2) new_user_text

Update rules:
1. Fill unresolved fields from new_user_text when evidence is explicit.
2. Do not overwrite known values unless the user clearly corrects them.
3. Remove missing_information items only when resolved by explicit evidence.
4. Add missing_information if new_user_text introduces new vague references.
5. Preserve existing valid data.
6. Use only canonical missing labels.
7. Deduplicate arrays and keep stable ordering.
8. No extra keys. No markdown. No explanation text.
"""


CANONICAL_MISSING = {
    "friend_name",
    "boss_name",
    "mother_name",
    "father_name",
    "partner_name",
    "teacher_name",
    "event_detail",
    "timeline_detail",
    "trigger_detail",
}

ROLE_ALIASES = {
    "friend": "friend",
    "boss": "boss",
    "mother": "mother",
    "mom": "mother",
    "father": "father",
    "dad": "father",
    "partner": "partner",
    "boyfriend": "partner",
    "girlfriend": "partner",
    "teacher": "teacher",
    "sir": "teacher",
    "maam": "teacher",
}


def _canonical_role(role: str) -> str:
    token = " ".join((role or "").strip().lower().split())
    return ROLE_ALIASES.get(token, token)


def _missing_for_role(role: str) -> str | None:
    role_name = _canonical_role(role)
    key = f"{role_name}_name"
    return key if key in CANONICAL_MISSING else None


def _dedupe_stable(values: list[str]) -> list[str]:
    out: list[str] = []
    seen = set()
    for value in values:
        token = " ".join((value or "").strip().split())
        if not token:
            continue
        lowered = token.lower()
        if lowered in seen:
            continue
        seen.add(lowered)
        out.append(token)
    return out


def normalize_session_state(state: SessionState) -> SessionState:
    """Normalize extraction output into a deterministic canonical state."""
    dedup_people: OrderedDict[tuple[str, str], Person] = OrderedDict()
    missing = list(state.missing_information or [])

    for raw_person in state.people or []:
        role = _canonical_role(raw_person.role)
        if not role:
            continue
        name = " ".join((raw_person.name or "").strip().split()) or None
        person = Person(role=role, name=name)
        dedup_people[(role, (name or "").lower())] = person
        if not name:
            missing_key = _missing_for_role(role)
            if missing_key:
                missing.append(missing_key)

    dedup_events: OrderedDict[tuple[str, bool], Event] = OrderedDict()
    for raw_event in state.events or []:
        description = " ".join((raw_event.description or "").strip().split())
        if not description:
            continue
        known = bool(raw_event.known)
        dedup_events[(description.lower(), known)] = Event(description=description, known=known)
        if not known and "event_detail" not in missing:
            missing.append("event_detail")

    emotions = _dedupe_stable([str(x).lower() for x in (state.emotions or [])])

    cleaned_missing = []
    for key in _dedupe_stable([str(x).lower() for x in missing]):
        if key in CANONICAL_MISSING:
            cleaned_missing.append(key)
    cleaned_missing = sorted(cleaned_missing)

    ignored = _dedupe_stable([str(x).lower() for x in (state.ignored_information or [])])

    return SessionState(
        people=list(dedup_people.values()),
        events=list(dedup_events.values()),
        emotions=emotions,
        missing_information=cleaned_missing,
        ignored_information=ignored,
    )


def extract_state_with_llm(user_text: str) -> SessionState:
    """Extract canonical conversation state from user text."""
    if not (user_text or "").strip():
        return SessionState()

    payload = {"user_text": user_text[:2000]}
    for attempt in (1, 2):
        try:
            resp = chat_json(
                model="gpt-4o-mini",
                system=SYSTEM_PROMPT_EXTRACT_STATE,
                user=json.dumps(payload, ensure_ascii=False),
            )
            raw = (resp.choices[0].message.content or "").strip()
            data = json.loads(raw)
            parsed = SessionState(**data)
            return normalize_session_state(parsed)
        except (json.JSONDecodeError, ValidationError) as exc:
            logger.warning("extract_state_with_llm attempt %s failed: %s", attempt, exc)
        except Exception as exc:  # pragma: no cover
            logger.exception("extract_state_with_llm error: %s", exc)
            break
    return SessionState()


def update_state_with_user_reply(state: SessionState, new_text: str) -> SessionState:
    """Incrementally update extracted state with new user reply."""
    if not (new_text or "").strip():
        return normalize_session_state(state)

    payload = {
        "previous_state": state.model_dump(),
        "new_user_text": new_text[:2000],
    }

    for attempt in (1, 2):
        try:
            resp = chat_json(
                model="gpt-4o-mini",
                system=SYSTEM_PROMPT_UPDATE_STATE,
                user=json.dumps(payload, ensure_ascii=False),
            )
            raw = (resp.choices[0].message.content or "").strip()
            data = json.loads(raw)
            parsed = SessionState(**data)
            return normalize_session_state(parsed)
        except (json.JSONDecodeError, ValidationError) as exc:
            logger.warning("update_state_with_user_reply attempt %s failed: %s", attempt, exc)
        except Exception as exc:  # pragma: no cover
            logger.exception("update_state_with_user_reply error: %s", exc)
            break

    # Deterministic fallback: preserve old state when update fails.
    return normalize_session_state(state)


def prefill_slots_with_llm(user_text: str) -> SlotPrefillResponse:
    """Infer domains and slot prefills from the initial user text."""
    if not (user_text or "").strip():
        return SlotPrefillResponse(active_domains=[], prefill={}, extracted_state=SessionState())

    payload = {
        "SLOT_SCHEMA": SLOT_SCHEMA,
        "user_text": user_text[:2000],
    }

    for attempt in (1, 2):
        try:
            resp = chat_json(
                model="gpt-4o-mini",
                system=SYSTEM_PROMPT_PREFILL,
                user=json.dumps(payload, ensure_ascii=False),
            )
            raw = (resp.choices[0].message.content or "").strip()
            data = json.loads(raw)
            parsed = SlotPrefillResponse(**data)

            clean_prefill: dict[str, dict[str, str]] = {}
            negated_slots: list[str] = []
            for domain, slots in (parsed.prefill or {}).items():
                if domain not in SLOT_SCHEMA or not isinstance(slots, dict):
                    continue
                for slot, value in slots.items():
                    if (
                        slot in SLOT_SCHEMA[domain]
                        and isinstance(value, str)
                        and value.strip()
                    ):
                        clean_prefill.setdefault(domain, {})[slot] = (
                            " ".join(value.strip().split())[:80]
                        )

            for slot in parsed.negated_slots or []:
                slot_name = (slot or "").strip()
                if not slot_name:
                    continue
                if any(slot_name in SLOT_SCHEMA[d] for d in SLOT_SCHEMA):
                    negated_slots.append(slot_name)

            extracted_state = extract_state_with_llm(user_text)

            return SlotPrefillResponse(
                active_domains=parsed.active_domains or [],
                prefill=clean_prefill,
                negated_slots=negated_slots,
                extracted_state=extracted_state,
            )
        except (json.JSONDecodeError, ValidationError) as exc:
            logger.warning("prefill_slots_with_llm attempt %s failed: %s", attempt, exc)
        except Exception as exc:  # pragma: no cover
            logger.exception("prefill_slots_with_llm error: %s", exc)
            break

    return SlotPrefillResponse(
        active_domains=[],
        prefill={},
        extracted_state=extract_state_with_llm(user_text),
    )


__all__ = [
    "prefill_slots_with_llm",
    "extract_state_with_llm",
    "normalize_session_state",
    "update_state_with_user_reply",
]
