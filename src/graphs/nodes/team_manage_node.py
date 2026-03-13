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
from storage.database.shared.model import Teams, TeamMembers

logger = logging.getLogger(__name__)


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
    desc: 处理团队创建、查询、成员管理等操作
    integrations: 数据库
    """
    ctx = runtime.context
    
    operation_type = state.operation_type
    db = get_session()
    
    try:
        if operation_type == "create_team":
            # 创建团队
            if not state.name:
                return TeamManageOutput(
                    response_data={"code": 400, "msg": "团队名称不能为空", "data": None}
                )
            
            team_id = str(uuid.uuid4())
            team = Teams(
                id=team_id,
                name=state.name,
                balance=0,
                total_consumed=0,
                member_count=1,
                status="active"
            )
            db.add(team)
            
            # 创建者自动成为管理员
            member_id = str(uuid.uuid4())
            member = TeamMembers(
                id=member_id,
                team_id=team_id,
                user_id=state.user_id,
                username=state.target_username or "",
                role="admin",
                total_consumed=0
            )
            db.add(member)
            db.commit()
            
            return TeamManageOutput(
                response_data={
                    "code": 0,
                    "msg": "创建团队成功",
                    "data": {
                        "team_id": team_id,
                        "name": team.name,
                        "balance": team.balance
                    }
                }
            )
        
        elif operation_type == "get_team":
            # 查询团队信息
            if not state.user_id:
                return TeamManageOutput(
                    response_data={"code": 400, "msg": "用户ID不能为空", "data": None}
                )
            
            # 查找用户所属团队
            member = db.query(TeamMembers).filter(TeamMembers.user_id == state.user_id).first()
            if not member:
                return TeamManageOutput(
                    response_data={"code": 404, "msg": "用户未加入任何团队", "data": None}
                )
            
            team = db.query(Teams).filter(Teams.id == member.team_id).first()
            
            return TeamManageOutput(
                response_data={
                    "code": 0,
                    "msg": "查询成功",
                    "data": {
                        "team_id": team.id,
                        "name": team.name,
                        "balance": team.balance,
                        "total_consumed": team.total_consumed
                    }
                }
            )
        
        elif operation_type == "add_member":
            # 添加成员
            if not state.user_id or not state.target_user_id:
                return TeamManageOutput(
                    response_data={"code": 400, "msg": "用户ID和目标用户ID不能为空", "data": None}
                )
            
            # 查找用户所属团队
            admin_member = db.query(TeamMembers).filter(
                TeamMembers.user_id == state.user_id,
                TeamMembers.role == "admin"
            ).first()
            
            if not admin_member:
                return TeamManageOutput(
                    response_data={"code": 403, "msg": "只有管理员可以添加成员", "data": None}
                )
            
            # 检查目标用户是否已在团队中
            existing = db.query(TeamMembers).filter(TeamMembers.user_id == state.target_user_id).first()
            if existing:
                return TeamManageOutput(
                    response_data={"code": 400, "msg": "该用户已在团队中", "data": None}
                )
            
            # 添加成员
            member_id = str(uuid.uuid4())
            new_member = TeamMembers(
                id=member_id,
                team_id=admin_member.team_id,
                user_id=state.target_user_id,
                username=state.target_username or "",
                role=state.target_role or "member",
                total_consumed=0
            )
            db.add(new_member)
            
            # 更新团队成员数
            team = db.query(Teams).filter(Teams.id == admin_member.team_id).first()
            team.member_count += 1
            team.updated_at = datetime.utcnow()
            
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
            
            # 查找用户所属团队
            member = db.query(TeamMembers).filter(TeamMembers.user_id == state.user_id).first()
            if not member:
                return TeamManageOutput(
                    response_data={"code": 404, "msg": "用户未加入任何团队", "data": None}
                )
            
            # 查询所有成员
            members = db.query(TeamMembers).filter(TeamMembers.team_id == member.team_id).all()
            
            member_list = [
                {
                    "user_id": m.user_id,
                    "username": m.username,
                    "role": m.role,
                    "total_consumed": m.total_consumed
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
