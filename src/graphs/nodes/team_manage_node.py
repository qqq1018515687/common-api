"""
团队管理节点
负责创建团队、查询团队、添加成员等管理操作
"""
import logging
import uuid
from datetime import datetime
from langchain_core.runnables import RunnableConfig
from langgraph.runtime import Runtime
from coze_coding_utils.runtime_ctx.context import Context
from graphs.team_balance_state import TeamManageInput, TeamManageOutput
from storage.database.db import get_session
from storage.database.shared.model import Teams, TeamMembers

logger = logging.getLogger(__name__)


def team_manage_node(state: TeamManageInput, config: RunnableConfig, runtime: Runtime[Context]) -> TeamManageOutput:
    """
    title: 团队管理
    desc: 创建团队、查询团队信息、添加团队成员
    integrations: 数据库
    """
    ctx = runtime.context
    operation = state.action

    try:
        if operation == "create_team":
            result = _create_team(state)
        elif operation == "get_team":
            result = _get_team(state)
        elif operation == "add_member":
            result = _add_member(state)
        elif operation == "list_members":
            result = _list_members(state)
        else:
            result = {
                "success": False,
                "message": f"未知操作: {operation}",
                "data": {}
            }

        return TeamManageOutput(
            response_data={
                "code": 0 if result.get("success") else 1,
                "msg": result.get("message", ""),
                "data": result.get("data", {})
            }
        )

    except Exception as e:
        logger.error(f"团队管理操作失败: {e}")
        return TeamManageOutput(
            response_data={
                "code": 1,
                "msg": f"操作失败: {str(e)}",
                "data": {}
            }
        )


def _create_team(state: TeamManageInput) -> dict:
    """创建团队"""
    team_id = state.team_id or str(uuid.uuid4())[:8]
    name = state.name or f"团队 {team_id}"
    user_id = state.user_id
    username = state.username or "管理员"

    with get_session() as session:
        # 检查团队ID是否已存在
        existing = session.query(Teams).filter(Teams.id == team_id).first()
        if existing:
            return {
                "success": False,
                "message": f"团队ID '{team_id}' 已存在",
                "data": {}
            }

        # 创建团队
        team = Teams(
            id=team_id,
            name=name,
            balance=0,
            total_consumed=0,
            member_count=1,
            status="active"
        )
        session.add(team)

        # 创建者为管理员
        member = TeamMembers(
            id=str(uuid.uuid4())[:16],
            team_id=team_id,
            user_id=user_id,
            username=username,
            role="admin",
            total_consumed=0
        )
        session.add(member)
        session.commit()

        return {
            "success": True,
            "message": "团队创建成功",
            "data": {
                "team_id": team_id,
                "name": name,
                "balance": 0,
                "member_count": 1,
                "creator": {
                    "user_id": user_id,
                    "username": username,
                    "role": "admin"
                }
            }
        }


def _get_team(state: TeamManageInput) -> dict:
    """查询团队信息"""
    team_id = state.team_id

    with get_session() as session:
        team = session.query(Teams).filter(Teams.id == team_id).first()
        if not team:
            return {
                "success": False,
                "message": f"团队 '{team_id}' 不存在",
                "data": {}
            }

        return {
            "success": True,
            "message": "查询成功",
            "data": {
                "team_id": team.id,
                "name": team.name,
                "description": team.description,
                "balance": team.balance,
                "total_consumed": team.total_consumed,
                "member_count": team.member_count,
                "status": team.status,
                "created_at": team.created_at.isoformat() if team.created_at else None
            }
        }


def _add_member(state: TeamManageInput) -> dict:
    """添加团队成员"""
    team_id = state.team_id
    target_user_id = state.target_user_id
    target_username = state.target_username or "成员"
    target_role = state.target_role or "member"

    if not target_user_id:
        return {
            "success": False,
            "message": "缺少目标用户ID",
            "data": {}
        }

    with get_session() as session:
        # 检查团队是否存在
        team = session.query(Teams).filter(Teams.id == team_id).first()
        if not team:
            return {
                "success": False,
                "message": f"团队 '{team_id}' 不存在",
                "data": {}
            }

        # 检查用户是否已在团队中
        existing = session.query(TeamMembers).filter(
            TeamMembers.team_id == team_id,
            TeamMembers.user_id == target_user_id
        ).first()
        if existing:
            return {
                "success": False,
                "message": "该用户已是团队成员",
                "data": {}
            }

        # 添加成员
        member = TeamMembers(
            id=str(uuid.uuid4())[:16],
            team_id=team_id,
            user_id=target_user_id,
            username=target_username,
            role=target_role,
            total_consumed=0
        )
        session.add(member)

        # 更新团队人数
        team.member_count += 1
        session.commit()

        return {
            "success": True,
            "message": "成员添加成功",
            "data": {
                "team_id": team_id,
                "user_id": target_user_id,
                "username": target_username,
                "role": target_role
            }
        }


def _list_members(state: TeamManageInput) -> dict:
    """列出团队成员"""
    team_id = state.team_id

    with get_session() as session:
        members = session.query(TeamMembers).filter(
            TeamMembers.team_id == team_id
        ).all()

        member_list = [
            {
                "user_id": m.user_id,
                "username": m.username,
                "role": m.role,
                "total_consumed": m.total_consumed,
                "joined_at": m.joined_at.isoformat() if m.joined_at else None
            }
            for m in members
        ]

        return {
            "success": True,
            "message": f"共 {len(member_list)} 位成员",
            "data": {
                "team_id": team_id,
                "members": member_list
            }
        }
