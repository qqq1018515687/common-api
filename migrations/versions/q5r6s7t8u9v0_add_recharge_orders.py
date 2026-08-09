"""add recharge orders

Revision ID: q5r6s7t8u9v0
Revises: t6u7v8w9x0y1
Create Date: 2026-08-08 00:00:00.000000

充值订单数据层迁移：
- 新增续充订单表 recharge_orders（订单面额真源、入账进度、业务状态机）
- recharge_codes 新增 order_id 列（一个订单可关联多个兑换码）
- 新增兑换失败尝试审计表 recharge_failed_attempts（风控/防刷用）
- 新增冲正申请表 recharge_reversal_requests（已入账订单人工冲正流程）
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = 'q5r6s7t8u9v0'
down_revision: Union[str, Sequence[str], None] = 't6u7v8w9x0y1'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _inspector():
    return sa.inspect(op.get_bind())


def _table_exists(table_name: str) -> bool:
    return _inspector().has_table(table_name)


def _column_exists(table_name: str, column_name: str) -> bool:
    columns = _inspector().get_columns(table_name)
    return any(column['name'] == column_name for column in columns)


def _index_exists(table_name: str, index_name: str) -> bool:
    return any(index['name'] == index_name for index in _inspector().get_indexes(table_name))


def _constraint_exists(table_name: str, constraint_name: str) -> bool:
    return any(constraint['name'] == constraint_name for constraint in _inspector().get_unique_constraints(table_name))


def _create_index_if_missing(index_name: str, table_name: str, columns: list[str]) -> None:
    if not _index_exists(table_name, index_name):
        op.create_index(index_name, table_name, columns)


def _create_unique_constraint_if_missing(constraint_name: str, table_name: str, columns: list[str]) -> None:
    if not _constraint_exists(table_name, constraint_name):
        op.create_unique_constraint(constraint_name, table_name, columns)


def upgrade() -> None:
    # 1. 新建续充订单表
    if not _table_exists('recharge_orders'):
        op.create_table(
            'recharge_orders',
            sa.Column('id', sa.String(64), primary_key=True, comment='订单ID'),
            sa.Column('order_no', sa.String(40), nullable=False, comment='订单号'),
            sa.Column('user_id', sa.String(36), nullable=True, comment='下单用户ID'),
            sa.Column('team_id', sa.String(64), nullable=True, comment='关联团队ID'),
            sa.Column('package_id', sa.String(64), nullable=True, comment='套餐ID'),
            sa.Column('package_name', sa.String(100), nullable=True, comment='套餐名称'),
            sa.Column('amount_paid', sa.Numeric(12, 2), nullable=False, comment='订单面额（真源）'),
            sa.Column('credited_amount', sa.Numeric(12, 2), nullable=True, comment='实际已入账金额（按已兑码累加）'),
            sa.Column('currency', sa.String(8), nullable=False, server_default=sa.text("'CNY'"), comment='币种'),
            sa.Column('channel', sa.String(32), nullable=False, server_default=sa.text("'manual'"), comment='渠道：wechat/xianyu/manual/campaign/compensation/ldxp'),
            sa.Column('source_type', sa.String(20), nullable=False, server_default=sa.text("'paid'"), comment='来源类型：paid/manual/compensation/campaign'),
            sa.Column('status', sa.String(20), nullable=False, server_default=sa.text("'paid'"), comment='状态：pending_payment/paid/issued/redeemed/refunded/cancelled/exception'),
            sa.Column('external_order_id', sa.String(128), nullable=True, comment='外部支付订单号'),
            sa.Column('external_ref', sa.String(255), nullable=True, comment='外部参考信息'),
            sa.Column('paid_at', sa.DateTime(timezone=True), nullable=True, comment='支付时间'),
            sa.Column('issued_at', sa.DateTime(timezone=True), nullable=True, comment='首次发码时间'),
            sa.Column('redeemed_at', sa.DateTime(timezone=True), nullable=True, comment='全量兑换完成时间'),
            sa.Column('refunded_at', sa.DateTime(timezone=True), nullable=True, comment='退款时间'),
            sa.Column('cancelled_at', sa.DateTime(timezone=True), nullable=True, comment='取消时间'),
            sa.Column('issued_code_count', sa.Integer(), nullable=False, server_default=sa.text('0'), comment='已发码数量'),
            sa.Column('refund_amount', sa.Numeric(12, 2), nullable=True, comment='退款金额'),
            sa.Column('operator_id', sa.String(64), nullable=True, comment='人工介入者 user_id'),
            sa.Column('note', sa.Text(), nullable=True, comment='备注'),
            sa.Column('metadata', sa.JSON(), nullable=True, comment='扩展信息'),
            sa.Column('created_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.text('now()'), comment='创建时间'),
            sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.text('now()'), comment='更新时间'),
            sa.UniqueConstraint('order_no', name='recharge_orders_order_no_key'),
            sa.UniqueConstraint('external_order_id', name='recharge_orders_external_order_id_key'),
            comment='金豆充值订单表',
        )
    _create_unique_constraint_if_missing('recharge_orders_order_no_key', 'recharge_orders', ['order_no'])
    _create_unique_constraint_if_missing('recharge_orders_external_order_id_key', 'recharge_orders', ['external_order_id'])
    _create_index_if_missing('ix_recharge_orders_order_no', 'recharge_orders', ['order_no'])
    _create_index_if_missing('ix_recharge_orders_user_id_created_at', 'recharge_orders', ['user_id', 'created_at'])
    _create_index_if_missing('ix_recharge_orders_status', 'recharge_orders', ['status'])
    _create_index_if_missing('ix_recharge_orders_channel', 'recharge_orders', ['channel'])
    _create_index_if_missing('ix_recharge_orders_source_type', 'recharge_orders', ['source_type'])
    _create_index_if_missing('ix_recharge_orders_created_at', 'recharge_orders', ['created_at'])

    # 2. recharge_codes 新增 order_id 关联列 + 索引
    if not _column_exists('recharge_codes', 'order_id'):
        op.add_column('recharge_codes', sa.Column('order_id', sa.String(64), nullable=True, comment='关联充值订单ID'))
    _create_index_if_missing('ix_recharge_codes_order_id', 'recharge_codes', ['order_id'])

    # 3. 新建兑换失败尝试审计表
    if not _table_exists('recharge_failed_attempts'):
        op.create_table(
            'recharge_failed_attempts',
            sa.Column('id', sa.String(64), primary_key=True, comment='记录ID'),
            sa.Column('user_id', sa.String(36), nullable=True, comment='尝试用户'),
            sa.Column('ip', sa.String(64), nullable=True, comment='请求IP'),
            sa.Column('code_suffix', sa.String(12), nullable=True, comment='兑换码后缀'),
            sa.Column('code_hash', sa.String(128), nullable=True, comment='兑换码哈希'),
            sa.Column('reason_type', sa.String(32), nullable=True, comment='失败类型：invalid_code/expired/already_used/no_team/blocked_account/unknown'),
            sa.Column('reason', sa.String(255), nullable=True, comment='失败原因描述'),
            sa.Column('created_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.text('now()'), comment='创建时间'),
            comment='兑换失败尝试记录表（风控/防刷）',
        )
    _create_index_if_missing('ix_failed_attempts_user_time', 'recharge_failed_attempts', ['user_id', 'created_at'])
    _create_index_if_missing('ix_failed_attempts_ip_time', 'recharge_failed_attempts', ['ip', 'created_at'])
    _create_index_if_missing('ix_failed_attempts_code_hash', 'recharge_failed_attempts', ['code_hash', 'created_at'])

    # 4. 新建冲正申请表
    if not _table_exists('recharge_reversal_requests'):
        op.create_table(
            'recharge_reversal_requests',
            sa.Column('id', sa.String(64), primary_key=True, comment='申请ID'),
            sa.Column('order_id', sa.String(64), nullable=False, comment='订单ID'),
            sa.Column('order_no', sa.String(40), nullable=True, comment='订单号'),
            sa.Column('user_id', sa.String(36), nullable=True, comment='下单用户ID'),
            sa.Column('team_id', sa.String(64), nullable=True, comment='关联团队ID'),
            sa.Column('requested_by', sa.String(64), nullable=True, comment='申请人 user_id'),
            sa.Column('reason', sa.Text(), nullable=False, comment='冲正原因'),
            sa.Column('status', sa.String(20), nullable=False, server_default=sa.text("'pending'"), comment='pending/approved/rejected/completed'),
            sa.Column('resolution_note', sa.Text(), nullable=True, comment='处理备注'),
            sa.Column('resolved_by', sa.String(64), nullable=True, comment='处理人 user_id'),
            sa.Column('resolved_at', sa.DateTime(timezone=True), nullable=True, comment='处理时间'),
            sa.Column('created_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.text('now()'), comment='创建时间'),
            sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.text('now()'), comment='更新时间'),
            sa.UniqueConstraint('order_id', name='recharge_reversal_requests_order_id_key'),
            comment='充值订单冲正申请表',
        )
    _create_unique_constraint_if_missing('recharge_reversal_requests_order_id_key', 'recharge_reversal_requests', ['order_id'])
    _create_index_if_missing('ix_reversal_requests_status', 'recharge_reversal_requests', ['status'])
    _create_index_if_missing('ix_reversal_requests_created_at', 'recharge_reversal_requests', ['created_at'])


def downgrade() -> None:
    if _table_exists('recharge_reversal_requests'):
        op.drop_index('ix_reversal_requests_created_at', table_name='recharge_reversal_requests')
        op.drop_index('ix_reversal_requests_status', table_name='recharge_reversal_requests')
        op.drop_constraint('recharge_reversal_requests_order_id_key', 'recharge_reversal_requests', type_='unique')
        op.drop_table('recharge_reversal_requests')

    # 3. 逆向删除失败尝试表
    if _table_exists('recharge_failed_attempts'):
        op.drop_index('ix_failed_attempts_code_hash', table_name='recharge_failed_attempts')
        op.drop_index('ix_failed_attempts_ip_time', table_name='recharge_failed_attempts')
        op.drop_index('ix_failed_attempts_user_time', table_name='recharge_failed_attempts')
        op.drop_table('recharge_failed_attempts')

    # 2. 删除 recharge_codes.order_id 关联
    if _column_exists('recharge_codes', 'order_id'):
        op.drop_index('ix_recharge_codes_order_id', table_name='recharge_codes')
        op.drop_column('recharge_codes', 'order_id')

    # 1. 逆向删除订单表
    if _table_exists('recharge_orders'):
        op.drop_index('ix_recharge_orders_created_at', table_name='recharge_orders')
        op.drop_index('ix_recharge_orders_source_type', table_name='recharge_orders')
        op.drop_index('ix_recharge_orders_channel', table_name='recharge_orders')
        op.drop_index('ix_recharge_orders_status', table_name='recharge_orders')
        op.drop_index('ix_recharge_orders_user_id_created_at', table_name='recharge_orders')
        op.drop_index('ix_recharge_orders_order_no', table_name='recharge_orders')
        op.drop_constraint('recharge_orders_external_order_id_key', 'recharge_orders', type_='unique')
        op.drop_constraint('recharge_orders_order_no_key', 'recharge_orders', type_='unique')
        op.drop_table('recharge_orders')
