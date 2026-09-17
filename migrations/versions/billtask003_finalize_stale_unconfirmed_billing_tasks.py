"""finalize stale unconfirmed billing task projections

Revision ID: billtask003
Revises: billtask002
Create Date: 2026-09-17 11:30:00.000000

Runtime recovery handles new rows. This migration closes historical rows that
already exceeded the two-minute provider confirmation window.
"""

from typing import Sequence, Union

from alembic import op


revision: str = "billtask003"
down_revision: Union[str, Sequence[str], None] = "billtask002"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        """
        UPDATE tasks
        SET status = 'failed',
            final_reason = 'submitted_unconfirmed_failed',
            confirmation_state = 'confirmed',
            cancellation_source = 'system',
            error = COALESCE(
                NULLIF(error, ''),
                '提交后未取得真实平台任务ID或生成结果，任务无法继续查询'
            ),
            user_friendly_message = COALESCE(
                NULLIF(user_friendly_message, ''),
                '任务提交未确认，任务已结束，请联系管理员处理费用'
            ),
            failed_at = COALESCE(
                failed_at,
                CASE
                    WHEN created_at ~ '^[0-9]+$' THEN (created_at::bigint + 120000)::text
                    ELSE updated_at
                END
            ),
            completed_at = NULL,
            cancelled_at = NULL,
            status_updated_at = COALESCE(
                CASE
                    WHEN created_at ~ '^[0-9]+$' THEN (created_at::bigint + 120000)::text
                    ELSE updated_at
                END,
                status_updated_at
            ),
            updated_at = COALESCE(
                CASE
                    WHEN created_at ~ '^[0-9]+$' THEN (created_at::bigint + 120000)::text
                    ELSE updated_at
                END,
                updated_at
            ),
            elapsed_time_seconds = 120,
            parameter_snapshot = ((
                COALESCE(parameter_snapshot::jsonb, '{}'::jsonb)
                - 'pendingReason'
                - 'pendingSince'
            ) || jsonb_build_object(
                'confirmationState', 'confirmed',
                'submittedUnconfirmedRepair', true,
                'submittedUnconfirmedRepairReason', 'missing_provider_task_id_and_result'
            ))::json
        WHERE status = 'submitted_unconfirmed'
          AND platform_task_id LIKE 'pending:%'
          AND result IS NULL
          AND result_fallback IS NULL
          AND created_at ~ '^[0-9]+$'
          AND created_at::bigint <= (EXTRACT(EPOCH FROM clock_timestamp()) * 1000)::bigint - 120000
        """
    )


def downgrade() -> None:
    # Restoring these rows would recreate indefinitely stuck tasks.
    pass
