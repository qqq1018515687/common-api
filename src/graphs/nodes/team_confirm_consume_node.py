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


class TeamConfirmInput(BaseModel):
    """确认消费节点的输入"""
    operation_type: Optional[str] = Field(default=None, description="操作类型")
    record_id: Optional[str] = Field(default=None, description="预扣记录ID")
    user_id: Optional[str] = Field(default=None, description="用户ID")
    actual_amount: Optional[int] = Field(default=None, description="实际消费金额（如果与预扣不同）")
    description: Optional[str] = Field(default=None, description="消费描述")


class TeamConfirmOutput(BaseModel):
    """确认消费节点的输出"""
    response_data: dict = Field(default={}, description="统一响应数据")


def team_confirm_consume_node(state: TeamConfirmInput, config: RunnableConfig, runtime: Runtime[Context]) -> TeamConfirmOutput:
    """
    title: 确认消费
    desc: 确认预扣消费，将pending状态改为confirmed，支持按实际金额结算
    integrations: 数据库
    """
    ctx = runtime.context
    
    db = get_session()
    
    try:
        if not state.record_id:
            return TeamConfirmOutput(
                response_data={"code": 400, "msg": "记录ID不能为空", "data": None}
            )
        
        # 查找预扣记录
        record = db.query(TeamConsumptionRecords).filter(
            TeamConsumptionRecords.id == state.record_id
        ).first()
        
        if not record:
            return TeamConfirmOutput(
                response_data={"code": 404, "msg": "预扣记录不存在", "data": None}
            )
        
        if record.status != "pending":
            return TeamConfirmOutput(
                response_data={"code": 400, "msg": f"记录状态不是pending，当前状态: {record.status}", "data": None}
            )
        
        # 获取团队信息
        team = db.query(Teams).filter(Teams.id == record.team_id).first()
        if not team:
            return TeamConfirmOutput(
                response_data={"code": 404, "msg": "团队不存在", "data": None}
            )
        
        pre_deduct_amount = abs(record.amount)
        actual_amount = state.actual_amount if state.actual_amount is not None else pre_deduct_amount
        
        # 如果实际金额与预扣不同，需要调整余额
        if actual_amount != pre_deduct_amount:
            # 退回差额
            refund_amount = pre_deduct_amount - actual_amount
            if refund_amount > 0:
                team.balance += refund_amount
                team.total_consumed -= refund_amount
            
            # 更新记录金额
            record.amount = -actual_amount
            record.balance_after = team.balance
        
        # 更新记录状态
        record.status = "confirmed"
        if state.description:
            record.description = state.description
        
        team.updated_at = datetime.utcnow()
        record.extra_data = record.extra_data or {}
        record.extra_data["confirmed_at"] = datetime.utcnow().isoformat()
        
        db.commit()
        
        return TeamConfirmOutput(
            response_data={
                "code": 0,
                "msg": "消费确认成功",
                "data": {
                    "record_id": record.id,
                    "pre_deduct_amount": pre_deduct_amount,
                    "actual_amount": actual_amount,
                    "refunded": pre_deduct_amount - actual_amount,
                    "balance": team.balance
                }
            }
        )
    
    except Exception as e:
        db.rollback()
        logger.error(f"确认消费失败: {e}")
        return TeamConfirmOutput(
            response_data={"code": 500, "msg": f"确认失败: {str(e)}", "data": None}
        )
    finally:
        db.close()
