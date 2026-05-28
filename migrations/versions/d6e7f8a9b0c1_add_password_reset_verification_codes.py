"""add password reset verification codes table

Revision ID: d6e7f8a9b0c1
Revises: c5d6e7f8a9b0
Create Date: 2026-05-28 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "d6e7f8a9b0c1"
down_revision: Union[str, Sequence[str], None] = "c5d6e7f8a9b0"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "password_reset_verification_codes",
        sa.Column("id", sa.String(64), primary_key=True, comment="记录唯一标识"),
        sa.Column("phone", sa.String(11), nullable=False, comment="手机号"),
        sa.Column("code_hash", sa.String(64), nullable=False, comment="验证码哈希"),
        sa.Column("ip_address", sa.String(64), nullable=True, comment="请求 IP"),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False, comment="过期时间"),
        sa.Column("used_at", sa.DateTime(timezone=True), nullable=True, comment="使用时间"),
        sa.Column("attempts", sa.Integer(), nullable=False, server_default="0", comment="校验失败次数"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()"), comment="创建时间"),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()"), comment="更新时间"),
        comment="密码重置验证码表，仅保存验证码哈希和消费状态",
        if_not_exists=True,
    )
    op.create_index("ix_password_reset_codes_phone_created_at", "password_reset_verification_codes", ["phone", "created_at"], if_not_exists=True)
    op.create_index("ix_password_reset_codes_phone_used_expires", "password_reset_verification_codes", ["phone", "used_at", "expires_at"], if_not_exists=True)


def downgrade() -> None:
    op.drop_index("ix_password_reset_codes_phone_used_expires", table_name="password_reset_verification_codes", if_exists=True)
    op.drop_index("ix_password_reset_codes_phone_created_at", table_name="password_reset_verification_codes", if_exists=True)
    op.drop_table("password_reset_verification_codes", if_exists=True)
