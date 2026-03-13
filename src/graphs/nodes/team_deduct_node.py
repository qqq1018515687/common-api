import os
import json
import logging
import uuid
from typing import Optional
from jinja2 import Template
from langchain_core.runnables import RunnableConfig
from langgraph.runtime import Runtime
from coze_coding_utils.runtime_ctx.context import Context
from pydantic import BaseModel, Field
from datetime import datetime

from storage.database.db import get_session
from storage.database.shared.model import Teams, TeamMembers, TeamConsumptionRecords

logger = logging.getLogger(__name__)


class TeamDeductInput(BaseModel):
    """团队扣费节点的输入"""
    operation_type: Optional[str] = Field(default=None, description="操作类型")
    user_id: Optional[str] = Field(default=None, description="用户ID")
    amount: Optional[int] = Field(default=None, description="扣费金额")
    description: Optional[str] = Field(default=None, description="扣费描述")


class TeamDeductOutput(BaseModel):
    """团队扣费节点的输出"""
    response_data: dict = Field(default={}, description="统一响应数据")


def team_deduct_node(state: TeamDeductInput, config: RunnableConfig, runtime: Runtime[Context]) -> TeamDeductOutput:
    """
    title: 团队扣费
    desc: 从团队余额扣费
    integrations: 数据库
    """
    ctx = runtime.context
    
    operation_type = state.operation_type
    db = get_session()
    
    try:
        if not state.user_id:
            return TeamDeductOutput(
                response_data={"code": 400, "msg": "用户ID不能为空", "data": None}
            )
        
        if not state.amount or state.amount <= 0:
            return TeamDeductOutput(
                response_data={"code": 400, "msg": "扣费金额必须大于0", "data": None}
            )
        
        # 查找用户所属团队
        member = db.query(TeamMembers).filter(TeamMembers.user_id == state.user_id).first()
        if not member:
            return TeamDeductOutput(
                response_data={"code": 404, "msg": "用户未加入任何团队", "data": None}
            )
        
        # 检查团队余额
        team = db.query(Teams).filter(Teams.id == member.team_id).first()
        if team.balance < state.amount:
            return TeamDeductOutput(
                response_data={"code": 400, "msg": "团队余额不足", "data": None}
            )
        
        # 扣除余额
        balance_before = team.balance
        team.balance -= state.amount
        team.total_consumed += state.amount
        team.updated_at = datetime.utcnow()
        
        # 更新成员累计消费
        member.total_consumed += state.amount
        member.updated_at = datetime.utcnow()
        
        # 记录消费
        record_id = str(uuid.uuid4())
        record = TeamConsumptionRecords(
            id=record_id,
            team_id=team.id,
            user_id=state.user_id,
            username=member.username,
            operation_type="consumption",
            amount=-state.amount,  # 消费为负数
            balance_before=balance_before,
            balance_after=team.balance,
            description=state.description or "团队消费"
        )
        db.add(record)
        db.commit()
        
        return TeamDeductOutput(
            response_data={
                "code": 0,
                "msg": "扣费成功",
                "data": {
                    "balance": team.balance,
                    "amount": state.amount,
                    "record_id": record_id
                }
            }
        )
    
    except Exception as e:
        db.rollback()
        logger.error(f"团队扣费失败: {e}")
        return TeamDeductOutput(
            response_data={"code": 500, "msg": f"扣费失败: {str(e)}", "data": None}
        )
    finally:
        db.close()
