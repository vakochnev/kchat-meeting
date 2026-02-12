"""unify to full_name: meeting_admins, invited, meeting_users

Revision ID: b10_full_name_unified
Revises: b9_remove_fields
Create Date: 2026-02-12

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "b10_full_name_unified"
down_revision: Union[str, Sequence[str], None] = "b9_remove_fields"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    conn = op.get_bind()

    # meeting_admins: add full_name, migrate, drop old
    with op.batch_alter_table("meeting_admins") as batch_op:
        batch_op.add_column(sa.Column("full_name", sa.String(255), nullable=True))
    conn.execute(sa.text(
        "UPDATE meeting_admins SET full_name = TRIM(COALESCE(last_name,'')||' '||COALESCE(first_name,'')||' '||COALESCE(middle_name,'')) WHERE full_name IS NULL"
    ))
    conn.execute(sa.text("UPDATE meeting_admins SET full_name = NULL WHERE full_name = ''"))
    with op.batch_alter_table("meeting_admins") as batch_op:
        batch_op.drop_column("last_name")
        batch_op.drop_column("first_name")
        batch_op.drop_column("middle_name")

    # invited: add full_name, migrate, drop old
    with op.batch_alter_table("invited") as batch_op:
        batch_op.add_column(sa.Column("full_name", sa.String(255), nullable=True))
    conn.execute(sa.text(
        "UPDATE invited SET full_name = TRIM(COALESCE(last_name,'')||' '||COALESCE(first_name,'')||' '||COALESCE(middle_name,'')) WHERE full_name IS NULL"
    ))
    conn.execute(sa.text("UPDATE invited SET full_name = NULL WHERE full_name = ''"))
    with op.batch_alter_table("invited") as batch_op:
        batch_op.drop_column("last_name")
        batch_op.drop_column("first_name")
        batch_op.drop_column("middle_name")

    # meeting_users: add full_name, migrate, drop old
    with op.batch_alter_table("meeting_users") as batch_op:
        batch_op.add_column(sa.Column("full_name", sa.String(255), nullable=True))
    conn.execute(sa.text(
        "UPDATE meeting_users SET full_name = TRIM(COALESCE(last_name,'')||' '||COALESCE(first_name,'')||' '||COALESCE(middle_name,'')) WHERE full_name IS NULL"
    ))
    conn.execute(sa.text("UPDATE meeting_users SET full_name = NULL WHERE full_name = ''"))
    with op.batch_alter_table("meeting_users") as batch_op:
        batch_op.drop_column("last_name")
        batch_op.drop_column("first_name")
        batch_op.drop_column("middle_name")


def downgrade() -> None:
    with op.batch_alter_table("meeting_admins") as batch_op:
        batch_op.add_column(sa.Column("last_name", sa.String(100), nullable=True))
        batch_op.add_column(sa.Column("first_name", sa.String(100), nullable=True))
        batch_op.add_column(sa.Column("middle_name", sa.String(100), nullable=True))
    with op.batch_alter_table("meeting_admins") as batch_op:
        batch_op.drop_column("full_name")

    with op.batch_alter_table("invited") as batch_op:
        batch_op.add_column(sa.Column("last_name", sa.String(100), nullable=True))
        batch_op.add_column(sa.Column("first_name", sa.String(100), nullable=True))
        batch_op.add_column(sa.Column("middle_name", sa.String(100), nullable=True))
    with op.batch_alter_table("invited") as batch_op:
        batch_op.drop_column("full_name")

    with op.batch_alter_table("meeting_users") as batch_op:
        batch_op.add_column(sa.Column("last_name", sa.String(100), nullable=True))
        batch_op.add_column(sa.Column("first_name", sa.String(100), nullable=True))
        batch_op.add_column(sa.Column("middle_name", sa.String(100), nullable=True))
    with op.batch_alter_table("meeting_users") as batch_op:
        batch_op.drop_column("full_name")
