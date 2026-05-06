"""Shared Flask extensions."""
from __future__ import annotations

from flask_migrate import Migrate
from flask_sqlalchemy import SQLAlchemy
from flask_socketio import SocketIO


db = SQLAlchemy()
migrate = Migrate()

# Flask-SocketIO defaults to managing the Flask session on Socket.IO events.
# With newer Flask versions this can raise:
#   AttributeError: property 'session' of 'RequestContext' object has no setter
# We don't rely on Flask session mutation in websocket handlers, so disable it.
socketio = SocketIO(cors_allowed_origins="*", async_mode="eventlet", manage_session=False)


__all__ = ["db", "migrate", "socketio"]
