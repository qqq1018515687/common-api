"""add task result fallback

Revision ID: m1n2o3p4q5r6
Revises: h1i2j3k4l5m6
Create Date: 2026-07-30 07:40:00.000000
"""

from alembic import op
import sqlalchemy as sa


revision = 'm1n2o3p4q5r6'
down_revision = 'h1i2j3k4l5m6'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column('tasks', sa.Column('result_fallback', sa.JSON(), nullable=True, comment='结果转存失败时保留的原始回退结果'))


def downgrade() -> None:
    op.drop_column('tasks', 'result_fallback')
