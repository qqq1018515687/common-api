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


TEAM_COLUMNS = {
    'id',
    'name',
    'description',
    'balance',
    'total_consumed',
    'member_count',
    'status',
    'settings',
    'created_at',
    'updated_at',
}

TEAM_MEMBER_COLUMNS = {
    'id',
    'team_id',
    'user_id',
    'role',
    'total_consumed',
    'joined_at',
    'updated_at',
}

TEAM_RECORD_COLUMNS = {
    'id',
    'team_id',
    'user_id',
    'amount',
    'balance_before',
    'balance_after',
    'operation_type',
    'related_id',
    'description',
    'metadata',
    'created_at',
}


def _inspector():
    return sa.inspect(op.get_bind())


def _table_exists(table_name: str) -> bool:
    return _inspector().has_table(table_name)


def _validate_columns(table_name: str, expected_columns: set[str]) -> None:
    existing_columns = {column['name'] for column in _inspector().get_columns(table_name)}
    missing_columns = sorted(expected_columns - existing_columns)

    if missing_columns:
        raise RuntimeError(
            f'Table {table_name} already exists but is missing required columns: '
            f'{", ".join(missing_columns)}'
        )


def _column_exists(table_name: str, column_name: str) -> bool:
    return any(column['name'] == column_name for column in _inspector().get_columns(table_name))


def _index_exists(table_name: str, index_name: str) -> bool:
    return any(index['name'] == index_name for index in _inspector().get_indexes(table_name))


def _constraint_exists(table_name: str, constraint_name: str) -> bool:
    constraints = _inspector().get_unique_constraints(table_name)
    return any(constraint['name'] == constraint_name for constraint in constraints)


def _create_index_if_missing(index_name: str, table_name: str, columns: list[str]) -> None:
    if not _index_exists(table_name, index_name):
        op.create_index(index_name, table_name, columns)


def _ensure_no_duplicate_team_members() -> None:
    duplicate_rows = op.get_bind().execute(sa.text("""
        SELECT team_id, user_id, COUNT(*) AS duplicate_count
        FROM team_members
        GROUP BY team_id, user_id
        HAVING COUNT(*) > 1
        LIMIT 10
    """)).mappings().all()

    if duplicate_rows:
        duplicate_summary = '; '.join(
            f"team_id={row['team_id']}, user_id={row['user_id']}, count={row['duplicate_count']}"
            for row in duplicate_rows
        )
        raise RuntimeError(
            'Cannot create team_members_team_user_key because duplicate team members exist: '
            f'{duplicate_summary}'
        )


def _create_team_member_unique_constraint_if_missing() -> None:
    constraint_name = 'team_members_team_user_key'
    if _constraint_exists('team_members', constraint_name):
        return

    _ensure_no_duplicate_team_members()
    op.create_unique_constraint(constraint_name, 'team_members', ['team_id', 'user_id'])


def _add_column_if_missing(table_name: str, column: sa.Column) -> None:
    if not _column_exists(table_name, column.name):
        op.add_column(table_name, column)


def upgrade() -> None:
    """Upgrade schema."""
    # 创建 teams 表
    if _table_exists('teams'):
        _validate_columns('teams', TEAM_COLUMNS)
    else:
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
    _create_index_if_missing('ix_teams_status', 'teams', ['status'])

    # 创建 team_members 表
    if _table_exists('team_members'):
        _validate_columns('team_members', TEAM_MEMBER_COLUMNS)
    else:
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
    _create_index_if_missing('ix_team_members_team', 'team_members', ['team_id'])
    _create_index_if_missing('ix_team_members_user', 'team_members', ['user_id'])
    _create_index_if_missing('ix_team_members_role', 'team_members', ['team_id', 'role'])
    _create_team_member_unique_constraint_if_missing()

    # 创建 team_consumption_records 表
    if _table_exists('team_consumption_records'):
        _validate_columns('team_consumption_records', TEAM_RECORD_COLUMNS)
    else:
        op.create_table(
            'team_consumption_records',
            sa.Column('id', sa.String(64), primary_key=True),
            sa.Column('team_id', sa.String(64), nullable=False, comment='团队ID'),
            sa.Column('user_id', sa.String(36), nullable=False, comment='消费的用户ID'),
            sa.Column('username', sa.String(50), nullable=True, comment='用户名（冗余字段）'),
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

    _add_column_if_missing(
        'team_consumption_records',
        sa.Column('username', sa.String(50), nullable=True, comment='用户名（冗余字段）')
    )

    # 创建 team_consumption_records 表索引
    _create_index_if_missing('ix_team_records_team_time', 'team_consumption_records', ['team_id', 'created_at'])
    _create_index_if_missing('ix_team_records_user_time', 'team_consumption_records', ['user_id', 'created_at'])
    _create_index_if_missing('ix_team_records_type', 'team_consumption_records', ['team_id', 'operation_type'])


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
