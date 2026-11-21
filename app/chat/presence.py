"""Who is connected right now and which chat each phone has open (one server process)."""
from __future__ import annotations

import threading
from typing import Optional

_lock = threading.Lock()
_sid_user: dict[str, str] = {}
_sid_viewing: dict[str, Optional[str]] = {}
_user_sids: dict[str, set[str]] = {}


def connected(sid: str, user_id: str) -> None:
    with _lock:
        _sid_user[sid] = user_id
        _sid_viewing[sid] = None
        _user_sids.setdefault(user_id, set()).add(sid)


def disconnected(sid: str) -> Optional[str]:
    with _lock:
        user_id = _sid_user.pop(sid, None)
        _sid_viewing.pop(sid, None)
        if user_id:
            sids = _user_sids.get(user_id)
            if sids:
                sids.discard(sid)
                if not sids:
                    _user_sids.pop(user_id, None)
        return user_id


def viewing(sid: str, group_id: Optional[str]) -> None:
    with _lock:
        if sid in _sid_user:
            _sid_viewing[sid] = group_id


def user_of(sid: str) -> Optional[str]:
    with _lock:
        return _sid_user.get(sid)


def is_online(user_id: str) -> bool:
    with _lock:
        return bool(_user_sids.get(user_id))


def is_viewing(user_id: str, group_id: str) -> bool:
    """True when one of the user's phones has this chat open: no notification needed."""
    with _lock:
        return any(_sid_viewing.get(sid) == group_id for sid in _user_sids.get(user_id, ()))
