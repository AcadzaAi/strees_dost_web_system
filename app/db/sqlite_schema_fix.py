"""SQLite dev-time schema fixups.

This project uses Flask-Migrate for proper migrations, but local SQLite files
often linger across runs. When models change (e.g. adding optional columns),
SQLite won't auto-update the existing table, leading to runtime 500s.

We keep this module small and defensive: only add missing nullable columns.
"""

from __future__ import annotations

import logging

from sqlalchemy import text

from ..extensions import db

logger = logging.getLogger(__name__)


def _sqlite_table_columns(table_name: str) -> set[str]:
    rows = db.session.execute(text(f"PRAGMA table_info({table_name})")).fetchall()
    # row format: (cid, name, type, notnull, dflt_value, pk)
    return {str(row[1]) for row in rows}


def ensure_sessions_academic_columns() -> None:
    """Ensure new academic topic columns exist on SQLite `sessions` table.

    This is a minimal compatibility shim for dev environments. In production
    you should run migrations instead.
    """

    dialect = getattr(db.engine, "dialect", None)
    if not dialect or dialect.name != "sqlite":
        return

    try:
        cols = _sqlite_table_columns("sessions")
    except Exception as exc:  # pragma: no cover
        # Table might not exist yet (first run)
        logger.debug("sqlite schema check skipped: %s", exc)
        return

    to_add: list[tuple[str, str]] = []
    if "academic_topics_raw" not in cols:
        to_add.append(("academic_topics_raw", "TEXT"))
    if "academic_topics_subject" not in cols:
        to_add.append(("academic_topics_subject", "VARCHAR(50)"))
    if "academic_topics_topics" not in cols:
        to_add.append(("academic_topics_topics", "TEXT"))

    if not to_add:
        return

    for col, sql_type in to_add:
        logger.warning("SQLite schema fix: adding missing column sessions.%s", col)
        db.session.execute(text(f"ALTER TABLE sessions ADD COLUMN {col} {sql_type}"))
    db.session.commit()

