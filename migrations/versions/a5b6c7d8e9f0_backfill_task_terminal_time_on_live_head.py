"""backfill task terminal time columns (failed_at/cancelled_at) on live head

背景：u7v8w9x0y1z2 新增 failed_at/cancelled_at/status_updated_at 时间字段时未回填历史数据，
导致存量 failed/cancelled 任务的终态时间列全部为空：
  - failed/error 1505/1506 条 failed_at 为空
  - cancelled 全部 27 条 cancelled_at 为空
叠加任务列表"状态筛选 -> 时间维度 = failed_at"只统计已回填行，出现
"统计按 created_at 显示 N 条失败，点进列表(按 failed_at 过滤)却为空"。

本迁移：
1) 回填 failed_at / cancelled_at（取 status_updated_at -> completed_at -> created_at，
   其中 completed_at 是旧收口逻辑写入的"终态收口时间"，语义上最贴近真实失败/取消时刻）；
2) 终态时间列唯一化：failed/error 清 completed_at/cancelled_at，
   cancelled 清 completed_at/failed_at，completed 清 failed_at/cancelled_at，
   避免同一任务两个终态时间列并存导致统计把失败任务的 completed_at 误算进完成口径；
3) 顺带回填 completed 状态缺 completed_at 的历史数据；
4) 清空 failed/cancelled 任务的 completed_at 前，先把耗时固化到
   elapsed_time_seconds（completed_at - started_at，钳制 0~86400），
   避免管理后台"总耗时"列因此退化为空。

downgrade 说明：数据迁移不可逆，downgrade 仅 pass，不修改表结构；线上历史数据回填后
若要还原"失败任务的完成时间展示"，重新部署旧版本即可，不会造成表结构或查询不可用。

Revision ID: a5b6c7d8e9f0
Revises: b3a0aa0bb1c2
Create Date: 2026-08-20 12:00:00.000000
"""

from typing import Sequence, Union

from alembic import op


revision: str = "a5b6c7d8e9f0"
down_revision: Union[str, Sequence[str], None] = "b3a0aa0bb1c2"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # 1) 回填 failed_at / cancelled_at：
    #    优先 status_updated_at（真实状态变更时刻），其次 completed_at（旧收口写入的终态时间），
    #    最后回退 created_at（保证终态任务必有时间）。
    op.execute(
        """
        UPDATE tasks
        SET failed_at = COALESCE(NULLIF(status_updated_at, ''), completed_at, created_at)
        WHERE status IN ('failed', 'error')
          AND (failed_at IS NULL OR failed_at = '')
        """
    )
    op.execute(
        """
        UPDATE tasks
        SET cancelled_at = COALESCE(NULLIF(status_updated_at, ''), completed_at, created_at)
        WHERE status = 'cancelled'
          AND (cancelled_at IS NULL OR cancelled_at = '')
        """
    )
    # 2) 顺带回填 completed 缺 completed_at 的历史数据
    op.execute(
        """
        UPDATE tasks
        SET completed_at = created_at
        WHERE status = 'completed' AND completed_at IS NULL
        """
    )
    # 2.5) 回填 elapsed_time_seconds：在清空 failed/cancelled 任务的 completed_at 之前，
    #      先按（completed_at - started_at）把耗时固化到 elapsed_time_seconds，
    #      避免"清掉 completed_at 后管理后台总耗时列从有效值退化为 -"。
    #      口径与 update_task/calculate_elapsed_time 保持一致：>=0 且钳制到 86400。
    op.execute(
        """
        UPDATE tasks
        SET elapsed_time_seconds = LEAST(
                GREATEST(
                    0,
                    (CAST(completed_at AS BIGINT) - COALESCE(CAST(started_at AS BIGINT), CAST(created_at AS BIGINT))) / 1000
                ),
                86400
            )
        WHERE status IN ('failed', 'error', 'cancelled')
          AND (elapsed_time_seconds IS NULL OR elapsed_time_seconds <= 0)
          AND completed_at IS NOT NULL
          AND CAST(completed_at AS BIGINT) >= COALESCE(CAST(started_at AS BIGINT), CAST(created_at AS BIGINT))
        """
    )
    # 3) 终态时间列唯一化：每个终态任务只保留其对应的终态时间列，
    #    避免失败任务的 completed_at 残留被"完成口径"统计误算。
    op.execute(
        """
        UPDATE tasks
        SET completed_at = NULL, cancelled_at = NULL
        WHERE status IN ('failed', 'error')
        """
    )
    op.execute(
        """
        UPDATE tasks
        SET completed_at = NULL, failed_at = NULL
        WHERE status = 'cancelled'
        """
    )
    op.execute(
        """
        UPDATE tasks
        SET failed_at = NULL, cancelled_at = NULL
        WHERE status = 'completed'
        """
    )


def downgrade() -> None:
    pass