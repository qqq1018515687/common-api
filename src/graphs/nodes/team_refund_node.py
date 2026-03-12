"""
团队退款节点
负责将金额退还到团队账户（任务失败时）
"""
import logging
import uuid
from datetime import datetime
from langchain_core.runnables import RunnableConfig
from langgraph.runtime import Runtime
from coze_coding_utils.runtime_ctx.context import Context
from graphs.team_balance_state import TeamRefundInput, TeamRefundOutput
from storage.database.db import get_session
from storage.database.shared.model import Teams, TeamMembers, TeamConsumptionRecords

logger = logging.getLogger(__name__)


def team_refund_node(state: TeamRefundInput, config: RunnableConfig, runtime: Runtime[Context]) -> TeamRefundOutput:
    """
    title: 团队退款
    desc: 将金额退还到团队账户（任务失败时），支持部分退款
    integrations: 数据库
    """
    ctx = runtime.context

    try:
        team_id = state.team_id
        user_id = state.user_id
        username = state.username or "未知用户"
        amount = state.amount
        original_record_id = state.original_record_id
        reason = state.reason or "任务退款"

        if not amount or amount <= 0:
            return TeamRefundOutput(
                response_data={
                    "code": 1,
                    "msg": "退款金额必须大于0",
                    "data": {}
                }
            )

        with get_session() as session:
            team = session.query(Teams).filter(Teams.id == team_id).first()
            if not team:
                return TeamRefundOutput(
                    response_data={
                        "code": 1,
                        "msg": f"团队 '{team_id}' 不存在",
                        "data": {}
                    }
                )

            # 可选：验证原消费记录是否存在
            if original_record_id:
                original_record = session.query(TeamConsumptionRecords).filter(
                    TeamConsumptionRecords.id == original_record_id,
                    TeamConsumptionRecords.operation_type == "consumption"
                ).first()
                
                if not original_record:
                    return TeamRefundOutput(
                        response_data={
                            "code": 1,
                            "msg": f"原消费记录 '{original_record_id}' 不存在",
                            "data": {}
                        }
                    )

            # 记录退款前余额
            balance_before = team.balance

            # 增加团队余额（退款）
            team.balance += amount

            # 更新成员累计消费（扣减）
            member = session.query(TeamMembers).filter(
                TeamMembers.team_id == team_id,
                TeamMembers.user_id == user_id
            ).first()
            if member:
                member.total_consumed = max(0, member.total_consumed - amount)

            # 创建退款记录
            record = TeamConsumptionRecords(
                id=str(uuid.uuid4())[:16],
                team_id=team_id,
                user_id=user_id,
                username=username,
                amount=-amount,  # 负数表示退款
                balance_before=balance_before,
                balance_after=team.balance,
                operation_type="refund",
                related_id=original_record_id,
                description=reason,
                extra_data={"refund_reason": reason}
            )
            session.add(record)
            session.commit()

            return TeamRefundOutput(
                response_data={
                    "code": 0,
                    "msg": "退款成功",
                    "data": {
                        "team_id": team_id,
                        "refund_amount": amount,
                        "balance_before": balance_before,
                        "balance_after": team.balance,
                        "record_id": record.id,
                        "original_record_id": original_record_id,
                        "reason": reason
                    }
                }
            )

    except Exception as e:
        logger.error(f"团队退款失败: {e}")
        return TeamRefundOutput(
            response_data={
                "code": 1,
                "msg": f"退款失败: {str(e)}",
                "data": {}
            }
        )
