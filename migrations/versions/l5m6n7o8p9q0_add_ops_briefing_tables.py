"""add ops briefing tables

Revision ID: l5m6n7o8p9q0
Revises: k4l5m6n7o8p9
Create Date: 2026-07-27 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "l5m6n7o8p9q0"
down_revision: Union[str, Sequence[str], None] = "k4l5m6n7o8p9"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "ops_briefing_raw_items",
        sa.Column("id", sa.String(64), primary_key=True, comment="记录ID"),
        sa.Column("briefing_date", sa.String(10), nullable=False, comment="晨报日期 YYYY-MM-DD"),
        sa.Column("title", sa.String(500), nullable=False, comment="标题"),
        sa.Column("source_name", sa.String(120), nullable=False, comment="来源名称"),
        sa.Column("source_type", sa.String(40), nullable=False, comment="official/news/trend/product_signal"),
        sa.Column("url", sa.Text(), nullable=False, comment="原文链接"),
        sa.Column("published_at", sa.DateTime(timezone=True), nullable=True, comment="原文发布时间"),
        sa.Column("collected_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()"), comment="采集时间"),
        sa.Column("category", sa.String(60), nullable=False, comment="分类"),
        sa.Column("credibility", sa.String(20), nullable=False, server_default="medium", comment="可信度 high/medium/low"),
        sa.Column("summary", sa.Text(), nullable=True, comment="原始摘要"),
        sa.Column("raw_payload", sa.JSON(), nullable=True, comment="原始扩展数据"),
        sa.Column("collector_id", sa.String(80), nullable=True, comment="采集器标识"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()"), comment="创建时间"),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()"), comment="更新时间"),
        sa.UniqueConstraint("url", name="uq_ops_briefing_raw_items_url"),
        comment="美国亚马逊运营晨报原始采集资料",
        if_not_exists=True,
    )
    op.create_index("ix_ops_briefing_raw_items_date", "ops_briefing_raw_items", ["briefing_date"], if_not_exists=True)
    op.create_index("ix_ops_briefing_raw_items_source", "ops_briefing_raw_items", ["source_name"], if_not_exists=True)
    op.create_index("ix_ops_briefing_raw_items_category", "ops_briefing_raw_items", ["category"], if_not_exists=True)

    op.create_table(
        "ops_daily_briefings",
        sa.Column("id", sa.String(64), primary_key=True, comment="晨报ID"),
        sa.Column("briefing_date", sa.String(10), nullable=False, comment="晨报日期 YYYY-MM-DD"),
        sa.Column("status", sa.String(20), nullable=False, server_default="empty", comment="ready/empty/partial_failed"),
        sa.Column("summary", sa.Text(), nullable=True, comment="今日一句话总结"),
        sa.Column("official_updates", sa.JSON(), nullable=True, comment="Amazon 官方动态"),
        sa.Column("ecommerce_news", sa.JSON(), nullable=True, comment="行业资讯快报"),
        sa.Column("product_signals", sa.JSON(), nullable=True, comment="公开选品信号"),
        sa.Column("action_items", sa.JSON(), nullable=True, comment="今日建议动作"),
        sa.Column("warnings", sa.JSON(), nullable=True, comment="数据质量提示"),
        sa.Column("source_stats", sa.JSON(), nullable=True, comment="来源统计"),
        sa.Column("generated_at", sa.DateTime(timezone=True), nullable=True, comment="生成时间"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()"), comment="创建时间"),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()"), comment="更新时间"),
        sa.UniqueConstraint("briefing_date", name="uq_ops_daily_briefings_date"),
        comment="美国亚马逊运营晨报每日结果",
        if_not_exists=True,
    )
    op.create_index("ix_ops_daily_briefings_status", "ops_daily_briefings", ["status"], if_not_exists=True)


def downgrade() -> None:
    op.drop_index("ix_ops_daily_briefings_status", table_name="ops_daily_briefings", if_exists=True)
    op.drop_table("ops_daily_briefings", if_exists=True)
    op.drop_index("ix_ops_briefing_raw_items_category", table_name="ops_briefing_raw_items", if_exists=True)
    op.drop_index("ix_ops_briefing_raw_items_source", table_name="ops_briefing_raw_items", if_exists=True)
    op.drop_index("ix_ops_briefing_raw_items_date", table_name="ops_briefing_raw_items", if_exists=True)
    op.drop_table("ops_briefing_raw_items", if_exists=True)
