"""add deduction_result field to tasks table

Revision ID: 63e39be22dfc
Revises: 000000000000
Create Date: 2026-02-05 15:39:27.365144

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '63e39be22dfc'
down_revision: Union[str, Sequence[str], None] = '000000000000'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    # 添加 deduction_result 字段到 tasks 表
    op.add_column('tasks', sa.Column('deduction_result', sa.JSON(), nullable=True, comment='扣费结果记录'))


def downgrade() -> None:
    """Downgrade schema."""
    # 删除 deduction_result 字段
    op.drop_column('tasks', 'deduction_result')
