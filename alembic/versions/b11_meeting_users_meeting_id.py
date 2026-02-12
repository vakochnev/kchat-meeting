"""meeting_users: meeting_datetime -> meeting_id (FK to meetings)

Revision ID: b11_meeting_users_meeting_id
Revises: b10_full_name_unified
Create Date: 2026-02-12

Связь meeting_users с собранием через meeting_id вместо meeting_datetime.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "b11_meeting_users_meeting_id"
down_revision: Union[str, Sequence[str], None] = "b10_full_name_unified"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    conn = op.get_bind()
    insp = sa.inspect(conn)
    cols = [c["name"] for c in insp.get_columns("meeting_users")]

    # 1. Удалить unique-индекс по meeting_datetime (если есть)
    conn.execute(
        sa.text("DROP INDEX IF EXISTS ix_meeting_users_sender_group_workspace_meeting")
    )

    if "meeting_id" not in cols:
        # 2. Добавить meeting_id (FK на уровне приложения/модели)
        with op.batch_alter_table("meeting_users") as batch_op:
            batch_op.add_column(
                sa.Column("meeting_id", sa.Integer(), nullable=True)
            )

        # 3. Перенести данные: голоса с meeting_datetime -> meeting_id
        conn.execute(
            sa.text("""
                UPDATE meeting_users
                SET meeting_id = (SELECT id FROM meetings ORDER BY id DESC LIMIT 1)
                WHERE meeting_datetime IS NOT NULL AND meeting_id IS NULL
            """)
        )

        # 4. Удалить индекс и колонку meeting_datetime
        try:
            op.drop_index(
                op.f("ix_meeting_users_meeting_datetime"),
                table_name="meeting_users",
            )
        except Exception:
            pass
        if "meeting_datetime" in cols:
            with op.batch_alter_table("meeting_users") as batch_op:
                batch_op.drop_column("meeting_datetime")

        cols = [c["name"] for c in insp.get_columns("meeting_users")]

    # 5. Индекс для meeting_id (если нет)
    indexes = [i["name"] for i in insp.get_indexes("meeting_users")]
    if "ix_meeting_users_meeting_id" not in indexes:
        op.create_index(
            op.f("ix_meeting_users_meeting_id"),
            "meeting_users",
            ["meeting_id"],
            unique=False,
        )

    # 5.5 Удалить дубликаты (оставить запись с max id на группу)
    conn.execute(
        sa.text("""
            DELETE FROM meeting_users WHERE id NOT IN (
                SELECT id FROM (
                    SELECT MAX(id) AS id FROM meeting_users
                    GROUP BY sender_id, group_id, workspace_id, meeting_id
                )
            )
        """)
    )

    # 6. Unique: один голос на (sender_id, group_id, workspace_id, meeting_id)
    indexes = [i["name"] for i in insp.get_indexes("meeting_users")]
    if "ix_meeting_users_sender_group_workspace_meeting" not in indexes:
        op.create_index(
            "ix_meeting_users_sender_group_workspace_meeting",
            "meeting_users",
            ["sender_id", "group_id", "workspace_id", "meeting_id"],
            unique=True,
        )


def downgrade() -> None:
    # Удалить новый unique-индекс
    op.drop_index(
        "ix_meeting_users_sender_group_workspace_meeting",
        table_name="meeting_users",
    )
    op.drop_index(
        op.f("ix_meeting_users_meeting_id"),
        table_name="meeting_users",
    )

    # Вернуть meeting_datetime
    with op.batch_alter_table("meeting_users") as batch_op:
        batch_op.add_column(sa.Column("meeting_datetime", sa.DateTime(), nullable=True))
    op.create_index(
        op.f("ix_meeting_users_meeting_datetime"),
        "meeting_users",
        ["meeting_datetime"],
        unique=False,
    )

    # Старый unique-индекс
    op.create_index(
        "ix_meeting_users_sender_group_workspace_meeting",
        "meeting_users",
        ["sender_id", "group_id", "workspace_id", "meeting_datetime"],
        unique=True,
    )

    # Удалить meeting_id
    with op.batch_alter_table("meeting_users") as batch_op:
        batch_op.drop_column("meeting_id")
