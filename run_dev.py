"""Development server runner without eventlet."""
from __future__ import annotations

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


# --- Request logging ---
@app.before_request
def _start_timer():
    request._start_time = time.time()


@app.after_request
def _log_response(resp):
    try:
        dur_ms = int((time.time() - request._start_time) * 1000)
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

    # Enable Socket.IO logging
    socketio.logger = True
    socketio.engineio_logger = True

    port = int(os.getenv("PORT", "5002"))
    print(f"\n{'='*60}")
    print(f"🚀 Starting Stress-Dost Development Server")
    print(f"{'='*60}")
    print(f"📍 Server: http://127.0.0.1:{port}")
    print(f"⚠️  Running in development mode (threading, not eventlet)")
    print(f"{'='*60}\n")
    
    socketio.run(
        app,
        host="127.0.0.1",
        port=port,
        allow_unsafe_werkzeug=True,
        use_reloader=False,
        log_output=True,
    )
