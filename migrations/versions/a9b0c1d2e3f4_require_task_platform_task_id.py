"""require task platform task id after backfill

Revision ID: a9b0c1d2e3f4
Revises: f8a9b0c1d2e3
Create Date: 2026-06-01 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "a9b0c1d2e3f4"
down_revision: Union[str, Sequence[str], None] = "f8a9b0c1d2e3"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute("update tasks set platform_task_id = concat('pending:', id) where platform_task_id is null")
    op.alter_column(
        "tasks",
        "platform_task_id",
        existing_type=sa.String(length=100),
        nullable=False,
    )


def downgrade() -> None:
    op.alter_column(
        "tasks",
        "platform_task_id",
        existing_type=sa.String(length=100),
        nullable=True,
    )
