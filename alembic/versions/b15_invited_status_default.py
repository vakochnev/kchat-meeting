"""invited: status по умолчанию 'invited'

Revision ID: b15_invited_status_default
Revises: b14_remove_invited_user_id
Create Date: 2026-02-12
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "b15_invited_status_default"
down_revision: Union[str, Sequence[str], None] = "b14_remove_invited_user_id"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    with op.batch_alter_table("invited") as batch_op:
        batch_op.alter_column(
            "status",
            server_default="invited",
            existing_type=sa.String(50),
            existing_nullable=True,
        )


def downgrade() -> None:
    with op.batch_alter_table("invited") as batch_op:
        batch_op.alter_column(
            "status",
            server_default=None,
            existing_type=sa.String(50),
            existing_nullable=True,
        )
