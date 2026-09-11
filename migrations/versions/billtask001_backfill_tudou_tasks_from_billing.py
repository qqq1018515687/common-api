"""backfill missing Tudou tasks from billing records

Revision ID: billtask001
Revises: mars005_agent_run_items
Create Date: 2026-09-11 00:00:00.000000

The backfill is intentionally irreversible: a generated task may be read or updated
immediately after deployment, so downgrade must not remove recovered user history.
"""

from typing import Sequence, Union

from alembic import op


revision: str = "billtask001"
down_revision: Union[str, Sequence[str], None] = "mars005_agent_run_items"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        """
        WITH migration_window AS (
            SELECT clock_timestamp() AS ended_at
        ),
        tudou_deducts AS (
            SELECT d.*
            FROM billing_records d
            CROSS JOIN migration_window w
            WHERE d.operation_type = 'deduct'
              AND d.status = 'completed'
              AND d.task_id IS NOT NULL
              AND d.task_id <> ''
              AND d.created_at >= TIMESTAMPTZ '2026-09-10 18:54:00+08'
              AND d.created_at <= w.ended_at
              AND (
                  lower(COALESCE(d.extra_data->>'platform', '')) = 'tudou'
                  OR lower(COALESCE(d.extra_data->>'provider', '')) = 'tudou'
                  OR lower(COALESCE(d.extra_data->>'selected_account', '')) = 'tudou'
                  OR lower(COALESCE(d.extra_data->>'model_key', d.extra_data->>'model_name', '')) ~ '_tudou$'
              )
        ),
        terminal AS (
            SELECT
                d.id AS deduct_id,
                (array_agg(r.id ORDER BY r.created_at DESC)
                    FILTER (WHERE r.operation_type = 'refund' AND r.status = 'completed'))[1] AS refund_id,
                (array_agg(r.id ORDER BY r.created_at DESC)
                    FILTER (WHERE r.operation_type = 'settle' AND r.status = 'completed'))[1] AS settle_id,
                max(r.created_at) FILTER (
                    WHERE r.operation_type = 'refund' AND r.status = 'completed'
                ) AS refunded_at,
                max(r.created_at) FILTER (
                    WHERE r.operation_type = 'settle' AND r.status = 'completed'
                ) AS settled_at
            FROM tudou_deducts d
            LEFT JOIN billing_records r ON r.related_id = d.id
            GROUP BY d.id
        )
        INSERT INTO tasks (
            id, user_id, team_id, platform, platform_task_id, type, status,
            created_at, updated_at, status_updated_at, workflow_parameters,
            parameter_snapshot, deduction_result, completed_at, failed_at,
            confirmation_state, connection_mode
        )
        SELECT
            d.task_id,
            d.user_id,
            COALESCE(d.team_id, d.extra_data->>'team_id'),
            'tudou',
            'pending:' || d.task_id,
            CASE lower(COALESCE(d.extra_data->>'task_type', d.extra_data->>'type', 'image'))
                WHEN 'audio' THEN 'audio'
                WHEN 'video' THEN 'video'
                ELSE 'image'
            END,
            CASE WHEN t.refund_id IS NOT NULL THEN 'failed'
                 WHEN t.settle_id IS NOT NULL THEN 'completed'
                 ELSE 'submitted_unconfirmed' END,
            (extract(epoch FROM d.created_at) * 1000)::bigint::text,
            (extract(epoch FROM COALESCE(t.refunded_at, t.settled_at, d.created_at)) * 1000)::bigint::text,
            (extract(epoch FROM COALESCE(t.refunded_at, t.settled_at, d.created_at)) * 1000)::bigint::text,
            COALESCE(d.extra_data, '{}'::json),
            jsonb_strip_nulls(jsonb_build_object(
                'workflowId', COALESCE(d.extra_data->>'workflow_id', d.extra_data->>'workflow'),
                'workflowName', d.extra_data->>'workflow_name',
                'modelName', d.extra_data->>'model_display_name',
                'modelValue', COALESCE(d.extra_data->>'model_key', d.extra_data->>'model_name'),
                'channelLabel', d.extra_data->>'channel_label',
                'billingMetadata', COALESCE(d.extra_data, '{}'::json),
                'confirmationState', CASE WHEN t.refund_id IS NULL AND t.settle_id IS NULL THEN 'pending' ELSE 'confirmed' END,
                'pendingReason', CASE WHEN t.refund_id IS NULL AND t.settle_id IS NULL
                    THEN '账单已扣费，等待生成平台返回任务ID' END
            )),
            jsonb_strip_nulls(jsonb_build_object(
                'billing_record_id', d.id,
                'status', CASE WHEN t.refund_id IS NOT NULL THEN 'refunded'
                               WHEN t.settle_id IS NOT NULL THEN 'settled'
                               ELSE 'deducted' END,
                'amount', d.amount,
                'mode', d.credit_type,
                'refunded_record_id', t.refund_id,
                'settled_record_id', CASE WHEN t.refund_id IS NULL THEN t.settle_id END
            )),
            CASE WHEN t.refund_id IS NULL AND t.settle_id IS NOT NULL
                THEN (extract(epoch FROM t.settled_at) * 1000)::bigint::text END,
            CASE WHEN t.refund_id IS NOT NULL
                THEN (extract(epoch FROM t.refunded_at) * 1000)::bigint::text END,
            CASE WHEN t.refund_id IS NULL AND t.settle_id IS NULL THEN 'pending' ELSE 'confirmed' END,
            'sse'
        FROM tudou_deducts d
        JOIN terminal t ON t.deduct_id = d.id
        WHERE NOT EXISTS (SELECT 1 FROM tasks existing WHERE existing.id = d.task_id)
        ON CONFLICT (id) DO NOTHING
        """
    )


def downgrade() -> None:
    pass
