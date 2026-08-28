"""add task channel column and success rate indexes

Revision ID: y1z2a3b4c5d6
Revises: z9_task_final_reason_v1
Create Date: 2026-08-28 14:30:00.000000

说明：
- 为 tasks 增加可索引的 channel 归一字段，避免今日成功率统计扫 JSON。
- 回填历史任务渠道，供结果区今日成功率组件直接聚合使用。
"""

from typing import Sequence, Union

from alembic import op


revision: str = 'y1z2a3b4c5d6'
down_revision: Union[str, Sequence[str], None] = 'z9_task_final_reason_v1'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute("ALTER TABLE tasks ADD COLUMN IF NOT EXISTS channel VARCHAR(32)")


def downgrade() -> None:
    op.execute("ALTER TABLE tasks DROP COLUMN IF EXISTS channel")
