"""reassert user status column lengths

Revision ID: d3e4f5a6b7c8
Revises: c2d3e4f5a6b7
Create Date: 2026-06-02 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op


revision: str = "d3e4f5a6b7c8"
down_revision: Union[str, Sequence[str], None] = "c2d3e4f5a6b7"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute("alter table users alter column role type varchar(32)")
    op.execute("alter table users alter column tier type varchar(32)")
    op.execute("alter table users alter column account_status type varchar(32)")
    op.execute("alter table users alter column role set default 'user'")
    op.execute("alter table users alter column tier set default 'commercial_registered'")
    op.execute("alter table users alter column account_status set default 'active'")


def downgrade() -> None:
    # Keep downgrade data-safe: commercial tier names do not fit into varchar(20).
    op.execute("alter table users alter column role set default 'user'")
    op.execute("alter table users alter column tier set default 'commercial_registered'")
    op.execute("alter table users alter column account_status set default 'active'")
