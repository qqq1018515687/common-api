"""repair resultless completed billing task projections

Revision ID: billtask002
Revises: marsquota002
Create Date: 2026-09-17 10:30:00.000000

Billing settlement proves only that charging finished. It does not prove that the
generation provider returned a task id or a result, so these rows must not remain
in completed statistics.
"""

from typing import Sequence, Union

from alembic import op


revision: str = "billtask002"
down_revision: Union[str, Sequence[str], None] = "marsquota002"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        """
        UPDATE tasks
        SET status = 'failed',
            error = COALESCE(
                NULLIF(error, ''),
                '账单已结算，但生成平台任务ID和结果未成功写入，需人工核查'
            ),
            user_friendly_message = COALESCE(
                NULLIF(user_friendly_message, ''),
                '任务结果保存失败，请联系管理员核查'
            ),
            final_reason = 'persistence_failed',
            failed_at = COALESCE(failed_at, completed_at, status_updated_at, updated_at, created_at),
            completed_at = NULL,
            status_updated_at = COALESCE(completed_at, status_updated_at, updated_at, created_at),
            updated_at = COALESCE(completed_at, status_updated_at, updated_at, created_at),
            confirmation_state = 'confirmed',
            parameter_snapshot = ((
                COALESCE(parameter_snapshot::jsonb, '{}'::jsonb)
                - 'pendingReason'
                - 'pendingSince'
            ) || jsonb_build_object(
                'confirmationState', 'confirmed',
                'billingProjectionRepair', true,
                'billingProjectionRepairReason', 'settled_without_provider_task_or_result'
            ))::json,
            elapsed_time_seconds = CASE
                WHEN COALESCE(completed_at, status_updated_at, updated_at, created_at) ~ '^[0-9]+$'
                 AND COALESCE(started_at, created_at) ~ '^[0-9]+$'
                THEN LEAST(
                    86400,
                    GREATEST(
                        0,
                        (
                            COALESCE(completed_at, status_updated_at, updated_at, created_at)::bigint
                            - COALESCE(started_at, created_at)::bigint
                        ) / 1000
                    )
                )::integer
                ELSE 0
            END
        WHERE status = 'completed'
          AND platform_task_id LIKE 'pending:%'
          AND COALESCE((parameter_snapshot->>'billingProjection')::boolean, false) = true
          AND result IS NULL
          AND result_fallback IS NULL
        """
    )


def downgrade() -> None:
    # The original rows were false positives. Restoring them to completed would
    # knowingly corrupt success statistics again, so this data repair is irreversible.
    pass
