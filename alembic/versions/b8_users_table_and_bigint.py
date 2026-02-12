"""users table + BigInteger for meeting_users (sender_id, group_id, workspace_id)

Revision ID: b8_users_table_and_bigint
Revises: b7_meeting_admins_remove_meeting_id
Create Date: 2026-02-12

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy import inspect


revision: str = "b8_users_table_and_bigint"
down_revision: Union[str, Sequence[str], None] = "b7_meeting_admins_remove_meeting_id"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # 1. Создаём таблицу users (если ещё нет — на случай частичного предыдущего запуска)
    conn = op.get_bind()
    inspector = inspect(conn)
    if "users" not in inspector.get_table_names():
        op.create_table(
            "users",
            sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
            sa.Column("full_name", sa.String(255), nullable=False),
            sa.Column("sender_id", sa.BigInteger(), nullable=False),
            sa.Column("group_id", sa.BigInteger(), nullable=False),
            sa.Column("workspace_id", sa.BigInteger(), nullable=False),
            sa.Column("email", sa.String(255), nullable=True),
            sa.Column("phone", sa.String(50), nullable=True),
            sa.Column(
                "created_at",
                sa.DateTime(timezone=True),
                server_default=sa.func.now(),
                nullable=True,
            ),
            sa.PrimaryKeyConstraint("id"),
        )
        op.create_index(op.f("ix_users_sender_id"), "users", ["sender_id"])
        op.create_index(op.f("ix_users_group_id"), "users", ["group_id"])
        op.create_index(op.f("ix_users_workspace_id"), "users", ["workspace_id"])
        op.create_index(op.f("ix_users_email"), "users", ["email"])

    # 2. Меняем тип sender_id, group_id, workspace_id в meeting_users на BigInteger
    # SQLite не поддерживает ALTER COLUMN TYPE — используем batch_alter_table
    with op.batch_alter_table("meeting_users") as batch_op:
        batch_op.alter_column(
            "sender_id",
            existing_type=sa.Integer(),
            type_=sa.BigInteger(),
            existing_nullable=False,
        )
        batch_op.alter_column(
            "group_id",
            existing_type=sa.Integer(),
            type_=sa.BigInteger(),
            existing_nullable=False,
        )
        batch_op.alter_column(
            "workspace_id",
            existing_type=sa.Integer(),
            type_=sa.BigInteger(),
            existing_nullable=False,
        )


def downgrade() -> None:
    # Откат meeting_users (batch для SQLite)
    with op.batch_alter_table("meeting_users") as batch_op:
        batch_op.alter_column(
            "sender_id",
            existing_type=sa.BigInteger(),
            type_=sa.Integer(),
            existing_nullable=False,
        )
        batch_op.alter_column(
            "group_id",
            existing_type=sa.BigInteger(),
            type_=sa.Integer(),
            existing_nullable=False,
        )
        batch_op.alter_column(
            "workspace_id",
            existing_type=sa.BigInteger(),
            type_=sa.Integer(),
            existing_nullable=False,
        )

    # Удаляем таблицу users
    op.drop_index(op.f("ix_users_email"), table_name="users")
    op.drop_index(op.f("ix_users_workspace_id"), table_name="users")
    op.drop_index(op.f("ix_users_group_id"), table_name="users")
    op.drop_index(op.f("ix_users_sender_id"), table_name="users")
    op.drop_table("users")
