import os
import json
import logging
import uuid
from typing import Optional
from langchain_core.runnables import RunnableConfig
from langgraph.runtime import Runtime
from coze_coding_utils.runtime_ctx.context import Context
from pydantic import BaseModel, Field
from datetime import datetime

from storage.database.db import get_session
from storage.database.shared.model import Teams, Users, TeamConsumptionRecords

logger = logging.getLogger(__name__)


class TeamRefundInput(BaseModel):
    """团队退款节点的输入"""
    operation_type: Optional[str] = Field(default=None, description="操作类型")
    user_id: Optional[str] = Field(default=None, description="用户ID")
    original_record_id: Optional[str] = Field(default=None, description="原消费记录ID")
    reason: Optional[str] = Field(default=None, description="退款原因")


class TeamRefundOutput(BaseModel):
    """团队退款节点的输出"""
    response_data: dict = Field(default={}, description="统一响应数据")


def team_refund_node(state: TeamRefundInput, config: RunnableConfig, runtime: Runtime[Context]) -> TeamRefundOutput:
    """
    title: 团队退款
    desc: 任务失败时退还团队余额
    integrations: 数据库
    """
    ctx = runtime.context
    
    operation_type = state.operation_type
    db = get_session()
    
    try:
        if not state.user_id:
            return TeamRefundOutput(
                response_data={"code": 400, "msg": "用户ID不能为空", "data": None}
            )
        
        if not state.original_record_id:
            return TeamRefundOutput(
                response_data={"code": 400, "msg": "原消费记录ID不能为空", "data": None}
            )
        
        # 通过 users 表查找用户及其团队
        user = db.query(Users).filter(Users.user_id == state.user_id).first()
        if not user:
            return TeamRefundOutput(
                response_data={"code": 404, "msg": "用户不存在", "data": None}
            )
        
        if not user.team_id:
            return TeamRefundOutput(
                response_data={"code": 404, "msg": "用户未加入任何团队", "data": None}
            )
        
        # 查找原消费记录
        original_record = db.query(TeamConsumptionRecords).filter(
            TeamConsumptionRecords.id == state.original_record_id,
            TeamConsumptionRecords.operation_type == "consumption"
        ).first()
        
        if not original_record:
            return TeamRefundOutput(
                response_data={"code": 404, "msg": "原消费记录不存在", "data": None}
            )
        
        # 验证用户是否属于同一团队
        if original_record.team_id != user.team_id:
            return TeamRefundOutput(
                response_data={"code": 403, "msg": "无权操作该记录", "data": None}
            )
        
        # 计算退款金额（原消费金额的绝对值）
        refund_amount = abs(original_record.amount)
        
        # 更新团队余额
        team = db.query(Teams).filter(Teams.id == user.team_id).first()
        balance_before = team.balance
        team.balance += refund_amount
        team.total_consumed -= refund_amount
        team.updated_at = datetime.utcnow()
        
        # 记录退款
        record_id = str(uuid.uuid4())
        record = TeamConsumptionRecords(
            id=record_id,
            team_id=team.id,
            user_id=state.user_id,
            username=user.username,
            operation_type="refund",
            amount=refund_amount,  # 退款为正数
            balance_before=balance_before,
            balance_after=team.balance,
            description=f"退款 - {state.reason or '任务失败'}",
            related_id=state.original_record_id
        )
        db.add(record)
        db.commit()
        
        return TeamRefundOutput(
            response_data={
                "code": 0,
                "msg": "退款成功",
                "data": {
                    "balance": team.balance,
                    "refund_amount": refund_amount,
                    "record_id": record_id
                }
            }
        )
    
    except Exception as e:
        db.rollback()
        logger.error(f"团队退款失败: {e}")
        return TeamRefundOutput(
            response_data={"code": 500, "msg": f"退款失败: {str(e)}", "data": None}
        )
    finally:
        db.close()
