"""add deleted_image_urls column to tasks table

Revision ID: g0h1i2j3k4l5
Revises: f9a0b1c2d3e4
Create Date: 2026-07-01 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "g0h1i2j3k4l5"
down_revision: Union[str, Sequence[str], None] = ("f9a0b1c2d3e4", "v001_add_seat_maps")
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Add the column with default empty array
    op.add_column('tasks', sa.Column('deleted_image_urls', sa.ARRAY(sa.Text()), nullable=True))
    # Create index for faster queries on this field
    op.create_index('ix_tasks_deleted_image_urls', 'tasks', ['deleted_image_urls'])


def downgrade() -> None:
    op.drop_index('ix_tasks_deleted_image_urls', table_name='tasks')
    op.drop_column('tasks', 'deleted_image_urls')
