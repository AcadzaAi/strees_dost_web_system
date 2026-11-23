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
        "fucked", "fucks", "fuk", "dickhead", "cunt", "cock", "boobs", "boob", "tits", "titties",
        "horny", "blowjob", "handjob", "sexy", "xxx", "onlyfans", "pornhub", "xvideos", "fap",
        "masturbate", "rape", "rapist", "nigga", "nigger", "retard", "bullshit",
        # Hinglish (common spellings; add more from Firebase: chatConfig/moderation/extraWords)
        "madarchod", "maderchod", "madarjaat", "mc", "mkc", "tmkc", "behenchod", "behnchod", "bc",
        "bhenchod", "benchod", "bkl", "chutiya", "chutiye", "chutiyapa", "chutmarike", "chut", "chudai",
        "chodu", "lund", "lauda", "loda", "lavda", "lawda", "lavde", "lawde", "lodu", "gaand", "gand",
        "gandu", "gaandu", "randi", "raand", "randwa", "chinal", "chhinal", "bhadwa", "bhadwe", "bhadve",
        "harami", "haramzada", "haramzade", "haramkhor", "kamina", "kamine", "kutiya", "bhosdike",
        "bhosdi", "bhosda", "bhosdiwale", "bhosdiwala", "bsdk", "jhant", "jhaat", "jhaant", "jhantu",
        "jhaatu", "hijda", "hijde", "tatti", "suar",
        "teri maa ki", "teri ma ki", "teri behen ki", "maa chod", "behen chod",
    ],
    # Hindi in Devanagari (matched as written, with or without the dot under letters).
    "bannedWordsHindi": [
        "मादरचोद", "मादरचोत", "बहनचोद", "बहिनचोद", "भेनचोद", "चूतिया", "चुतिया", "चूत", "लंड", "लौड़ा", "लौडा",
        "लोड़ा", "लोडा", "गांड", "गाँड", "गांडू", "रंडी", "भोसड़ी", "भोसडी", "भोसड़ीके", "भोसडीके", "हरामी",
        "हरामजादा", "हरामज़ादा", "कमीना", "कमीने", "भड़वा", "भडवा", "छिनाल", "कुतिया", "चुदाई", "झांट", "झाँट",
        "तेरी माँ की", "तेरी मां की", "तेरी बहन की",
    ],
    # Not blocked: these make admins look at the chat at once (a student may need help).
    "selfHarmPhrases": [
        "kill myself", "want to die", "end my life", "suicide", "suicidal", "cut myself",
        "marna chahta", "marna chahti", "mar jaunga", "mar jaungi", "jeena nahi", "khudkushi", "aatmahatya",
        "आत्महत्या", "खुदकुशी", "मरना चाहता", "मरना चाहती", "मर जाऊंगा", "मर जाऊंगी",
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
    """The built-in lists, plus what admins add in Firebase (chatConfig/moderation):
    extraWords / extraHindiWords / extraCompetitors are blocked too; allowWords un-blocks a
    built-in word that causes trouble (a name, a subject term)."""
    global _rules_cache
    at, cached = _rules_cache
    if time.time() - at < 60:
        return cached
    doc = db().settings.find_one({"_id": "moderation"}) or {}
    merged = {**DEFAULT_RULES, **{k: v for k, v in doc.items() if k != "_id"}}
    try:
        from . import chatconfig
        fb = chatconfig.get().get("moderation") or {}
    except Exception:  # noqa: BLE001
        fb = {}
    def words(v) -> list[str]:
        # A list, or what the Firebase console makes of one ({"0": "word", "1": "word"}).
        items = list(v.values()) if isinstance(v, dict) else (v if isinstance(v, list) else [])
        return [str(w).strip() for w in items if w is not None and str(w).strip()]
    allow = {w.lower() for w in words(fb.get("allowWords"))}
    merged["bannedWords"] = [w for w in list(merged.get("bannedWords", [])) + words(fb.get("extraWords")) if w.lower() not in allow]
    merged["bannedWordsHindi"] = [w for w in list(merged.get("bannedWordsHindi", [])) + words(fb.get("extraHindiWords")) if w not in allow]
    merged["competitors"] = list(merged.get("competitors", [])) + words(fb.get("extraCompetitors"))
    _rules_cache = (time.time(), merged)
    return merged


def _deva(text: str) -> str:
    """Devanagari compared as written: the dot under letters (ड़ / ड़) and ँ / ं don't matter."""
    t = unicodedata.normalize("NFKD", text)
    t = t.replace("\u093c", "").replace("\u0901", "\u0902").replace("\u200d", "").replace("\u200c", "")
    return re.sub(r"\s+", " ", t)


_MASK = "*#%^&_~"


def _masked_hit(text: str, terms: list[str]) -> bool:
    """"f*ck", "ch#tiya", "b**ch": a word with a few letters hidden behind symbols still counts."""
    singles = [normalize(t) for t in terms if " " not in t.strip()]
    singles = [t for t in singles if len(t) >= 4]
    for token in re.findall(r"[a-z0-9@$!" + re.escape(_MASK) + r"]{4,}", text.lower()):
        letters = sum(ch.isalpha() for ch in token)
        if letters < 2:
            continue
        # "c___hu__tiya": each run of symbols hides up to 2 letters (or none), at most 3 runs.
        parts = re.split("([" + re.escape(_MASK) + "]+)", token.translate(_LEET))
        runs = [x for x in parts if x and x[0] in _MASK]
        if not runs or len(runs) > 3:
            continue
        pattern = "".join("[a-z]{0,2}" if (x and x[0] in _MASK) else re.escape(x) for x in parts)
        if any(re.fullmatch(pattern, t) for t in singles):
            return True
    return False


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

    deva = _deva(text)
    if any(_has_term(norm, squeezed, w) for w in r.get("bannedWords", [])) \
            or any(_deva(w) in deva for w in r.get("bannedWordsHindi", []) if w) \
            or _masked_hit(text, r.get("bannedWords", [])):
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

    # Self-harm is never blocked: the message goes through and the group's admins are told.
    alert = any((p in norm) if p.isascii() else (_deva(p) in deva) for p in r.get("selfHarmPhrases", []))
    if not reasons and ai and r.get("useAiModeration", True):
        ai = _ai_categories(text)
        if ai:
            blocked = [c for c in AI_BLOCK if ai.get(c)]
            if blocked:
                reasons.extend(f"ai:{c}" for c in blocked)
            alert = alert or any(ai.get(c) for c in AI_ALERT)

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

