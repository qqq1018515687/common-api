"""
团队余额管理API接口
提供团队充值、余额查询等功能
"""

from fastapi import APIRouter, HTTPException, Depends
from pydantic import BaseModel, Field
from typing import Optional
from datetime import datetime
import uuid
import logging

from storage.database.shared.model import (
    Teams,
    TeamMembers,
    TeamConsumptionRecords,
)
from storage.database.db import get_session
from sqlalchemy.orm import Session
from sqlalchemy import select, func
from sqlalchemy.exc import IntegrityError

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/teams", tags=["团队余额管理"])


def get_db():
    """获取数据库会话"""
    db = get_session()
    try:
        yield db
    finally:
        db.close()


# ==================== 请求/响应模型 ====================

class RechargeRequest(BaseModel):
    """团队充值请求"""
    amount: int = Field(..., gt=0, description="充值金额（金豆）")
    payment_method: Optional[str] = Field(None, description="支付方式")
    description: Optional[str] = Field(None, description="充值说明")


class RechargeResponse(BaseModel):
    """充值响应"""
    balance_before: int
    balance_after: int
    amount: int
    transaction_id: str


class BalanceInfo(BaseModel):
    """余额信息"""
    team_id: str
    balance: int
    total_consumed: int
    recent_consumption: int  # 近24小时消费


class DeductBalanceRequest(BaseModel):
    """扣减余额请求"""
    user_id: str = Field(..., description="消费用户ID")
    amount: int = Field(..., gt=0, description="消费金额")
    task_id: Optional[str] = Field(None, description="关联任务ID")
    description: Optional[str] = Field(None, description="消费说明")


class DeductBalanceResponse(BaseModel):
    """扣减余额响应"""
    balance_before: int
    balance_after: int
    amount: int
    success: bool


class RefundBalanceRequest(BaseModel):
    """退款请求"""
    user_id: str = Field(..., description="消费用户ID")
    amount: int = Field(..., gt=0, description="退款金额")
    task_id: Optional[str] = Field(None, description="关联任务ID")
    description: Optional[str] = Field(None, description="退款说明")


# ==================== 余额管理接口 ====================

@router.get("/{team_id}/balance", response_model=BalanceInfo)
async def get_team_balance(
    team_id: str,
    db: Session = Depends(get_db)
):
    """
    查询团队余额

    返回当前余额、总消费、近24小时消费
    """
    try:
        # 查询团队信息
        team = db.scalars(
            select(Teams).where(Teams.id == team_id)
        ).first()

        if not team:
            raise HTTPException(status_code=404, detail="团队不存在")

        # 查询近24小时消费
        from sqlalchemy import text
        recent_consumption = db.execute(
            text("""
                SELECT COALESCE(SUM(amount), 0) as total
                FROM team_consumption_records
                WHERE team_id = :team_id
                  AND operation_type = 'consumption'
                  AND created_at >= NOW() - INTERVAL '24 hours'
            """),
            {"team_id": team_id}
        ).scalar() or 0

        return BalanceInfo(
            team_id=team.id,
            balance=team.balance,
            total_consumed=team.total_consumed,
            recent_consumed=int(recent_consumption)
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"查询团队余额失败: {e}")
        raise HTTPException(status_code=500, detail=f"查询失败: {str(e)}")


@router.post("/{team_id}/recharge", response_model=RechargeResponse)
async def recharge_team_balance(
    team_id: str,
    request: RechargeRequest,
    db: Session = Depends(get_db)
):
    """
    团队充值

    充值操作会增加团队余额，并记录充值记录
    """
    try:
        # 查询团队信息
        team = db.scalars(
            select(Teams).where(Teams.id == team_id)
        ).first()

        if not team:
            raise HTTPException(status_code=404, detail="团队不存在")

        balance_before = team.balance

        # 充值金额（注意：这里amount是充值金额，balance增加）
        amount = request.amount

        # 更新团队余额
        team.balance += amount
        team.updated_at = datetime.now()

        # 创建充值记录（operation_type=recharge，amount为负数表示增加余额）
        record = TeamConsumptionRecords(
            id=f"tcr_{uuid.uuid4().hex[:8]}",
            team_id=team_id,
            user_id="",  # 充值操作没有具体用户
            amount=-amount,  # 负数表示充值
            balance_before=balance_before,
            balance_after=team.balance,
            operation_type="recharge",
            description=request.description or f"充值{amount}金豆",
            metadata={"payment_method": request.payment_method}
        )

        db.add(record)
        db.commit()

        logger.info(f"团队 {team_id} 充值成功：{amount}金豆，余额从 {balance_before} 增加到 {team.balance}")

        return RechargeResponse(
            balance_before=balance_before,
            balance_after=team.balance,
            amount=amount,
            transaction_id=record.id
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"团队充值失败: {e}")
        db.rollback()
        raise HTTPException(status_code=500, detail=f"充值失败: {str(e)}")


@router.post("/{team_id}/deduct", response_model=DeductBalanceResponse)
async def deduct_team_balance(
    team_id: str,
    request: DeductBalanceRequest,
    db: Session = Depends(get_db)
):
    """
    扣减团队余额（消费）

    用于任务执行时扣减团队余额
    """
    try:
        # 查询团队信息
        team = db.scalars(
            select(Teams).where(Teams.id == team_id)
        ).first()

        if not team:
            raise HTTPException(status_code=404, detail="团队不存在")

        # 检查余额是否充足
        if team.balance < request.amount:
            raise HTTPException(
                status_code=400,
                detail=f"余额不足：当前余额 {team.balance}，需要 {request.amount}"
            )

        # 检查用户是否在团队中
        member = db.scalars(
            select(TeamMembers).where(
                TeamMembers.team_id == team_id,
                TeamMembers.user_id == request.user_id
            )
        ).first()

        if not member:
            raise HTTPException(status_code=403, detail="用户不在团队中，无法使用团队余额")

        balance_before = team.balance

        # 扣减余额
        team.balance -= request.amount
        team.total_consumed += request.amount
        team.updated_at = datetime.now()

        # 更新成员消费
        member.total_consumed += request.amount
        member.updated_at = datetime.now()

        # 创建消费记录
        record = TeamConsumptionRecords(
            id=f"tcr_{uuid.uuid4().hex[:8]}",
            team_id=team_id,
            user_id=request.user_id,
            amount=request.amount,  # 正数表示消费
            balance_before=balance_before,
            balance_after=team.balance,
            operation_type="consumption",
            related_id=request.task_id,
            description=request.description or "任务消费",
            metadata={}
        )

        db.add(record)
        db.commit()

        logger.info(
            f"团队 {team_id} 扣费成功：用户 {request.user_id} 消费 {request.amount}金豆，"
            f"余额从 {balance_before} 减少到 {team.balance}"
        )

        return DeductBalanceResponse(
            balance_before=balance_before,
            balance_after=team.balance,
            amount=request.amount,
            success=True
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"扣减团队余额失败: {e}")
        db.rollback()
        raise HTTPException(status_code=500, detail=f"扣费失败: {str(e)}")


@router.post("/{team_id}/refund")
async def refund_team_balance(
    team_id: str,
    request: RefundBalanceRequest,
    db: Session = Depends(get_db)
):
    """
    团队余额退款

    用于任务失败时退款
    """
    try:
        # 查询团队信息
        team = db.scalars(
            select(Teams).where(Teams.id == team_id)
        ).first()

        if not team:
            raise HTTPException(status_code=404, detail="团队不存在")

        # 检查用户是否在团队中
        member = db.scalars(
            select(TeamMembers).where(
                TeamMembers.team_id == team_id,
                TeamMembers.user_id == request.user_id
            )
        ).first()

        if not member:
            raise HTTPException(status_code=403, detail="用户不在团队中")

        balance_before = team.balance

        # 退款：增加余额，减少总消费
        team.balance += request.amount
        team.total_consumed -= request.amount
        team.updated_at = datetime.now()

        # 减少成员消费
        member.total_consumed -= request.amount
        member.updated_at = datetime.now()

        # 创建退款记录（负数表示退款）
        record = TeamConsumptionRecords(
            id=f"tcr_{uuid.uuid4().hex[:8]}",
            team_id=team_id,
            user_id=request.user_id,
            amount=-request.amount,  # 负数表示退款
            balance_before=balance_before,
            balance_after=team.balance,
            operation_type="refund",
            related_id=request.task_id,
            description=request.description or "任务退款",
            metadata={}
        )

        db.add(record)
        db.commit()

        logger.info(
            f"团队 {team_id} 退款成功：用户 {request.user_id} 退款 {request.amount}金豆，"
            f"余额从 {balance_before} 增加到 {team.balance}"
        )

        return {
            "message": "退款成功",
            "balance_before": balance_before,
            "balance_after": team.balance,
            "amount": request.amount
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"团队退款失败: {e}")
        db.rollback()
        raise HTTPException(status_code=500, detail=f"退款失败: {str(e)}")
