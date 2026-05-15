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
from storage.database.amounts import assert_gold_amount_schema, gold_amount_to_number, normalize_gold_amount

logger = logging.getLogger(__name__)


class TeamDeductInput(BaseModel):
    """团队扣费节点的输入"""
    operation_type: Optional[str] = Field(default=None, description="操作类型")
    user_id: Optional[str] = Field(default=None, description="用户ID")
    amount: Optional[float] = Field(default=None, description="扣费金额")
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
        assert_gold_amount_schema(db)

        if not state.user_id:
            return TeamDeductOutput(
                response_data={"code": 400, "msg": "用户ID不能为空", "data": None}
            )
        
        if state.amount is None:
            return TeamDeductOutput(
                response_data={"code": 400, "msg": "扣费金额必须大于0", "data": None}
            )
        try:
            amount = normalize_gold_amount(state.amount)
        except ValueError as exc:
            return TeamDeductOutput(
                response_data={"code": 400, "msg": str(exc), "data": None}
            )
        
        # 通过 users 表查找用户及其团队
        user = db.query(Users).filter(Users.user_id == state.user_id).first()
        if not user:
            return TeamDeductOutput(
                response_data={"code": 404, "msg": "用户不存在", "data": None}
            )
        
        if not user.team_id:
            return TeamDeductOutput(
                response_data={"code": 404, "msg": "用户未加入任何团队", "data": None}
            )
        
        # 检查团队余额
        team = db.query(Teams).filter(Teams.id == user.team_id).first()
        if team.balance < amount:
            return TeamDeductOutput(
                response_data={"code": 400, "msg": "团队余额不足", "data": None}
            )
        
        # 扣除余额
        balance_before = team.balance
        team.balance -= amount
        team.total_consumed += amount
        team.updated_at = datetime.utcnow()
        
        # 记录消费
        record_id = str(uuid.uuid4())
        record = TeamConsumptionRecords(
            id=record_id,
            team_id=team.id,
            user_id=state.user_id,
            username=user.username,
            operation_type="consumption",
            amount=-amount,  # 消费为负数
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
                    "balance": gold_amount_to_number(team.balance),
                    "amount": gold_amount_to_number(amount),
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
