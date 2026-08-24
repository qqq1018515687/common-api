"""ensure mars_assistant_sessions table and indexes exist

Revision ID: mars001_add_mars_assistant_sessions
Revises: d1e2f3a4b5c6
Create Date: 2026-08-24 19:20:00.000000
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB


revision: str = 'mars001_add_mars_assistant_sessions'
down_revision: Union[str, Sequence[str], None] = 'd1e2f3a4b5c6'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _inspector() -> sa.engine.Inspector:
    return sa.inspect(op.get_bind())


def _table_exists(table_name: str) -> bool:
    return table_name in _inspector().get_table_names()


def _index_exists(table_name: str, index_name: str) -> bool:
    return any(index['name'] == index_name for index in _inspector().get_indexes(table_name))


def upgrade() -> None:
    if not _table_exists('mars_assistant_sessions'):
        op.create_table(
            'mars_assistant_sessions',
            sa.Column('session_id', sa.String(length=64), nullable=False),
            sa.Column('user_id', sa.String(length=64), nullable=False),
            sa.Column('team_id', sa.String(length=64), nullable=True),
            sa.Column('task_state', JSONB(), nullable=True),
            sa.Column('image_asset_state', JSONB(), nullable=True),
            sa.Column('metadata', JSONB(), nullable=True),
            sa.Column('created_at', sa.BigInteger(), nullable=False),
            sa.Column('updated_at', sa.BigInteger(), nullable=False),
            sa.PrimaryKeyConstraint('session_id', name='mars_assistant_sessions_pkey'),
            comment='火星助手服务端会话状态表',
        )

    if not _index_exists('mars_assistant_sessions', 'ix_mars_assistant_sessions_user_updated'):
        op.create_index(
            'ix_mars_assistant_sessions_user_updated',
            'mars_assistant_sessions',
            ['user_id', 'updated_at'],
        )

    if not _index_exists('mars_assistant_sessions', 'ix_mars_assistant_sessions_team_updated'):
        op.create_index(
            'ix_mars_assistant_sessions_team_updated',
            'mars_assistant_sessions',
            ['team_id', 'updated_at'],
        )


def downgrade() -> None:
    pass
