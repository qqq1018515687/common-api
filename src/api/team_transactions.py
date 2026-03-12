"""
团队消费记录查询API接口
提供消费记录查询、统计等功能
"""

from fastapi import APIRouter, HTTPException, Depends, Query
from pydantic import BaseModel, Field
from typing import Optional, List
from datetime import datetime, timedelta
import logging

from storage.database.shared.model import (
    TeamConsumptionRecords,
    TeamMembers,
    Users,
    Teams,
    engine
)
from sqlalchemy.orm import Session
from sqlalchemy import select, func, desc, and_

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/teams", tags=["团队消费记录"])


def get_db():
    """获取数据库会话"""
    db = Session(engine)
    try:
        yield db
    finally:
        db.close()


# ==================== 请求/响应模型 ====================

class TransactionInfo(BaseModel):
    """消费记录信息"""
    id: str
    team_id: str
    user_id: str
    username: Optional[str]
    amount: int
    balance_before: Optional[int]
    balance_after: Optional[int]
    operation_type: str
    related_id: Optional[str]
    description: Optional[str]
    created_at: str


class TransactionsResponse(BaseModel):
    """消费记录列表响应"""
    total: int
    page: int
    page_size: int
    records: List[TransactionInfo]


class RecentTransactionsResponse(BaseModel):
    """近N天消费记录响应"""
    team_id: str
    days: int
    total_amount: int
    total_count: int
    records: List[TransactionInfo]


class MemberStatsResponse(BaseModel):
    """成员统计响应"""
    user_id: str
    username: Optional[str]
    role: str
    total_consumed: int
    transaction_count: int
    avg_consumption: float
    recent_transactions: List[TransactionInfo]


class TeamStatsResponse(BaseModel):
    """团队统计响应"""
    team_id: str
    total_consumed: int
    total_transactions: int
    member_count: int
    top_consumers: List[dict]


# ==================== 消费记录查询接口 ====================

@router.get("/{team_id}/transactions", response_model=TransactionsResponse)
async def get_team_transactions(
    team_id: str,
    user_id: Optional[str] = Query(None, description="筛选特定用户"),
    operation_type: Optional[str] = Query(None, description="操作类型：consumption/refund/recharge"),
    start_date: Optional[str] = Query(None, description="开始日期（YYYY-MM-DD）"),
    end_date: Optional[str] = Query(None, description="结束日期（YYYY-MM-DD）"),
    page: int = Query(1, ge=1, description="页码"),
    page_size: int = Query(20, ge=1, le=100, description="每页数量"),
    db: Session = Depends(get_db)
):
    """
    查询团队消费记录

    支持按用户、操作类型、时间范围筛选
    """
    try:
        # 检查团队是否存在
        team = db.scalars(
            select(Teams).where(Teams.id == team_id)
        ).first()

        if not team:
            raise HTTPException(status_code=404, detail="团队不存在")

        # 构建查询
        query = select(TeamConsumptionRecords).where(
            TeamConsumptionRecords.team_id == team_id
        )

        # 筛选用户
        if user_id:
            query = query.where(TeamConsumptionRecords.user_id == user_id)

        # 筛选操作类型
        if operation_type:
            query = query.where(TeamConsumptionRecords.operation_type == operation_type)

        # 筛选时间范围
        if start_date:
            try:
                start_dt = datetime.strptime(start_date, "%Y-%m-%d")
                query = query.where(TeamConsumptionRecords.created_at >= start_dt)
            except ValueError:
                raise HTTPException(status_code=400, detail="开始日期格式错误，应为 YYYY-MM-DD")

        if end_date:
            try:
                end_dt = datetime.strptime(end_date, "%Y-%m-%d") + timedelta(days=1)
                query = query.where(TeamConsumptionRecords.created_at < end_dt)
            except ValueError:
                raise HTTPException(status_code=400, detail="结束日期格式错误，应为 YYYY-MM-DD")

        # 查询总数
        total_query = select(func.count()).select_from(query.subquery())
        total = db.scalar(total_query)

        # 分页查询
        query = query.order_by(desc(TeamConsumptionRecords.created_at))
        query = query.limit(page_size).offset((page - 1) * page_size)

        records = db.scalars(query).all()

        # 获取用户名
        user_ids = list(set([r.user_id for r in records if r.user_id]))
        users_map = {}
        if user_ids:
            users = db.scalars(
                select(Users).where(Users.user_id.in_(user_ids))
            ).all()
            users_map = {u.user_id: u.username for u in users}

        # 构建响应
        transaction_list = []
        for record in records:
            transaction_list.append(TransactionInfo(
                id=record.id,
                team_id=record.team_id,
                user_id=record.user_id,
                username=users_map.get(record.user_id),
                amount=record.amount,
                balance_before=record.balance_before,
                balance_after=record.balance_after,
                operation_type=record.operation_type,
                related_id=record.related_id,
                description=record.description,
                created_at=record.created_at.isoformat()
            ))

        return TransactionsResponse(
            total=total,
            page=page,
            page_size=page_size,
            records=transaction_list
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"查询消费记录失败: {e}")
        raise HTTPException(status_code=500, detail=f"查询失败: {str(e)}")


@router.get("/{team_id}/transactions/recent", response_model=RecentTransactionsResponse)
async def get_recent_transactions(
    team_id: str,
    days: int = Query(30, ge=1, le=365, description="查询最近N天"),
    db: Session = Depends(get_db)
):
    """
    查询近N天消费记录
    """
    try:
        # 检查团队是否存在
        team = db.scalars(
            select(Teams).where(Teams.id == team_id)
        ).first()

        if not team:
            raise HTTPException(status_code=404, detail="团队不存在")

        # 计算时间范围
        start_date = datetime.now() - timedelta(days=days)

        # 查询消费记录
        query = select(TeamConsumptionRecords).where(
            and_(
                TeamConsumptionRecords.team_id == team_id,
                TeamConsumptionRecords.operation_type == "consumption",
                TeamConsumptionRecords.created_at >= start_date
            )
        ).order_by(desc(TeamConsumptionRecords.created_at))

        records = db.scalars(query).all()

        # 统计总额
        total_amount = sum([r.amount for r in records])

        # 获取用户名
        user_ids = list(set([r.user_id for r in records if r.user_id]))
        users_map = {}
        if user_ids:
            users = db.scalars(
                select(Users).where(Users.user_id.in_(user_ids))
            ).all()
            users_map = {u.user_id: u.username for u in users}

        # 构建响应
        transaction_list = []
        for record in records:
            transaction_list.append(TransactionInfo(
                id=record.id,
                team_id=record.team_id,
                user_id=record.user_id,
                username=users_map.get(record.user_id),
                amount=record.amount,
                balance_before=record.balance_before,
                balance_after=record.balance_after,
                operation_type=record.operation_type,
                related_id=record.related_id,
                description=record.description,
                created_at=record.created_at.isoformat()
            ))

        return RecentTransactionsResponse(
            team_id=team_id,
            days=days,
            total_amount=total_amount,
            total_count=len(transaction_list),
            records=transaction_list
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"查询近期消费记录失败: {e}")
        raise HTTPException(status_code=500, detail=f"查询失败: {str(e)}")


@router.get("/{team_id}/members/{user_id}/stats", response_model=MemberStatsResponse)
async def get_member_stats(
    team_id: str,
    user_id: str,
    db: Session = Depends(get_db)
):
    """
    查询成员消费统计

    返回该成员的总消费、消费次数、平均消费、最近消费记录
    """
    try:
        # 检查用户是否在团队中
        member = db.scalars(
            select(TeamMembers).where(
                TeamMembers.team_id == team_id,
                TeamMembers.user_id == user_id
            )
        ).first()

        if not member:
            raise HTTPException(status_code=404, detail="成员不存在")

        # 查询用户名
        user = db.scalars(
            select(Users).where(Users.user_id == user_id)
        ).first()

        # 统计消费次数
        transaction_count = db.scalar(
            select(func.count()).select_from(
                select(TeamConsumptionRecords).where(
                    and_(
                        TeamConsumptionRecords.team_id == team_id,
                        TeamConsumptionRecords.user_id == user_id,
                        TeamConsumptionRecords.operation_type == "consumption"
                    )
                )
            )
        ) or 0

        # 计算平均消费
        avg_consumption = 0.0
        if transaction_count > 0 and member.total_consumed > 0:
            avg_consumption = member.total_consumed / transaction_count

        # 查询最近10条消费记录
        recent_records = db.scalars(
            select(TeamConsumptionRecords).where(
                and_(
                    TeamConsumptionRecords.team_id == team_id,
                    TeamConsumptionRecords.user_id == user_id
                )
            ).order_by(desc(TeamConsumptionRecords.created_at)).limit(10)
        ).all()

        # 构建最近记录列表
        recent_transactions = []
        for record in recent_records:
            recent_transactions.append(TransactionInfo(
                id=record.id,
                team_id=record.team_id,
                user_id=record.user_id,
                username=user.username if user else None,
                amount=record.amount,
                balance_before=record.balance_before,
                balance_after=record.balance_after,
                operation_type=record.operation_type,
                related_id=record.related_id,
                description=record.description,
                created_at=record.created_at.isoformat()
            ))

        return MemberStatsResponse(
            user_id=user_id,
            username=user.username if user else None,
            role=member.role,
            total_consumed=member.total_consumed,
            transaction_count=transaction_count,
            avg_consumption=round(avg_consumption, 2),
            recent_transactions=recent_transactions
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"查询成员统计失败: {e}")
        raise HTTPException(status_code=500, detail=f"查询失败: {str(e)}")


@router.get("/{team_id}/stats", response_model=TeamStatsResponse)
async def get_team_stats(
    team_id: str,
    db: Session = Depends(get_db)
):
    """
    查询团队统计信息

    返回团队总消费、总交易数、成员数、消费排行
    """
    try:
        # 检查团队是否存在
        team = db.scalars(
            select(Teams).where(Teams.id == team_id)
        ).first()

        if not team:
            raise HTTPException(status_code=404, detail="团队不存在")

        # 统计交易数
        total_transactions = db.scalar(
            select(func.count()).select_from(
                select(TeamConsumptionRecords).where(
                    and_(
                        TeamConsumptionRecords.team_id == team_id,
                        TeamConsumptionRecords.operation_type == "consumption"
                    )
                )
            )
        ) or 0

        # 查询成员消费排行
        members = db.scalars(
            select(TeamMembers).where(
                TeamMembers.team_id == team_id
            ).order_by(desc(TeamMembers.total_consumed))
        ).all()

        # 获取用户名
        user_ids = [m.user_id for m in members]
        users_map = {}
        if user_ids:
            users = db.scalars(
                select(Users).where(Users.user_id.in_(user_ids))
            ).all()
            users_map = {u.user_id: u.username for u in users}

        # 构建消费排行
        top_consumers = []
        for member in members:
            top_consumers.append({
                "user_id": member.user_id,
                "username": users_map.get(member.user_id),
                "role": member.role,
                "total_consumed": member.total_consumed
            })

        return TeamStatsResponse(
            team_id=team_id,
            total_consumed=team.total_consumed,
            total_transactions=total_transactions,
            member_count=team.member_count,
            top_consumers=top_consumers
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"查询团队统计失败: {e}")
        raise HTTPException(status_code=500, detail=f"查询失败: {str(e)}")
