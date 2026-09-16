"""backfill legacy Mars special quota usage

Revision ID: marsquota002
Revises: marsquota001
Create Date: 2026-09-16 15:00:00.000000
"""

from typing import Sequence, Union

from alembic import op


revision: str = "marsquota002"
down_revision: Union[str, Sequence[str], None] = "marsquota001"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute(
        """
        INSERT INTO mars_special_quota_transactions (
            id, idempotency_key, user_id, task_id, transaction_type,
            source, amount, status, quota_date, extra_data, created_at, updated_at
        )
        SELECT
            'legacy:' || tasks.id,
            'mars_special:usage:' || tasks.id,
            tasks.user_id,
            tasks.id,
            'usage',
            'legacy',
            0,
            CASE
                WHEN tasks.status = 'completed' THEN 'consumed'
                WHEN tasks.status IN ('failed', 'cancelled') THEN 'released'
                ELSE 'reserved'
            END,
            NULL,
            json_build_object('platform', 'local_sub2api', 'legacy', true),
            now(),
            now()
        FROM tasks
        WHERE tasks.platform = 'local_sub2api'
        ON CONFLICT DO NOTHING
        """
    )


def downgrade() -> None:
    op.execute(
        "DELETE FROM mars_special_quota_transactions "
        "WHERE source = 'legacy' AND COALESCE(extra_data->>'legacy', 'false') = 'true'"
    )
