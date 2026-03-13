import os
import json
import logging
from typing import Optional
from langchain_core.runnables import RunnableConfig
from langgraph.runtime import Runtime
from coze_coding_utils.runtime_ctx.context import Context
from pydantic import BaseModel, Field

from storage.database.team_balance_init import create_team_balance_tables

logger = logging.getLogger(__name__)


class TeamInitInput(BaseModel):
    """团队初始化节点的输入"""
    operation_type: Optional[str] = Field(default=None, description="操作类型")


class TeamInitOutput(BaseModel):
    """团队初始化节点的输出"""
    response_data: dict = Field(default={}, description="统一响应数据")


def team_init_node(state: TeamInitInput, config: RunnableConfig, runtime: Runtime[Context]) -> TeamInitOutput:
    """
    title: 团队初始化
    desc: 初始化团队余额相关数据库表
    integrations: 数据库
    """
    ctx = runtime.context
    
    try:
        # 初始化团队余额相关表
        result = create_team_balance_tables()
        
        if result.get("success"):
            return TeamInitOutput(
                response_data={
                    "code": 0,
                    "msg": "团队余额表初始化成功",
                    "data": result
                }
            )
        else:
            return TeamInitOutput(
                response_data={
                    "code": 500,
                    "msg": f"初始化失败: {result.get('error', '未知错误')}",
                    "data": None
                }
            )
    except Exception as e:
        logger.error(f"团队初始化失败: {e}")
        return TeamInitOutput(
            response_data={
                "code": 500,
                "msg": f"初始化异常: {str(e)}",
                "data": None
            }
        )
