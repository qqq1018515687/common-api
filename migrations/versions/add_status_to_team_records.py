"""add status field to team_consumption_records

Revision ID: add_status_team_records
Revises: 8a1b2c3d4e5f
Create Date: 2024-01-01

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'add_status_team_records'
down_revision: Union[str, None] = '8a1b2c3d4e5f'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    # 添加 status 字段到 team_consumption_records 表
    op.add_column(
        'team_consumption_records',
        sa.Column('status', sa.String(20), nullable=True, server_default='confirmed', comment='记录状态：pending/confirmed/cancelled')
    )


def downgrade() -> None:
    """Downgrade schema."""
    # 删除 status 字段
    op.drop_column('team_consumption_records', 'status')
