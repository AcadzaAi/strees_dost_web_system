"""Phone check for students' chat, so nobody else can use a student's account in the chat.

Who has to type an OTP (sent by Acadza to the phone number on the student's account):
- The first time a student is in a group that a teacher put them in from the app (added by hand,
  copied from another group, or let in after asking to join). Not when they only came in "from
  the backend": the coaching's own batch/roster (auto-join groups, groups filled from a batch).
- Whenever the student opens the chat on a different phone than the one last checked. Only one
  phone at a time: verifying on a new phone switches the old one off (no messages, no notifications).
Teachers and admins are never asked.

The phone is told by the app as a device id (X-Chat-Device header / socket auth "device"); it is
Android's id for this app on this phone, so it survives reinstalling the app.

The OTP is Acadza's own (api.acadza.in/phonelogin/send and /verify, the same as Login with OTP).
The server sends and checks it itself, so the app can't fake a "verified".

Firebase chatConfig/security: phoneCheck (true), allowWithoutPhone (true: an account without a
phone number can't get an OTP, so it is let in and logged).
"""
from __future__ import annotations

import logging
import re
import time
from typing import Optional

import requests

from . import settings
from .mongo import db

log = logging.getLogger(__name__)

BACKEND_SOURCES = ("auto",)
BACKEND_PREFIXES = ("batch:",)
_DEVICE = re.compile(r"^[A-Za-z0-9_-]{8,64}$")
_OK_FOR_S = 60
_ok: dict[tuple[str, str], float] = {}          # (user, device) -> checked fine until
SENDS_PER_HOUR = 5
TRIES = 5
PENDING_MS = 10 * 60_000


class VerifyNeeded(Exception):
    def __init__(self, reason: str, phone: str):
        super().__init__(reason)
        self.reason, self.phone = reason, phone

    def to_dict(self) -> dict:
        msg = ("You're using the chat on a new phone. Verify it with the OTP sent to your number."
               if self.reason == "new_phone" else "Verify your phone number once to use the chat.")
        return {"ok": False, "error": "verify_phone", "reason": self.reason, "phone": self.phone, "message": msg}


def _config() -> dict:
    try:
        from . import chatconfig
        return chatconfig.get().get("security") or {}
    except Exception:  # noqa: BLE001
        return {}


def clean_device(raw) -> str:
    d = str(raw or "").strip()
    return d if _DEVICE.match(d) else ""


def masked(phone: str) -> str:
    digits = re.sub(r"\D", "", phone or "")[-10:]
    return f"{'•' * 6}{digits[-4:]}" if len(digits) >= 4 else ""


def _phone_of(doc: dict) -> str:
    digits = re.sub(r"\D", "", str(doc.get("phone") or ""))[-10:]
    return digits if len(digits) == 10 and digits[0] in "6789" else ""


def _is_backend(sources) -> bool:
    return any(s in BACKEND_SOURCES or str(s).startswith(BACKEND_PREFIXES) for s in (sources or []))


def added_by_hand(user_id: str) -> bool:
    """In any group (not a private chat) only because someone added them from the app."""
    rows = list(db().members.find({"userId": user_id, "removed": {"$ne": True}, "role": "student"},
                                  projection={"groupId": 1, "sources": 1}))
    manual = [r["groupId"] for r in rows if r.get("sources") and not _is_backend(r.get("sources"))]
    if not manual:
        return False
    direct = {g["_id"] for g in db().groups.find({"_id": {"$in": manual}, "type": "direct"}, projection={"_id": 1})}
    return any(gid not in direct for gid in manual)


def needs(user, device: str) -> Optional[VerifyNeeded]:
    """None when this student may use the chat on this phone; else why not."""
    if user.is_staff or _config().get("phoneCheck", True) in (False, "false", 0, "0"):
        return None
    key = (user.id, device)
    if device and _ok.get(key, 0) > time.time():
        return None
    doc = db().users.find_one({"_id": user.id}, projection={"verifiedDevice": 1, "phone": 1}) or {}
    bound = doc.get("verifiedDevice") or {}
    phone = masked(_phone_of(doc))
    if not device:
        return VerifyNeeded("update_app" if not bound else "new_phone", phone)
    if bound.get("id") and bound["id"] != device:
        return VerifyNeeded("new_phone", phone)
    if bound.get("how") not in ("otp", "no_phone") and added_by_hand(user.id):
        return VerifyNeeded("first_add", phone)
    if not bound.get("id") and db().members.count_documents({"userId": user.id, "removed": {"$ne": True}}, limit=1):
        # Only backend groups so far: this phone becomes theirs without an OTP.
        db().users.update_one({"_id": user.id, "verifiedDevice": {"$exists": False}},
                              {"$set": {"verifiedDevice": {"id": device, "at": _now(), "how": "backend"}}})
    _ok[key] = time.time() + _OK_FOR_S
    return None


def status(user, device: str) -> dict:
    n = needs(user, device)
    return {"required": False} if n is None else {"required": True, "reason": n.reason, "phone": n.phone}


def _now() -> int:
    return int(time.time() * 1000)


def _otp_url(path: str) -> str:
    return f"{settings.ACADZA_OTP_BASE}/phonelogin/{path}"


def start(user, device: str) -> dict:
    """Sends the OTP to the number on the student's account."""
    from .service import ChatError
    if not device:
        raise ChatError("update_app", "Please update the app to use the chat.", 400)
    if needs(user, device) is None:
        return {"required": False}
    doc = db().users.find_one({"_id": user.id}, projection={"phone": 1, "otpSends": 1}) or {}
    phone = _phone_of(doc)
    if not phone:
        if _config().get("allowWithoutPhone", True) not in (False, "false", 0, "0"):
            _bind(user.id, device, "no_phone")
            log.warning("chat verify: %s has no phone number on the account; let in without an OTP", user.id)
            return {"required": False}
        raise ChatError("no_phone", "Your account has no phone number. Ask your coaching to add it.", 400)
    hour_ago = _now() - 3600_000
    recent = [t for t in doc.get("otpSends") or [] if t > hour_ago]
    if len(recent) >= SENDS_PER_HOUR:
        raise ChatError("otp_limit", "Too many OTPs. Try again in an hour.", 429)
    try:
        r = requests.post(_otp_url("send"), json={"phone": phone}, timeout=15)
        data = r.json() if r.content else {}
    except Exception:  # noqa: BLE001
        log.exception("chat verify: OTP send failed")
        raise ChatError("otp_failed", "Couldn't send the OTP. Check your internet and try again.", 502)
    challenge = data.get("challengeId")
    if r.status_code >= 300 or not data.get("isSuccessful") or not challenge:
        log.warning("chat verify: OTP send refused (%s): %s", r.status_code, str(data)[:200])
        raise ChatError("otp_failed", data.get("message") or "Couldn't send the OTP. Try again.", 502)
    db().users.update_one({"_id": user.id}, {
        "$set": {"otpPending": {"challengeId": challenge, "device": device, "at": _now(), "tries": 0}},
        "$push": {"otpSends": {"$each": [_now()], "$slice": -10}}})
    return {"required": True, "sent": True, "phone": masked(phone),
            "resendAfter": int(data.get("resendAfter") or 60), "expiresIn": int(data.get("expiresIn") or 300)}


def finish(user, device: str, otp: str) -> dict:
    from .service import ChatError
    otp = re.sub(r"\D", "", str(otp or ""))
    if len(otp) != 6:
        raise ChatError("bad_otp", "Enter the 6-digit OTP.", 400)
    doc = db().users.find_one({"_id": user.id}, projection={"phone": 1, "otpPending": 1}) or {}
    p = doc.get("otpPending") or {}
    if not p or p.get("device") != device or _now() - int(p.get("at") or 0) > PENDING_MS:
        raise ChatError("otp_expired", "This OTP has expired. Send a new one.", 400)
    if int(p.get("tries") or 0) >= TRIES:
        raise ChatError("otp_expired", "Too many wrong tries. Send a new OTP.", 400)
    try:
        r = requests.post(_otp_url("verify"), json={"phone": _phone_of(doc), "challengeId": p["challengeId"], "otp": otp},
                          timeout=15)
        data = r.json() if r.content else {}
    except Exception:  # noqa: BLE001
        log.exception("chat verify: OTP check failed")
        raise ChatError("otp_failed", "Couldn't check the OTP. Try again.", 502)
    if r.status_code >= 300 or not data.get("isSuccessful"):
        db().users.update_one({"_id": user.id}, {"$inc": {"otpPending.tries": 1}})
        raise ChatError("wrong_otp", "That OTP isn't right.", 400)
    _bind(user.id, device, "otp")
    return {"required": False, "verified": True}


def _bind(user_id: str, device: str, how: str) -> None:
    """This phone is the student's chat phone now; any other phone is switched off."""
    db().users.update_one({"_id": user_id}, {
        "$set": {"verifiedDevice": {"id": device, "at": _now(), "how": how}},
        "$unset": {"otpPending": ""},
        # Notifications only to this phone from now on.
        "$pull": {"fcmTokens": {"device": {"$ne": device}}}})
    for k in [k for k in _ok if k[0] == user_id]:
        _ok.pop(k, None)
    try:
        from . import sockets
        sockets.drop_other_phones(user_id, device)
    except Exception:  # noqa: BLE001
        log.exception("chat verify: could not disconnect the old phone")
