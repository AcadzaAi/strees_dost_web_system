"""Additive API endpoints for the Android practice leaderboard."""
from __future__ import annotations

from datetime import datetime, timezone
from zoneinfo import ZoneInfo

from flask import Blueprint, jsonify, request
from sqlalchemy import Float, case, cast, func, select

from ..db.leaderboard_models import LeaderboardEntry
from ..extensions import db


bp = Blueprint("leaderboard", __name__, url_prefix="/api/leaderboard")

WEIGHTS = {"EASY": 5, "MEDIUM": 10, "HARD": 20}
IST = ZoneInfo("Asia/Kolkata")


def compute_points(level: str, correct: int, incorrect: int) -> int:
    """Apply the server-owned JEE/NEET-style scoring rule."""
    weight = WEIGHTS.get((level or "").upper(), 10)
    return max(0, round(correct * weight - incorrect * (weight / 4)))


def _non_negative_int(value) -> int:
    try:
        return max(0, int(value))
    except (TypeError, ValueError):
        return 0


def _utc_start_for_scope(scope: str) -> datetime | None:
    now_ist = datetime.now(IST)
    today_start = now_ist.replace(hour=0, minute=0, second=0, microsecond=0)
    if scope == "today":
        return today_start.astimezone(timezone.utc).replace(tzinfo=None)
    if scope == "week":
        week_start = today_start.replace(day=today_start.day - today_start.weekday())
        return week_start.astimezone(timezone.utc).replace(tzinfo=None)
    return None


def _entry_payload(row) -> dict:
    return {
        "rank": int(row.rank),
        "userId": row.user_id,
        "name": row.name or "",
        "points": int(row.points or 0),
        "correct": int(row.correct or 0),
        "incorrect": int(row.incorrect or 0),
        "hardSolved": int(row.hard_solved or 0),
    }


def _aggregates(filters):
    correct = func.coalesce(func.sum(LeaderboardEntry.correct), 0).label("correct")
    incorrect = func.coalesce(func.sum(LeaderboardEntry.incorrect), 0).label("incorrect")
    points = func.coalesce(func.sum(LeaderboardEntry.points), 0).label("points")
    hard_solved = func.coalesce(
        func.sum(
            case(
                (LeaderboardEntry.level == "HARD", LeaderboardEntry.correct),
                else_=0,
            )
        ),
        0,
    ).label("hard_solved")
    return (
        select(
            LeaderboardEntry.user_id.label("user_id"),
            func.coalesce(func.max(LeaderboardEntry.name), "").label("name"),
            correct,
            incorrect,
            points,
            hard_solved,
        )
        .where(*filters)
        .group_by(LeaderboardEntry.user_id)
        .subquery()
    )


def _ranked_statement(aggregates, metric: str, require_minimum_attempts: bool):
    attempts = aggregates.c.correct + aggregates.c.incorrect
    accuracy = cast(aggregates.c.correct, Float) / func.nullif(attempts, 0)
    primary = accuracy if metric == "accuracy" else aggregates.c.points
    order = [
        primary.desc(),
        aggregates.c.points.desc(),
        aggregates.c.correct.desc(),
        aggregates.c.user_id.asc(),
    ]
    statement = select(
        func.rank().over(order_by=order).label("rank"),
        aggregates.c.user_id,
        aggregates.c.name,
        aggregates.c.points,
        aggregates.c.correct,
        aggregates.c.incorrect,
        aggregates.c.hard_solved,
    )
    if require_minimum_attempts:
        statement = statement.where(attempts >= 20)
    return statement.order_by(*order)


@bp.post("/submit")
def submit():
    """Store idempotent, server-scored practice breakdown rows."""
    body = request.get_json(silent=True) or {}
    user_id = str(body.get("userId") or "").strip()
    practice_id = str(body.get("practiceId") or "").strip()
    breakdown = body.get("breakdown")
    if not user_id or not practice_id or not isinstance(breakdown, list) or not breakdown:
        return jsonify({"error": "userId, practiceId, and breakdown are required"}), 400

    rows = []
    for item in breakdown:
        if not isinstance(item, dict):
            return jsonify({"error": "breakdown entries must be objects"}), 400
        # Subject/chapter are deliberately stored verbatim for client syllabus matching.
        subject = item.get("subject")
        chapter = item.get("chapter")
        if not isinstance(subject, str) or not isinstance(chapter, str):
            return jsonify({"error": "breakdown subject and chapter are required"}), 400
        rows.append((subject, chapter, _non_negative_int(item.get("correct")), _non_negative_int(item.get("incorrect"))))

    level = str(body.get("level") or "").upper()
    name = str(body.get("name") or "")[:120]
    reference = str(body.get("reference") or "")[:64]
    attempted_at = datetime.utcnow()

    for subject, chapter, correct, incorrect in rows:
        entry = LeaderboardEntry.query.filter_by(
            user_id=user_id,
            practice_id=practice_id,
            subject=subject,
            chapter=chapter,
        ).first()
        if entry is None:
            entry = LeaderboardEntry(
                user_id=user_id,
                practice_id=practice_id,
                subject=subject,
                chapter=chapter,
                attempted_at=attempted_at,
            )
            db.session.add(entry)

        # Updating an existing scope keeps retry/resume submissions idempotent.
        entry.name = name
        entry.reference = reference
        entry.level = level
        entry.correct = correct
        entry.incorrect = incorrect
        entry.points = compute_points(level, correct, incorrect)

    try:
        db.session.commit()
    except Exception:
        db.session.rollback()
        return jsonify({"error": "could not save leaderboard result"}), 500
    return jsonify({"status": "ok"})


@bp.get("")
def leaderboard():
    """Return a filtered, SQL-aggregated leaderboard and caller row."""
    scope = request.args.get("scope", "week")
    metric = request.args.get("metric", "points")
    group_by = request.args.get("groupBy", "global")
    level = request.args.get("level", "all").lower()
    if scope not in {"today", "week", "allTime"}:
        return jsonify({"error": "scope must be today, week, or allTime"}), 400
    if metric not in {"points", "accuracy"}:
        return jsonify({"error": "metric must be points or accuracy"}), 400
    if group_by not in {"global", "subject", "chapter"}:
        return jsonify({"error": "groupBy must be global, subject, or chapter"}), 400
    if level not in {"all", "easy", "medium", "hard"}:
        return jsonify({"error": "level must be all, easy, medium, or hard"}), 400

    subject = request.args.get("subject")
    chapter = request.args.get("chapter")
    if group_by in {"subject", "chapter"} and not subject:
        return jsonify({"error": "subject is required for subject and chapter boards"}), 400

    filters = []
    start = _utc_start_for_scope(scope)
    if start is not None:
        filters.append(LeaderboardEntry.attempted_at >= start)
    reference = request.args.get("reference")
    if reference:
        filters.append(LeaderboardEntry.reference == reference)
    if subject:
        filters.append(LeaderboardEntry.subject == subject)
    if chapter:
        filters.append(LeaderboardEntry.chapter == chapter)
    if level != "all":
        filters.append(LeaderboardEntry.level == level.upper())

    aggregates = _aggregates(filters)
    entries_statement = _ranked_statement(
        aggregates,
        metric,
        require_minimum_attempts=metric == "accuracy",
    ).limit(50)
    entries = [_entry_payload(row) for row in db.session.execute(entries_statement).all()]

    # The caller is ranked against all matching rows, even when they do not meet
    # the accuracy board's 20-attempt threshold.
    user_id = request.args.get("userId")
    me = None
    if user_id:
        me_statement = _ranked_statement(aggregates, metric, require_minimum_attempts=False)
        me_row = db.session.execute(
            me_statement.where(aggregates.c.user_id == user_id)
        ).first()
        if me_row is not None:
            me = _entry_payload(me_row)
            entries = [entry for entry in entries if entry["userId"] != user_id]

    eligible = _ranked_statement(
        aggregates,
        metric,
        require_minimum_attempts=metric == "accuracy",
    ).subquery()
    total_students = db.session.execute(select(func.count()).select_from(eligible)).scalar_one()
    return jsonify({"entries": entries, "me": me, "totalStudents": int(total_students or 0)})


__all__ = ["bp", "compute_points"]
