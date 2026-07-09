"""add tasks elapsed time fields

任务耗时字段迁移,用于后端统一计算任务耗时。

新增字段:
- started_at: 任务真正开始执行时间(VARCHAR 20,毫秒时间戳字符串)
- elapsed_time_seconds: 任务耗时秒数(INTEGER,默认0)

Revision ID: v002_add_tasks_elapsed_time_fields
Revises: h1i2j3k4l5m6
Create Date: 2026-07-09 16:30:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = 'v002_add_tasks_elapsed_time_fields'
down_revision: Union[str, Sequence[str], None] = 'h1i2j3k4l5m6'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """新增任务耗时字段"""

    # 新增 started_at 字段(可空,毫秒时间戳字符串)
    op.add_column(
        'tasks',
        sa.Column('started_at', sa.String(20), nullable=True, comment='任务真正开始执行的时间戳(毫秒字符串)')
    )

    # 新增 elapsed_time_seconds 字段(整数,默认0)
    op.add_column(
        'tasks',
        sa.Column('elapsed_time_seconds', sa.Integer(), server_default='0', nullable=True, comment='任务耗时(秒),由后端统一计算')
    )

    # 为旧任务回填 started_at(使用 created_at 作为兜底)
    # 注意:使用原生 SQL 更新,避免 ORM 开销
    op.execute("""
        UPDATE tasks
        SET started_at = created_at
        WHERE started_at IS NULL
    """)


def downgrade() -> None:
    """移除任务耗时字段(保留数据安全,不删除数据)"""

    # 注意:downgrade 会丢失耗时数据,但这是合理的回滚行为
    op.drop_column('tasks', 'elapsed_time_seconds')
    op.drop_column('tasks', 'started_at')
