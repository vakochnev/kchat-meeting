"""meeting_admins: replace sender_id with email, add FIO

Revision ID: b6_meeting_admins_email_fio
Revises: b5_add_meeting_admins
Create Date: 2026-02-11

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "b6_meeting_admins_email_fio"
down_revision: Union[str, Sequence[str], None] = "b5_add_meeting_admins"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.drop_table("meeting_admins")

    op.create_table(
        "meeting_admins",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("meeting_id", sa.Integer(), nullable=False),
        sa.Column("email", sa.String(255), nullable=False),
        sa.Column("last_name", sa.String(100), nullable=True),
        sa.Column("first_name", sa.String(100), nullable=True),
        sa.Column("middle_name", sa.String(100), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=True),
        sa.Column("updated_at", sa.DateTime(), nullable=True),
        sa.ForeignKeyConstraint(
            ["meeting_id"],
            ["meetings.id"],
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("meeting_id", "email", name="uq_meeting_admin"),
    )
    op.create_index(
        op.f("ix_meeting_admins_email"),
        "meeting_admins",
        ["email"],
        unique=False,
    )
    op.create_index(
        op.f("ix_meeting_admins_meeting_id"),
        "meeting_admins",
        ["meeting_id"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index(op.f("ix_meeting_admins_meeting_id"), table_name="meeting_admins")
    op.drop_index(op.f("ix_meeting_admins_email"), table_name="meeting_admins")
    op.drop_table("meeting_admins")

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
    op.create_index(op.f("ix_meeting_admins_meeting_id"), "meeting_admins", ["meeting_id"])
    op.create_index(op.f("ix_meeting_admins_sender_id"), "meeting_admins", ["sender_id"])
