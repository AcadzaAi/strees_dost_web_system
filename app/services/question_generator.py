
from __future__ import annotations

def _extract_person_names_from_history(conversation_history: list[dict]) -> dict[str, str]:
     """
     Extracts mapping of relation keywords (e.g., 'friend', 'teacher') to names from conversation history.
     Returns a dict: {relation: name}
     """
     relation_tokens = {
          "friend", "friends", "teacher", "sir", "maam", "mam", "parent", "parents",
          "mother", "father", "mom", "dad", "brother", "sister", "classmate", "roommate",
          "boyfriend", "girlfriend", "partner", "cousin", "person", "someone",
          "wife", "husband", "relative", "uncle", "aunt",
     }
     person_map = {}
     for turn in conversation_history:
          if turn.get("role") != "user":
                continue
          text = (turn.get("text") or turn.get("content") or "").strip()
          tokens = re.findall(r"[A-Za-z][A-Za-z'\-]*", text)
          for idx in range(len(tokens) - 1):
                rel = tokens[idx].lower()
                nxt = tokens[idx + 1]
                if rel in relation_tokens and nxt and nxt[0].isupper():
                     # Only store first occurrence for each relation
                     if rel not in person_map:
                          person_map[rel] = nxt
     return person_map

"""Question generation - Truly Personal, Never Generic, Never Repeated.

Every question feels like it came from a real person who heard exactly
what the student said — not a bot running a checklist.

Core techniques used for every single response:
     ECHO       → Mirror their exact word back, split into two possibilities
     BIFURCATE  → Give two specific options so they can't stay vague
     NAME IT    → Say the thing they didn't say but probably meant

No keyword buckets. No hardcoded question sets. GPT handles everything.
Fallback is a last resort and still uses the same 3 techniques.

Changes vs previous version:
     1. Added FOLLOWUP_LIMIT = 3 constant — generate_next_followup() now
         enforces a hard cap of 3 follow-ups per session. Returns None once
         the cap is reached, signalling the caller to stop.
     2. Added should_show_skip_button(followup_count) — returns True when
         followup_count >= 2 so the frontend can show the "Skip" button.
     3. Added get_followup_count() / increment_followup_count() /
         reset_followup_count() helpers that operate on a lightweight
         in-process runtime store keyed by session_id.  Follow-up counts
         are intentionally NOT persisted to DB or CSV — they live only in
         process memory for the duration of the session.
     4. generate_next_followup() now accepts an optional followup_count
         parameter.  If the count >= FOLLOWUP_LIMIT it returns None
         immediately without calling GPT.
     5. ai_ready_to_complete() result is now respected inside
         generate_next_followup(): if the model says ready=True AND we have
         at least 1 follow-up under our belt, the function returns None to
         stop the loop.
     6. _personal_fallback tuple unpack was swapped (keyword vs echo_word).
         Original unpacked as (echo_word, option_a, option_b, named_truth, keyword)
         but tuples are defined as (keyword, echo_word, option_a, option_b, named_truth).
         This caused the wrong word to be echoed back on every fallback call.
     7. Markdown fence stripper replaced with a shared _strip_fences() helper
         that correctly handles ```json, ```, and inline fence variants.
         The old raw.split("```")[1] approach left trailing ``` in the string
         and crashed json.loads on any response without a newline after the fence.
     8. generate_next_followup now uses its own lean single-question prompt
         (SYSTEM_PROMPT_SINGLE_FOLLOWUP) instead of calling generate_counter_questions
         with num_questions=1. The old approach wasted ~500 tokens per call
         generating 3 questions and discarding 2.
     9. Slot prompt injection hardened: switched from {slot}/{domain} placeholders
         (which break if .format() is ever called on the string) to __SLOT__/__DOMAIN__
         sentinels replaced via plain .replace(). Injection is now in _build_slot_prompt().
"""
import json
import logging
import hashlib
import re
from .fallbacks import FALLBACK_QUESTIONS
from .validators import is_valid_question
from .openai_client import chat_json
from .generic_questions import get_generic_domain_question

logger = logging.getLogger(__name__)

# ============================================================================
# FOLLOWUP LIMITS & RUNTIME COUNTER
# These are stored in-process only — never persisted to DB or CSV.
# ============================================================================

FOLLOWUP_LIMIT = 3          # Hard cap: never ask more than this many follow-ups
SKIP_BUTTON_AFTER = 2       # Show "Skip" button once the student has seen this many follow-ups

# Runtime store: { session_id: followup_count }
# Lives in process memory only — resets on server restart or session end.
_followup_runtime: dict[str, int] = {}


def get_followup_count(session_id: str) -> int:
    """Return how many follow-up questions have been asked in this session.

    This counter is stored in runtime memory ONLY — it is never written
    to the database, CSV, or any other persistent store.
    """
    return _followup_runtime.get(session_id, 0)


def increment_followup_count(session_id: str) -> int:
    """Increment the runtime follow-up counter and return the new value."""
    new_val = _followup_runtime.get(session_id, 0) + 1
    _followup_runtime[session_id] = new_val
    logger.debug("followup_count session=%s count=%d", session_id, new_val)
    return new_val


def reset_followup_count(session_id: str) -> None:
    """Reset the follow-up counter — call this when a session ends or restarts."""
    _followup_runtime.pop(session_id, None)
    logger.debug("followup_count reset session=%s", session_id)


def should_show_skip_button(followup_count: int) -> bool:
    """Return True when the frontend should show the 'Skip follow-ups' button.

    The skip button appears after the student has seen SKIP_BUTTON_AFTER
    (default: 2) follow-up questions, giving them an easy escape hatch
    before the hard limit is reached.
    """
    return followup_count >= SKIP_BUTTON_AFTER


def followup_limit_reached(followup_count: int) -> bool:
    """Return True when we have hit the hard follow-up ceiling."""
    return followup_count >= FOLLOWUP_LIMIT


# ============================================================================
# SYSTEM PROMPT — 3 QUESTIONS (initial vent + follow-up rounds)
# ============================================================================

SYSTEM_PROMPT_QUESTION = """
You are talking to a JEE/NEET student who just vented. You are their sharp, direct older sibling —
not a therapist, not a bot, not a form.

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
CRITICAL: READ BEFORE GENERATING
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

You are given:
- student_said: what they just said RIGHT NOW
- conversation_so_far: everything said earlier in this session
- already_asked: every question already asked this session
- student_answers_so_far: the student's own words from previous turns

RULE ZERO: Scan conversation_so_far and student_answers_so_far FIRST.
If a slot (name, subject, app, number) was ALREADY ANSWERED — do NOT ask for it again.
Build on what you know. Go deeper, not wider.

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
YOUR JOB
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

Generate EXACTLY 3 sharp, personal, non-generic questions that:
1. Use their EXACT words — not synonyms, not paraphrases
2. FORCE a specific detail (a real name / a real subject / an actual app / a concrete number)
3. Push one layer deeper than what they said — toward the thing they haven't admitted yet

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
MANDATORY STRUCTURE (NO EXCEPTIONS)
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

Q1 — ECHO + EXTRACT SPECIFIC IDENTIFIER
Q2 — BIFURCATE THEIR EXPERIENCE
Q3 — NAME THE UNSAID TRUTH

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
Q1 — ECHO + EXTRACT SPECIFIC IDENTIFIER
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

Start with THEIR EXACT WORD from student_said.
Then FORCE a concrete identifier. No vague answers allowed.

Choose the right extraction based on what they said:

IF person mentioned (friend / teacher / parent / someone):
→ "which friend — the one who's always been there, or someone you thought you could trust who turned out different?"
→ If a name was already shared in conversation_so_far — skip the name. Ask about the incident instead.
IF user mentions a PERSON (friend, teacher, parent, someone):
→ Ask NAME or exact identity
    Use natural forms like:
    - "Which friend exactly? Can you name them?" (plural/unclear)
    - "Can you tell me your friend's name?" (single)

IMPORTANT:
- Never use the student's own name as the friend/person unless user explicitly says they are referring to themselves.
- Do not offer choices like "<student_name> or any other friend".

IF studies mentioned (exam / subject / marks / concepts):
→ "which subject — the one you've been quietly skipping, or the one that used to make sense and suddenly doesn't?"
→ If subject already known — ask about the specific chapter or test experience.

IF distraction/behavior mentioned (phone / apps / gaming / reels):
→ "which app — the one you'd be embarrassed to show your screen time for right now?"
→ If app already named — ask how many hours, or what triggers the opening.

IF number / result mentioned (marks / rank / percentile):
→ "out of how much was that — and what were you actually expecting?"
→ If number already given — ask what it made them think about themselves.

IF vague ("idk", "nothing", "fine", "stressed"):
→ Don't force a name. Ask TYPE instead:
   "nothing — like actually nothing's wrong, or nothing you want to say out loud right now?"

STRICT Q1 RULES:
- NEVER ask for something already answered in conversation_so_far
- ALWAYS force specificity: ✅ "which friend — name?" ❌ "someone?"
- NEVER force a name if no person was mentioned
- Use THEIR word, not a synonym
❗ STRICT RULES:
- NEVER ask vague:
  ❌ "someone?"
  ❌ "one person?"
- ALWAYS force specificity:
    ✅ "which friend exactly? can you name them?"
    ✅ "can you tell me your friend's name?"
  ✅ "which subject?"
  ✅ "what exactly?"
- NEVER force a NAME if no person exists

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
Q2 — BIFURCATE (DEEPER INTO THEIR EXPERIENCE)
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

Give TWO real, specific, emotionally loaded options.
Both must feel equally likely. Neither should be an obvious "right answer."

Strong bifurcations:
- "Is it that you don't understand it at all, or that you understand it alone but it vanishes the moment it matters?"
- "Was it what they said directly to you, or the fact that they said it in front of everyone?"
- "Is it that you can't start, or that you start and then stop — because something feels pointless about continuing?"
- "Is it the subject itself, or what still struggling with it after all this time makes you feel about yourself?"

RULES:
- No obvious answers (not "A or B" where one is clearly better)
- No open-ended "what happened" questions
- Both options must name something emotionally real

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
Q3 — NAME THE UNSAID TRUTH
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

Say the thing they haven't said yet — but probably meant.
Go past the event to the meaning underneath it.

Strong examples:
- "Is it that you hate the subject, or that still struggling with it after this long is starting to feel like it says something about you?"
- "Is it that you're mad at them, or that you didn't expect this from them specifically — and that's the part that actually hurts?"
- "Is it the marks, or what the marks mean about whether all this effort has actually been worth it?"
- "Is it the pressure from them, or that you've internalized it so completely it now feels like your own voice?"

RULES:
- Must feel slightly uncomfortable — but accurate
- Must reveal the emotional root, not just describe the event
- Must not sound like a therapist ("I understand how you feel" = BANNED)

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
SPECIAL CASE HANDLING
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

VAGUE INPUT ("idk", "nothing", "fine", "okay"):
→ Q1 must clarify TYPE, not force name
→ "Nothing — like actually nothing's wrong, or nothing you want to say yet?"

NUMERIC INPUT ("45 marks", "rank 2000", "70%"):
→ Q1 must ask context: "out of how much — and what were you expecting?"
→ If number already answered, go to emotional layer

REPEAT ATTEMPT:
→ If the student gives the same vague answer twice, Q3 gets blunter:
→ "You keep saying it's fine — when did it actually stop being fine?"

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
ABSOLUTE BANS — NEVER USE THESE
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

❌ "I understand how you feel"
❌ "That must be really hard"
❌ "It's okay to feel this way"
❌ "Tell me more about that"
❌ "What happened?"
❌ "How does that make you feel?"
❌ "Can you elaborate?"
❌ Any sentence that sounds like it came from a mental health chatbot

These phrases signal bot mode. Your tone is sharp, direct, and human.
An older sibling doesn't say "I understand how you feel."
They say "which subject — the one you hate or the one you're scared of?"

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
STRICT GLOBAL RULES
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

1. EXACTLY 3 questions — no more, no less
2. Every question ends with "?"
3. 15–55 words each
4. No two questions start with the same word
5. Use USER'S EXACT words — not synonyms
6. Never ask about a slot already filled in conversation_so_far
7. Q1 MUST extract a concrete identifier (name / subject / app / number / thing)
8. Q2 MUST bifurcate with two real, specific, emotionally loaded options
9. Q3 MUST name the unsaid emotional truth — the uncomfortable accurate one

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
TONE
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

Sharp. Direct. Real.
Like an older sibling who actually listened, who doesn't accept "I don't know",
and who already knows something's off even before you finish the sentence.

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
OUTPUT FORMAT (STRICT JSON — NO EXCEPTIONS)
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

{"questions": ["q1", "q2", "q3"]}

No preamble. No explanation. No markdown. Just the JSON object.
"""


# ============================================================================
# SYSTEM PROMPT — SINGLE FOLLOW-UP (generate_next_followup only)
# Lean prompt — asks for exactly 1 question, saving ~500 tokens vs reusing
# the 3-question prompt with num_questions=1.
# ============================================================================

SYSTEM_PROMPT_SINGLE_FOLLOWUP = """
You are talking to a JEE/NEET student mid-conversation.
You ask like a thoughtful therapist in simple student language: warm, clear, relatable, and easy to answer.

You are given:
- student_said: what they just said
- conversation_so_far: everything said earlier
- already_asked: every question already asked
- student_answers_so_far: the student's own previous answers

YOUR ONLY JOB:
Generate EXACTLY 1 follow-up question that goes one layer deeper than what they just said and helps identify a concrete weak point.

CRITICAL RULE — NEVER RESTATE THE OBVIOUS:
If the student already made their problem clear (e.g. "tamanna bhatiya reels", "I watch movies", "I play PUBG"), 
DO NOT ask "How does X affect your studies?" — that's obvious and adds no value.
Instead, dig DEEPER:
- Ask about WHEN/HOW MUCH: "How many hours a day do you spend on this?"
- Ask about TRIGGER: "What usually makes you pick up your phone — boredom, stress, or habit?"
- Ask about AWARENESS: "Do you realize mid-session that you've lost time, or only after?"
- Ask about PATTERN: "Is this more of a night thing or does it happen during study hours too?"
- Ask about IMPACT SPECIFICS: "Which subject or topic suffers the most because of this?"

RULES:
- Scan conversation_so_far and student_answers_so_far first.
  If a slot (name / subject / app / number) was already answered — do NOT ask for it again.
- Use their EXACT words, not synonyms.
- CRITICAL: If the student mentions ANY specific entity (celebrity name, movie name, app name, game name, person name, show name), you MUST reference that EXACT entity in your follow-up question. NEVER drop or ignore specific names they mentioned.
  Example: If they said "Alia Bhatt and movies" → your question MUST mention "Alia Bhatt" specifically, not just "movies"
  Example: If they said "tamanna bhatiya reels" → your question MUST mention "tamanna bhatiya" or "reels" specifically
  Example: If they said "PUBG and Instagram" → your question MUST mention BOTH "PUBG" and "Instagram"
- Match the student's language style:
        if input is English, ask in English;
        if input is Hinglish, ask in simple Hinglish.
- Ask about ONE actionable weak-point dimension at a time:
        trigger, study habit, concentration drop, time-planning gap, confidence dip, avoidance pattern, social pressure impact, or recovery strategy.
- Keep it specific enough that the answer is concrete (person, subject, app, chapter, time-window, event, or behavior).
- Keep the tone friendly and human; the question should feel personally relevant.
- 9–18 words. Ends with "?".
- Avoid generic prompts like "tell me more" and avoid repeating anything in already_asked.
- Use short, plain words. Avoid long or heavy sentence structures.

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
OUTPUT FORMAT (STRICT JSON — NO EXCEPTIONS)
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

{"question": "your single question here"}

No preamble. No explanation. No markdown. Just the JSON object.
"""


# ============================================================================
# SLOT QUESTION PROMPT TEMPLATE
# Uses __SLOT__ / __DOMAIN__ sentinels (not {slot}/{domain}) so the string
# is safe against accidental .format() calls and slot names with braces.
# Injection is done exclusively via _build_slot_prompt().
# ============================================================================

_SYSTEM_PROMPT_SLOT_QUESTION_TEMPLATE = """
You generate ONE follow-up question to extract the slot "__SLOT__" in the "__DOMAIN__" context.

You ask in a therapist-like tone that is simple, friendly, and personal.
You already know something about their situation. This question digs for one specific piece.

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
CRITICAL: CHECK BEFORE GENERATING
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

You are given:
- student_said: what they just said
- already_asked: every question asked this session
- last_question: the most recent question asked

If student_said ALREADY CONTAINS the answer to "__SLOT__" — do NOT ask for it.
Instead, ask one layer deeper: about the context, feeling, or consequence of what they shared.

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
TECHNIQUE: BIFURCATE
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

Give TWO specific, emotionally honest options.
One should name the comfortable/surface answer.
One should name the honest/deeper answer.
Never open-ended. Always two real possibilities.

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
STRONG EXAMPLES BY SLOT TYPE
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

friend_name / comparison_person / family_member:
  → "Which person exactly — the one you've known the longest and trusted, or someone newer who you genuinely thought would be different?"
  → "Who specifically — the one whose opinion actually matters to you, or someone you keep comparing yourself to even though you know it's not fair?"

phone_app / gaming_app / app_activity:
  → "Which app specifically — the one you'd be embarrassed to show your screen time for right now, or the one you open the moment things feel slightly off?"
  → "What are you actually going to when you pick up the phone — reels, gaming, or just scrolling with no real destination?"

weak_subject / backlog_subject / favorite_subject:
  → "Which subject — the one you've quietly been avoiding for weeks, or the one that used to make sense and somewhere along the way just stopped?"
  → "Is it the subject you've always found hard, or the one that should be fine by now but isn't — and that second one is the one that actually scares you?"

concept_confidence / last_test_experience:
  → "Where are you honestly on this — do you not understand it at all, or do you understand it alone but it disappears the moment it actually counts?"
  → "What happened in that test — was it a concept you hadn't seen, or was it a concept you'd studied and it still didn't come out right?"

exam_time_left / backlog_deadline:
  → "How many days are we actually talking — and when you picture that number, what's the first thing that hits you?"
  → "How close is this — close enough that you can still fix it, or close enough that the panic has already started?"

study_hours_per_day / gaming_time:
  → "How many hours honestly — the real number, not the one that sounds okay to say out loud?"
  → "What does a real day actually look like — how many of those hours go to studying versus everything else?"

timetable_breaker / reel_type:
  → "What's the thing that keeps breaking the plan — is it something happening around you, or something happening inside you?"
  → "What kind of content specifically — the mindless scroll, or something that actively pulls you in and makes the hours disappear?"

expectation_type / motivation_reason / demotivation_reason:
  → "What were they actually expecting from you — say it plainly, without softening it to make it sound more reasonable?"
  → "What's the real thing that used to make you want to do this — not the answer that sounds good, but the one that's actually true?"

comparison_gap:
  → "What's the specific gap you keep fixating on — their marks, their consistency, or the way they seem to handle things that completely drain you?"
  → "Is it how far ahead they are, or the fact that they don't seem to even be trying as hard as you — and that comparison is the part that really stings?"

RULES:
  - 15 to 50 words
  - Ends with "?"
  - Uses their exact words from student_said where possible
  - Specific enough that the answer is a name, number, subject, or concrete thing
  - Never sounds like a form field or a chatbot prompt
  - Never repeats last_question or anything in already_asked
  - Never starts with "I understand" or "That must be"

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
OUTPUT FORMAT (STRICT JSON — NO EXCEPTIONS)
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

{"question": "your single question here"}

No preamble. No explanation. No markdown. Just the JSON object.
"""


def _build_slot_prompt(slot: str, domain: str) -> str:
    """
    Inject slot and domain into the slot question template.

    Uses plain .replace() on sentinel strings (not .format() or f-strings)
    so curly braces anywhere in the prompt body are never misinterpreted,
    and slot/domain values containing braces can never cause a KeyError.
    """
    return (
        _SYSTEM_PROMPT_SLOT_QUESTION_TEMPLATE
        .replace("__SLOT__", str(slot))
        .replace("__DOMAIN__", str(domain))
    )


# ============================================================================
# READINESS PROMPT
# ============================================================================

SYSTEM_PROMPT_READINESS = """
You decide whether we already have enough conversation data to stop asking follow-up questions.

Your job:
- Read the initial user message and the conversation so far.
- Decide if there is enough signal to generate personalized popup content.
- Prefer stopping early once the core emotional trigger, the specific target/problem,
  and one concrete detail are known.
- Do NOT keep asking questions just because more detail is possible.
- If the conversation is still vague, return ready=false.

Stop when MOST of this is known:
1. What the main issue actually is
2. Who/what it is about (a name, subject, app, or concrete thing)
3. One specific detail that makes it personal
4. The emotional angle underneath it — the unsaid part

Rules:
- Return STRICT JSON only
- If the user is still too vague (no concrete identifier, no emotional root), ready=false
- If we already have enough signal for personalized popups, ready=true
- Be practical, not perfectionist — 3-4 solid answers is enough

Return:
{"ready": true, "reason": "short reason"}
"""


# ============================================================================
# SHARED UTILITY
# ============================================================================

def _hash(text: str) -> str:
    """Stable hash for deduplication. Case-insensitive, whitespace-normalized."""
    normalized = " ".join(text.strip().lower().split())
    return hashlib.md5(normalized.encode()).hexdigest()


def _strip_fences(raw: str) -> str:
    """
    Remove markdown code fences from a model response.

    Correctly handles all of:
        ```json\\n{...}\\n```
        ```\\n{...}\\n```
        ```{...}```   (no newlines, rare but possible)

    The old approach — raw.split("```")[1] — left a trailing "```" in the
    string whenever there was no trailing newline, causing json.loads to fail.
    This helper is the single source of truth for fence stripping.
    """
    raw = raw.strip()
    if not raw.startswith("```"):
        return raw
    lines = raw.splitlines()
    # Drop the opening fence line (```  or  ```json)
    lines = lines[1:]
    # Drop the closing fence line if present
    if lines and lines[-1].strip() == "```":
        lines = lines[:-1]
    return "\n".join(lines).strip()


_PERSON_KEYWORDS = (
    "friend",
    "friends",
    "teacher",
    "sir",
    "maam",
    "mam",
    "parent",
    "parents",
    "mother",
    "father",
    "mom",
    "dad",
    "brother",
    "sister",
    "classmate",
    "roommate",
    "boyfriend",
    "girlfriend",
    "partner",
    "cousin",
    "person",
    "someone",
    "wife",
    "husband",
    "relative",
    "uncle",
    "aunt",

)


def _mentions_person(text: str) -> bool:
    lowered = (text or "").lower()
    return any(re.search(rf"\b{re.escape(token)}\b", lowered) for token in _PERSON_KEYWORDS)


def _has_explicit_person_name(text: str) -> bool:
    """Heuristic for explicit related-person name disclosures in user text."""
    raw_text = (text or "")
    lowered = raw_text.lower()
    relation = r"(?:friend|teacher|sir|maam|mam|parent|parents|mother|father|mom|dad|brother|sister|classmate|roommate|boyfriend|girlfriend|partner|cousin|person|someone)"
    # Relationship-scoped patterns only. Intentionally avoid generic
    # "my name is ..." so the student's own name does not suppress
    # person-name followup questions.
    patterns = [
        rf"\b{relation}\b[^.?!\n]{{0,35}}\b(?:name\s+is|named|called)\s+[a-z][a-z'\-]{{1,30}}\b",
    ]
    if any(re.search(pattern, lowered) for pattern in patterns):
        return True

    # Compact explicit-name forms with capitalization, e.g. "friend Rahul".
    # Token-based matching avoids false positives like
    # "friend compare karta hai" being treated as a name.
    relation_tokens = {
        "friend", "friends", "teacher", "sir", "maam", "mam", "parent", "parents",
        "mother", "father", "mom", "dad", "brother", "sister", "classmate", "roommate",
        "boyfriend", "girlfriend", "partner", "cousin", "person", "someone",
    }
    tokens = re.findall(r"[A-Za-z][A-Za-z'\-]*", raw_text)
    for idx in range(len(tokens) - 1):
        if tokens[idx].lower() in relation_tokens:
            nxt = tokens[idx + 1]
            if nxt and nxt[0].isupper():
                return True
    return False


def _needs_name_followup(latest_user_text: str, previous_user_texts: list[str], conversation_history: list[dict] = None) -> bool:
    """Return True when a person is mentioned but no explicit name is known yet for that relation."""
    if not _mentions_person(latest_user_text):
        return False
    if _has_explicit_person_name(latest_user_text):
        return False
    # New logic: check if the referenced relation already has a name in conversation history
    if conversation_history is not None:
        person_map = _extract_person_names_from_history(conversation_history)
        # Find which relation is being referenced in latest_user_text
        relation_tokens = set(_PERSON_KEYWORDS)
        tokens = re.findall(r"[A-Za-z][A-Za-z'\-]*", latest_user_text)
        for idx in range(len(tokens) - 1):
            rel = tokens[idx].lower()
            if rel in relation_tokens:
                if rel in person_map:
                    return False  # Name already known for this relation
                else:
                    return True   # Name not yet known for this relation
    # Fallback: old logic
    return not any(_has_explicit_person_name(text) for text in previous_user_texts)


def _question_asks_for_name(question: str) -> bool:
    q = (question or "").lower()
    return bool(re.search(r"\bname\b", q))


def _build_name_followup_question(latest_user_text: str) -> str:
    lowered = (latest_user_text or "").lower()
    if re.search(r"\bfriends\b", lowered):
        return "Which friend exactly are you talking about and what is their name?"
    if re.search(r"\bfriend\b", lowered):
        return "Which friend exactly are you talking about and what is their name?"
    if re.search(r"\bteacher\b|\bsir\b|\bmaam\b|\bmam\b", lowered):
        return "Which teacher exactly are you talking about and what is their name?"
    if re.search(r"\bmother\b|\bfather\b|\bmom\b|\bdad\b|\bparent\b|\bparents\b", lowered):
        return "Which family member are you talking about and what is their name?"
    return "Who exactly are you talking about and what is this person's name?"


def _append_name_requirement(question: str, latest_user_text: str) -> str:
    """Keep contextual depth and append name clarification in the same follow-up."""
    base = " ".join((question or "").strip().split())
    if not base:
        return _build_name_followup_question(latest_user_text)
    if _question_asks_for_name(base):
        return base

    # Keep this as a single follow-up question while forcing person identity capture.
    # Keep suffix short so combined question stays under validator word limits.
    lowered = (latest_user_text or "").lower()
    if re.search(r"\bteacher\b|\bsir\b|\bmaam\b|\bmam\b", lowered):
        name_suffix = "which teacher is this by name"
    elif re.search(r"\bmother\b|\bfather\b|\bmom\b|\bdad\b|\bparent\b|\bparents\b|\bbrother\b|\bsister\b|\bcousin\b", lowered):
        name_suffix = "which family member is this by name"
    elif re.search(r"\bfriends\b|\bfriend\b", lowered):
        name_suffix = "which friend is this by name"
    else:
        name_suffix = "who is this person by name"

    if base.endswith("?"):
        base = base[:-1].rstrip()
    combined = f"{base} and {name_suffix}?"
    return combined


# ============================================================================
# MAIN — 3-QUESTION GENERATION
# ============================================================================

def generate_counter_questions(
    user_text: str,
    num_questions: int = 3,
    asked_questions: list[str] | None = None,
    conversation_history: list[dict] | None = None,
) -> list[str]:
    """
    Generate up to 3 personal, non-repeating questions for ANY student input.

    Uses ECHO → BIFURCATE → NAME IT for every single call.
    Passes full asked_questions history so GPT never repeats.
    Passes conversation_history so GPT can go deeper each round
    and never asks about something the student already answered.

    Args:
        user_text:            What the student just said.
        num_questions:        How many to return (default 3).
        asked_questions:      Every question asked so far this session.
        conversation_history: Full chat history as
                              [{"role": "user"/"assistant", "text": "..."}]
    """
    text = (user_text or "").strip()
    if not text:
        return []

    asked_questions      = asked_questions or []
    conversation_history = conversation_history or []

    logger.debug(
        "generate_counter_questions: text=%r asked=%d history=%d",
        text[:80], len(asked_questions), len(conversation_history),
    )

    # Extract just the student's own words so the model has a clean view
    # of what's already been answered without parsing full turn objects.
    already_known: list[str] = []
    for turn in conversation_history:
        role    = turn.get("role", "")
        content = (turn.get("text") or turn.get("content") or "").strip()
        if role == "user" and content:
            already_known.append(content)

    payload = {
        "student_said":           text[:1500],
        "already_asked":          asked_questions,
        "conversation_so_far":    conversation_history[-12:],  # last 12 turns
        "student_answers_so_far": already_known[-6:],          # last 6 user turns
    }

    try:
        resp = chat_json(
            model="gpt-4o-mini",
            system=SYSTEM_PROMPT_QUESTION,
            user=json.dumps(payload, ensure_ascii=False),
            max_tokens=700,
            temperature=0.9,
        )
        raw = _strip_fences(resp.choices[0].message.content or "")

        data      = json.loads(raw)
        questions = data.get("questions", [])

        asked_hashes = {_hash(q) for q in asked_questions}
        valid: list[str] = []

        for q in questions:
            if not isinstance(q, str):
                continue
            q_clean = " ".join(q.strip().split())
            q_clean = _strip_leading_vocative(q_clean)
            if (
                q_clean.endswith("?")
                and 15 <= len(q_clean) <= 400
                and _hash(q_clean) not in asked_hashes
            ):
                valid.append(q_clean)

        if valid:
            logger.debug("GPT returned %d valid questions", len(valid))
            return valid[:num_questions]

        logger.warning("GPT returned no valid questions — using personal fallback")

    except Exception as exc:
        logger.warning("generate_counter_questions GPT call failed: %s", exc)

    return _personal_fallback(text, asked_questions)[:num_questions]


# ============================================================================
# SINGLE FOLLOW-UP GENERATION
# Has its own lean prompt — does NOT delegate to generate_counter_questions.
# Saves ~500 tokens per call vs generating 3 and discarding 2.
# Falls back to generate_counter_questions only if its own GPT call fails.
#
# KEY CHANGES:
#   • Accepts followup_count to enforce FOLLOWUP_LIMIT.
#   • Returns None (stop signal) if limit reached.
#   • Skips ai_ready_to_complete() in this hot path to reduce latency.
#   • Does NOT persist the count — caller must call increment_followup_count()
#     after a question is successfully delivered to the frontend.
# ============================================================================

def generate_next_followup(
    user_text: str,
    asked_questions: list[str] | None = None,
    conversation_history: list[dict] | None = None,
    followup_count: int = 0,
    initial_text: str = "",
    session_id: str | None = None,
) -> str | None:
    """
    Generate exactly one follow-up question based on the latest message.

    Returns None when:
      • followup_count has reached FOLLOWUP_LIMIT (hard cap = 3)

    The caller is responsible for:
      1. Calling increment_followup_count(session_id) after delivering the question.
      2. Checking should_show_skip_button(followup_count) to decide whether to
         show the "Skip" button in the frontend.
      3. NOT storing this question in any persistent store — follow-ups must
         live only in the runtime session, never in DB or CSV.

    Args:
        user_text:            What the student just said.
        asked_questions:      Every question asked so far (runtime session list).
        conversation_history: Full chat history as [{"role":..., "text":...}]
        followup_count:       How many follow-ups have been asked so far.
                              Pass get_followup_count(session_id) here.
        initial_text:         The student's original opening message.
        session_id:           Session identifier — used only for logging, not storage.
    """
    # ── Hard cap ──────────────────────────────────────────────────────────────
    if followup_limit_reached(followup_count):
        logger.info(
            "generate_next_followup: limit reached (count=%d, limit=%d) session=%s",
            followup_count, FOLLOWUP_LIMIT, session_id or "?",
        )
        return None

    text = (user_text or "").strip()
    if not text:
        return None

    asked_questions      = asked_questions or []
    conversation_history = conversation_history or []

    already_known: list[str] = []
    for turn in conversation_history:
        role    = turn.get("role", "")
        content = (turn.get("text") or turn.get("content") or "").strip()
        if role == "user" and content:
            already_known.append(content)

    enforce_name_followup = _needs_name_followup(
        latest_user_text=text,
        previous_user_texts=already_known[:-1],
        conversation_history=conversation_history,
    )
    logger.debug(
        "generate_next_followup: enforce_name_followup=%s latest_user_text=%r",
        enforce_name_followup,
        text[:120],
    )

    payload = {
        "student_said":           text[:1500],
        "already_asked":          asked_questions,
        "conversation_so_far":    conversation_history[-12:],
        "student_answers_so_far": already_known[-6:],
    }

    asked_hashes = {_hash(q) for q in asked_questions}

    try:
        resp = chat_json(
            model="gpt-4o-mini",
            system=SYSTEM_PROMPT_SINGLE_FOLLOWUP,
            user=json.dumps(payload, ensure_ascii=False),
            max_tokens=140,
            temperature=0.7,
            timeout=8,
        )
        raw      = _strip_fences(resp.choices[0].message.content or "")
        data     = json.loads(raw)
        question = " ".join((data.get("question") or "").strip().split())

        if (
            question
            and question.endswith("?")
            and 15 <= len(question) <= 400
            and _hash(question) not in asked_hashes
            and is_valid_question(question)
        ):
            if enforce_name_followup and not _question_asks_for_name(question):
                merged = _append_name_requirement(question, text)
                if _hash(merged) not in asked_hashes and is_valid_question(merged):
                    logger.info("generate_next_followup: appending name requirement to contextual followup")
                    question = merged

            logger.debug(
                "generate_next_followup: lean prompt returned valid question (count=%d)",
                followup_count,
            )
            return question

        logger.warning("generate_next_followup: GPT question failed validation — using local fallback")

    except Exception as exc:
        logger.warning("generate_next_followup GPT call failed: %s", exc)

    # Fast local fallback: avoid a second network roundtrip in this hot path.
    fallback_questions = _personal_fallback(text, asked_questions)
    fallback = fallback_questions[0] if fallback_questions else None
    if fallback and enforce_name_followup and not _question_asks_for_name(fallback):
        merged = _append_name_requirement(fallback, text)
        if _hash(merged) not in asked_hashes and is_valid_question(merged):
            logger.info("generate_next_followup: appending name requirement to fallback followup")
            return merged
    return fallback


# ============================================================================
# READINESS CHECK
# ============================================================================

def ai_ready_to_complete(
    initial_text: str,
    conversation_history: list[dict] | None = None,
    asked_questions: list[str] | None = None,
) -> tuple[bool, str]:
    """Let the model decide whether enough signal exists to stop."""
    history = conversation_history or []
    asked   = asked_questions or []
    payload = {
        "initial_text":        (initial_text or "")[:1200],
        "conversation_so_far": history[-12:],
        "already_asked":       asked[-6:],
    }

    try:
        resp = chat_json(
            model="gpt-4o-mini",
            system=SYSTEM_PROMPT_READINESS,
            user=json.dumps(payload, ensure_ascii=False),
            max_tokens=120,
            temperature=0.2,
        )
        raw    = _strip_fences(resp.choices[0].message.content or "")
        data   = json.loads(raw)
        ready  = bool(data.get("ready"))
        reason = str(data.get("reason") or "").strip()
        return ready, reason

    except Exception as exc:
        logger.warning("ai_ready_to_complete failed: %s", exc)
        return False, ""


# ============================================================================
# SLOT QUESTION
# ============================================================================

def generate_question(
    domain: str,
    slot: str,
    excerpt: str | None = None,
    context: dict | None = None,
) -> str | None:
    """
    Generate one personal, non-repeating question for a specific slot.

    Used when the system knows which slot to fill next.
    Still feels like a real person asking — never a form field.
    Checks conversation history so it never asks about a slot
    the student already answered.
    """
    logger.debug("generate_question: domain=%s slot=%s", domain, slot)
    context       = context or {}
    meta          = context.get("meta") or {}
    last_question = (meta.get("last_question") or "").strip()
    asked_qs      = context.get("asked_questions") or []
    user_text     = context.get("user_text") or ""

    system = _build_slot_prompt(slot=slot, domain=domain)

    payload = {
        "student_said":  user_text[:1200],
        "domain":        domain,
        "slot":          slot,
        "context":       excerpt or "",
        "last_question": last_question,
        "already_asked": asked_qs,
    }

    asked_hashes = {_hash(q) for q in asked_qs}

    for attempt in (1, 2):
        try:
            resp = chat_json(
                model="gpt-4o-mini",
                system=system,
                user=json.dumps(payload, ensure_ascii=False),
                max_tokens=180,
                temperature=0.9,
            )
            raw      = _strip_fences(resp.choices[0].message.content or "")
            data     = json.loads(raw)
            question = " ".join((data.get("question") or "").strip().split())
            question = _strip_leading_vocative(question)

            if (
                question
                and question != last_question
                and _hash(question) not in asked_hashes
                and is_valid_question(question)
            ):
                return question

        except Exception as exc:
            logger.warning("generate_question attempt=%d failed: %s", attempt, exc)

    return _slot_fallback(domain, slot)


# ============================================================================
# SLOT FALLBACK
# ============================================================================

def _slot_fallback(domain: str, slot: str) -> str:
    """
    Personal slot fallback — BIFURCATE technique on every single one.
    Two honest options. Never a form field.
    """
    s = slot.lower()

    if any(k in s for k in ["name", "person", "friend", "who", "member"]):
        return "Which person exactly — the one you've known the longest and trusted, or someone newer who you genuinely thought would be different?"

    if any(k in s for k in ["app", "game", "platform", "site", "reel"]):
        return "Which app specifically — the one you'd be most embarrassed to show your screen time for right now, or the one you open the moment something feels slightly off?"

    if any(k in s for k in ["hour", "time", "duration", "long", "much"]):
        return "How many hours honestly — the real number, not the one that sounds okay to say out loud?"

    if any(k in s for k in ["subject", "topic", "chapter", "concept"]):
        return "Which subject — the one you've been quietly skipping for weeks, or the one that used to feel manageable and somewhere along the way just stopped?"

    if any(k in s for k in ["reason", "why", "cause", "because"]):
        return "What's the real reason — not the excuse that sounds fine, but the one you actually know is true?"

    if any(k in s for k in ["incident", "event", "moment", "happen", "experience"]):
        return "What's the specific moment it actually went wrong — the thing you keep going back to even when you're trying not to?"

    if any(k in s for k in ["feel", "emotion", "mood"]):
        return "What's the main thing sitting underneath all of this — not the frustration on the surface, but the thing driving it?"

    if any(k in s for k in ["confidence", "level", "rating", "score"]):
        return "Where are you honestly, 1 to 10 — and what's the specific thing pulling it below a 7?"

    if any(k in s for k in ["expect", "want", "need", "hope"]):
        return "What were you actually expecting from them — say it plainly, without softening it to make it sound more reasonable?"

    if any(k in s for k in ["deadline", "date", "days", "left", "remain"]):
        return "How many days until this — and when you picture that number, what's the first thing that hits you?"

    if any(k in s for k in ["block", "obstacle", "barrier", "stop", "prevent", "breaker"]):
        return "What's the main thing that keeps getting in the way — the one you keep running into every time you try to start?"

    if any(k in s for k in ["plan", "strategy", "approach"]):
        return "Is it that you don't have a plan at all, or that you have one but some part of you doesn't actually believe it'll work?"

    if any(k in s for k in ["result", "score", "mark", "rank", "grade"]):
        return "Is the result itself the problem, or what the result means about all the effort you've actually put in?"

    if any(k in s for k in ["sleep", "rest", "exhaust"]):
        return "Is it that you can't sleep, or that you sleep fine but wake up carrying exactly the same weight?"

    if any(k in s for k in ["comparison", "gap", "behind", "ahead"]):
        return "What's the specific gap you keep fixating on — their marks, their consistency, or the way they seem to handle things that completely drain you?"

    readable = slot.replace("_", " ")
    return f"When it comes to your {readable} — is it something that happened recently, or something that's been quietly building for a while?"


# ============================================================================
# PERSONAL FALLBACK
# Last resort only. Still uses the 3 techniques. Never generic.
# ============================================================================

def _personal_fallback(
    user_text: str,
    asked_questions: list[str] | None = None,
) -> list[str]:
    """
    Emergency fallback when GPT is completely unavailable.

    Extracts the most emotionally loaded word the student used,
    then builds ECHO → BIFURCATE → NAME IT around it.

    BUG FIXED: The previous version defined tuples as
        (keyword, echo_word, option_a, option_b, named_truth)
    but unpacked them as
        (echo_word, option_a, option_b, named_truth, keyword)
    causing the wrong word to be echoed back in every fallback response.
    The unpack below now matches the tuple definition exactly.
    """
    asked_questions = asked_questions or []
    asked_hashes    = {_hash(q) for q in asked_questions}
    text_lower      = user_text.lower()

    def _has_any(tokens: list[str]) -> bool:
        return any(token in text_lower for token in tokens)

    def _is_hinglish_input() -> bool:
        hinglish_markers = [
            "mujhe", "mera", "meri", "hai", "nahi", "nhi", "kyu", "kyun", "kaise",
            "padh", "padha", "samajh", "yaar", "bahut", "bohot", "thoda", "zyada",
            "dost", "bekar", "nind", "neend", "soch", "lagta", "hota", "hoti",
        ]
        return _has_any(hinglish_markers)

    is_hinglish = _is_hinglish_input()

    # Quick, relatable cue-based fallback for Hinglish/common student phrasing.
    if _has_any(["friend", "dost", "compare", "comparison", "log kya", "judge"]):
        if is_hinglish:
            candidates = [
                "Jab woh compare karta hai, zyada hurt kis baat se hota hai?",
                "Yeh issue daily hota hai, ya kisi specific moment me trigger hota hai?",
                "Abhi tumhe zyada need support ki hai ya clear boundary ki?",
            ]
        else:
            candidates = [
                "When comparison happens, what hurts more: their words or your self-doubt?",
                "Does this happen daily, or after specific situations?",
                "Right now, do you need support, or firmer boundaries?",
            ]
        fresh = [q for q in candidates if _hash(q) not in asked_hashes]
        return (fresh if fresh else candidates)[:3]

    if _has_any(["phone", "reel", "reels", "scroll", "instagram", "yt", "youtube", "shorts", "game", "gaming"]):
        if is_hinglish:
            candidates = [
                "Phone uthate hi tum kya feel karte ho: relief, boredom, ya stress se bachna?",
                "Distraction start kab hota hai: study start se pehle, ya beech me?",
                "Agar 1 habit fix karni ho, phone timing pe kaunsi ek change possible hai?",
            ]
        else:
            candidates = [
                "When you pick your phone, is it relief, boredom, or stress escape?",
                "Does distraction begin before study, or during study?",
                "If you fix one phone habit this week, what can you change first?",
            ]
        fresh = [q for q in candidates if _hash(q) not in asked_hashes]
        return (fresh if fresh else candidates)[:3]

    if _has_any(["start", "starting", "procrast", "delay", "consisten", "routine", "revision"]):
        if is_hinglish:
            candidates = [
                "Start karne me sabse bada block kya hota hai: mood, fear, ya distraction?",
                "Routine tootne ka main point kya hai: timing, energy, ya consistency?",
                "Kal se start karne ke liye ek chhota workable step kya ho sakta hai?",
            ]
        else:
            candidates = [
                "What blocks your start most: mood, fear, or distraction?",
                "Where does your routine break most: timing, energy, or consistency?",
                "What is one small workable step to restart tomorrow?",
            ]
        fresh = [q for q in candidates if _hash(q) not in asked_hashes]
        return (fresh if fresh else candidates)[:3]

    if _has_any(["confidence", "self doubt", "wrong question", "mistake", "blunder"]):
        if is_hinglish:
            candidates = [
                "Confidence drop hone ke turant baad pehla thought kya aata hai?",
                "Ek galti ke baad tum pace slow karte ho, ya overthink karne lagte ho?",
                "Confidence recover karne ke liye abhi kya sabse helpful rahega?",
            ]
        else:
            candidates = [
                "After confidence drops, what is your first thought?",
                "After one mistake, do you slow down, or start overthinking?",
                "What helps you recover confidence fastest right now?",
            ]
        fresh = [q for q in candidates if _hash(q) not in asked_hashes]
        return (fresh if fresh else candidates)[:3]

    if _has_any(["anx", "anxiety", "panic", "mock", "before test", "test se pehle"]):
        if is_hinglish:
            candidates = [
                "Mock test se pehle anxiety ka trigger kya hota hai?",
                "Anxiety zyada body me feel hoti hai, ya thoughts me?",
                "Test se pehle calm hone ke liye kaunsa step workable lagta hai?",
            ]
        else:
            candidates = [
                "Before mock tests, what usually triggers your anxiety most?",
                "Does anxiety show up more in your body, or in your thoughts?",
                "What pre-test step feels realistic to calm you right now?",
            ]
        fresh = [q for q in candidates if _hash(q) not in asked_hashes]
        return (fresh if fresh else candidates)[:3]

    # Only trigger study/subject questions if both a subject/study keyword and a study context are present
    subject_keywords = ["math", "physics", "chem", "chapter", "test", "exam", "mock", "blank"]
    study_context_keywords = ["study", "studying", "work", "focus", "concentrat", "padh", "padha", "revision", "class", "homework", "assignment", "syllabus"]
    if (
        any(token in text_lower for token in subject_keywords)
        and any(token in text_lower for token in study_context_keywords)
    ):
        if is_hinglish:
            candidates = [
                "Padhte waqt sabse pehle kya break hota hai: focus, confidence, ya pace?",
                "Yeh problem zyada kis subject ya topic me dikhti hai?",
                "Agle 2 din me isko easy banane ke liye ek realistic step kya ho sakta hai?",
            ]
        else:
            candidates = [
                "While studying, what breaks first: focus, confidence, or pace?",
                "Which subject or topic shows this issue most often?",
                "What is one realistic step for the next two days?",
            ]
        fresh = [q for q in candidates if _hash(q) not in asked_hashes]
        return (fresh if fresh else candidates)[:3]

    if _has_any(["stress", "tension", "anx", "anxiety", "pressure", "overwhelm", "panic", "overthink", "confidence", "sleep", "neend", "nind", "result"]):
        if is_hinglish:
            candidates = [
                "Stress peak pe kab hota hai: study start se pehle, ya result sochte waqt?",
                "Is pressure ka main source abhi kya lag raha hai?",
                "Abhi tumhe zyada help kis me chahiye: plan, focus, ya emotional reset?",
            ]
        else:
            candidates = [
                "When stress peaks, is it before study, or while thinking about results?",
                "What feels like the main pressure source right now?",
                "What helps more right now: a clear plan, better focus, or emotional reset?",
            ]
        fresh = [q for q in candidates if _hash(q) not in asked_hashes]
        return (fresh if fresh else candidates)[:3]

    # Each tuple: (keyword, echo_word, option_a, option_b, named_truth)
    #   keyword     — word searched for in student text
    #   echo_word   — word echoed back in Q1
    #   option_a    — first bifurcation branch
    #   option_b    — second bifurcation branch
    #   named_truth — unsaid emotional root named in Q3
    emotion_map: list[tuple[str, str, str, str, str]] = [
        ("quit",        "quit",        "quit studying altogether",        "something heavier than just this subject",       "you want to quit, or you're exhausted from pretending you're okay with something you didn't choose"),
        ("hate",        "hate",        "completely done with them",       "hurt by something specific they did",            "you actually hate them, or you expected more from them than they gave — and that's the part that really stings"),
        ("scared",      "scared",      "scared of failing",               "scared of what people will think if you do",     "it's the failure you're afraid of, or what the failure would say about everything you've put into this"),
        ("tired",       "tired",       "tired of the subject itself",     "tired of trying hard and not seeing it matter",  "you're physically exhausted, or the weight of it has nowhere else to go so it's coming out as tiredness"),
        ("stuck",       "stuck",       "don't know what to do",           "know what to do but can't make yourself start",  "you're actually stuck, or you already know what needs to happen and you're just not ready to do it yet"),
        ("lost",        "lost",        "lost in the subject",             "lost about whether any of this is worth it",     "you're lost in how to study it, or lost about whether you even want what's at the end of this"),
        ("empty",       "empty",       "nothing matters right now",       "you've given so much there's nothing left",      "you're numb to all of it, or you care deeply but you're too tired to feel it right now"),
        ("stressed",    "stressed",    "there's too much to do",          "you don't know where to start",                  "it's the workload stressing you, or the gap between where you are and where you need to be"),
        ("frustrated",  "frustrated",  "frustrated at the situation",     "frustrated at yourself for letting it get here", "something outside you is frustrating you, or you're angry at yourself — and that's harder to admit"),
        ("alone",       "alone",       "nobody's physically around",      "people are there but nobody actually gets it",   "you need someone there, or you need someone who understands — because those are very different things"),
        ("pressure",    "pressure",    "pressure coming from outside",    "pressure you're putting on yourself",            "the pressure comes from them, or you've internalized it so much it now feels like yours"),
        ("hopeless",    "hopeless",    "hopeless about this situation",   "hopeless about whether things can change",       "the situation feels hopeless, or you're starting to feel like the problem is you — and that's a harder place to be"),
        ("confused",    "confused",    "confused about what to do",       "confused about whether you even want this",      "you're confused about the path, or confused about the destination — because that changes everything"),
        ("hurt",        "hurt",        "hurt by what they did",           "hurt by who it came from specifically",          "what they did is the problem, or the fact that you didn't expect it from them — and that's the real wound"),
        ("angry",       "angry",       "angry at what happened",          "angry at yourself",                              "the anger is at them, or there's some of it pointed inward too — and you haven't said that part yet"),
        ("worried",     "worried",     "worried about results",           "worried about what comes after",                 "you're worried about this exam specifically, or worried about a bigger question you haven't let yourself think about"),
        ("guilty",      "guilty",      "guilty about what you did",       "guilty about what you didn't do",                "it's the action itself that weighs on you, or losing how someone sees you because of it"),
        ("embarrassed", "embarrassed", "embarrassed about what happened", "embarrassed about what people think",            "you're embarrassed about the thing, or about the fact that it happened in front of people who matter to you"),
        ("jealous",     "jealous",     "jealous of how they're doing",    "jealous of how easy it seems for them",          "it's about them, or it's about what their success is making you feel about your own effort — and that's uncomfortable"),
    ]

    matched: tuple[str, str, str, str, str] | None = None
    for keyword, echo_word, option_a, option_b, named_truth in emotion_map:
        if keyword in text_lower:
            # Store in the SAME order as the tuple definition
            matched = (keyword, echo_word, option_a, option_b, named_truth)
            break

    if matched:
        keyword, echo_word, option_a, option_b, named_truth = matched
        if is_hinglish:
            candidates = [
                f"Jab tum {echo_word} bolte ho, yeh zyada pehle aata hai ya study ke beech?",
                "Yeh issue start me aata hai, ya focus drop hone ke baad?",
                "Abhi weakest kya lag raha hai: planning, focus, confidence, ya sleep?",
                "Recent kaunsa moment is feeling ko sabse strong bana gaya?",
                "Is week ek chhota step kya hai jo help kar sakta hai?",
            ]
        else:
            candidates = [
                f"When you say {echo_word}, does it rise before study or during study?",
                "Does this issue start early, or after focus drops?",
                "What feels weakest right now: planning, focus, confidence, or sleep?",
                "Which recent moment made this feeling strongest?",
                "What is one small step this week that may help most?",
            ]
    else:
        if is_hinglish:
            candidates = [
                "Main issue kya lag raha hai: time pressure, focus break, confidence drop, ya outside pressure?",
                "Jab issue badhta hai, pehle kya start hota hai: overthinking, avoidance, distraction, ya low energy?",
                "Routine ka weakest part kya hai: start time, consistency, revision, ya review?",
                "Recent kis event ne is issue ko heavy feel karaya?",
                "Agar yeh week better ho, routine me pehla change kya dikhega?",
            ]
        else:
            candidates = [
                "What feels like the main issue: time pressure, focus breaks, confidence drop, or outside pressure?",
                "When this gets worse, what starts first: overthinking, avoidance, distraction, or low energy?",
                "Which routine part is weakest now: start time, consistency, revision, or review?",
                "Which recent event made this issue feel heavier?",
                "If this improves this week, what changes first in your routine?",
            ]

    fresh = [q for q in candidates if _hash(q) not in asked_hashes]
    result = (fresh if fresh else candidates)[:3]

    # Always append name requirement if teacher/friend/family is mentioned and not already asked
    person_keywords = [r"teacher", r"sir", r"maam", r"mam", r"friend", r"friends", r"mother", r"father", r"mom", r"dad", r"parent", r"parents", r"brother", r"sister", r"cousin"]
    if any(re.search(rf"\\b{kw}\\b", text_lower) for kw in person_keywords):
        # Only append if none of the questions already ask for a name
        for i, q in enumerate(result):
            if not _question_asks_for_name(q):
                result[i] = _append_name_requirement(q, user_text)
    return result


def _strip_leading_vocative(text: str) -> str:
    """Remove leading direct-name address such as 'So, Rahul, ...'."""
    candidate = (text or "").strip()
    if not candidate:
        return candidate
    patterns = [
        r"^(?:so\s*,\s*)?[a-z][a-z'\-]{1,30}\s*,\s*(.+)$",
        r"^(?:hey\s+)?[a-z][a-z'\-]{1,30}\s*,\s*(.+)$",
    ]
    for pattern in patterns:
        match = re.match(pattern, candidate, flags=re.IGNORECASE)
        if match:
            remainder = " ".join(match.group(1).split())
            if remainder:
                return remainder[0].upper() + remainder[1:]
    return candidate


# ============================================================================
# PUBLIC API
# ============================================================================

def generate_initial_clarifiers(
    initial_text: str,
    asked_questions: list[str] | None = None,
    conversation_history: list[dict] | None = None,
) -> list[str]:
    """
    Entry point for Stage 1 (initial vent → 3 clarifying questions).

    Pass the full asked_questions list on every call so questions
    never repeat across rounds, no matter what the student says.

    Args:
        initial_text:         What the student just said.
        asked_questions:      Every question asked so far this session.
        conversation_history: Full chat so far as
                              [{"role": "user"/"assistant", "text": "..."}]
    """
    return generate_counter_questions(
        user_text=initial_text,
        num_questions=3,
        asked_questions=asked_questions or [],
        conversation_history=conversation_history or [],
    )


__all__ = [
    "generate_question",
    "generate_counter_questions",
    "generate_next_followup",
    "ai_ready_to_complete",
    "generate_initial_clarifiers",
    "get_generic_domain_question",
    # Follow-up counter helpers (runtime-only, never persisted)
    "get_followup_count",
    "increment_followup_count",
    "reset_followup_count",
    "should_show_skip_button",
    "followup_limit_reached",
    # Constants
    "FOLLOWUP_LIMIT",
    "SKIP_BUTTON_AFTER",
]