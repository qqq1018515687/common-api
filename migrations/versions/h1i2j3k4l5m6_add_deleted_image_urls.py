"""add deleted_image_urls column to tasks table

Revision ID: h1i2j3k4l5m6
Revises: g0h1i2j3k4l5
Create Date: 2026-07-02 00:00:00.000000

"""
from alembic import op
import sqlalchemy as sa


revision = "h1i2j3k4l5m6"
down_revision = "g0h1i2j3k4l5"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column('tasks', sa.Column('deleted_image_urls', sa.JSON(), nullable=True))


def downgrade():
    op.drop_column('tasks', 'deleted_image_urls')