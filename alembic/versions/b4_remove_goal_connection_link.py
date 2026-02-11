"""remove goal and connection_link from meetings

Revision ID: b4_remove_goal_connection_link
Revises: b3_add_meetings_invited
Create Date: 2026-02-11

"""
from typing import Sequence, Union

from alembic import op


revision: str = "b4_remove_goal_connection_link"
down_revision: Union[str, Sequence[str], None] = "b3_add_meetings_invited"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.drop_column("meetings", "goal")
    op.drop_column("meetings", "connection_link")


def downgrade() -> None:
    op.add_column("meetings", op.Column("goal", op.String(500), nullable=True))
    op.add_column("meetings", op.Column("connection_link", op.String(500), nullable=True))
