"""add team balance tables

Revision ID: 8a1b2c3d4e5f
Revises: 797491086294
Create Date: 2026-03-04 21:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '8a1b2c3d4e5f'
down_revision: Union[str, Sequence[str], None] = '797491086294'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    # 创建 teams 表
    op.create_table(
        'teams',
        sa.Column('id', sa.String(64), primary_key=True),
        sa.Column('name', sa.String(100), nullable=False, comment='团队名称'),
        sa.Column('description', sa.String(255), nullable=True, comment='团队描述'),
        sa.Column('balance', sa.Integer(), nullable=False, server_default='0', comment='团队金豆余额'),
        sa.Column('total_consumed', sa.Integer(), nullable=False, server_default='0', comment='团队总消费金额'),
        sa.Column('member_count', sa.Integer(), nullable=False, server_default='0', comment='成员数量'),
        sa.Column('status', sa.String(20), nullable=False, server_default='active', comment='状态：active/disabled'),
        sa.Column('settings', sa.JSON(), nullable=True, comment='团队配置（限额、预警等）'),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.text('now()'), comment='创建时间'),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.text('now()'), comment='更新时间'),
        comment='团队基本信息表，存储团队的金豆余额和基本信息'
    )

    # 创建 teams 表索引
    op.create_index('ix_teams_status', 'teams', ['status'])

    # 创建 team_members 表
    op.create_table(
        'team_members',
        sa.Column('id', sa.String(64), primary_key=True),
        sa.Column('team_id', sa.String(64), nullable=False, comment='团队ID'),
        sa.Column('user_id', sa.String(36), nullable=False, comment='用户ID'),
        sa.Column('role', sa.String(20), nullable=False, server_default='member', comment='角色：admin/member'),
        sa.Column('total_consumed', sa.Integer(), nullable=False, server_default='0', comment='该成员在团队中的总消费'),
        sa.Column('joined_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.text('now()'), comment='加入时间'),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.text('now()'), comment='更新时间'),
        comment='团队成员关系表，记录用户与团队的关联关系'
    )

    # 创建 team_members 表索引
    op.create_index('ix_team_members_team', 'team_members', ['team_id'])
    op.create_index('ix_team_members_user', 'team_members', ['user_id'])
    op.create_index('ix_team_members_role', 'team_members', ['team_id', 'role'])
    op.create_unique_constraint('team_members_team_user_key', 'team_members', ['team_id', 'user_id'])

    # 创建 team_consumption_records 表
    op.create_table(
        'team_consumption_records',
        sa.Column('id', sa.String(64), primary_key=True),
        sa.Column('team_id', sa.String(64), nullable=False, comment='团队ID'),
        sa.Column('user_id', sa.String(36), nullable=False, comment='消费的用户ID'),
        sa.Column('amount', sa.BigInteger(), nullable=False, comment='消费金额（正数表示消费，负数表示退款/充值）'),
        sa.Column('balance_before', sa.BigInteger(), nullable=True, comment='变动前余额'),
        sa.Column('balance_after', sa.BigInteger(), nullable=True, comment='变动后余额'),
        sa.Column('operation_type', sa.String(20), nullable=False, comment='操作类型：consumption/refund/recharge'),
        sa.Column('related_id', sa.String(64), nullable=True, comment='关联ID（任务ID/订单ID）'),
        sa.Column('description', sa.String(255), nullable=True, comment='描述说明'),
        sa.Column('metadata', sa.JSON(), nullable=True, comment='扩展信息（任务类型、产品信息等）'),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.text('now()'), comment='创建时间'),
        comment='团队消费记录表，记录团队内每笔消费的详细信息'
    )

    # 创建 team_consumption_records 表索引
    op.create_index('ix_team_records_team_time', 'team_consumption_records', ['team_id', 'created_at'])
    op.create_index('ix_team_records_user_time', 'team_consumption_records', ['user_id', 'created_at'])
    op.create_index('ix_team_records_type', 'team_consumption_records', ['team_id', 'operation_type'])


def downgrade() -> None:
    """Downgrade schema."""
    # 删除 team_consumption_records 表
    op.drop_index('ix_team_records_type', table_name='team_consumption_records')
    op.drop_index('ix_team_records_user_time', table_name='team_consumption_records')
    op.drop_index('ix_team_records_team_time', table_name='team_consumption_records')
    op.drop_table('team_consumption_records')

    # 删除 team_members 表
    op.drop_constraint('team_members_team_user_key', 'team_members')
    op.drop_index('ix_team_members_role', table_name='team_members')
    op.drop_index('ix_team_members_user', table_name='team_members')
    op.drop_index('ix_team_members_team', table_name='team_members')
    op.drop_table('team_members')

    # 删除 teams 表
    op.drop_index('ix_teams_status', table_name='teams')
    op.drop_table('teams')
