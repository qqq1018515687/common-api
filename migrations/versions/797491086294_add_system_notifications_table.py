"""add system_notifications table

Revision ID: 797491086294
Revises: 63e39be22dfc
Create Date: 2026-03-04 20:10:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '797491086294'
down_revision: Union[str, Sequence[str], None] = '63e39be22dfc'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    # 创建 system_notifications 表
    op.create_table(
        'system_notifications',
        sa.Column('id', sa.String(36), primary_key=True),
        sa.Column('type', sa.String(20), nullable=False, comment='通知类型：info/warning/error/maintenance/update'),
        sa.Column('title', sa.String(200), nullable=False, comment='通知标题（短文本）'),
        sa.Column('content', sa.Text(), nullable=False, comment='通知内容（支持HTML）'),
        sa.Column('priority', sa.String(10), nullable=False, server_default='medium', comment='优先级：low/medium/high/urgent'),
        sa.Column('is_active', sa.Boolean(), nullable=False, server_default='true', comment='是否激活'),
        sa.Column('start_time', sa.BigInteger(), nullable=False, comment='生效时间戳（毫秒）'),
        sa.Column('end_time', sa.BigInteger(), nullable=True, comment='失效时间戳（毫秒，null表示永久）'),
        sa.Column('dismissible', sa.Boolean(), nullable=False, server_default='true', comment='是否允许用户关闭'),
        sa.Column('link_url', sa.String(500), nullable=True, comment='点击跳转链接（可选）'),
        sa.Column('target_audience', sa.String(20), nullable=False, server_default='all', comment='目标用户：all/logged_in/guest/admin'),
        sa.Column('created_at', sa.BigInteger(), nullable=False, comment='创建时间（毫秒）'),
        sa.Column('updated_at', sa.BigInteger(), nullable=True, comment='更新时间（毫秒）'),
        sa.Column('created_by', sa.String(36), nullable=False, comment='创建者用户ID'),
        comment='系统通知表，用于显示网站实时状态条内容'
    )

    # 创建索引
    op.create_index('ix_system_notifications_is_active', 'system_notifications', ['is_active'])
    op.create_index('ix_system_notifications_priority', 'system_notifications', ['priority'])
    op.create_index('ix_system_notifications_type', 'system_notifications', ['type'])
    op.create_index('ix_system_notifications_time_range', 'system_notifications', ['start_time', 'end_time'])


def downgrade() -> None:
    """Downgrade schema."""
    # 删除索引
    op.drop_index('ix_system_notifications_time_range', table_name='system_notifications')
    op.drop_index('ix_system_notifications_type', table_name='system_notifications')
    op.drop_index('ix_system_notifications_priority', table_name='system_notifications')
    op.drop_index('ix_system_notifications_is_active', table_name='system_notifications')

    # 删除表
    op.drop_table('system_notifications')
