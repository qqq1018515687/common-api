"""add tasks elapsed time fields

任务耗时字段迁移,用于后端统一计算任务耗时。

新增字段:
- started_at: 任务真正开始执行时间(VARCHAR 20,毫秒时间戳字符串)
- elapsed_time_seconds: 任务耗时秒数(INTEGER,默认0)

本迁移同时确保 users 表字段为 varchar(32),避免触发 varchar(20) 限制错误
(因数据库中存在 commercial_registered 等 21 字符的 tier 值)

Revision ID: v003_tasks_elapsed
Revises: h1i2j3k4l5m6
Create Date: 2026-07-10 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op

# revision identifiers, used by Alembic.
revision: str = 'v003_tasks_elapsed'
down_revision: Union[str, Sequence[str], None] = 'h1i2j3k4l5m6'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """先确保 users 表字段长度,再添加 tasks 表耗时字段"""

    # 【防护】先确保 users 表字段为 varchar(32),避免后续迁移触发 varchar(20) 限制
    # 使用 IF NOT EXISTS 语义不可用,这里直接 ALTER TYPE(幂等,已经是 varchar(32) 也不会报错)
    op.execute("ALTER TABLE users ALTER COLUMN role TYPE varchar(32)")
    op.execute("ALTER TABLE users ALTER COLUMN tier TYPE varchar(32)")
    op.execute("ALTER TABLE users ALTER COLUMN account_status TYPE varchar(32)")

    # 【新增】tasks 表耗时字段(使用 IF NOT EXISTS 避免与运行时 _ensure_task_schema 冲突)
    op.execute("ALTER TABLE tasks ADD COLUMN IF NOT EXISTS started_at VARCHAR(20)")
    op.execute("ALTER TABLE tasks ADD COLUMN IF NOT EXISTS elapsed_time_seconds INTEGER DEFAULT 0")

    # 【回填】旧任务的 started_at 用 created_at 兜底
    op.execute("""
        UPDATE tasks
        SET started_at = created_at
        WHERE started_at IS NULL
    """)


def downgrade() -> None:
    """移除 tasks 表耗时字段(不动 users 表,避免数据丢失)"""

    op.drop_column('tasks', 'elapsed_time_seconds')
    op.drop_column('tasks', 'started_at')
