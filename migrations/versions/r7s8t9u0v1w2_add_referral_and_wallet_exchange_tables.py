"""add referral and wallet exchange tables

Revision ID: r7s8t9u0v1w2
Revises: z1y2x3w4v5u6
Create Date: 2026-08-24 21:30:00.000000
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = 'r7s8t9u0v1w2'
down_revision: Union[str, Sequence[str], None] = 'z1y2x3w4v5u6'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        'user_referral_profiles',
        sa.Column('id', sa.String(length=64), nullable=False),
        sa.Column('user_id', sa.String(length=36), nullable=False),
        sa.Column('referral_code', sa.String(length=32), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.PrimaryKeyConstraint('id', name='user_referral_profiles_pkey'),
        sa.UniqueConstraint('user_id', name='user_referral_profiles_user_id_key'),
        sa.UniqueConstraint('referral_code', name='user_referral_profiles_referral_code_key'),
        comment='用户推荐码档案表',
    )
    op.create_index('ix_user_referral_profiles_referral_code', 'user_referral_profiles', ['referral_code'])

    op.create_table(
        'user_referral_relations',
        sa.Column('id', sa.String(length=64), nullable=False),
        sa.Column('referrer_user_id', sa.String(length=36), nullable=False),
        sa.Column('referee_user_id', sa.String(length=36), nullable=False),
        sa.Column('referral_code', sa.String(length=32), nullable=False),
        sa.Column('reward_status', sa.String(length=20), server_default='pending', nullable=False),
        sa.Column('bound_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.Column('reward_granted_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('first_completed_task_id', sa.String(length=36), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.PrimaryKeyConstraint('id', name='user_referral_relations_pkey'),
        sa.UniqueConstraint('referee_user_id', name='user_referral_relations_referee_user_id_key'),
        comment='用户邀请关系表',
    )
    op.create_index('ix_user_referral_relations_referrer_user_id', 'user_referral_relations', ['referrer_user_id'])
    op.create_index('ix_user_referral_relations_bound_at', 'user_referral_relations', ['bound_at'])

    op.create_table(
        'referral_reward_records',
        sa.Column('id', sa.String(length=64), nullable=False),
        sa.Column('relation_id', sa.String(length=64), nullable=False),
        sa.Column('referrer_user_id', sa.String(length=36), nullable=False),
        sa.Column('referee_user_id', sa.String(length=36), nullable=False),
        sa.Column('task_id', sa.String(length=36), nullable=False),
        sa.Column('reward_credit_type', sa.String(length=20), server_default='personal_gold', nullable=False),
        sa.Column('reward_amount', sa.Numeric(12, 2), nullable=False),
        sa.Column('billing_record_id', sa.String(length=64), nullable=True),
        sa.Column('description', sa.String(length=255), nullable=True),
        sa.Column('extra_data', sa.JSON(), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.PrimaryKeyConstraint('id', name='referral_reward_records_pkey'),
        sa.UniqueConstraint('relation_id', name='referral_reward_records_relation_id_key'),
        sa.UniqueConstraint('task_id', name='referral_reward_records_task_id_key'),
        comment='邀请奖励发放记录表',
    )
    op.create_index('ix_referral_reward_records_referrer_user_id', 'referral_reward_records', ['referrer_user_id'])
    op.create_index('ix_referral_reward_records_referee_user_id', 'referral_reward_records', ['referee_user_id'])
    op.create_index('ix_referral_reward_records_created_at', 'referral_reward_records', ['created_at'])

    op.create_table(
        'wallet_exchange_records',
        sa.Column('id', sa.String(length=64), nullable=False),
        sa.Column('idempotency_key', sa.String(length=128), nullable=False),
        sa.Column('user_id', sa.String(length=36), nullable=False),
        sa.Column('exchange_direction', sa.String(length=32), server_default='gold_to_silver', nullable=False),
        sa.Column('gold_amount', sa.Numeric(12, 2), nullable=False),
        sa.Column('silver_amount', sa.Integer(), nullable=False),
        sa.Column('exchange_rate', sa.Integer(), server_default='1000', nullable=False),
        sa.Column('gold_balance_before', sa.Numeric(12, 2), nullable=True),
        sa.Column('gold_balance_after', sa.Numeric(12, 2), nullable=True),
        sa.Column('silver_balance_before', sa.Integer(), nullable=True),
        sa.Column('silver_balance_after', sa.Integer(), nullable=True),
        sa.Column('out_billing_record_id', sa.String(length=64), nullable=True),
        sa.Column('in_billing_record_id', sa.String(length=64), nullable=True),
        sa.Column('status', sa.String(length=20), server_default='completed', nullable=False),
        sa.Column('description', sa.String(length=255), nullable=True),
        sa.Column('extra_data', sa.JSON(), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.PrimaryKeyConstraint('id', name='wallet_exchange_records_pkey'),
        sa.UniqueConstraint('idempotency_key', name='wallet_exchange_records_idempotency_key'),
        comment='钱包金豆换银豆主记录表',
    )
    op.create_index('ix_wallet_exchange_records_user_id', 'wallet_exchange_records', ['user_id'])
    op.create_index('ix_wallet_exchange_records_status', 'wallet_exchange_records', ['status'])
    op.create_index('ix_wallet_exchange_records_created_at', 'wallet_exchange_records', ['created_at'])


def downgrade() -> None:
    op.drop_index('ix_wallet_exchange_records_created_at', table_name='wallet_exchange_records')
    op.drop_index('ix_wallet_exchange_records_status', table_name='wallet_exchange_records')
    op.drop_index('ix_wallet_exchange_records_user_id', table_name='wallet_exchange_records')
    op.drop_table('wallet_exchange_records')

    op.drop_index('ix_referral_reward_records_created_at', table_name='referral_reward_records')
    op.drop_index('ix_referral_reward_records_referee_user_id', table_name='referral_reward_records')
    op.drop_index('ix_referral_reward_records_referrer_user_id', table_name='referral_reward_records')
    op.drop_table('referral_reward_records')

    op.drop_index('ix_user_referral_relations_bound_at', table_name='user_referral_relations')
    op.drop_index('ix_user_referral_relations_referrer_user_id', table_name='user_referral_relations')
    op.drop_table('user_referral_relations')

    op.drop_index('ix_user_referral_profiles_referral_code', table_name='user_referral_profiles')
    op.drop_table('user_referral_profiles')
