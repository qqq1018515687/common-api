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
from sqlalchemy import or_, and_, func, exists

from storage.database.db import get_session
from storage.database.shared.model import Teams, Users
from storage.database.amounts import gold_amount_to_number
from storage.database.team_invite_manager import TeamInviteManager

logger = logging.getLogger(__name__)

团队管理业务错误码映射 = {
    '用户不存在': 404,
    '目标用户不存在': 404,
    '团队不存在': 404,
    '邀请码不存在': 404,
    '邀请码不存在，请检查后重试': 404,
    '操作者未加入任何团队': 403,
    '当前管理员无权管理该团队的邀请码': 403,
    '只有团队管理员可以管理邀请码': 403,
    '只有管理员可以添加成员': 403,
    '账号不可用': 403,
    '邀请码已停用': 400,
    '邀请码已过期': 400,
    '邀请码已达使用上限': 400,
    '邀请码不能为空': 400,
    '当前账号已加入团队，如需切换团队请联系管理员处理': 400,
}


def _team_manage_error_response(message: str) -> 'TeamManageOutput':
    code = 团队管理业务错误码映射.get(message, 500)
    return TeamManageOutput(
        response_data={"code": code, "msg": message if code != 500 else f"操作失败: {message}", "data": None}
    )


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
    page: Optional[int] = Field(default=1, description="分页页码")
    limit: Optional[int] = Field(default=50, description="分页数量")
    keyword: Optional[str] = Field(default=None, description="搜索关键字")
    team_id: Optional[str] = Field(default=None, description="团队ID")
    invite_code: Optional[str] = Field(default=None, description="邀请码")
    invite_id: Optional[str] = Field(default=None, description="邀请码ID")
    max_uses: Optional[int] = Field(default=None, description="邀请码最大使用次数")
    expires_in_days: Optional[int] = Field(default=None, description="邀请码有效天数")
    note: Optional[str] = Field(default=None, description="备注")
    operator_user_id: Optional[str] = Field(default=None, description="操作者用户ID")
    operator_role: Optional[str] = Field(default=None, description="操作者角色")


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
    invite_mgr = TeamInviteManager()
    
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
        
        elif operation_type == "list_teams":
            # 批量查询团队列表 - 一条聚合查询替代前端全量扫用户 + 逐团队 fan-out
            page = max(1, int(state.page or 1))
            limit = min(max(1, int(state.limit or 50)), 200)
            keyword = (state.keyword or "").strip()

            base = db.query(Teams)

            if keyword:
                kw = f"%{keyword}%"
                member_match = exists().where(
                    and_(
                        Users.team_id == Teams.id,
                        or_(Users.username.ilike(kw), Users.user_id.ilike(kw))
                    )
                )
                base = base.filter(
                    or_(
                        Teams.id.ilike(kw),
                        Teams.name.ilike(kw),
                        member_match
                    )
                )

            total = base.count()

            rows = (
                base.order_by(Teams.created_at.desc())
                .offset((page - 1) * limit)
                .limit(limit)
                .all()
            )

            team_ids = [t.id for t in rows]
            members_all: dict[str, list] = {}
            if team_ids:
                member_rows = db.query(Users).filter(Users.team_id.in_(team_ids)).all()
                for m in member_rows:
                    members_all.setdefault(m.team_id, []).append(m)

            team_list = []
            for team in rows:
                all_members = members_all.get(team.id, [])
                active_members = [
                    m for m in all_members
                    if m.account_status is None or m.account_status != "deleted"
                ]
                admin_member = next(
                    (m for m in active_members if str(m.role or "").lower() == "admin"),
                    None
                )
                anchor = admin_member or (active_members[0] if active_members else None)
                team_list.append({
                    "team_id": team.id,
                    "name": team.name,
                    "balance": gold_amount_to_number(team.balance),
                    "total_consumed": gold_amount_to_number(team.total_consumed),
                    "member_count": len(active_members),
                    "anchor_user_id": anchor.user_id if anchor else "",
                    "admin_user_id": admin_member.user_id if admin_member else "",
                    "members_preview": [
                        {
                            "user_id": m.user_id,
                            "username": m.username,
                            "role": m.role,
                            "gold_credits": gold_amount_to_number(m.gold_credits)
                        }
                        for m in active_members[:6]
                    ]
                })

            return TeamManageOutput(
                response_data={
                    "code": 0,
                    "msg": "查询成功",
                    "data": {
                        "total": total,
                        "page": page,
                        "limit": limit,
                        "teams": team_list
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

        elif operation_type == "create_invite":
            team_id = (state.team_id or '').strip()
            if not team_id:
                return TeamManageOutput(
                    response_data={"code": 400, "msg": "团队ID不能为空", "data": None}
                )

            operator = invite_mgr.ensure_team_admin_access(
                db,
                operator_user_id=(state.operator_user_id or state.user_id or '').strip(),
                team_id=team_id,
            )
            invite = invite_mgr.create_invite(
                db,
                team_id=team_id,
                created_by_user_id=operator.user_id,
                created_by_username=operator.username,
                team_name=state.name,
                max_uses=max(1, int(state.max_uses or 1)),
                expires_in_days=state.expires_in_days,
                note=state.note,
            )
            return TeamManageOutput(
                response_data={
                    "code": 0,
                    "msg": "创建邀请码成功",
                    "data": {"invite": invite_mgr.serialize_invite(invite)}
                }
            )

        elif operation_type == "list_invites":
            team_id = (state.team_id or '').strip()
            if not team_id:
                return TeamManageOutput(
                    response_data={"code": 400, "msg": "团队ID不能为空", "data": None}
                )

            invite_mgr.ensure_team_admin_access(
                db,
                operator_user_id=(state.operator_user_id or state.user_id or '').strip(),
                team_id=team_id,
            )
            invites = [invite_mgr.serialize_invite(item) for item in invite_mgr.list_invites(db, team_id=team_id)]
            return TeamManageOutput(
                response_data={
                    "code": 0,
                    "msg": "查询成功",
                    "data": {"invites": invites}
                }
            )

        elif operation_type == "disable_invite":
            invite_id = (state.invite_id or '').strip()
            if not invite_id:
                return TeamManageOutput(
                    response_data={"code": 400, "msg": "邀请码ID不能为空", "data": None}
                )

            invite = invite_mgr.disable_invite(
                db,
                invite_id=invite_id,
                operator_user_id=(state.operator_user_id or state.user_id or '').strip(),
            )
            return TeamManageOutput(
                response_data={
                    "code": 0,
                    "msg": "停用邀请码成功",
                    "data": {"invite": invite_mgr.serialize_invite(invite)}
                }
            )

        elif operation_type == "join_by_invite":
            if not state.user_id:
                return TeamManageOutput(
                    response_data={"code": 400, "msg": "用户ID不能为空", "data": None}
                )
            if not state.invite_code:
                return TeamManageOutput(
                    response_data={"code": 400, "msg": "邀请码不能为空", "data": None}
                )

            invite, user, join_record = invite_mgr.join_by_invite(
                db,
                user_id=state.user_id,
                invite_code=state.invite_code,
            )
            return TeamManageOutput(
                response_data={
                    "code": 0,
                    "msg": "加入团队成功",
                    "data": {
                        "invite": invite_mgr.serialize_invite(invite),
                        "join_record": invite_mgr.serialize_join_record(join_record),
                        "team_id": user.team_id,
                        "team_name": invite.team_name,
                    }
                }
            )
        
        else:
            return TeamManageOutput(
                response_data={"code": 400, "msg": f"未知操作: {operation_type}", "data": None}
            )
    
    except ValueError as e:
        db.rollback()
        logger.warning(f"团队管理业务拒绝: {e}")
        return _team_manage_error_response(str(e))
    except Exception as e:
        db.rollback()
        logger.error(f"团队管理操作失败: {e}")
        return TeamManageOutput(
            response_data={"code": 500, "msg": f"操作失败: {str(e)}", "data": None}
        )
    finally:
        db.close()
