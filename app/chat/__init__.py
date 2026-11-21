"""Group chat for the Acadza student app (WhatsApp-like), living inside stress-dost.

Switched on only when MONGODB_URI is set, so deploying this changes nothing until then.
See routes.py (REST) and sockets.py (live) for the API.
"""
from __future__ import annotations

import logging

from flask import Flask

from . import settings

log = logging.getLogger(__name__)


def init_chat(app: Flask) -> None:
    if not settings.ENABLED:
        log.info("chat: MONGODB_URI not set, chat is off")
        return
    from .mongo import ensure_indexes
    from .routes import bp
    from . import sockets  # noqa: F401  (registers the /chat socket events)

    app.register_blueprint(bp)
    try:
        ensure_indexes()
    except Exception:  # noqa: BLE001  the app still starts; indexes are retried next boot
        log.exception("chat: could not reach MongoDB at startup")
    log.info("chat: on (db=%s, push=%s)", settings.CHAT_DB_NAME, bool(settings.FIREBASE_SERVICE_ACCOUNT_JSON))


__all__ = ["init_chat"]
