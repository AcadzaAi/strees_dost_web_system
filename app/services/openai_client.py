"""Shared OpenAI chat helpers."""
from __future__ import annotations

from openai import OpenAI

client = OpenAI(timeout=30.0)  # 30 second timeout
client_no_retry = OpenAI(max_retries=0, timeout=10.0)  # 10 second timeout for latency-critical calls


def chat_text(model: str, system: str, user: str, **kwargs):
    """Basic chat completion returning text."""
    return client.chat.completions.create(
        model=model,
        messages=[
            {"role": "system", "content": system},
            {"role": "user", "content": user},
        ],
        **kwargs,
    )


def chat_json(model: str, system: str, user: str, **kwargs):
    """Chat completion forced to return JSON object."""
    options = {
        "model": model,
        "messages": [
            {"role": "system", "content": system},
            {"role": "user", "content": user},
        ],
        "response_format": {"type": "json_object"},
    }
    options.update(kwargs)
    return client.chat.completions.create(**options)


def chat_json_no_retry(model: str, system: str, user: str, **kwargs):
    """Latency-critical JSON chat completion with SDK retries disabled."""
    options = {
        "model": model,
        "messages": [
            {"role": "system", "content": system},
            {"role": "user", "content": user},
        ],
        "response_format": {"type": "json_object"},
    }
    options.update(kwargs)
    return client_no_retry.chat.completions.create(**options)


def transcribe_audio(file_storage, model: str = "gpt-4o-mini-transcribe") -> str:
    """Transcribe an uploaded audio file and return plain text."""
    filename = getattr(file_storage, "filename", None) or "recording.webm"
    media_type = getattr(file_storage, "mimetype", None) or "audio/webm"
    payload = file_storage.read()
    result = client.audio.transcriptions.create(
        model=model,
        file=(filename, payload, media_type),
        response_format="text",
    )
    if isinstance(result, str):
        return result.strip()
    text = getattr(result, "text", "") or ""
    return text.strip()


__all__ = ["chat_text", "chat_json", "chat_json_no_retry", "transcribe_audio"]
