"""change timestamp fields to varchar in tasks table

Revision ID: a1b2c3d4e5f6
Revises: 63e39be22dfc
Create Date: 2026-02-06 11:50:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'a1b2c3d4e5f6'
down_revision: Union[str, Sequence[str], None] = '63e39be22dfc'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    # 将时间字段从 bigint 改为 varchar(30)
    with op.batch_alter_table('tasks', schema=None) as batch_op:
        batch_op.alter_column('created_at',
               existing_type=sa.BigInteger(),
               type_=sa.String(30),
               existing_nullable=False,
               comment='任务创建时间')
        batch_op.alter_column('updated_at',
               existing_type=sa.BigInteger(),
               type_=sa.String(30),
               existing_nullable=False,
               comment='任务更新时间')
        batch_op.alter_column('completed_at',
               existing_type=sa.BigInteger(),
               type_=sa.String(30),
               existing_nullable=True,
               comment='完成时间')
        # 添加 disconnected_at 字段
        batch_op.add_column(sa.Column('disconnected_at', sa.String(30), nullable=True, comment='断开时间'))


def downgrade() -> None:
    """Downgrade schema."""
    # 回滚修改
    with op.batch_alter_table('tasks', schema=None) as batch_op:
        batch_op.alter_column('completed_at',
               existing_type=sa.String(30),
               type_=sa.BigInteger(),
               existing_nullable=True)
        batch_op.alter_column('updated_at',
               existing_type=sa.String(30),
               type_=sa.BigInteger(),
               existing_nullable=False)
        batch_op.alter_column('created_at',
               existing_type=sa.String(30),
               type_=sa.BigInteger(),
               existing_nullable=False)
        # 删除 disconnected_at 字段
        batch_op.drop_column('disconnected_at')
