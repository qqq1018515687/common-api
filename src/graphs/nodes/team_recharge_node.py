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


class TeamRechargeInput(BaseModel):
    """团队充值节点的输入"""
    operation_type: Optional[str] = Field(default=None, description="操作类型")
    user_id: Optional[str] = Field(default=None, description="操作用户ID")
    amount: Optional[float] = Field(default=None, description="充值金额")
    description: Optional[str] = Field(default=None, description="充值描述")


class TeamRechargeOutput(BaseModel):
    """团队充值节点的输出"""
    response_data: dict = Field(default={}, description="统一响应数据")


def team_recharge_node(state: TeamRechargeInput, config: RunnableConfig, runtime: Runtime[Context]) -> TeamRechargeOutput:
    """
    title: 团队充值
    desc: 为团队充值余额
    integrations: 数据库
    """
    ctx = runtime.context
    
    operation_type = state.operation_type
    db = get_session()
    
    try:
        assert_gold_amount_schema(db)

        if not state.user_id:
            return TeamRechargeOutput(
                response_data={"code": 400, "msg": "用户ID不能为空", "data": None}
            )
        
        if state.amount is None:
            return TeamRechargeOutput(
                response_data={"code": 400, "msg": "充值金额必须大于0", "data": None}
            )
        try:
            amount = normalize_gold_amount(state.amount)
        except ValueError as exc:
            return TeamRechargeOutput(
                response_data={"code": 400, "msg": str(exc), "data": None}
            )
        
        # 通过 users 表查找用户及其团队
        user = db.query(Users).filter(Users.user_id == state.user_id).first()
        if not user:
            return TeamRechargeOutput(
                response_data={"code": 404, "msg": "用户不存在", "data": None}
            )
        
        if not user.team_id:
            return TeamRechargeOutput(
                response_data={"code": 404, "msg": "用户未加入任何团队", "data": None}
            )
        
        # 只有管理员可以充值
        if user.role != "admin":
            return TeamRechargeOutput(
                response_data={"code": 403, "msg": "只有管理员可以充值", "data": None}
            )
        
        # 更新团队余额
        team = db.query(Teams).filter(Teams.id == user.team_id).first()
        balance_before = team.balance
        team.balance += amount
        team.updated_at = datetime.utcnow()
        
        # 记录充值
        record_id = str(uuid.uuid4())
        record = TeamConsumptionRecords(
            id=record_id,
            team_id=team.id,
            user_id=state.user_id,
            username=user.username,
            operation_type="recharge",
            amount=amount,
            balance_before=balance_before,
            balance_after=team.balance,
            description=state.description or "团队充值"
        )
        db.add(record)
        db.commit()
        
        return TeamRechargeOutput(
            response_data={
                "code": 0,
                "msg": "充值成功",
                "data": {
                    "balance": gold_amount_to_number(team.balance),
                    "amount": gold_amount_to_number(amount)
                }
            }
        )
    
    except Exception as e:
        db.rollback()
        logger.error(f"团队充值失败: {e}")
        return TeamRechargeOutput(
            response_data={"code": 500, "msg": f"充值失败: {str(e)}", "data": None}
        )
    finally:
        db.close()
