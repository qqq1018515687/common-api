import os
import json
import logging
from typing import Optional
from langchain_core.runnables import RunnableConfig
from langgraph.runtime import Runtime
from coze_coding_utils.runtime_ctx.context import Context
from pydantic import BaseModel, Field
from datetime import datetime

from storage.database.db import get_session
from storage.database.shared.model import Teams, Users, TeamConsumptionRecords

logger = logging.getLogger(__name__)


class TeamCancelInput(BaseModel):
    """取消预扣节点的输入"""
    operation_type: Optional[str] = Field(default=None, description="操作类型")
    record_id: Optional[str] = Field(default=None, description="预扣记录ID")
    user_id: Optional[str] = Field(default=None, description="用户ID")
    reason: Optional[str] = Field(default=None, description="取消原因")


class TeamCancelOutput(BaseModel):
    """取消预扣节点的输出"""
    response_data: dict = Field(default={}, description="统一响应数据")


def team_cancel_deduct_node(state: TeamCancelInput, config: RunnableConfig, runtime: Runtime[Context]) -> TeamCancelOutput:
    """
    title: 取消预扣
    desc: 取消预扣消费，退回余额，将pending记录改为cancelled
    integrations: 数据库
    """
    ctx = runtime.context
    
    db = get_session()
    
    try:
        if not state.record_id:
            return TeamCancelOutput(
                response_data={"code": 400, "msg": "记录ID不能为空", "data": None}
            )
        
        # 查找预扣记录
        record = db.query(TeamConsumptionRecords).filter(
            TeamConsumptionRecords.id == state.record_id
        ).first()
        
        if not record:
            return TeamCancelOutput(
                response_data={"code": 404, "msg": "预扣记录不存在", "data": None}
            )
        
        if record.status != "pending":
            return TeamCancelOutput(
                response_data={"code": 400, "msg": f"记录状态不是pending，当前状态: {record.status}", "data": None}
            )
        
        # 获取团队信息
        team = db.query(Teams).filter(Teams.id == record.team_id).first()
        if not team:
            return TeamCancelOutput(
                response_data={"code": 404, "msg": "团队不存在", "data": None}
            )
        
        # 退回余额
        refund_amount = abs(record.amount)
        team.balance += refund_amount
        team.total_consumed -= refund_amount
        team.updated_at = datetime.utcnow()
        
        # 更新记录状态
        record.status = "cancelled"
        record.extra_data = record.extra_data or {}
        record.extra_data["cancelled_at"] = datetime.utcnow().isoformat()
        record.extra_data["cancel_reason"] = state.reason or "任务取消/失败"
        
        db.commit()
        
        return TeamCancelOutput(
            response_data={
                "code": 0,
                "msg": "预扣已取消，余额已退回",
                "data": {
                    "record_id": record.id,
                    "refunded_amount": refund_amount,
                    "balance": team.balance
                }
            }
        )
    
    except Exception as e:
        db.rollback()
        logger.error(f"取消预扣失败: {e}")
        return TeamCancelOutput(
            response_data={"code": 500, "msg": f"取消失败: {str(e)}", "data": None}
        )
    finally:
        db.close()
