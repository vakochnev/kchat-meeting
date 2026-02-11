"""add meetings and invited tables

Revision ID: b3_add_meetings_invited
Revises: b2_add_meeting_vote_unique
Create Date: 2026-02-09

Таблицы meetings (собрания) и invited (приглашённые).
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "b3_add_meetings_invited"
down_revision: Union[str, Sequence[str], None] = "b2_add_meeting_vote_unique"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "meetings",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("topic", sa.String(500), nullable=True),
        sa.Column("url", sa.String(500), nullable=True),
        sa.Column("date", sa.String(50), nullable=True),
        sa.Column("time", sa.String(50), nullable=True),
        sa.Column("datetime_utc", sa.DateTime(), nullable=True),
        sa.Column("place", sa.String(255), nullable=True),
        sa.Column("goal", sa.String(500), nullable=True),
        sa.Column("link", sa.String(500), nullable=True),
        sa.Column("connection_link", sa.String(500), nullable=True),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.text("1")),
        sa.Column("created_at", sa.DateTime(), nullable=True),
        sa.Column("updated_at", sa.DateTime(), nullable=True),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        op.f("ix_meetings_datetime_utc"),
        "meetings",
        ["datetime_utc"],
        unique=False,
    )

    op.create_table(
        "invited",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("meeting_id", sa.Integer(), nullable=False),
        sa.Column("last_name", sa.String(100), nullable=True),
        sa.Column("first_name", sa.String(100), nullable=True),
        sa.Column("middle_name", sa.String(100), nullable=True),
        sa.Column("email", sa.String(255), nullable=True),
        sa.Column("phone", sa.String(50), nullable=True),
        sa.Column("login", sa.String(100), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=True),
        sa.Column("updated_at", sa.DateTime(), nullable=True),
        sa.ForeignKeyConstraint(
            ["meeting_id"],
            ["meetings.id"],
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        op.f("ix_invited_email"),
        "invited",
        ["email"],
        unique=False,
    )
    op.create_index(
        op.f("ix_invited_meeting_id"),
        "invited",
        ["meeting_id"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index(op.f("ix_invited_meeting_id"), table_name="invited")
    op.drop_index(op.f("ix_invited_email"), table_name="invited")
    op.drop_table("invited")
    op.drop_index(op.f("ix_meetings_datetime_utc"), table_name="meetings")
    op.drop_table("meetings")
