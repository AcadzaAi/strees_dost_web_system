"""Checks every message before anyone sees it.

1. Group rules from Mongo `settings/moderation` (editable without a redeploy):
   bannedWords (vulgar / abusive, English + Hinglish), competitors (other coachings' names),
   and for students: no links, no phone numbers, no WhatsApp/Telegram invites.
2. OpenAI's moderation model (free) for harassment, hate and sexual content.
   If it can't be reached in time the message is still checked by the rules above.

Self-harm signals are never silently blocked: the message goes through and admins are alerted,
because a student who says that needs a person to notice.
"""
from __future__ import annotations

import logging
import re
import time
import unicodedata
from dataclasses import dataclass, field
from typing import Optional

import requests

from . import settings
from .mongo import db

log = logging.getLogger(__name__)

DEFAULT_RULES = {
    "bannedWords": [
        # English
        "fuck", "fucker", "fucking", "bitch", "bastard", "asshole", "dick", "pussy", "slut", "whore",
        "motherfucker", "porn", "nude", "nudes", "sex chat",
        # Hinglish (common spellings; extend from the admin panel)
        "madarchod", "mc", "behenchod", "bc", "bhenchod", "chutiya", "chutiye", "chut", "lund",
        "lauda", "loda", "gaand", "gand", "randi", "harami", "kamina", "bhosdike", "bsdk", "chod",
        "tatti", "jhaatu", "suar",
    ],
    "competitors": [
        "allen", "aakash", "physics wallah", "physicswallah", "pw app", "unacademy", "vedantu",
        "motion iit", "motion kota", "fiitjee", "resonance", "narayana", "sri chaitanya",
        "byjus", "byju's", "infinity learn", "embibe", "doubtnut", "apni kaksha",
    ],
    "blockLinksForStudents": True,
    "blockPhonesForStudents": True,
    "useAiModeration": True,
}

_LEET = str.maketrans({"0": "o", "1": "i", "3": "e", "4": "a", "5": "s", "7": "t", "@": "a", "$": "s", "!": "i"})
_URL = re.compile(
    r"(https?://|www\.|t\.me/|wa\.me/|chat\.whatsapp"
    r"|\b[a-z0-9-]+\.(com|in|net|org|io|me|app|link|ly|co|xyz|us|gg|edu|gov|ai|tv|to|cc|info|biz|live|site|online|page|dev|club|tech|store)\b"
    r"|\b[a-z0-9-]+\.[a-z]{2,6}/\S+)",            # any site with a path: zoom.us/j/123, meet.new/abc
    re.I)
_PHONE = re.compile(r"(?<!\d)(?:\+?91[\s-]?)?[6-9](?:[\s-]?\d){9}(?!\d)")
_INVITE = re.compile(r"\b(whatsapp|telegram|insta(gram)?|snapchat|discord)\s*(group|grp|channel|id|link|pe|par|me)\b", re.I)

AI_BLOCK = ("harassment", "harassment/threatening", "hate", "hate/threatening", "sexual", "sexual/minors", "illicit")
AI_ALERT = ("self-harm", "self-harm/intent", "self-harm/instructions")

_rules_cache: tuple[float, dict] = (0.0, DEFAULT_RULES)


@dataclass
class Verdict:
    allowed: bool
    reasons: list[str] = field(default_factory=list)
    alert: bool = False          # deliver, but tell admins (self-harm)

    @property
    def message(self) -> str:
        if self.reasons == ["link_admin"]:
            return "Only admins can send links."
        if "competitor" in self.reasons:
            return "Promoting other coachings isn't allowed in this group."
        if "link" in self.reasons or "phone" in self.reasons or "invite" in self.reasons:
            return "Links, phone numbers and group invites aren't allowed here."
        return "This message goes against the group rules."


def rules() -> dict:
    global _rules_cache
    at, cached = _rules_cache
    if time.time() - at < 60:
        return cached
    doc = db().settings.find_one({"_id": "moderation"}) or {}
    merged = {**DEFAULT_RULES, **{k: v for k, v in doc.items() if k != "_id"}}
    _rules_cache = (time.time(), merged)
    return merged


def normalize(text: str) -> str:
    t = unicodedata.normalize("NFKD", text).encode("ascii", "ignore").decode().lower()
    t = t.translate(_LEET)
    t = re.sub(r"(.)\1{2,}", r"\1\1", t)          # "fuuuuck" -> "fuuck"
    t = re.sub(r"[^a-z0-9'\s]", " ", t)
    return re.sub(r"\s+", " ", t).strip()


def _collapse(t: str) -> str:
    """Every repeated letter once: "fuuuck" and "fuck" compare equal."""
    return re.sub(r"(.)\1+", r"\1", t)


def _has_term(norm: str, squeezed: str, term: str) -> bool:
    term_n = normalize(term)
    if not term_n:
        return False
    if " " in term_n:
        return term_n in norm or _collapse(term_n) in _collapse(norm)
    if re.search(rf"\b{re.escape(term_n)}\b", norm):
        return True
    # Stretched spellings, only for words of 4+ letters: short ones ("bc", "mc") must match exactly,
    # or "bcc" (a crystal lattice) would read as "bc".
    if len(term_n) >= 4 and re.search(rf"\b{re.escape(_collapse(term_n))}\b", _collapse(norm)):
        return True
    # "f u c k" / "f.u.c.k": letters spread out with spaces
    return len(term_n) >= 4 and re.search(rf"\b{re.escape(_collapse(term_n))}\b", _collapse(squeezed)) is not None


def has_link(text: str) -> bool:
    return bool(_URL.search(text or ""))


def check(text: str, *, is_staff: bool, ai: bool = True, can_link: Optional[bool] = None) -> Verdict:
    """[can_link]: links (a Meet link, a PDF on Drive…) are for admins only. None = the old rule
    (staff yes, students no)."""
    r = rules()
    norm = normalize(text)
    squeezed = re.sub(r"\b(\w) (?=\w\b)", r"\1", norm)
    reasons: list[str] = []

    if any(_has_term(norm, squeezed, w) for w in r.get("bannedWords", [])):
        reasons.append("abusive")
    if is_staff and can_link is False and r.get("blockLinksForStudents", True) and _URL.search(text):
        reasons.append("link_admin")                   # a teacher who isn't an admin
    if not is_staff:
        if any(_has_term(norm, squeezed, c) for c in r.get("competitors", [])):
            reasons.append("competitor")
        if r.get("blockLinksForStudents", True) and _URL.search(text):
            reasons.append("link")
        if r.get("blockPhonesForStudents", True) and _PHONE.search(text):
            reasons.append("phone")
        if _INVITE.search(text):
            reasons.append("invite")

    alert = False
    if not reasons and ai and r.get("useAiModeration", True):
        ai = _ai_categories(text)
        if ai:
            blocked = [c for c in AI_BLOCK if ai.get(c)]
            if blocked:
                reasons.extend(f"ai:{c}" for c in blocked)
            alert = any(ai.get(c) for c in AI_ALERT)

    return Verdict(allowed=not reasons, reasons=reasons, alert=alert)


def _ai_categories(text: str) -> Optional[dict]:
    if not settings.OPENAI_API_KEY:
        return None
    try:
        resp = requests.post(
            "https://api.openai.com/v1/moderations",
            headers={"Authorization": f"Bearer {settings.OPENAI_API_KEY}"},
            json={"model": "omni-moderation-latest", "input": text[:4000]},
            timeout=2.5,
        )
        if resp.status_code != 200:
            return None
        result = (resp.json().get("results") or [{}])[0]
        return result.get("categories") or {}
    except Exception:  # noqa: BLE001  (network, bad JSON…): the message simply isn't AI-checked
        return None


def ai_check(text: str) -> Verdict:
    """Only the AI part (run after a message is delivered, so sending never waits for it)."""
    if not text or not rules().get("useAiModeration", True):
        return Verdict(allowed=True)
    found = _ai_categories(text)
    if not found:
        return Verdict(allowed=True)
    blocked = [f"ai:{c}" for c in AI_BLOCK if found.get(c)]
    return Verdict(allowed=not blocked, reasons=blocked, alert=any(found.get(c) for c in AI_ALERT))

