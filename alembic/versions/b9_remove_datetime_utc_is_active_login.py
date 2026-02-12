"""remove datetime_utc, is_active from meetings; login from invited

Revision ID: b9_remove_fields
Revises: b8_users_table_and_bigint
Create Date: 2026-02-12

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "b9_remove_fields"
down_revision: Union[str, Sequence[str], None] = "b8_users_table_and_bigint"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # meetings: drop index on datetime_utc, then drop columns datetime_utc, is_active
    op.drop_index(op.f("ix_meetings_datetime_utc"), table_name="meetings")
    with op.batch_alter_table("meetings") as batch_op:
        batch_op.drop_column("datetime_utc")
        batch_op.drop_column("is_active")

    # invited: drop login
    with op.batch_alter_table("invited") as batch_op:
        batch_op.drop_column("login")


def downgrade() -> None:
    # invited: add login back
    with op.batch_alter_table("invited") as batch_op:
        batch_op.add_column(sa.Column("login", sa.String(100), nullable=True))

    # meetings: add datetime_utc, is_active back
    with op.batch_alter_table("meetings") as batch_op:
        batch_op.add_column(sa.Column("datetime_utc", sa.DateTime(), nullable=True))
        batch_op.add_column(
            sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.text("1"))
        )
        batch_op.create_index("ix_meetings_datetime_utc", ["datetime_utc"])
