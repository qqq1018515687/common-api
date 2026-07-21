"""add recharge code tables

Revision ID: k4l5m6n7o8p9
Revises: j3k4l5m6n7o8
Create Date: 2026-07-21 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = 'k4l5m6n7o8p9'
down_revision: Union[str, Sequence[str], None] = 'j3k4l5m6n7o8'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _inspector():
    return sa.inspect(op.get_bind())


def _table_exists(table_name: str) -> bool:
    return _inspector().has_table(table_name)


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
    if not _table_exists('recharge_code_batches'):
        op.create_table(
            'recharge_code_batches',
            sa.Column('id', sa.String(64), primary_key=True, comment='批次ID'),
            sa.Column('name', sa.String(100), nullable=False, comment='批次名称'),
            sa.Column('credit_type', sa.String(20), nullable=False, comment='gold/personal_gold/team_gold'),
            sa.Column('amount', sa.Numeric(12, 2), nullable=False, comment='单码充值金额'),
            sa.Column('code_count', sa.Integer(), nullable=False, comment='生成数量'),
            sa.Column('status', sa.String(20), nullable=False, server_default=sa.text("'active'"), comment='active/disabled'),
            sa.Column('channel', sa.String(32), nullable=True, comment='售卖/发放渠道'),
            sa.Column('expires_at', sa.DateTime(timezone=True), nullable=True, comment='过期时间'),
            sa.Column('note', sa.Text(), nullable=True, comment='备注'),
            sa.Column('created_by', sa.String(36), nullable=False, comment='创建管理员'),
            sa.Column('created_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.text('now()'), comment='创建时间'),
            sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.text('now()'), comment='更新时间'),
            comment='金豆兑换码批次表',
        )
    _create_index_if_missing('ix_recharge_code_batches_status', 'recharge_code_batches', ['status'])
    _create_index_if_missing('ix_recharge_code_batches_created_at', 'recharge_code_batches', ['created_at'])

    if not _table_exists('recharge_codes'):
        op.create_table(
            'recharge_codes',
            sa.Column('id', sa.String(64), primary_key=True, comment='兑换码ID'),
            sa.Column('batch_id', sa.String(64), nullable=False, comment='批次ID'),
            sa.Column('code_hash', sa.String(128), nullable=False, comment='兑换码哈希'),
            sa.Column('code_suffix', sa.String(12), nullable=False, comment='兑换码后缀'),
            sa.Column('credit_type', sa.String(20), nullable=False, comment='gold/personal_gold/team_gold'),
            sa.Column('amount', sa.Numeric(12, 2), nullable=False, comment='充值金额'),
            sa.Column('status', sa.String(20), nullable=False, server_default=sa.text("'unused'"), comment='unused/used/disabled/expired'),
            sa.Column('used_by', sa.String(36), nullable=True, comment='兑换用户'),
            sa.Column('used_team_id', sa.String(64), nullable=True, comment='团队码入账团队'),
            sa.Column('used_at', sa.DateTime(timezone=True), nullable=True, comment='兑换时间'),
            sa.Column('billing_record_id', sa.String(64), nullable=True, comment='个人金豆账单ID'),
            sa.Column('team_record_id', sa.String(64), nullable=True, comment='团队金豆流水ID'),
            sa.Column('expires_at', sa.DateTime(timezone=True), nullable=True, comment='过期时间'),
            sa.Column('created_by', sa.String(36), nullable=False, comment='创建管理员'),
            sa.Column('created_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.text('now()'), comment='创建时间'),
            sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.text('now()'), comment='更新时间'),
            comment='金豆兑换码表，仅保存 hash 和后缀',
        )
    _create_unique_constraint_if_missing('recharge_codes_code_hash_key', 'recharge_codes', ['code_hash'])
    _create_index_if_missing('ix_recharge_codes_batch', 'recharge_codes', ['batch_id'])
    _create_index_if_missing('ix_recharge_codes_status', 'recharge_codes', ['status'])
    _create_index_if_missing('ix_recharge_codes_used_by', 'recharge_codes', ['used_by'])
    _create_index_if_missing('ix_recharge_codes_suffix', 'recharge_codes', ['code_suffix'])

    if not _table_exists('recharge_redemptions'):
        op.create_table(
            'recharge_redemptions',
            sa.Column('id', sa.String(64), primary_key=True, comment='兑换记录ID'),
            sa.Column('code_id', sa.String(64), nullable=False, comment='兑换码ID'),
            sa.Column('user_id', sa.String(36), nullable=False, comment='兑换用户'),
            sa.Column('team_id', sa.String(64), nullable=True, comment='入账团队'),
            sa.Column('credit_type', sa.String(20), nullable=False, comment='实际入账类型 personal_gold/team_gold'),
            sa.Column('amount', sa.Numeric(12, 2), nullable=False, comment='充值金额'),
            sa.Column('balance_before', sa.Numeric(12, 2), nullable=True, comment='入账前余额'),
            sa.Column('balance_after', sa.Numeric(12, 2), nullable=True, comment='入账后余额'),
            sa.Column('billing_record_id', sa.String(64), nullable=True, comment='个人金豆账单ID'),
            sa.Column('team_record_id', sa.String(64), nullable=True, comment='团队金豆流水ID'),
            sa.Column('status', sa.String(20), nullable=False, server_default=sa.text("'completed'"), comment='completed/failed'),
            sa.Column('error_message', sa.Text(), nullable=True, comment='失败原因'),
            sa.Column('metadata', sa.JSON(), nullable=True, comment='扩展信息'),
            sa.Column('created_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.text('now()'), comment='创建时间'),
            comment='金豆兑换记录表',
        )
    _create_unique_constraint_if_missing('recharge_redemptions_code_id_key', 'recharge_redemptions', ['code_id'])
    _create_index_if_missing('ix_recharge_redemptions_user_time', 'recharge_redemptions', ['user_id', 'created_at'])
    _create_index_if_missing('ix_recharge_redemptions_team_time', 'recharge_redemptions', ['team_id', 'created_at'])


def downgrade() -> None:
    if _table_exists('recharge_redemptions'):
        op.drop_index('ix_recharge_redemptions_team_time', table_name='recharge_redemptions')
        op.drop_index('ix_recharge_redemptions_user_time', table_name='recharge_redemptions')
        op.drop_constraint('recharge_redemptions_code_id_key', 'recharge_redemptions', type_='unique')
        op.drop_table('recharge_redemptions')

    if _table_exists('recharge_codes'):
        op.drop_index('ix_recharge_codes_suffix', table_name='recharge_codes')
        op.drop_index('ix_recharge_codes_used_by', table_name='recharge_codes')
        op.drop_index('ix_recharge_codes_status', table_name='recharge_codes')
        op.drop_index('ix_recharge_codes_batch', table_name='recharge_codes')
        op.drop_constraint('recharge_codes_code_hash_key', 'recharge_codes', type_='unique')
        op.drop_table('recharge_codes')

    if _table_exists('recharge_code_batches'):
        op.drop_index('ix_recharge_code_batches_created_at', table_name='recharge_code_batches')
        op.drop_index('ix_recharge_code_batches_status', table_name='recharge_code_batches')
        op.drop_table('recharge_code_batches')
