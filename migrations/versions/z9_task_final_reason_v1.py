"""add task final_reason and cancellation_source

Revision ID: z9_task_final_reason_v1
Revises: mars002_mars_chat_entities, n1o2p3q4r5s6, v001_add_seat_maps
Create Date: 2026-08-26 12:00:00.000000

说明：统一退款裁决依据。
- final_reason：任务终态原因（user_cancelled/provider_failed/recovery_timeout_failed/submitted_unconfirmed_failed）
- cancellation_source：取消来源（user/system）
两者取代原先按渠道/模型判断是否退款的散落逻辑。
"""

from typing import Sequence, Union

from alembic import op


revision: str = 'z9_task_final_reason_v1'
down_revision: Union[str, Sequence[str], None] = (
    'mars002_mars_chat_entities',
    'n1o2p3q4r5s6',
    'v001_add_seat_maps',
)
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        "ALTER TABLE tasks ADD COLUMN IF NOT EXISTS final_reason VARCHAR(32)"
    )
    op.execute(
        "ALTER TABLE tasks ADD COLUMN IF NOT EXISTS cancellation_source VARCHAR(16)"
    )

    # 历史 failed 任务可安全回填为 provider_failed；历史 cancelled 无法可靠区分用户/系统取消，保持 NULL
    op.execute(
        "UPDATE tasks SET final_reason = 'provider_failed' WHERE status = 'failed' AND final_reason IS NULL"
    )


def downgrade() -> None:
    op.execute("ALTER TABLE tasks DROP COLUMN IF EXISTS final_reason")
    op.execute("ALTER TABLE tasks DROP COLUMN IF EXISTS cancellation_source")
