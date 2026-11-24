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
    _keep_awake()
    if not app.testing:
        from . import mongo, push, service
        mongo.warm()                       # database connections open before the first message
        push.warm_up()
        service.start_media_sweeper()      # files older than chatConfig.media.retentionDays
        from . import chatconfig
        chatconfig.start_watch()           # chatConfig edits in Firebase apply at once


_awake_started = False


def _keep_awake() -> None:
    """Render's free plan puts the server to sleep after 15 minutes without visitors; the next
    phone then waits up to a minute for it to wake (chats stuck on "Connecting"). While chat is on,
    the server visits its own /health every 10 minutes so it never falls asleep.
    Off with CHAT_KEEP_AWAKE=0, and only on Render (RENDER_EXTERNAL_URL is set there)."""
    global _awake_started
    import os
    base = os.getenv("RENDER_EXTERNAL_URL", "").rstrip("/")
    if _awake_started or not base or os.getenv("CHAT_KEEP_AWAKE", "1") == "0":
        return
    _awake_started = True

    def loop() -> None:
        import time
        import requests
        while True:
            time.sleep(600)
            try:
                requests.get(f"{base}/health", timeout=20)
            except Exception:  # noqa: BLE001
                log.warning("chat: keep-awake ping failed")

    from ..extensions import socketio
    socketio.start_background_task(loop)
    log.info("chat: keep-awake on (%s/health every 10 min)", base)


__all__ = ["init_chat"]
