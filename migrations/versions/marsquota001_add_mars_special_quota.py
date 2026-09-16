"""add mars special quota accounts and transactions

Revision ID: marsquota001
Revises: timg001
Create Date: 2026-09-16 12:00:00.000000
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "marsquota001"
down_revision: Union[str, Sequence[str], None] = "timg001"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.alter_column(
        "users",
        "silver_credits",
        existing_type=sa.Integer(),
        server_default=sa.text("2000"),
        existing_nullable=True,
    )
    op.add_column(
        "user_referral_relations",
        sa.Column(
            "reward_policy_version",
            sa.String(length=32),
            server_default="gold_v1",
            nullable=False,
        ),
    )
    op.execute(
        "UPDATE user_referral_relations "
        "SET reward_policy_version = 'gold_v1' "
        "WHERE reward_policy_version IS NULL OR reward_policy_version = ''"
    )

    op.create_table(
        "mars_special_quota_accounts",
        sa.Column("user_id", sa.String(length=36), nullable=False),
        sa.Column("permanent_remaining", sa.Integer(), server_default="0", nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.PrimaryKeyConstraint("user_id", name="mars_special_quota_accounts_pkey"),
        comment="火星特供永久次数账户；每日次数由流水按北京时间自然日计算",
    )
    op.create_table(
        "mars_special_quota_transactions",
        sa.Column("id", sa.String(length=64), nullable=False),
        sa.Column("idempotency_key", sa.String(length=160), nullable=False),
        sa.Column("user_id", sa.String(length=36), nullable=False),
        sa.Column("task_id", sa.String(length=36), nullable=True),
        sa.Column("transaction_type", sa.String(length=32), nullable=False),
        sa.Column("source", sa.String(length=32), nullable=False),
        sa.Column("amount", sa.Integer(), nullable=False),
        sa.Column("status", sa.String(length=20), nullable=False),
        sa.Column("quota_date", sa.String(length=10), nullable=True),
        sa.Column("related_id", sa.String(length=64), nullable=True),
        sa.Column("extra_data", sa.JSON(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.PrimaryKeyConstraint("id", name="mars_special_quota_transactions_pkey"),
        sa.UniqueConstraint("idempotency_key", name="mars_special_quota_transactions_idempotency_key"),
        sa.UniqueConstraint(
            "task_id",
            "transaction_type",
            "user_id",
            name="uq_mars_special_quota_task_type_user",
        ),
        comment="火星特供次数流水，统一审计用量与邀请赠送",
    )
    op.create_index(
        "ix_mars_special_quota_user_created",
        "mars_special_quota_transactions",
        ["user_id", "created_at"],
    )
    op.create_index(
        "ix_mars_special_quota_status",
        "mars_special_quota_transactions",
        ["status"],
    )


def downgrade() -> None:
    op.drop_index("ix_mars_special_quota_status", table_name="mars_special_quota_transactions")
    op.drop_index("ix_mars_special_quota_user_created", table_name="mars_special_quota_transactions")
    op.drop_table("mars_special_quota_transactions")
    op.drop_table("mars_special_quota_accounts")
    op.drop_column("user_referral_relations", "reward_policy_version")
    op.alter_column(
        "users",
        "silver_credits",
        existing_type=sa.Integer(),
        server_default=sa.text("999999999"),
        existing_nullable=True,
    )
