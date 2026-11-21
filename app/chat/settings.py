"""Chat configuration, all from the environment (Render dashboard → Environment)."""
from __future__ import annotations

import os


def _list(name: str) -> list[str]:
    return [v.strip() for v in os.getenv(name, "").split(",") if v.strip()]


# MongoDB Atlas connection string. Without it the chat stays switched off and the rest of
# stress-dost runs exactly as before.
MONGODB_URI = os.getenv("MONGODB_URI", "").strip()
CHAT_DB_NAME = os.getenv("CHAT_DB_NAME", "acadza_chat")

# Acadza's own API: every chat user is verified with their Acadza token (no separate login).
ACADZA_API_BASE = os.getenv("ACADZA_API_BASE", "https://api.acadza.in").rstrip("/")

# Firebase service account (the whole JSON as one line) for FCM HTTP v1 notifications.
FIREBASE_SERVICE_ACCOUNT_JSON = os.getenv("FIREBASE_SERVICE_ACCOUNT_JSON", "").strip()

# Acadza user ids that may create groups and manage members (comma separated). More admins can
# be added in the `chat_admins` collection without a redeploy.
CHAT_ADMIN_IDS = set(_list("CHAT_ADMIN_IDS"))

# OpenAI's moderation endpoint is free; it uses the key stress-dost already has.
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY", "").strip()

MAX_TEXT_LENGTH = 2000
PAGE_SIZE = 50
MAX_PAGE_SIZE = 200
# Anti-spam: at most this many messages per user in the window.
RATE_LIMIT_COUNT = 10
RATE_LIMIT_WINDOW_S = 10
# A sender can delete their own message for everyone within this many minutes; staff any time.
DELETE_WINDOW_MIN = 60
# Blocked messages before a short automatic mute in that group.
STRIKES_BEFORE_MUTE = 3
STRIKE_WINDOW_S = 10 * 60
AUTO_MUTE_MIN = 30

ENABLED = bool(MONGODB_URI)
