"""repair user status column lengths

Revision ID: 0d1e2f3a4b5c
Revises: f9a0b1c2d3e4
Create Date: 2026-06-22 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op


revision: str = "0d1e2f3a4b5c"
down_revision: Union[str, Sequence[str], None] = "f9a0b1c2d3e4"
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
    # Do not shrink these columns back to varchar(20); existing production data
    # can contain commercial_registered, which does not fit in the old schema.
    op.execute("alter table users alter column role set default 'user'")
    op.execute("alter table users alter column tier set default 'commercial_registered'")
    op.execute("alter table users alter column account_status set default 'active'")
