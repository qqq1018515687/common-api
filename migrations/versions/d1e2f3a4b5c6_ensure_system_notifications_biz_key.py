"""ensure system_notifications.biz_key column + unique constraint exist

背景：b3a0aa0bb1c2_add_biz_key_to_system_notifications 迁移曾用无保险的 op.add_column
给 system_notifications 加 biz_key，但线上库存在"Alembic 已标记但线上漏列"的历史问题，
导致 alembic_version 标记该迁移已应用而物理列未建出。管理后台通知栏 / get_by_biz_key /
upsert_by_biz_key 查询 biz_key 时报 UndefinedColumn。

本迁移做幂等补偿：
- biz_key 列不存在则 ADD COLUMN IF NOT EXISTS
- uq_system_notifications_biz_key 唯一约束不存在则 create_unique_constraint

downgrade 说明：补偿迁移只补齐缺失对象，列/约束存在时为 no-op；
执行后不主动删除任何对象，downgrade 仅 pass。

Revision ID: d1e2f3a4b5c6
Revises: a5b6c7d8e9f0
Create Date: 2026-08-20 13:00:00.000000
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "d1e2f3a4b5c6"
down_revision: Union[str, Sequence[str], None] = "a5b6c7d8e9f0"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _inspector() -> sa.engine.Inspector:
    return sa.inspect(op.get_bind())


def _column_exists(table_name: str, column_name: str) -> bool:
    return any(column["name"] == column_name for column in _inspector().get_columns(table_name))


def _unique_constraint_exists(unique_name: str) -> bool:
    # 唯一约束在 pg 中同样体现为唯一索引（pg_indexes 会列出）。
    # 用 pg_indexes 检测可同时兼容"约束形式"与"历史 index 形式"，避免 ADD CONSTRAINT 冲突。
    row = op.get_bind().execute(
        sa.text(
            "SELECT 1 FROM pg_indexes "
            "WHERE tablename = 'system_notifications' AND indexname = :name"
        ),
        {"name": unique_name},
    ).fetchone()
    return row is not None


def upgrade() -> None:
    if not _column_exists("system_notifications", "biz_key"):
        op.add_column(
            "system_notifications",
            sa.Column("biz_key", sa.String(64), nullable=True, comment="业务标识：固定运营通知用（如 channel_status_t / channel_status_r），普通通知为空"),
        )
    if not _unique_constraint_exists("uq_system_notifications_biz_key"):
        # 兼容"unique index 已存在但约束名未登记在默认约束列表"的历史形态：
        # 若 pg_indexes 显示同名唯一索引存在，则补建约束会冲突，改为仅补唯一索引。
        row = op.get_bind().execute(
            sa.text(
                "SELECT indexdef FROM pg_indexes "
                "WHERE tablename = 'system_notifications' AND indexname = 'uq_system_notifications_biz_key'"
            )
        ).fetchone()
        if row and "UNIQUE" in (row[0] or "").upper():
            op.execute(
                "CREATE UNIQUE INDEX IF NOT EXISTS uq_system_notifications_biz_key ON system_notifications (biz_key)"
            )
        else:
            op.create_unique_constraint(
                "uq_system_notifications_biz_key",
                "system_notifications",
                ["biz_key"],
            )


def downgrade() -> None:
    pass