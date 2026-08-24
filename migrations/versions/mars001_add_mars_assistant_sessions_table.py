"""add mars assistant sessions table

Revision ID: mars001_add_mars_assistant_sessions
Revises: z1y2x3w4v5u6
Create Date: 2026-08-24 19:20:00.000000
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB


revision: str = 'mars001_add_mars_assistant_sessions'
down_revision: Union[str, Sequence[str], None] = 'z1y2x3w4v5u6'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
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
    op.create_index('ix_mars_assistant_sessions_user_updated', 'mars_assistant_sessions', ['user_id', 'updated_at'])
    op.create_index('ix_mars_assistant_sessions_team_updated', 'mars_assistant_sessions', ['team_id', 'updated_at'])


def downgrade() -> None:
    op.drop_index('ix_mars_assistant_sessions_team_updated', table_name='mars_assistant_sessions')
    op.drop_index('ix_mars_assistant_sessions_user_updated', table_name='mars_assistant_sessions')
    op.drop_table('mars_assistant_sessions')
