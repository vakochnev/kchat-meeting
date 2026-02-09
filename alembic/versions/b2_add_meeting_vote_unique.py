"""add unique vote per user per meeting date

Revision ID: b2_add_meeting_vote_unique
Revises: d1a1491cf31a
Create Date: 2026-02-07

Один голос на пользователя и дату совещания: (sender_id, group_id, workspace_id, meeting_datetime).
"""
from typing import Sequence, Union

from alembic import op


revision: str = "b2_add_meeting_vote_unique"
down_revision: Union[str, Sequence[str], None] = "d1a1491cf31a"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_index(
        "ix_meeting_users_sender_group_workspace_meeting",
        "meeting_users",
        ["sender_id", "group_id", "workspace_id", "meeting_datetime"],
        unique=True,
    )


def downgrade() -> None:
    op.drop_index(
        "ix_meeting_users_sender_group_workspace_meeting",
        table_name="meeting_users",
    )
