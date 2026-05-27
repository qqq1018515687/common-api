"""add update_announcements table

Revision ID: c5d6e7f8a9b0
Revises: b4c5d6e7f8a9
Create Date: 2026-05-27 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "c5d6e7f8a9b0"
down_revision: Union[str, Sequence[str], None] = "b4c5d6e7f8a9"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "update_announcements",
        sa.Column("id", sa.String(36), primary_key=True, comment="公告ID"),
        sa.Column("title", sa.String(200), nullable=False, comment="公告标题"),
        sa.Column("summary", sa.Text(), nullable=True, comment="公告摘要"),
        sa.Column("items", sa.JSON(), nullable=True, comment="公告条目数组"),
        sa.Column("cta_text", sa.String(120), nullable=True, comment="行动按钮文案"),
        sa.Column("cta_url", sa.String(500), nullable=True, comment="行动按钮链接"),
        sa.Column("target_audience", sa.String(20), nullable=False, server_default="all", comment="目标用户：all/logged_in/guest/admin"),
        sa.Column("priority", sa.String(10), nullable=False, server_default="medium", comment="优先级：low/medium/high/urgent"),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default="true", comment="是否启用"),
        sa.Column("start_time", sa.BigInteger(), nullable=False, comment="生效时间戳（毫秒）"),
        sa.Column("end_time", sa.BigInteger(), nullable=True, comment="失效时间戳（毫秒，null表示永久）"),
        sa.Column("version", sa.String(64), nullable=True, comment="公告版本"),
        sa.Column("created_at", sa.BigInteger(), nullable=False, comment="创建时间（毫秒）"),
        sa.Column("updated_at", sa.BigInteger(), nullable=False, comment="更新时间（毫秒）"),
        sa.Column("created_by", sa.String(36), nullable=False, comment="创建者用户ID"),
        comment="更新公告表，用于首页弹窗公告",
        if_not_exists=True,
    )

    op.create_index("ix_update_announcements_is_active", "update_announcements", ["is_active"], if_not_exists=True)
    op.create_index("ix_update_announcements_target_audience", "update_announcements", ["target_audience"], if_not_exists=True)
    op.create_index("ix_update_announcements_priority", "update_announcements", ["priority"], if_not_exists=True)
    op.create_index("ix_update_announcements_time_range", "update_announcements", ["start_time", "end_time"], if_not_exists=True)


def downgrade() -> None:
    op.drop_index("ix_update_announcements_time_range", table_name="update_announcements", if_exists=True)
    op.drop_index("ix_update_announcements_priority", table_name="update_announcements", if_exists=True)
    op.drop_index("ix_update_announcements_target_audience", table_name="update_announcements", if_exists=True)
    op.drop_index("ix_update_announcements_is_active", table_name="update_announcements", if_exists=True)
    op.drop_table("update_announcements", if_exists=True)
