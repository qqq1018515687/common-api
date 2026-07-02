"""add deleted_image_urls column to tasks table

Revision ID: g0h1i2j3k4l5
Revises: v001_add_seat_maps
Create Date: 2026-07-01 00:00:00.000000

"""
from alembic import op
import sqlalchemy as sa


revision = "g0h1i2j3k4l5"
down_revision = "v001_add_seat_maps"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column('tasks', sa.Column('deleted_image_urls', sa.JSON(), nullable=True))


def downgrade():
    op.drop_column('tasks', 'deleted_image_urls')
