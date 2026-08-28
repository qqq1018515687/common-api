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
    op.execute(
        "UPDATE tasks SET channel = CASE "
        "WHEN lower(coalesce(parameter_snapshot ->> 'channel', parameter_snapshot ->> 'channelKey', workflow_parameters ->> 'channel', parameter_snapshot ->> 'channelLabel', workflow_parameters ->> 'channelLabel', split_part(parameter_snapshot ->> 'modelDisplayLabel', ' ', 1), split_part(workflow_parameters ->> 'modelDisplayLabel', ' ', 1), '')) IN ('local', '本地', '局域', '局域网') THEN 'local' "
        "WHEN lower(coalesce(parameter_snapshot ->> 'channel', parameter_snapshot ->> 'channelKey', workflow_parameters ->> 'channel', parameter_snapshot ->> 'channelLabel', workflow_parameters ->> 'channelLabel', split_part(parameter_snapshot ->> 'modelDisplayLabel', ' ', 1), split_part(workflow_parameters ->> 'modelDisplayLabel', ' ', 1), '')) IN ('free', '免费') THEN 'free' "
        "WHEN lower(coalesce(parameter_snapshot ->> 'channel', parameter_snapshot ->> 'channelKey', workflow_parameters ->> 'channel', parameter_snapshot ->> 'channelLabel', workflow_parameters ->> 'channelLabel', split_part(parameter_snapshot ->> 'modelDisplayLabel', ' ', 1), split_part(workflow_parameters ->> 'modelDisplayLabel', ' ', 1), '')) = 'r' OR lower(coalesce(parameter_snapshot ->> 'channelLabel', workflow_parameters ->> 'channelLabel', split_part(parameter_snapshot ->> 'modelDisplayLabel', ' ', 1), split_part(workflow_parameters ->> 'modelDisplayLabel', ' ', 1), '')) LIKE 'r版%' THEN 'r' "
        "WHEN lower(coalesce(parameter_snapshot ->> 'channel', parameter_snapshot ->> 'channelKey', workflow_parameters ->> 'channel', parameter_snapshot ->> 'channelLabel', workflow_parameters ->> 'channelLabel', split_part(parameter_snapshot ->> 'modelDisplayLabel', ' ', 1), split_part(workflow_parameters ->> 'modelDisplayLabel', ' ', 1), '')) = 't' OR lower(coalesce(parameter_snapshot ->> 'channelLabel', workflow_parameters ->> 'channelLabel', split_part(parameter_snapshot ->> 'modelDisplayLabel', ' ', 1), split_part(workflow_parameters ->> 'modelDisplayLabel', ' ', 1), '')) LIKE 't版%' THEN 't' "
        "WHEN coalesce(parameter_snapshot ->> 'channelLabel', workflow_parameters ->> 'channelLabel', parameter_snapshot ->> 'modelDisplayLabel', workflow_parameters ->> 'modelDisplayLabel', '') <> '' THEN 'other' "
        "ELSE channel END "
        "WHERE channel IS NULL OR btrim(channel) = ''"
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS idx_tasks_channel_created_at "
        "ON tasks (channel, created_at)"
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS idx_tasks_channel_status_created_at "
        "ON tasks (channel, status, created_at)"
    )


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS idx_tasks_channel_status_created_at")
    op.execute("DROP INDEX IF EXISTS idx_tasks_channel_created_at")
    op.execute("ALTER TABLE tasks DROP COLUMN IF EXISTS channel")
