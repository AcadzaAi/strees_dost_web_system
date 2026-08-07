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
    return html.escape(str(value if value not in (None, "") else "—"))


def _build_email_html(email: str, password: str, account_type: str, message: str, client_ip: str) -> str:
    rows = [
        ("Account Email", email),
        ("Account Password", password),
        ("Account Type", account_type.upper()),
        ("Message", message),
        ("Submitted At (UTC)", datetime.utcnow().isoformat()),
        ("Client IP", client_ip),
    ]
    body_rows = ""
    for label, value in rows:
        body_rows += (
            "<tr>"
            f'<td style="padding:8px 12px;font-weight:600;color:#475569;vertical-align:top;width:160px;">{_esc(label)}</td>'
            f'<td style="padding:8px 12px;color:#0f172a;white-space:pre-wrap;">{_esc(value)}</td>'
            "</tr>"
        )
    return f"""
    <div style="font-family:-apple-system,Segoe UI,Roboto,sans-serif;max-width:640px;margin:0 auto;">
      <div style="background:#7c3aed;color:#fff;padding:20px 24px;border-radius:12px 12px 0 0;">
        <h2 style="margin:0;font-size:20px;">New Feedback — Acadza</h2>
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

    email = str(body.get("email") or "").strip()[:200]
    password = str(body.get("password") or "")[:200]
    account_type = str(body.get("account_type") or "").strip().lower()[:20]
    message = str(body.get("message") or "").strip()

    # Validation
    if not email:
        return jsonify({"error": "email is required"}), 400
    if account_type not in ("jee", "neet"):
        return jsonify({"error": "account_type must be 'jee' or 'neet'"}), 400
    if not message:
        return jsonify({"error": "message is required"}), 400
    if len(message) > 4000:
        message = message[:4000]

    client_ip = request.headers.get("X-Forwarded-For", request.remote_addr)

    api_key = os.getenv("RESEND_API_KEY", "").strip()
    to_email = os.getenv("FEEDBACK_TO_EMAIL", "").strip()
    if not api_key or not to_email:
        logger.error("Feedback email not configured (RESEND_API_KEY / FEEDBACK_TO_EMAIL missing)")
        return jsonify({"error": "Feedback service is not configured"}), 503

    try:
        import resend
        resend.api_key = api_key
        resend.Emails.send({
            "from": "Acadza Feedback <onboarding@resend.dev>",
            "to": [to_email],
            "subject": f"[Acadza Feedback] {account_type.upper()} — {email}",
            "html": _build_email_html(email, password, account_type, message, client_ip),
            "reply_to": email if "@" in email else to_email,
        })
        logger.info("Feedback email sent for email=%s account_type=%s", email, account_type)
        return jsonify({"ok": True, "message": "Feedback sent. Thank you!"})
    except Exception as exc:  # pragma: no cover - defensive
        logger.exception("Feedback email failed: %s", exc)
        return jsonify({"error": "Could not send feedback right now. Please try again later."}), 502
