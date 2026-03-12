"""
团队扣费节点
负责从团队账户扣费（任务执行时）
"""
import logging
import uuid
from datetime import datetime
from langchain_core.runnables import RunnableConfig
from langgraph.runtime import Runtime
from coze_coding_utils.runtime_ctx.context import Context
from graphs.team_balance_state import TeamDeductInput, TeamDeductOutput
from storage.database.db import get_session
from storage.database.shared.model import Teams, TeamMembers, TeamConsumptionRecords

logger = logging.getLogger(__name__)


def team_deduct_node(state: TeamDeductInput, config: RunnableConfig, runtime: Runtime[Context]) -> TeamDeductOutput:
    """
    title: 团队扣费
    desc: 从团队账户扣减余额（任务执行时消费）
    integrations: 数据库
    """
    ctx = runtime.context

    try:
        team_id = state.team_id
        user_id = state.user_id
        username = state.username or "未知用户"
        amount = state.amount
        task_id = state.task_id
        description = state.description or f"任务消费: {task_id}"

        if not amount or amount <= 0:
            return TeamDeductOutput(
                response_data={
                    "code": 1,
                    "msg": "扣费金额必须大于0",
                    "data": {"balance": None}
                }
            )

        with get_session() as session:
            team = session.query(Teams).filter(Teams.id == team_id).first()
            if not team:
                return TeamDeductOutput(
                    response_data={
                        "code": 1,
                        "msg": f"团队 '{team_id}' 不存在",
                        "data": {"balance": None}
                    }
                )

            # 检查余额
            if team.balance < amount:
                return TeamDeductOutput(
                    response_data={
                        "code": 1,
                        "msg": f"余额不足，当前余额: {team.balance}，需要: {amount}",
                        "data": {"balance": team.balance}
                    }
                )

            # 记录扣费前余额
            balance_before = team.balance

            # 扣减团队余额
            team.balance -= amount
            team.total_consumed += amount

            # 更新成员累计消费
            member = session.query(TeamMembers).filter(
                TeamMembers.team_id == team_id,
                TeamMembers.user_id == user_id
            ).first()
            if member:
                member.total_consumed += amount

            # 创建消费记录
            record = TeamConsumptionRecords(
                id=str(uuid.uuid4())[:16],
                team_id=team_id,
                user_id=user_id,
                username=username,
                amount=amount,  # 正数表示消费
                balance_before=balance_before,
                balance_after=team.balance,
                operation_type="consumption",
                related_id=task_id,
                description=description
            )
            session.add(record)
            session.commit()

            return TeamDeductOutput(
                response_data={
                    "code": 0,
                    "msg": "扣费成功",
                    "data": {
                        "team_id": team_id,
                        "deduct_amount": amount,
                        "balance_before": balance_before,
                        "balance_after": team.balance,
                        "record_id": record.id,
                        "task_id": task_id
                    }
                }
            )

    except Exception as e:
        logger.error(f"团队扣费失败: {e}")
        return TeamDeductOutput(
            response_data={
                "code": 1,
                "msg": f"扣费失败: {str(e)}",
                "data": {"balance": None}
            }
        )
