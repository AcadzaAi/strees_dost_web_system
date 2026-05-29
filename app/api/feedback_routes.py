"""Feedback submission route — sends user complaints via Resend email."""
from __future__ import annotations

import html
import logging
import os
from datetime import datetime

from flask import Blueprint, jsonify, request

from ..extensions import limiter

logger = logging.getLogger(__name__)

bp = Blueprint("feedback", __name__, url_prefix="/api/feedback")


def _esc(value) -> str:
    """HTML-escape a value for safe embedding in the email body."""
    return html.escape(str(value if value is not None else "—"))


def _build_email_html(payload: dict) -> str:
    """Build a clean HTML email from the feedback payload."""
    user = payload.get("user") or {}
    device = payload.get("device") or {}
    message = payload.get("message") or ""
    category = payload.get("category") or "General"

    rows = [
        ("Category", category),
        ("Message", message),
        ("—", "—"),
        ("User ID", user.get("user_id")),
        ("Display Name", user.get("display_name")),
        ("Account Type", user.get("account_type")),
        ("Total Sessions", user.get("total_sessions")),
        ("Completed Sessions", user.get("completed_sessions")),
        ("Mood", user.get("mood")),
        ("Logged In At", user.get("logged_in_at")),
        ("—", "—"),
        ("Device Type", device.get("device_type")),
        ("Platform", device.get("platform")),
        ("Browser", device.get("user_agent")),
        ("Screen", device.get("screen")),
        ("Viewport", device.get("viewport")),
        ("Language", device.get("language")),
        ("Timezone", device.get("timezone")),
        ("Page URL", device.get("page_url")),
        ("—", "—"),
        ("Submitted At (UTC)", datetime.utcnow().isoformat()),
        ("Client IP", payload.get("_client_ip")),
    ]

    body_rows = ""
    for label, value in rows:
        if label == "—":
            body_rows += '<tr><td colspan="2" style="padding:6px 0;border-top:1px solid #e2e8f0;"></td></tr>'
            continue
        body_rows += (
            '<tr>'
            f'<td style="padding:8px 12px;font-weight:600;color:#475569;vertical-align:top;width:180px;">{_esc(label)}</td>'
            f'<td style="padding:8px 12px;color:#0f172a;white-space:pre-wrap;">{_esc(value)}</td>'
            '</tr>'
        )

    return f"""
    <div style="font-family:-apple-system,Segoe UI,Roboto,sans-serif;max-width:680px;margin:0 auto;">
      <div style="background:#7c3aed;color:#fff;padding:20px 24px;border-radius:12px 12px 0 0;">
        <h2 style="margin:0;font-size:20px;">New Feedback — Focus Dost</h2>
        <p style="margin:6px 0 0;opacity:0.85;font-size:13px;">A user submitted feedback through the in-app button.</p>
      </div>
      <table style="width:100%;border-collapse:collapse;background:#fff;border:1px solid #e2e8f0;border-top:none;border-radius:0 0 12px 12px;font-size:14px;">
        {body_rows}
      </table>
    </div>
    """


@bp.post("/submit")
@limiter.limit("5 per hour; 2 per minute")
def submit_feedback():
    body = request.get_json(force=True, silent=True) or {}

    message = str(body.get("message") or "").strip()
    if not message:
        return jsonify({"error": "Feedback message is required"}), 400
    if len(message) > 4000:
        message = message[:4000]

    category = str(body.get("category") or "General").strip()[:60]

    # Sanitize user details
    raw_user = body.get("user") if isinstance(body.get("user"), dict) else {}
    user = {
        "user_id": str(raw_user.get("user_id") or "")[:80],
        "display_name": str(raw_user.get("display_name") or "")[:120],
        "account_type": str(raw_user.get("account_type") or "")[:60],
        "total_sessions": raw_user.get("total_sessions"),
        "completed_sessions": raw_user.get("completed_sessions"),
        "mood": str(raw_user.get("mood") or "")[:80],
        "logged_in_at": str(raw_user.get("logged_in_at") or "")[:60],
    }

    # Sanitize device details
    raw_device = body.get("device") if isinstance(body.get("device"), dict) else {}
    device = {
        "device_type": str(raw_device.get("device_type") or "")[:40],
        "platform": str(raw_device.get("platform") or "")[:80],
        "user_agent": str(raw_device.get("user_agent") or "")[:400],
        "screen": str(raw_device.get("screen") or "")[:40],
        "viewport": str(raw_device.get("viewport") or "")[:40],
        "language": str(raw_device.get("language") or "")[:40],
        "timezone": str(raw_device.get("timezone") or "")[:60],
        "page_url": str(raw_device.get("page_url") or "")[:300],
    }

    payload = {
        "message": message,
        "category": category,
        "user": user,
        "device": device,
        "_client_ip": request.headers.get("X-Forwarded-For", request.remote_addr),
    }

    api_key = os.getenv("RESEND_API_KEY", "").strip()
    to_email = os.getenv("FEEDBACK_TO_EMAIL", "").strip()

    if not api_key or not to_email:
        logger.error("Feedback email not configured (RESEND_API_KEY / FEEDBACK_TO_EMAIL missing)")
        return jsonify({"error": "Feedback service is not configured"}), 503

    try:
        import resend
        resend.api_key = api_key

        name = user["display_name"] or "Anonymous"
        subject = f"[Focus Dost Feedback] {category} — {name}"

        resend.Emails.send({
            # Resend's shared onboarding sender works without domain verification.
            "from": "Focus Dost Feedback <onboarding@resend.dev>",
            "to": [to_email],
            "subject": subject,
            "html": _build_email_html(payload),
            "reply_to": to_email,
        })
        logger.info("Feedback email sent for user=%s category=%s", user["user_id"] or "anon", category)
        return jsonify({"ok": True, "message": "Feedback sent. Thank you!"})
    except Exception as exc:  # pragma: no cover - defensive
        logger.exception("Feedback email failed: %s", exc)
        return jsonify({"error": "Could not send feedback right now. Please try again later."}), 502
