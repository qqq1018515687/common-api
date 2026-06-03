"""ensure team member unique constraint

Revision ID: d3e4f5a6b7c8
Revises: c2d3e4f5a6b7
Create Date: 2026-06-03 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "d3e4f5a6b7c8"
down_revision: Union[str, Sequence[str], None] = "c2d3e4f5a6b7"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _table_exists(table_name: str) -> bool:
    return sa.inspect(op.get_bind()).has_table(table_name)


def _column_exists(table_name: str, column_name: str) -> bool:
    inspector = sa.inspect(op.get_bind())
    return any(column["name"] == column_name for column in inspector.get_columns(table_name))


def _unique_constraint_exists(table_name: str, constraint_name: str) -> bool:
    inspector = sa.inspect(op.get_bind())
    return any(
        constraint["name"] == constraint_name
        for constraint in inspector.get_unique_constraints(table_name)
    )


def _ensure_no_duplicate_team_members() -> None:
    duplicate_rows = op.get_bind().execute(sa.text("""
        SELECT team_id, user_id, COUNT(*) AS duplicate_count
        FROM team_members
        GROUP BY team_id, user_id
        HAVING COUNT(*) > 1
        LIMIT 10
    """)).mappings().all()

    if duplicate_rows:
        duplicate_summary = "; ".join(
            f"team_id={row['team_id']}, user_id={row['user_id']}, count={row['duplicate_count']}"
            for row in duplicate_rows
        )
        raise RuntimeError(
            "Cannot create team_members_team_user_key because duplicate team members exist: "
            f"{duplicate_summary}"
        )


def upgrade() -> None:
    if _table_exists("team_consumption_records") and not _column_exists("team_consumption_records", "username"):
        op.add_column(
            "team_consumption_records",
            sa.Column("username", sa.String(50), nullable=True, comment="用户名（冗余字段）"),
        )

    if not _table_exists("team_members"):
        return

    constraint_name = "team_members_team_user_key"
    if _unique_constraint_exists("team_members", constraint_name):
        return

    _ensure_no_duplicate_team_members()
    op.create_unique_constraint(constraint_name, "team_members", ["team_id", "user_id"])


def downgrade() -> None:
    if _table_exists("team_members") and _unique_constraint_exists("team_members", "team_members_team_user_key"):
        op.drop_constraint("team_members_team_user_key", "team_members", type_="unique")

    if _table_exists("team_consumption_records") and _column_exists("team_consumption_records", "username"):
        op.drop_column("team_consumption_records", "username")
