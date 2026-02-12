"""users: add updated_at for BaseModel compatibility

Revision ID: b13_users_add_updated_at
Revises: b12_merge_invited_meeting_users
Create Date: 2026-02-12
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "b13_users_add_updated_at"
down_revision: Union[str, Sequence[str], None] = "b12_merge_invited_meeting_users"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    conn = op.get_bind()
    insp = sa.inspect(conn)
    cols = [c["name"] for c in insp.get_columns("users")]
    if "updated_at" not in cols:
        with op.batch_alter_table("users") as batch_op:
            batch_op.add_column(
                sa.Column("updated_at", sa.DateTime(), nullable=True)
            )


def downgrade() -> None:
    with op.batch_alter_table("users") as batch_op:
        batch_op.drop_column("updated_at")
