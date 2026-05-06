"""Environment-driven configuration."""
from __future__ import annotations

import os
from pathlib import Path


class Config:
    ENV = os.getenv("ENV", "dev")
    SECRET_KEY = os.getenv("SECRET_KEY", "dev-secret")

    # Database configuration with proper path handling
    DATABASE_URL = os.getenv("DATABASE_URL", "")
    if not DATABASE_URL:
        # Default to SQLite in instance folder (relative to project root)
        BASE_DIR = Path(__file__).resolve().parent.parent
        INSTANCE_DIR = BASE_DIR / "instance"
        INSTANCE_DIR.mkdir(exist_ok=True)
        DATABASE_URL = f"sqlite:///{INSTANCE_DIR / 'stress.db'}"
    
    SQLALCHEMY_DATABASE_URI = DATABASE_URL
    SQLALCHEMY_TRACK_MODIFICATIONS = False

    SOCKETIO_CORS_ALLOWED_ORIGINS = os.getenv("SOCKETIO_CORS_ALLOWED_ORIGINS", "*")

    MIN_QUESTIONS = int(os.getenv("MIN_QUESTIONS", "3"))
    MAX_QUESTIONS = max(
        int(os.getenv("MAX_QUESTIONS", "3")),
        MIN_QUESTIONS,
    )
    MAX_DOMAIN_QUESTIONS = int(os.getenv("MAX_DOMAIN_QUESTIONS", "2"))


__all__ = ["Config"]
