"""add task terminal time fields

Revision ID: u7v8w9x0y1z2
Revises: q5r6s7t8u9v0, p2q3r4s5t6u7
Create Date: 2026-08-19 11:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = 'u7v8w9x0y1z2'
down_revision: Union[str, Sequence[str], None] = 'q5r6s7t8u9v0'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _inspector():
    return sa.inspect(op.get_bind())


def _column_exists(table_name: str, column_name: str) -> bool:
    return any(column['name'] == column_name for column in _inspector().get_columns(table_name))


def _index_exists(table_name: str, index_name: str) -> bool:
    return any(index['name'] == index_name for index in _inspector().get_indexes(table_name))


def _create_index_if_missing(index_name: str, table_name: str, columns: list[str]) -> None:
    if not _index_exists(table_name, index_name):
        op.create_index(index_name, table_name, columns)


def upgrade() -> None:
    if not _column_exists('tasks', 'failed_at'):
        op.add_column('tasks', sa.Column('failed_at', sa.String(length=20), nullable=True, comment='失败时间'))
    if not _column_exists('tasks', 'cancelled_at'):
        op.add_column('tasks', sa.Column('cancelled_at', sa.String(length=20), nullable=True, comment='取消时间'))
    if not _column_exists('tasks', 'status_updated_at'):
        op.add_column('tasks', sa.Column('status_updated_at', sa.String(length=20), nullable=True, comment='最近一次状态变更时间'))

    bind = op.get_bind()
    bind.execute(sa.text("UPDATE tasks SET failed_at = COALESCE(failed_at, updated_at) WHERE status = 'failed' AND failed_at IS NULL"))
    bind.execute(sa.text("UPDATE tasks SET cancelled_at = COALESCE(cancelled_at, updated_at) WHERE status = 'cancelled' AND cancelled_at IS NULL"))
    bind.execute(sa.text("UPDATE tasks SET status_updated_at = COALESCE(status_updated_at, updated_at) WHERE status_updated_at IS NULL"))

    _create_index_if_missing('idx_tasks_status_created_at', 'tasks', ['status', 'created_at'])
    _create_index_if_missing('idx_tasks_status_completed_at', 'tasks', ['status', 'completed_at'])
    _create_index_if_missing('idx_tasks_status_failed_at', 'tasks', ['status', 'failed_at'])
    _create_index_if_missing('idx_tasks_status_cancelled_at', 'tasks', ['status', 'cancelled_at'])


def downgrade() -> None:
    inspector = _inspector()
    index_names = {index['name'] for index in inspector.get_indexes('tasks')}
    for index_name in (
        'idx_tasks_status_cancelled_at',
        'idx_tasks_status_failed_at',
        'idx_tasks_status_completed_at',
        'idx_tasks_status_created_at',
    ):
        if index_name in index_names:
            op.drop_index(index_name, table_name='tasks')

    column_names = {column['name'] for column in inspector.get_columns('tasks')}
    for column_name in ('status_updated_at', 'cancelled_at', 'failed_at'):
        if column_name in column_names:
            op.drop_column('tasks', column_name)
