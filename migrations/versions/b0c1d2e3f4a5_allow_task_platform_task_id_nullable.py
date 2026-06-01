"""allow task platform task id nullable

Revision ID: b0c1d2e3f4a5
Revises: a9b0c1d2e3f4
Create Date: 2026-06-01 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "b0c1d2e3f4a5"
down_revision: Union[str, Sequence[str], None] = "a9b0c1d2e3f4"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.alter_column(
        "tasks",
        "platform_task_id",
        existing_type=sa.String(length=100),
        nullable=True,
    )


def downgrade() -> None:
    op.execute("update tasks set platform_task_id = concat('pending:', id) where platform_task_id is null")
    op.alter_column(
        "tasks",
        "platform_task_id",
        existing_type=sa.String(length=100),
        nullable=False,
    )
