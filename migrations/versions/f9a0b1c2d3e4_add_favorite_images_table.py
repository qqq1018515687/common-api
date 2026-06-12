"""add favorite_images table

Revision ID: f9a0b1c2d3e4
Revises: f5a6b7c8d9e0
Create Date: 2026-06-12 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "f9a0b1c2d3e4"
down_revision: Union[str, Sequence[str], None] = "f5a6b7c8d9e0"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "favorite_images",
        sa.Column("favorite_id", sa.String(36), nullable=False, comment="Favorite record ID"),
        sa.Column("user_id", sa.String(36), nullable=False, comment="Owner user ID"),
        sa.Column("task_id", sa.String(36), nullable=False, comment="Source task ID"),
        sa.Column("image_index", sa.Integer(), nullable=False, comment="Image index in task result"),
        sa.Column("source_url", sa.Text(), nullable=False, comment="Original source URL"),
        sa.Column("stored_url", sa.Text(), nullable=False, comment="Long-term stored URL"),
        sa.Column("file_key", sa.String(512), nullable=True, comment="Object storage key"),
        sa.Column("thumbnail_url", sa.Text(), nullable=True, comment="Thumbnail URL"),
        sa.Column("workflow_id", sa.String(128), nullable=True, comment="Workflow ID"),
        sa.Column("workflow_name", sa.String(255), nullable=True, comment="Workflow display name"),
        sa.Column("model_name", sa.String(128), nullable=True, comment="Model name"),
        sa.Column("parameter_snapshot", sa.JSON(), nullable=True, comment="Task parameter snapshot"),
        sa.Column("created_at", sa.BigInteger(), nullable=False, comment="Created timestamp in ms"),
        sa.PrimaryKeyConstraint("favorite_id", name="favorite_images_pkey"),
        sa.UniqueConstraint("user_id", "task_id", "image_index", name="uq_favorite_images_user_task_image"),
        comment="Image-level user favorites with long-term object storage",
        if_not_exists=True,
    )
    op.create_index("ix_favorite_images_user_created", "favorite_images", ["user_id", "created_at"], if_not_exists=True)
    op.create_index("ix_favorite_images_task_id", "favorite_images", ["task_id"], if_not_exists=True)


def downgrade() -> None:
    op.drop_index("ix_favorite_images_task_id", table_name="favorite_images", if_exists=True)
    op.drop_index("ix_favorite_images_user_created", table_name="favorite_images", if_exists=True)
    op.drop_table("favorite_images", if_exists=True)