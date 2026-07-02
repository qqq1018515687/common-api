"""add deleted_image_urls column to tasks table - merge heads

Revision ID: h1i2j3k4l5m6
Revises: v001_add_seat_maps
Create Date: 2026-07-02 00:00:00.000000

This migration also depends on 0d1e2f3a4b5c to merge the migration branches.
"""
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa


revision: str = "h1i2j3k4l5m6"
down_revision: Union[str, Sequence[str], None] = ("0d1e2f3a4b5c", "v001_add_seat_maps")
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column('tasks', sa.Column('deleted_image_urls', sa.JSON(), nullable=True))


def downgrade() -> None:
    op.drop_column('tasks', 'deleted_image_urls')