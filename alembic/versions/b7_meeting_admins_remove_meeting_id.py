"""meeting_admins: remove meeting_id (admins are global)

Revision ID: b7_meeting_admins_remove_meeting_id
Revises: b6_meeting_admins_email_fio
Create Date: 2026-02-11

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "b7_meeting_admins_remove_meeting_id"
down_revision: Union[str, Sequence[str], None] = "b6_meeting_admins_email_fio"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.drop_table("meeting_admins")

    op.create_table(
        "meeting_admins",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("email", sa.String(255), nullable=False),
        sa.Column("last_name", sa.String(100), nullable=True),
        sa.Column("first_name", sa.String(100), nullable=True),
        sa.Column("middle_name", sa.String(100), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=True),
        sa.Column("updated_at", sa.DateTime(), nullable=True),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("email", name="uq_meeting_admin_email"),
    )
    op.create_index(
        op.f("ix_meeting_admins_email"),
        "meeting_admins",
        ["email"],
        unique=True,
    )


def downgrade() -> None:
    op.drop_index(op.f("ix_meeting_admins_email"), table_name="meeting_admins")
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
    op.create_index("ix_meeting_admins_email", "meeting_admins", ["email"])
    op.create_index("ix_meeting_admins_meeting_id", "meeting_admins", ["meeting_id"])
