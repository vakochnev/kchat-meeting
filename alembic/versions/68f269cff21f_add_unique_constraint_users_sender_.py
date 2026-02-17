"""add_unique_constraint_users_sender_group_workspace

Revision ID: 68f269cff21f
Revises: 43f8fbde2bf0
Create Date: 2026-02-17 13:57:04.704230

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '68f269cff21f'
down_revision: Union[str, Sequence[str], None] = '43f8fbde2bf0'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Удаляем дубликаты, добавляем unique constraint."""
    # 1. Удаляем дубликаты: оставляем одну запись на (sender_id, group_id, workspace_id)
    op.execute("""
        DELETE FROM users
        WHERE id NOT IN (
            SELECT MIN(id) FROM users
            GROUP BY sender_id, group_id, workspace_id
        )
    """)
    # 2. SQLite не поддерживает ALTER ADD CONSTRAINT — используем batch (пересоздание таблицы)
    with op.batch_alter_table("users", schema=None) as batch_op:
        batch_op.create_unique_constraint(
            "uq_users_sender_group_workspace",
            ["sender_id", "group_id", "workspace_id"],
        )


def downgrade() -> None:
    """Удаляем unique constraint."""
    with op.batch_alter_table("users", schema=None) as batch_op:
        batch_op.drop_constraint(
            "uq_users_sender_group_workspace",
            type_="unique",
        )
