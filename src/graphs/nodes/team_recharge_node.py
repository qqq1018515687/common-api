"""
团队充值节点
负责给团队账户充值
"""
import logging
import uuid
from datetime import datetime
from langchain_core.runnables import RunnableConfig
from langgraph.runtime import Runtime
from coze_coding_utils.runtime_ctx.context import Context
from graphs.team_balance_state import TeamRechargeInput, TeamRechargeOutput
from storage.database.db import get_session
from storage.database.shared.model import Teams, TeamConsumptionRecords

logger = logging.getLogger(__name__)


def team_recharge_node(state: TeamRechargeInput, config: RunnableConfig, runtime: Runtime[Context]) -> TeamRechargeOutput:
    """
    title: 团队充值
    desc: 给团队账户充值余额
    integrations: 数据库
    """
    ctx = runtime.context

    try:
        team_id = state.team_id
        amount = state.amount
        description = state.description or "充值"
        operator_id = state.operator_user_id or "system"

        if not amount or amount <= 0:
            return TeamRechargeOutput(
                response_data={
                    "code": 1,
                    "msg": "充值金额必须大于0",
                    "data": {}
                }
            )

        with get_session() as session:
            team = session.query(Teams).filter(Teams.id == team_id).first()
            if not team:
                return TeamRechargeOutput(
                    response_data={
                        "code": 1,
                        "msg": f"团队 '{team_id}' 不存在",
                        "data": {}
                    }
                )

            # 记录充值前余额
            balance_before = team.balance

            # 增加余额
            team.balance += amount

            # 创建充值记录
            record = TeamConsumptionRecords(
                id=str(uuid.uuid4())[:16],
                team_id=team_id,
                user_id=operator_id,
                username="管理员",
                amount=-amount,  # 负数表示充值
                balance_before=balance_before,
                balance_after=team.balance,
                operation_type="recharge",
                description=description
            )
            session.add(record)
            session.commit()

            return TeamRechargeOutput(
                response_data={
                    "code": 0,
                    "msg": "充值成功",
                    "data": {
                        "team_id": team_id,
                        "recharge_amount": amount,
                        "balance_before": balance_before,
                        "balance_after": team.balance,
                        "record_id": record.id
                    }
                }
            )

    except Exception as e:
        logger.error(f"团队充值失败: {e}")
        return TeamRechargeOutput(
            response_data={
                "code": 1,
                "msg": f"充值失败: {str(e)}",
                "data": {}
            }
        )
