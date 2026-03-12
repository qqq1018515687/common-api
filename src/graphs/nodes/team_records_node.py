"""
团队消费记录节点
负责查询团队消费记录和统计
"""
import logging
from datetime import datetime, timedelta
from langchain_core.runnables import RunnableConfig
from langgraph.runtime import Runtime
from coze_coding_utils.runtime_ctx.context import Context
from graphs.team_balance_state import TeamRecordsInput, TeamRecordsOutput
from storage.database.db import get_session
from storage.database.shared.model import TeamConsumptionRecords
from sqlalchemy import func

logger = logging.getLogger(__name__)


def team_records_node(state: TeamRecordsInput, config: RunnableConfig, runtime: Runtime[Context]) -> TeamRecordsOutput:
    """
    title: 团队消费记录查询
    desc: 查询团队消费记录、统计信息（支持7天、30天等时间段）
    integrations: 数据库
    """
    ctx = runtime.context

    try:
        operation = state.action

        if operation == "get_records":
            result = _get_records(state)
        elif operation == "get_stats":
            result = _get_stats(state)
        elif operation == "get_member_stats":
            result = _get_member_stats(state)
        else:
            result = {
                "success": False,
                "message": f"未知操作: {operation}",
                "data": {}
            }

        return TeamRecordsOutput(
            response_data={
                "code": 0 if result.get("success") else 1,
                "msg": result.get("message", ""),
                "data": result.get("data", {})
            }
        )

    except Exception as e:
        logger.error(f"查询消费记录失败: {e}")
        return TeamRecordsOutput(
            response_data={
                "code": 1,
                "msg": f"查询失败: {str(e)}",
                "data": {}
            }
        )


def _get_records(state: TeamRecordsInput) -> dict:
    """获取消费记录列表"""
    team_id = state.team_id
    user_id = state.user_id  # 可选：筛选特定用户
    days = state.days or 30
    limit = state.limit or 50

    with get_session() as session:
        start_date = datetime.now() - timedelta(days=days)

        # 构建查询
        query = session.query(TeamConsumptionRecords).filter(
            TeamConsumptionRecords.team_id == team_id,
            TeamConsumptionRecords.created_at >= start_date
        )

        # 如果指定了 user_id，则筛选该用户的记录
        if user_id:
            query = query.filter(TeamConsumptionRecords.user_id == user_id)

        records = query.order_by(
            TeamConsumptionRecords.created_at.desc()
        ).limit(limit).all()

        record_list = [
            {
                "id": r.id,
                "user_id": r.user_id,
                "username": r.username,
                "amount": r.amount,
                "operation_type": r.operation_type,  # consumption/recharge/refund
                "description": r.description,
                "created_at": r.created_at.isoformat() if r.created_at else None
            }
            for r in records
        ]

        return {
            "success": True,
            "message": f"共 {len(record_list)} 条记录",
            "data": {
                "team_id": team_id,
                "user_id": user_id,
                "days": days,
                "records": record_list
            }
        }


def _get_stats(state: TeamRecordsInput) -> dict:
    """获取消费统计"""
    team_id = state.team_id
    days = state.days or 30

    with get_session() as session:
        start_date = datetime.now() - timedelta(days=days)

        # 消费总额（仅consumption）
        consumption_result = session.query(
            func.sum(TeamConsumptionRecords.amount)
        ).filter(
            TeamConsumptionRecords.team_id == team_id,
            TeamConsumptionRecords.operation_type == "consumption",
            TeamConsumptionRecords.created_at >= start_date
        ).scalar()

        # 充值总额（仅recharge）
        recharge_result = session.query(
            func.sum(TeamConsumptionRecords.amount)
        ).filter(
            TeamConsumptionRecords.team_id == team_id,
            TeamConsumptionRecords.operation_type == "recharge",
            TeamConsumptionRecords.created_at >= start_date
        ).scalar()

        consumption_total = consumption_result or 0
        recharge_total = abs(recharge_result or 0)  # 转为正数

        return {
            "success": True,
            "message": "统计成功",
            "data": {
                "team_id": team_id,
                "days": days,
                "consumption": consumption_total,
                "recharge": recharge_total,
                "record_count": session.query(TeamConsumptionRecords).filter(
                    TeamConsumptionRecords.team_id == team_id,
                    TeamConsumptionRecords.created_at >= start_date
                ).count()
            }
        }


def _get_member_stats(state: TeamRecordsInput) -> dict:
    """获取成员消费统计"""
    team_id = state.team_id
    days = state.days or 30

    with get_session() as session:
        start_date = datetime.now() - timedelta(days=days)

        # 按用户分组统计消费
        results = session.query(
            TeamConsumptionRecords.user_id,
            TeamConsumptionRecords.username,
            func.sum(TeamConsumptionRecords.amount).label('total')
        ).filter(
            TeamConsumptionRecords.team_id == team_id,
            TeamConsumptionRecords.operation_type == "consumption",
            TeamConsumptionRecords.created_at >= start_date
        ).group_by(
            TeamConsumptionRecords.user_id,
            TeamConsumptionRecords.username
        ).order_by(
            func.sum(TeamConsumptionRecords.amount).desc()
        ).all()

        member_stats = [
            {
                "user_id": r.user_id,
                "username": r.username,
                "consumption": r.total or 0
            }
            for r in results
        ]

        return {
            "success": True,
            "message": f"共 {len(member_stats)} 位成员有消费记录",
            "data": {
                "team_id": team_id,
                "days": days,
                "members": member_stats
            }
        }
