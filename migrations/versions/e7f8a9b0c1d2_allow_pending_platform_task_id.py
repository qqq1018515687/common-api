"""allow pending platform task id

Revision ID: e7f8a9b0c1d2
Revises: d6e7f8a9b0c1
Create Date: 2026-05-28 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op


revision: str = "e7f8a9b0c1d2"
down_revision: Union[str, Sequence[str], None] = "d6e7f8a9b0c1"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.alter_column("tasks", "platform_task_id", nullable=True)


def downgrade() -> None:
    op.execute("update tasks set platform_task_id = concat('pending:', id) where platform_task_id is null")
    op.alter_column("tasks", "platform_task_id", nullable=True)
