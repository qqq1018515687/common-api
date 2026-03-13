import os
import json
import logging
from typing import Optional
from langchain_core.runnables import RunnableConfig
from langgraph.runtime import Runtime
from coze_coding_utils.runtime_ctx.context import Context
from pydantic import BaseModel, Field
from datetime import datetime, timedelta

from storage.database.db import get_session
from storage.database.shared.model import Teams, Users, TeamConsumptionRecords

logger = logging.getLogger(__name__)


class TeamRecordsInput(BaseModel):
    """消费记录查询节点的输入"""
    operation_type: Optional[str] = Field(default=None, description="操作类型")
    user_id: Optional[str] = Field(default=None, description="用户ID")
    days: Optional[int] = Field(default=None, description="查询天数")


class TeamRecordsOutput(BaseModel):
    """消费记录查询节点的输出"""
    response_data: dict = Field(default={}, description="统一响应数据")


def team_records_node(state: TeamRecordsInput, config: RunnableConfig, runtime: Runtime[Context]) -> TeamRecordsOutput:
    """
    title: 消费记录
    desc: 查询团队消费记录和统计数据
    integrations: 数据库
    """
    ctx = runtime.context
    
    operation_type = state.operation_type
    db = get_session()
    
    try:
        if not state.user_id:
            return TeamRecordsOutput(
                response_data={"code": 400, "msg": "用户ID不能为空", "data": None}
            )
        
        # 通过 users 表查找用户及其团队
        user = db.query(Users).filter(Users.user_id == state.user_id).first()
        if not user:
            return TeamRecordsOutput(
                response_data={"code": 404, "msg": "用户不存在", "data": None}
            )
        
        if not user.team_id:
            return TeamRecordsOutput(
                response_data={"code": 404, "msg": "用户未加入任何团队", "data": None}
            )
        
        if operation_type == "get_records":
            # 查询消费记录
            days = state.days or 30  # 默认查询近30天
            start_time = datetime.utcnow() - timedelta(days=days)
            
            records = db.query(TeamConsumptionRecords).filter(
                TeamConsumptionRecords.team_id == user.team_id,
                TeamConsumptionRecords.created_at >= start_time
            ).order_by(TeamConsumptionRecords.created_at.desc()).all()
            
            record_list = [
                {
                    "record_id": r.id,
                    "user_id": r.user_id,
                    "username": r.username,
                    "operation_type": r.operation_type,
                    "amount": r.amount,
                    "balance_after": r.balance_after,
                    "description": r.description,
                    "created_at": int(r.created_at.timestamp() * 1000)
                }
                for r in records
            ]
            
            return TeamRecordsOutput(
                response_data={"code": 0, "msg": "查询成功", "data": {"records": record_list}}
            )
        
        elif operation_type == "get_stats":
            # 查询统计数据
            team = db.query(Teams).filter(Teams.id == user.team_id).first()
            
            # 查询所有该团队的成员
            members = db.query(Users).filter(Users.team_id == user.team_id).all()
            
            member_stats = [
                {
                    "user_id": m.user_id,
                    "username": m.username,
                    "role": m.role,
                    "gold_credits": m.gold_credits
                }
                for m in members
            ]
            
            return TeamRecordsOutput(
                response_data={
                    "code": 0,
                    "msg": "查询成功",
                    "data": {
                        "team_id": team.id,
                        "name": team.name,
                        "balance": team.balance,
                        "total_consumed": team.total_consumed,
                        "members": member_stats
                    }
                }
            )
        
        else:
            return TeamRecordsOutput(
                response_data={"code": 400, "msg": f"未知操作: {operation_type}", "data": None}
            )
    
    except Exception as e:
        logger.error(f"查询消费记录失败: {e}")
        return TeamRecordsOutput(
            response_data={"code": 500, "msg": f"查询失败: {str(e)}", "data": None}
        )
    finally:
        db.close()
