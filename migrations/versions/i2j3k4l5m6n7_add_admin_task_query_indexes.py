"""add admin task query indexes

Revision ID: i2j3k4l5m6n7
Revises: v003_tasks_elapsed
Create Date: 2026-07-15 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op


revision: str = "i2j3k4l5m6n7"
down_revision: Union[str, Sequence[str], None] = "v003_tasks_elapsed"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """为管理后台任务列表增加按时间/状态查询索引。"""

    op.execute(
        "CREATE INDEX IF NOT EXISTS idx_tasks_admin_created "
        "ON tasks (is_deleted, created_at DESC)"
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS idx_tasks_admin_status_created "
        "ON tasks (is_deleted, status, created_at DESC)"
    )


def downgrade() -> None:
    """删除管理后台任务查询索引。"""

    op.execute("DROP INDEX IF EXISTS idx_tasks_admin_status_created")
    op.execute("DROP INDEX IF EXISTS idx_tasks_admin_created")
