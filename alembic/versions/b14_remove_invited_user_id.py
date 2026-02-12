"""Удаление user_id из invited

Revision ID: b14_remove_invited_user_id
Revises: b13_users_add_updated_at
Create Date: 2026-02-12
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "b14_remove_invited_user_id"
down_revision: Union[str, Sequence[str], None] = "b13_users_add_updated_at"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    conn = op.get_bind()
    insp = sa.inspect(conn)
    cols = [c["name"] for c in insp.get_columns("invited")]
    if "user_id" in cols:
        try:
            op.drop_index(op.f("ix_invited_user_id"), table_name="invited")
        except Exception:
            pass
        with op.batch_alter_table("invited") as batch_op:
            batch_op.drop_column("user_id")


def downgrade() -> None:
    with op.batch_alter_table("invited") as batch_op:
        batch_op.add_column(sa.Column("user_id", sa.Integer(), nullable=True))
    op.create_index(
        op.f("ix_invited_user_id"),
        "invited",
        ["user_id"],
        unique=False,
    )
