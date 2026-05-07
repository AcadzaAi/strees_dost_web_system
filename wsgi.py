"""Gunicorn / dev entrypoint."""
from __future__ import annotations

# IMPORTANT: apply eventlet patches before anything else in server mode.
# For gunicorn with eventlet worker, always apply monkey patch
import eventlet
eventlet.monkey_patch()

import sys

import os
import sys
import time
import logging
from logging.handlers import RotatingFileHandler

from flask import request

from app import create_app
from app.extensions import socketio

app = create_app()


def setup_logging() -> None:
    level = os.getenv("LOG_LEVEL", "INFO").upper()

    # Root logger -> console
    logging.basicConfig(
        level=level,
        format="%(asctime)s | %(levelname)s | %(name)s | %(message)s",
        handlers=[logging.StreamHandler(sys.stdout)],
    )

    # Flask app logger + werkzeug
    app.logger.setLevel(level)
    logging.getLogger("werkzeug").setLevel(level)

    # Optional file logging
    if os.getenv("LOG_TO_FILE", "false").lower() in ("1", "true", "yes"):
        os.makedirs("logs", exist_ok=True)
        fh = RotatingFileHandler("logs/app.log", maxBytes=2_000_000, backupCount=3)
        fh.setLevel(level)
        fh.setFormatter(logging.Formatter("%(asctime)s | %(levelname)s | %(name)s | %(message)s"))
        app.logger.addHandler(fh)


# --- Request logging (you will see logs for every HTTP hit) ---
@app.before_request
def _start_timer():
    request._start_time = time.time()  # type: ignore[attr-defined]


@app.after_request
def _log_response(resp):
    try:
        dur_ms = int((time.time() - request._start_time) * 1000)  # type: ignore[attr-defined]
    except Exception:
        dur_ms = -1
    app.logger.info("HTTP %s %s -> %s (%sms)", request.method, request.path, resp.status_code, dur_ms)
    return resp


# --- Socket.IO basic visibility ---
@socketio.on("connect")
def _on_connect():
    app.logger.info("Socket.IO client connected: %s", request.sid)


@socketio.on("disconnect")
def _on_disconnect():
    app.logger.info("Socket.IO client disconnected: %s", request.sid)


if __name__ == "__main__":
    setup_logging()

    # IMPORTANT: enable these flags so you can see Socket.IO chatter in console
    socketio.logger = True
    socketio.engineio_logger = True

    port = int(os.getenv("PORT", "5002"))
    socketio.run(
        app,
        host="127.0.0.1",
        port=port,
        allow_unsafe_werkzeug=True,
        use_reloader=False,  # avoid double-logging on Windows
        log_output=True,
    )
