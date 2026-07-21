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
from sqlalchemy import or_

from storage.database.db import get_session
from storage.database.shared.model import Teams, Users
from storage.database.amounts import gold_amount_to_number

logger = logging.getLogger(__name__)


def _active_user_filter():
    return or_(Users.account_status.is_(None), Users.account_status != "deleted")


class TeamManageInput(BaseModel):
    """团队管理节点的输入"""
    operation_type: Optional[str] = Field(default=None, description="操作类型")
    user_id: Optional[str] = Field(default=None, description="用户ID")
    name: Optional[str] = Field(default=None, description="团队名称")
    target_user_id: Optional[str] = Field(default=None, description="目标用户ID")
    target_username: Optional[str] = Field(default=None, description="目标用户名")
    target_role: Optional[str] = Field(default=None, description="目标角色")


class TeamManageOutput(BaseModel):
    """团队管理节点的输出"""
    response_data: dict = Field(default={}, description="统一响应数据")


def team_manage_node(state: TeamManageInput, config: RunnableConfig, runtime: Runtime[Context]) -> TeamManageOutput:
    """
    title: 团队管理
    desc: 处理团队查询、成员管理等操作
    integrations: 数据库
    """
    ctx = runtime.context
    
    operation_type = state.operation_type
    db = get_session()
    
    try:
        if operation_type == "get_team":
            # 查询团队信息 - 通过 users 表的 team_id 字段
            if not state.user_id:
                return TeamManageOutput(
                    response_data={"code": 400, "msg": "用户ID不能为空", "data": None}
                )
            
            # 查找用户
            user = db.query(Users).filter(Users.user_id == state.user_id).first()
            if not user:
                return TeamManageOutput(
                    response_data={"code": 404, "msg": "用户不存在", "data": None}
                )
            
            # 检查用户是否加入了团队
            if not user.team_id:
                return TeamManageOutput(
                    response_data={"code": 404, "msg": "用户未加入任何团队", "data": None}
                )
            
            # 查询团队信息
            team = db.query(Teams).filter(Teams.id == user.team_id).first()
            if not team:
                return TeamManageOutput(
                    response_data={"code": 404, "msg": "团队不存在", "data": None}
                )
            
            return TeamManageOutput(
                response_data={
                    "code": 0,
                    "msg": "查询成功",
                    "data": {
                        "team_id": team.id,
                        "name": team.name,
                        "balance": gold_amount_to_number(team.balance),
                        "total_consumed": gold_amount_to_number(team.total_consumed)
                    }
                }
            )
        
        elif operation_type == "add_member":
            # 添加成员 - 更新用户的 team_id
            if not state.user_id or not state.target_user_id:
                return TeamManageOutput(
                    response_data={"code": 400, "msg": "用户ID和目标用户ID不能为空", "data": None}
                )
            
            # 查找操作者
            operator = db.query(Users).filter(Users.user_id == state.user_id).first()
            if not operator or not operator.team_id:
                return TeamManageOutput(
                    response_data={"code": 403, "msg": "操作者未加入任何团队", "data": None}
                )
            
            # 检查操作者是否是管理员（通过 users 表的 role 字段）
            if operator.role != "admin":
                return TeamManageOutput(
                    response_data={"code": 403, "msg": "只有管理员可以添加成员", "data": None}
                )
            
            # 检查目标用户是否已在团队中
            target_user = db.query(Users).filter(Users.user_id == state.target_user_id).first()
            if not target_user:
                return TeamManageOutput(
                    response_data={"code": 404, "msg": "目标用户不存在", "data": None}
                )
            
            if target_user.team_id:
                return TeamManageOutput(
                    response_data={"code": 400, "msg": "该用户已在团队中", "data": None}
                )
            
            # 添加成员 - 更新目标用户的 team_id
            target_user.team_id = operator.team_id
            target_user.updated_at = datetime.utcnow()
            db.commit()
            
            return TeamManageOutput(
                response_data={"code": 0, "msg": "添加成员成功", "data": {"user_id": state.target_user_id}}
            )
        
        elif operation_type == "list_members":
            # 列出团队成员
            if not state.user_id:
                return TeamManageOutput(
                    response_data={"code": 400, "msg": "用户ID不能为空", "data": None}
                )
            
            # 查找用户
            user = db.query(Users).filter(Users.user_id == state.user_id).first()
            if not user or not user.team_id:
                return TeamManageOutput(
                    response_data={"code": 404, "msg": "用户未加入任何团队", "data": None}
                )
            
            # 查询所有该团队的成员
            members = db.query(Users).filter(
                Users.team_id == user.team_id,
                _active_user_filter()
            ).all()
            
            member_list = [
                {
                    "user_id": m.user_id,
                    "username": m.username,
                    "role": m.role,
                    "gold_credits": gold_amount_to_number(m.gold_credits)
                }
                for m in members
            ]
            
            return TeamManageOutput(
                response_data={"code": 0, "msg": "查询成功", "data": {"members": member_list}}
            )
        
        else:
            return TeamManageOutput(
                response_data={"code": 400, "msg": f"未知操作: {operation_type}", "data": None}
            )
    
    except Exception as e:
        db.rollback()
        logger.error(f"团队管理操作失败: {e}")
        return TeamManageOutput(
            response_data={"code": 500, "msg": f"操作失败: {str(e)}", "data": None}
        )
    finally:
        db.close()
