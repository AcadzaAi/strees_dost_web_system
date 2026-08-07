"""add leaderboard entries

Revision ID: c2a4d0e8f8b1
Revises: 4b1b4f43a1d2
Create Date: 2026-08-07 00:00:00.000000
"""
from alembic import op
import sqlalchemy as sa


revision = "c2a4d0e8f8b1"
down_revision = "4b1b4f43a1d2"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "leaderboard_entries",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("user_id", sa.String(length=64), nullable=False),
        sa.Column("name", sa.String(length=120), nullable=True),
        sa.Column("reference", sa.String(length=64), nullable=True),
        sa.Column("practice_id", sa.String(length=64), nullable=False),
        sa.Column("level", sa.String(length=10), nullable=True),
        sa.Column("subject", sa.String(length=40), nullable=True),
        sa.Column("chapter", sa.String(length=160), nullable=True),
        sa.Column("correct", sa.Integer(), nullable=True),
        sa.Column("incorrect", sa.Integer(), nullable=True),
        sa.Column("points", sa.Integer(), nullable=True),
        sa.Column("attempted_at", sa.DateTime(), nullable=False),
        sa.UniqueConstraint(
            "user_id", "practice_id", "subject", "chapter",
            name="uq_leaderboard_user_practice_scope",
        ),
    )
    op.create_index("ix_leaderboard_entries_user_id", "leaderboard_entries", ["user_id"])
    op.create_index("ix_leaderboard_entries_reference", "leaderboard_entries", ["reference"])
    op.create_index("ix_leaderboard_entries_subject", "leaderboard_entries", ["subject"])
    op.create_index("ix_leaderboard_entries_chapter", "leaderboard_entries", ["chapter"])
    op.create_index("ix_leaderboard_entries_attempted_at", "leaderboard_entries", ["attempted_at"])
    op.create_index(
        "ix_leaderboard_query",
        "leaderboard_entries",
        ["reference", "subject", "chapter", "attempted_at"],
    )


def downgrade():
    op.drop_index("ix_leaderboard_query", table_name="leaderboard_entries")
    op.drop_index("ix_leaderboard_entries_attempted_at", table_name="leaderboard_entries")
    op.drop_index("ix_leaderboard_entries_chapter", table_name="leaderboard_entries")
    op.drop_index("ix_leaderboard_entries_subject", table_name="leaderboard_entries")
    op.drop_index("ix_leaderboard_entries_reference", table_name="leaderboard_entries")
    op.drop_index("ix_leaderboard_entries_user_id", table_name="leaderboard_entries")
    op.drop_table("leaderboard_entries")
