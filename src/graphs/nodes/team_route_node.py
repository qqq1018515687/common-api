import os
import json
import logging
from typing import Optional
from langchain_core.runnables import RunnableConfig
from langgraph.runtime import Runtime
from coze_coding_utils.runtime_ctx.context import Context
from pydantic import BaseModel, Field

logger = logging.getLogger(__name__)


class TeamRouteInput(BaseModel):
    """团队路由节点的输入"""
    operation_type: Optional[str] = Field(default=None, description="操作类型")


class TeamRouteOutput(BaseModel):
    """团队路由节点的输出"""
    operation_type: str = Field(..., description="操作类型")


def team_route_node(state: TeamRouteInput, config: RunnableConfig, runtime: Runtime[Context]) -> TeamRouteOutput:
    """
    title: 团队余额路由
    desc: 根据operation_type分发到对应的团队余额子节点
    integrations: 
    """
    ctx = runtime.context
    
    operation_type = state.operation_type
    
    if not operation_type:
        # 默认返回初始化
        return TeamRouteOutput(operation_type="init")
    
    return TeamRouteOutput(operation_type=operation_type)


def route_by_team_operation_type(state: TeamRouteOutput) -> str:
    """
    title: 根据团队操作类型路由
    desc: 根据operation_type将请求路由到具体的团队余额处理节点
    """
    operation_type = state.operation_type
    
    if operation_type == "init":
        return "初始化团队"
    elif operation_type == "create_team":
        return "团队管理"
    elif operation_type == "get_team":
        return "团队管理"
    elif operation_type == "add_member":
        return "团队管理"
    elif operation_type == "list_members":
        return "团队管理"
    elif operation_type == "recharge":
        return "团队充值"
    elif operation_type == "deduct":
        return "团队扣费"
    elif operation_type == "refund":
        return "团队退款"
    elif operation_type == "get_records":
        return "消费记录"
    elif operation_type == "get_stats":
        return "消费记录"
    else:
        return "初始化团队"  # 默认
