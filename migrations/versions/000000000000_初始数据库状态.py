"""初始数据库状态

本迁移标记当前数据库结构为初始状态，用于后续迁移的基准点。
数据库表包括：
- users: 用户表（user_id, phone, username, password_hash, avatar, team_id, credits, role, tier, account_status, created_at, updated_at）
- rate_limits: 限流表（record_id, phone, ip_address, request_count, first_request_at, last_request_at, is_blocked, blocked_until, created_at）
- history: 历史记录表（id, user_id, permanent_link, iso_timestamp, created_at, task_params, meta_data）

Revision ID: 000000000000
Revises:
Create Date: 2026-01-26 20:58:18.765728

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = '000000000000'
down_revision: Union[str, Sequence[str], None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """标记为初始数据库状态，不执行任何操作。

    当前数据库已包含以下表结构：
    - users: 用户表（user_id 为 10 位随机数字，phone 和 user_id 唯一）
    - rate_limits: 限流表
    - history: 历史记录表
    """
    pass


def downgrade() -> None:
    """回滚到初始数据库状态。

    注意：回滚将删除所有表结构，请谨慎操作！
    """
    # 回滚时删除所有表
    op.drop_table('history')
    op.drop_table('rate_limits')
    op.drop_table('users')
