"""reconcile user status schema

Revision ID: e4f5a6b7c8d9
Revises: d3e4f5a6b7c8
Create Date: 2026-06-03 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "e4f5a6b7c8d9"
down_revision: Union[str, Sequence[str], None] = "d3e4f5a6b7c8"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _table_exists(table_name: str) -> bool:
    return sa.inspect(op.get_bind()).has_table(table_name)


def upgrade() -> None:
    if not _table_exists("users"):
        return

    op.execute("alter table users alter column role type varchar(32)")
    op.execute("alter table users alter column tier type varchar(32)")
    op.execute("alter table users alter column account_status type varchar(32)")
    op.execute("alter table users alter column role set default 'user'")
    op.execute("alter table users alter column tier set default 'commercial_registered'")
    op.execute("alter table users alter column account_status set default 'active'")


def downgrade() -> None:
    # Keep downgrade data-safe: commercial tier names do not fit into varchar(20).
    if not _table_exists("users"):
        return

    op.execute("alter table users alter column role set default 'user'")
    op.execute("alter table users alter column tier set default 'commercial_registered'")
    op.execute("alter table users alter column account_status set default 'active'")
