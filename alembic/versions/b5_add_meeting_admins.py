"""add meeting_admins table

Revision ID: b5_add_meeting_admins
Revises: b4_remove_goal_connection_link
Create Date: 2026-02-11

Таблица администраторов собраний: meeting_id + sender_id.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "b5_add_meeting_admins"
down_revision: Union[str, Sequence[str], None] = "b4_remove_goal_connection_link"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "meeting_admins",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("meeting_id", sa.Integer(), nullable=False),
        sa.Column("sender_id", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=True),
        sa.Column("updated_at", sa.DateTime(), nullable=True),
        sa.ForeignKeyConstraint(
            ["meeting_id"],
            ["meetings.id"],
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("meeting_id", "sender_id", name="uq_meeting_admin"),
    )
    op.create_index(
        op.f("ix_meeting_admins_meeting_id"),
        "meeting_admins",
        ["meeting_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_meeting_admins_sender_id"),
        "meeting_admins",
        ["sender_id"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index(op.f("ix_meeting_admins_sender_id"), table_name="meeting_admins")
    op.drop_index(op.f("ix_meeting_admins_meeting_id"), table_name="meeting_admins")
    op.drop_table("meeting_admins")
