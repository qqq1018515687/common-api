"""add deleted_image_urls column to tasks table

Revision ID: g0h1i2j3k4l5
Revises: v001_add_seat_maps
Create Date: 2026-07-01 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB


revision: str = "g0h1i2j3k4l5"
down_revision: Union[str, Sequence[str], None] = "v001_add_seat_maps"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Add the column with JSONB type and default empty array
    op.add_column('tasks', sa.Column('deleted_image_urls', JSONB, nullable=True, server_default='[]'))
    # Create index for faster queries
    op.create_index('ix_tasks_deleted_image_urls', 'tasks', ['deleted_image_urls'])


def downgrade() -> None:
    op.drop_index('ix_tasks_deleted_image_urls', table_name='tasks')
    op.drop_column('tasks', 'deleted_image_urls')
