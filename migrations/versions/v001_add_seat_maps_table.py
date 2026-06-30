"""add seat_maps table

座位表数据存储表，用于管理公司座位布局信息。

表结构：
- id: 主键（自增）
- version: 版本号（乐观锁，唯一）
- departments: 部门列表（JSONB数组）
- rows: 座位排列表（JSONB数组）
- seats: 座位列表（JSONB数组）
- updated_at: 最后更新时间
- updated_by_label: 更新者标识
- created_at: 创建时间

Revision ID: v001_add_seat_maps
Revises: 0d1e2f3a4b5c
Create Date: 2026-06-30 11:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB

# revision identifiers, used by Alembic.
revision: str = 'v001_add_seat_maps'
down_revision: Union[str, Sequence[str], None] = '0d1e2f3a4b5c'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """创建seat_maps表和相关索引"""

    # 创建seat_maps表
    op.create_table(
        'seat_maps',
        sa.Column('id', sa.Integer(), sa.Identity(always=False, start=1, increment=1), nullable=False),
        sa.Column('version', sa.Integer(), nullable=False, comment='版本号（乐观锁）'),
        sa.Column('departments', JSONB(), nullable=False, comment='部门列表（JSON数组）'),
        sa.Column('rows', JSONB(), nullable=False, comment='座位排列表（JSON数组）'),
        sa.Column('seats', JSONB(), nullable=False, comment='座位列表（JSON数组）'),
        sa.Column('updated_at', sa.DateTime(), server_default=sa.text('now()'), nullable=False, comment='最后更新时间'),
        sa.Column('updated_by_label', sa.String(40), nullable=True, comment='更新者标识'),
        sa.Column('created_at', sa.DateTime(), server_default=sa.text('now()'), nullable=False, comment='创建时间'),
        sa.PrimaryKeyConstraint('id', name='seat_maps_pkey')
    )

    # 创建唯一约束（确保version唯一）
    op.create_unique_constraint('uq_seat_maps_version', 'seat_maps', ['version'])

    # 创建性能索引
    op.create_index('ix_seat_maps_version', 'seat_maps', ['version'], unique=False)
    op.create_index('ix_seat_maps_updated_at', 'seat_maps', ['updated_at'], unique=False)

    # 插入初始数据（版本1 - 空座位表）
    op.execute("""
        INSERT INTO seat_maps (id, version, departments, rows, seats, updated_at, updated_by_label, created_at)
        VALUES (
            1,
            1,
            '[]'::jsonb,
            '[]'::jsonb,
            '[]'::jsonb,
            NOW(),
            '系统初始化',
            NOW()
        )
    """)


def downgrade() -> None:
    """删除seat_maps表和相关索引"""

    # 删除索引
    op.drop_index('ix_seat_maps_updated_at', table_name='seat_maps')
    op.drop_index('ix_seat_maps_version', table_name='seat_maps')

    # 删除唯一约束
    op.drop_constraint('uq_seat_maps_version', table_name='seat_maps', type_='unique')

    # 删除表
    op.drop_table('seat_maps')