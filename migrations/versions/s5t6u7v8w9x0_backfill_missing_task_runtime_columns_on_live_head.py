"""backfill missing task runtime columns on live head

Revision ID: s5t6u7v8w9x0
Revises: l5m6n7o8p9q0, r4s5t6u7v8w9
Create Date: 2026-08-03 11:55:00.000000
"""

from typing import Sequence, Union

from alembic import op


revision: str = 's5t6u7v8w9x0'
down_revision: Union[str, Sequence[str], None] = ('l5m6n7o8p9q0', 'r4s5t6u7v8w9')
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("ALTER TABLE tasks ADD COLUMN IF NOT EXISTS started_at VARCHAR(20)")
    op.execute("ALTER TABLE tasks ADD COLUMN IF NOT EXISTS elapsed_time_seconds INTEGER DEFAULT 0")
    op.execute("ALTER TABLE tasks ADD COLUMN IF NOT EXISTS confirmation_state VARCHAR(20) DEFAULT 'none'")
    op.execute("ALTER TABLE tasks ADD COLUMN IF NOT EXISTS deleted_image_urls JSON")
    op.execute("ALTER TABLE tasks ADD COLUMN IF NOT EXISTS result_fallback JSON")
    op.execute("ALTER TABLE tasks ADD COLUMN IF NOT EXISTS persistence_status VARCHAR(20)")
    op.execute("ALTER TABLE tasks ADD COLUMN IF NOT EXISTS persistence_error TEXT")

    op.execute("UPDATE tasks SET started_at = created_at WHERE started_at IS NULL")
    op.execute("UPDATE tasks SET elapsed_time_seconds = 0 WHERE elapsed_time_seconds IS NULL")
    op.execute(
        """
        UPDATE tasks
        SET confirmation_state = CASE
            WHEN status = 'running'
             AND (
                (parameter_snapshot->>'confirmationState') = 'pending'
                OR COALESCE(user_friendly_message, '') LIKE '%结果确认中%'
             ) THEN 'pending'
            WHEN status IN ('completed', 'failed', 'cancelled') THEN 'confirmed'
            ELSE 'none'
        END
        WHERE confirmation_state IS NULL
        """
    )


def downgrade() -> None:
    pass
