"""add runtime_configs table

Revision ID: w1x2y3z4a5b6
Revises: y1z2a3b4c5d6
Create Date: 2026-09-02 16:00:00.000000
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = 'w1x2y3z4a5b6'
down_revision: Union[str, Sequence[str], None] = 'y1z2a3b4c5d6'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        'runtime_configs',
        sa.Column('id', sa.String(length=36), nullable=False),
        sa.Column('config_key', sa.String(length=128), nullable=False),
        sa.Column('config_scope', sa.String(length=32), nullable=False),
        sa.Column('config_type', sa.String(length=32), nullable=False),
        sa.Column('content_json', sa.JSON(), nullable=False),
        sa.Column('is_active', sa.Boolean(), nullable=False, server_default=sa.text('true')),
        sa.Column('is_public', sa.Boolean(), nullable=False, server_default=sa.text('false')),
        sa.Column('updated_by', sa.String(length=36), nullable=False),
        sa.Column('created_at', sa.BigInteger(), nullable=False),
        sa.Column('updated_at', sa.BigInteger(), nullable=False),
        sa.PrimaryKeyConstraint('id', name='runtime_configs_pkey'),
        sa.UniqueConstraint('config_key', name='uq_runtime_configs_config_key'),
        comment='运行时配置表，用于存储前端/站点可热更新的运营配置',
    )
    op.create_index('ix_runtime_configs_scope_type', 'runtime_configs', ['config_scope', 'config_type'], unique=False)
    op.create_index('ix_runtime_configs_is_active_public', 'runtime_configs', ['is_active', 'is_public'], unique=False)


def downgrade() -> None:
    op.drop_index('ix_runtime_configs_is_active_public', table_name='runtime_configs')
    op.drop_index('ix_runtime_configs_scope_type', table_name='runtime_configs')
    op.drop_table('runtime_configs')
