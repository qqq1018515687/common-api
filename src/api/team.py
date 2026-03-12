"""
团队管理API接口
提供团队的创建、成员管理、查询等功能
"""

from fastapi import APIRouter, HTTPException, Depends, Query
from pydantic import BaseModel, Field
from typing import Optional, List
from datetime import datetime
import uuid
import logging

from storage.database.shared.model import Teams, TeamMembers, Users
from storage.database.db import get_session
from sqlalchemy.orm import Session
from sqlalchemy import select, delete, update, func

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/teams", tags=["团队管理"])


def get_db():
    """获取数据库会话"""
    db = get_session()
# ==================== 请求/响应模型 ====================

class CreateTeamRequest(BaseModel):
    """创建团队请求"""
    name: str = Field(..., min_length=1, max_length=100, description="团队名称")
    description: Optional[str] = Field(None, max_length=255, description="团队描述")


class CreateTeamResponse(BaseModel):
    """创建团队响应"""
    id: str
    name: str
    description: Optional[str]
    balance: int
    member_count: int
    created_at: str


class TeamInfo(BaseModel):
    """团队信息"""
    id: str
    name: str
    description: Optional[str]
    balance: int
    total_consumed: int
    member_count: int
    status: str
    created_at: str


class AddMemberRequest(BaseModel):
    """添加成员请求"""
    user_id: str = Field(..., description="用户ID")
    role: str = Field(default="member", description="角色：admin/member")


class AddMemberResponse(BaseModel):
    """添加成员响应"""
    message: str
    member_count: int


class MemberInfo(BaseModel):
    """成员信息"""
    id: str
    user_id: str
    username: Optional[str]
    role: str
    total_consumed: int
    joined_at: str


class TeamMembersResponse(BaseModel):
    """团队成员列表响应"""
    team_id: str
    members: List[MemberInfo]
    total: int


# ==================== 团队管理接口 ====================

@router.post("", response_model=CreateTeamResponse)
async def create_team(
    request: CreateTeamRequest,
    db: Session = Depends(get_db)
):
    """
    创建团队

    创建后自动将当前用户添加为团队管理员
    """
    try:
        # 生成团队ID
        team_id = f"team_{uuid.uuid4().hex[:8]}"

        # 创建团队记录
        team = Teams(
            id=team_id,
            name=request.name,
            description=request.description,
            balance=0,
            total_consumed=0,
            member_count=1,
            status="active"
        )

        db.add(team)
        db.flush()  # 获取 team.id

        # TODO: 从请求中获取创建者用户ID
        # 这里暂时不自动添加成员，需要单独调用添加成员接口

        db.commit()

        return CreateTeamResponse(
            id=team.id,
            name=team.name,
            description=team.description,
            balance=team.balance,
            member_count=team.member_count,
            created_at=team.created_at.isoformat()
        )

    except Exception as e:
        logger.error(f"创建团队失败: {e}")
        db.rollback()
        raise HTTPException(status_code=500, detail=f"创建团队失败: {str(e)}")


@router.get("/{team_id}", response_model=TeamInfo)
async def get_team_info(
    team_id: str,
    db: Session = Depends(get_db)
):
    """
    查询团队信息
    """
    try:
        team = db.scalars(
            select(Teams).where(Teams.id == team_id)
        ).first()

        if not team:
            raise HTTPException(status_code=404, detail="团队不存在")

        return TeamInfo(
            id=team.id,
            name=team.name,
            description=team.description,
            balance=team.balance,
            total_consumed=team.total_consumed,
            member_count=team.member_count,
            status=team.status,
            created_at=team.created_at.isoformat()
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"查询团队信息失败: {e}")
        raise HTTPException(status_code=500, detail=f"查询失败: {str(e)}")


@router.get("", response_model=List[TeamInfo])
async def list_teams(
    status: Optional[str] = Query(None, description="状态筛选"),
    db: Session = Depends(get_db)
):
    """
    查询团队列表
    """
    try:
        query = select(Teams)

        if status:
            query = query.where(Teams.status == status)

        query = query.order_by(Teams.created_at.desc())

        teams = db.scalars(query).all()

        return [
            TeamInfo(
                id=team.id,
                name=team.name,
                description=team.description,
                balance=team.balance,
                total_consumed=team.total_consumed,
                member_count=team.member_count,
                status=team.status,
                created_at=team.created_at.isoformat()
            )
            for team in teams
        ]

    except Exception as e:
        logger.error(f"查询团队列表失败: {e}")
        raise HTTPException(status_code=500, detail=f"查询失败: {str(e)}")


@router.post("/{team_id}/members", response_model=AddMemberResponse)
async def add_team_member(
    team_id: str,
    request: AddMemberRequest,
    db: Session = Depends(get_db)
):
    """
    添加团队成员

    注意：一个用户只能属于一个团队
    """
    try:
        # 检查团队是否存在
        team = db.scalars(
            select(Teams).where(Teams.id == team_id)
        ).first()

        if not team:
            raise HTTPException(status_code=404, detail="团队不存在")

        # 检查用户是否存在
        user = db.scalars(
            select(Users).where(Users.user_id == request.user_id)
        ).first()

        if not user:
            raise HTTPException(status_code=404, detail="用户不存在")

        # 检查用户是否已在其他团队中
        existing_member = db.scalars(
            select(TeamMembers).where(TeamMembers.user_id == request.user_id)
        ).first()

        if existing_member:
            if existing_member.team_id == team_id:
                raise HTTPException(status_code=400, detail="用户已在团队中")
            else:
                raise HTTPException(status_code=400, detail="用户已在其他团队中，一个用户只能属于一个团队")

        # 检查用户是否已在团队中
        existing = db.scalars(
            select(TeamMembers).where(
                TeamMembers.team_id == team_id,
                TeamMembers.user_id == request.user_id
            )
        ).first()

        if existing:
            raise HTTPException(status_code=400, detail="用户已在团队中")

        # 添加成员
        member = TeamMembers(
            id=f"tm_{uuid.uuid4().hex[:8]}",
            team_id=team_id,
            user_id=request.user_id,
            username=user.username,  # 冗余字段
            role=request.role,
            total_consumed=0
        )

        db.add(member)

        # 更新团队成员数量
        team.member_count += 1
        team.updated_at = datetime.now()

        # 更新用户的 team_id（冗余字段）
        user.team_id = team_id

        db.commit()

        return AddMemberResponse(
            message="成员添加成功",
            member_count=team.member_count
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"添加成员失败: {e}")
        db.rollback()
        raise HTTPException(status_code=500, detail=f"添加成员失败: {str(e)}")


@router.delete("/{team_id}/members/{user_id}")
async def remove_team_member(
    team_id: str,
    user_id: str,
    db: Session = Depends(get_db)
):
    """
    移除团队成员
    """
    try:
        # 检查成员是否存在
        member = db.scalars(
            select(TeamMembers).where(
                TeamMembers.team_id == team_id,
                TeamMembers.user_id == user_id
            )
        ).first()

        if not member:
            raise HTTPException(status_code=404, detail="成员不存在")

        # 删除成员
        db.delete(member)

        # 更新团队
        team = db.scalars(
            select(Teams).where(Teams.id == team_id)
        ).first()

        if team and team.member_count > 0:
            team.member_count -= 1
            team.updated_at = datetime.now()

        # 清空用户的 team_id
        user = db.scalars(
            select(Users).where(Users.user_id == user_id)
        ).first()

        if user:
            user.team_id = None

        db.commit()

        return {"message": "成员移除成功"}

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"移除成员失败: {e}")
        db.rollback()
        raise HTTPException(status_code=500, detail=f"移除成员失败: {str(e)}")


@router.get("/{team_id}/members", response_model=TeamMembersResponse)
async def get_team_members(
    team_id: str,
    db: Session = Depends(get_db)
):
    """
    查询团队成员列表
    """
    try:
        # 检查团队是否存在
        team = db.scalars(
            select(Teams).where(Teams.id == team_id)
        ).first()

        if not team:
            raise HTTPException(status_code=404, detail="团队不存在")

        # 查询成员列表
        members = db.scalars(
            select(TeamMembers).where(TeamMembers.team_id == team_id)
        ).all()

        # 获取用户名
        member_list = []
        for member in members:
            user = db.scalars(
                select(Users).where(Users.user_id == member.user_id)
            ).first()

            member_list.append(MemberInfo(
                id=member.id,
                user_id=member.user_id,
                username=user.username if user else None,
                role=member.role,
                total_consumed=member.total_consumed,
                joined_at=member.joined_at.isoformat()
            ))

        return TeamMembersResponse(
            team_id=team_id,
            members=member_list,
            total=len(member_list)
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"查询团队成员失败: {e}")
        raise HTTPException(status_code=500, detail=f"查询失败: {str(e)}")


@router.get("/user/{user_id}/team")
async def get_user_team(
    user_id: str,
    db: Session = Depends(get_db)
):
    """
    查询用户所属的团队
    """
    try:
        # 通过 team_members 表查询
        member = db.scalars(
            select(TeamMembers).where(TeamMembers.user_id == user_id)
        ).first()

        if not member:
            return {"message": "用户不属于任何团队"}

        # 查询团队信息
        team = db.scalars(
            select(Teams).where(Teams.id == member.team_id)
        ).first()

        if not team:
            return {"message": "团队不存在"}

        return {
            "team_id": team.id,
            "team_name": team.name,
            "role": member.role,
            "user_consumed": member.total_consumed
        }

    except Exception as e:
        logger.error(f"查询用户团队失败: {e}")
        raise HTTPException(status_code=500, detail=f"查询失败: {str(e)}")
