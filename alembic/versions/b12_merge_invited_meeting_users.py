"""Объединение invited и meeting_users в таблицу invited

Revision ID: b12_merge_invited_meeting_users
Revises: b11_meeting_users_meeting_id
Create Date: 2026-02-12

Invited: meeting_id, full_name, phone, email, user_id (FK users), answer, status.
Удаление meeting_users.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "b12_merge_invited_meeting_users"
down_revision: Union[str, Sequence[str], None] = "b11_meeting_users_meeting_id"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    conn = op.get_bind()
    insp = sa.inspect(conn)
    cols_invited = [c["name"] for c in insp.get_columns("invited")]

    # 1. Добавить user_id, answer, status в invited
    if "user_id" not in cols_invited:
        with op.batch_alter_table("invited") as batch_op:
            batch_op.add_column(sa.Column("user_id", sa.Integer(), nullable=True))
    if "answer" not in cols_invited:
        with op.batch_alter_table("invited") as batch_op:
            batch_op.add_column(sa.Column("answer", sa.String(50), nullable=True))
    if "status" not in cols_invited:
        with op.batch_alter_table("invited") as batch_op:
            batch_op.add_column(sa.Column("status", sa.String(50), nullable=True))

    # 2. Индекс для user_id
    try:
        op.create_index(
            op.f("ix_invited_user_id"),
            "invited",
            ["user_id"],
            unique=False,
        )
    except Exception:
        pass

    # 3. Миграция данных из meeting_users
    if "meeting_users" in insp.get_table_names():
        for row in conn.execute(
            sa.text(
                "SELECT id, sender_id, group_id, workspace_id, full_name, email, phone, meeting_id, answer, status "
                "FROM meeting_users WHERE meeting_id IS NOT NULL"
            )
        ):
            mu_id, sid, gid, wid, full_name, email, phone, meeting_id, answer, status = row
            if not meeting_id:
                continue
            # Найти или создать User
            user_row = conn.execute(
                sa.text(
                    "SELECT id FROM users WHERE sender_id=:sid AND group_id=:gid AND workspace_id=:wid"
                ),
                {"sid": sid, "gid": gid, "wid": wid},
            ).fetchone()
            if not user_row:
                conn.execute(
                    sa.text(
                        "INSERT INTO users (full_name, sender_id, group_id, workspace_id, email, phone, created_at) "
                        "VALUES (:fn, :sid, :gid, :wid, :email, :phone, datetime('now'))"
                    ),
                    {
                        "fn": full_name or "—",
                        "sid": sid,
                        "gid": gid,
                        "wid": wid,
                        "email": email,
                        "phone": phone,
                    },
                )
                user_row = conn.execute(
                    sa.text(
                        "SELECT id FROM users WHERE sender_id=:sid AND group_id=:gid AND workspace_id=:wid"
                    ),
                    {"sid": sid, "gid": gid, "wid": wid},
                ).fetchone()
            if not user_row:
                continue
            user_id = user_row[0]
            email_norm = (email or "").strip().lower() if email else ""
            # Найти Invited по meeting_id и email
            inv_row = None
            if email_norm:
                inv_row = conn.execute(
                    sa.text(
                        "SELECT id FROM invited WHERE meeting_id=:mid AND LOWER(TRIM(email))=:email"
                    ),
                    {"mid": meeting_id, "email": email_norm},
                ).fetchone()
            if inv_row:
                conn.execute(
                    sa.text(
                        "UPDATE invited SET user_id=:uid, full_name=COALESCE(:fn, full_name), "
                        "phone=COALESCE(:phone, phone), answer=:ans, status=:st WHERE id=:id"
                    ),
                    {
                        "uid": user_id,
                        "fn": full_name,
                        "phone": phone,
                        "ans": answer,
                        "st": status,
                        "id": inv_row[0],
                    },
                )
            else:
                conn.execute(
                    sa.text(
                        "INSERT INTO invited (meeting_id, full_name, email, phone, user_id, answer, status, created_at, updated_at) "
                        "VALUES (:mid, :fn, :email, :phone, :uid, :ans, :st, datetime('now'), datetime('now'))"
                    ),
                    {
                        "mid": meeting_id,
                        "fn": full_name or "—",
                        "email": email,
                        "phone": phone,
                        "uid": user_id,
                        "ans": answer,
                        "st": status,
                    },
                )

    # 4. Удалить meeting_users
    if "meeting_users" in insp.get_table_names():
        for idx in insp.get_indexes("meeting_users"):
            try:
                op.drop_index(idx["name"], table_name="meeting_users")
            except Exception:
                pass
        op.drop_table("meeting_users")


def downgrade() -> None:
    op.create_table(
        "meeting_users",
        sa.Column("sender_id", sa.BigInteger(), nullable=False),
        sa.Column("group_id", sa.BigInteger(), nullable=False),
        sa.Column("workspace_id", sa.BigInteger(), nullable=False),
        sa.Column("username", sa.String(255), nullable=True),
        sa.Column("email", sa.String(255), nullable=True),
        sa.Column("phone", sa.String(50), nullable=True),
        sa.Column("job_title", sa.String(255), nullable=True),
        sa.Column("full_name", sa.String(255), nullable=True),
        sa.Column("meeting_id", sa.Integer(), nullable=True),
        sa.Column("answer", sa.String(50), nullable=True),
        sa.Column("status", sa.String(50), nullable=True),
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=True),
        sa.Column("updated_at", sa.DateTime(), nullable=True),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_meeting_users_email"), "meeting_users", ["email"])
    op.create_index(op.f("ix_meeting_users_meeting_id"), "meeting_users", ["meeting_id"])
    op.create_index(op.f("ix_meeting_users_sender_id"), "meeting_users", ["sender_id"])
    op.create_index(op.f("ix_meeting_users_group_id"), "meeting_users", ["group_id"])
    op.create_index(op.f("ix_meeting_users_workspace_id"), "meeting_users", ["workspace_id"])
    op.create_index(
        "ix_meeting_users_sender_group_workspace_meeting",
        "meeting_users",
        ["sender_id", "group_id", "workspace_id", "meeting_id"],
        unique=True,
    )
    with op.batch_alter_table("invited") as batch_op:
        batch_op.drop_column("user_id")
        batch_op.drop_column("answer")
        batch_op.drop_column("status")
