"""Pydantic schemas for popup generation."""
from __future__ import annotations

from typing import List, Literal

from pydantic import BaseModel, Field, field_validator

PopupType = Literal[
    "distraction",
    "self_doubt",
    "panic",
    "pressure",
    "motivation",
    "comparison",
    "guilt",
    "fear",
    "system_warning",
]

TYPE_MAP = {
    "stress": "panic",
    "anxiety": "panic",
    "fear": "panic",
    "panic": "panic",
    "parental_pressure": "pressure",
    "doubt": "self_doubt",
    "selfdoubt": "self_doubt",
    "self_doubt": "self_doubt",
    "pressure": "pressure",
    "motivation": "motivation",
    "distraction": "distraction",
    "comparison": "comparison",
    "guilt": "guilt",
    "fear": "fear",
    "system_warning": "system_warning",
    "girlfriend": "distraction",
    # Common AI-generated variants that should map to valid types
    "boredom": "distraction",
    "procrastination": "distraction",
    "entertainment": "distraction",
    "social_media": "distraction",
    "phone": "distraction",
    "gaming": "distraction",
    "laziness": "motivation",
    "burnout": "motivation",
    "exhaustion": "motivation",
    "overwhelm": "panic",
    "overwhelmed": "panic",
    "confidence": "self_doubt",
    "low_confidence": "self_doubt",
    "peer_pressure": "pressure",
    "exam_pressure": "pressure",
    "jealousy": "comparison",
    "envy": "comparison",
    "shame": "guilt",
    "regret": "guilt",
}


class Popup(BaseModel):
    type: PopupType
    message: str = Field(..., min_length=5, max_length=180)
    ttl: int = Field(..., ge=3000, le=15000)

    @field_validator("type", mode="before")
    @classmethod
    def normalize_type(cls, value):
        if not isinstance(value, str):
            return value
        key = value.strip().lower().replace("-", "_").replace(" ", "_")
        # Map to valid type, default to "distraction" for any unknown type
        return TYPE_MAP.get(key, "distraction")

    @field_validator("message")
    @classmethod
    def normalize_message(cls, value: str) -> str:
        return "\n".join(
            " ".join(line.strip().split())
            for line in value.strip().split("\n")
            if line.strip()
        )


class PopupResponse(BaseModel):
    popups: List[Popup]


__all__ = ["PopupType", "Popup", "PopupResponse"]
