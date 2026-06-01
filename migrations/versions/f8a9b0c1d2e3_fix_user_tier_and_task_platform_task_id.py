"""fix user tier and task platform task id schema

Revision ID: f8a9b0c1d2e3
Revises: e7f8a9b0c1d2
Create Date: 2026-06-01 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "f8a9b0c1d2e3"
down_revision: Union[str, Sequence[str], None] = "e7f8a9b0c1d2"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute("update tasks set platform_task_id = concat('pending:', id) where platform_task_id is null")
    op.alter_column(
        "tasks",
        "platform_task_id",
        existing_type=sa.String(length=100),
        nullable=True,
    )
    op.alter_column(
        "users",
        "tier",
        existing_type=sa.String(length=20),
        type_=sa.String(length=32),
        existing_nullable=True,
        existing_server_default=sa.text("'commercial_registered'::character varying"),
        server_default=sa.text("'commercial_registered'::character varying"),
    )


def downgrade() -> None:
    # Older schema cannot store commercial_* tier values longer than 20 chars.
    op.execute(
        "update users set tier = 'standard' "
        "where tier is not null and length(tier) > 20"
    )
    op.alter_column(
        "users",
        "tier",
        existing_type=sa.String(length=32),
        type_=sa.String(length=20),
        existing_nullable=True,
        existing_server_default=sa.text("'commercial_registered'::character varying"),
        server_default=sa.text("'standard'::character varying"),
    )
    op.execute("update tasks set platform_task_id = concat('pending:', id) where platform_task_id is null")
    op.alter_column(
        "tasks",
        "platform_task_id",
        existing_type=sa.String(length=100),
        nullable=False,
    )
