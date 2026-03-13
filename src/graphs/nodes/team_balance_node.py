"""
团队余额节点 - 完全重写
所有团队余额操作合并到一个节点
"""
import logging
import uuid
from datetime import datetime, timedelta
from langchain_core.runnables import RunnableConfig
from langgraph.runtime import Runtime
from coze_coding_utils.runtime_ctx.context import Context
from graphs.team_balance_state import TeamManageInput, TeamManageOutput
from storage.database.db import get_session
from storage.database.shared.model import Teams, TeamMembers, TeamConsumptionRecords
from sqlalchemy import func

logger = logging.getLogger(__name__)


def team_balance_node(state: TeamManageInput, config: RunnableConfig, runtime: Runtime[Context]) -> TeamManageOutput:
    """
    title: 团队余额管理
    desc: 处理所有团队余额相关操作：初始化、查询、充值、扣费、退款、记录查询
    integrations: 数据库
    """
    logger.info(f"[team_balance_node] action={state.action}, team_id={state.team_id}")
    
    try:
        action = state.action
        
        if action == "init" or action == "check":
            return _init_system()
        elif action == "get_team":
            return _get_team(state)
        elif action == "create_team":
            return _create_team(state)
        elif action == "add_member":
            return _add_member(state)
        elif action == "list_members":
            return _list_members(state)
        elif action == "recharge":
            return _recharge(state)
        elif action == "deduct":
            return _deduct(state)
        elif action == "refund":
            return _refund(state)
        elif action == "get_records":
            return _get_records(state)
        elif action == "get_stats":
            return _get_stats(state)
        elif action == "get_member_stats":
            return _get_member_stats(state)
        else:
            return TeamManageOutput(
                response_data={"code": 1, "msg": f"未知操作: {action}", "data": {}}
            )
    
    except Exception as e:
        logger.error(f"团队余额操作失败: {e}")
        return TeamManageOutput(
            response_data={"code": 1, "msg": f"操作失败: {str(e)}", "data": {}}
        )


def _init_system() -> TeamManageOutput:
    """初始化系统表"""
    try:
        from storage.database.team_balance_init import init_team_balance_system
        result = init_team_balance_system()
        return TeamManageOutput(
            response_data={"code": 0, "msg": result.get("message", "初始化成功"), "data": result}
        )
    except Exception as e:
        return TeamManageOutput(
            response_data={"code": 0, "msg": "表已存在", "data": {"success": True}}
        )


def _get_team(state: TeamManageInput) -> TeamManageOutput:
    """查询团队信息"""
    with get_session() as session:
        team = session.query(Teams).filter(Teams.id == state.team_id).first()
        if not team:
            return TeamManageOutput(
                response_data={"code": 1, "msg": f"团队不存在: {state.team_id}", "data": {}}
            )
        
        return TeamManageOutput(
            response_data={
                "code": 0,
                "msg": "查询成功",
                "data": {
                    "team_id": team.id,
                    "name": team.name,
                    "balance": team.balance,
                    "total_consumed": team.total_consumed,
                    "member_count": team.member_count,
                    "status": team.status
                }
            }
        )


def _create_team(state: TeamManageInput) -> TeamManageOutput:
    """创建团队"""
    team_id = state.team_id or str(uuid.uuid4())[:8]
    name = state.name or f"团队 {team_id}"
    
    with get_session() as session:
        existing = session.query(Teams).filter(Teams.id == team_id).first()
        if existing:
            return TeamManageOutput(
                response_data={"code": 1, "msg": f"团队ID已存在: {team_id}", "data": {}}
            )
        
        team = Teams(
            id=team_id,
            name=name,
            balance=0,
            total_consumed=0,
            member_count=1,
            status="active"
        )
        session.add(team)
        
        member = TeamMembers(
            id=str(uuid.uuid4())[:16],
            team_id=team_id,
            user_id=state.user_id,
            username=state.username or "管理员",
            role="admin",
            total_consumed=0
        )
        session.add(member)
        session.commit()
        
        return TeamManageOutput(
            response_data={
                "code": 0,
                "msg": "创建成功",
                "data": {"team_id": team_id, "name": name, "balance": 0}
            }
        )


def _add_member(state: TeamManageInput) -> TeamManageOutput:
    """添加成员"""
    with get_session() as session:
        team = session.query(Teams).filter(Teams.id == state.team_id).first()
        if not team:
            return TeamManageOutput(
                response_data={"code": 1, "msg": "团队不存在", "data": {}}
            )
        
        existing = session.query(TeamMembers).filter(
            TeamMembers.team_id == state.team_id,
            TeamMembers.user_id == state.target_user_id
        ).first()
        if existing:
            return TeamManageOutput(
                response_data={"code": 1, "msg": "用户已在团队中", "data": {}}
            )
        
        member = TeamMembers(
            id=str(uuid.uuid4())[:16],
            team_id=state.team_id,
            user_id=state.target_user_id,
            username=state.target_username or "成员",
            role=state.target_role or "member",
            total_consumed=0
        )
        session.add(member)
        team.member_count += 1
        session.commit()
        
        return TeamManageOutput(
            response_data={"code": 0, "msg": "添加成功", "data": {}}
        )


def _list_members(state: TeamManageInput) -> TeamManageOutput:
    """列出成员"""
    with get_session() as session:
        members = session.query(TeamMembers).filter(
            TeamMembers.team_id == state.team_id
        ).all()
        
        return TeamManageOutput(
            response_data={
                "code": 0,
                "msg": "查询成功",
                "data": {
                    "members": [
                        {"user_id": m.user_id, "username": m.username, "role": m.role, "total_consumed": m.total_consumed}
                        for m in members
                    ]
                }
            }
        )


def _recharge(state: TeamManageInput) -> TeamManageOutput:
    """充值"""
    amount = state.amount or 0
    if amount <= 0:
        return TeamManageOutput(response_data={"code": 1, "msg": "充值金额必须大于0", "data": {}})
    
    with get_session() as session:
        team = session.query(Teams).filter(Teams.id == state.team_id).first()
        if not team:
            return TeamManageOutput(response_data={"code": 1, "msg": "团队不存在", "data": {}})
        
        balance_before = team.balance
        team.balance += amount
        
        record = TeamConsumptionRecords(
            id=str(uuid.uuid4())[:16],
            team_id=state.team_id,
            user_id=state.user_id,
            username=state.username,
            amount=-amount,
            balance_before=balance_before,
            balance_after=team.balance,
            operation_type="recharge",
            description=state.description or "充值"
        )
        session.add(record)
        session.commit()
        
        return TeamManageOutput(
            response_data={"code": 0, "msg": "充值成功", "data": {"balance": team.balance}}
        )


def _deduct(state: TeamManageInput) -> TeamManageOutput:
    """扣费"""
    amount = state.amount or 0
    if amount <= 0:
        return TeamManageOutput(response_data={"code": 1, "msg": "扣费金额必须大于0", "data": {}})
    
    with get_session() as session:
        team = session.query(Teams).filter(Teams.id == state.team_id).first()
        if not team:
            return TeamManageOutput(response_data={"code": 1, "msg": "团队不存在", "data": {}})
        
        if team.balance < amount:
            return TeamManageOutput(
                response_data={"code": 1, "msg": f"余额不足: 当前{team.balance}", "data": {}}
            )
        
        balance_before = team.balance
        team.balance -= amount
        team.total_consumed += amount
        
        member = session.query(TeamMembers).filter(
            TeamMembers.team_id == state.team_id,
            TeamMembers.user_id == state.user_id
        ).first()
        if member:
            member.total_consumed += amount
        
        record = TeamConsumptionRecords(
            id=str(uuid.uuid4())[:16],
            team_id=state.team_id,
            user_id=state.user_id,
            username=state.username,
            amount=amount,
            balance_before=balance_before,
            balance_after=team.balance,
            operation_type="consumption",
            description=state.description or "消费"
        )
        session.add(record)
        session.commit()
        
        return TeamManageOutput(
            response_data={"code": 0, "msg": "扣费成功", "data": {"balance": team.balance}}
        )


def _refund(state: TeamManageInput) -> TeamManageOutput:
    """退款"""
    amount = state.amount or 0
    if amount <= 0:
        return TeamManageOutput(response_data={"code": 1, "msg": "退款金额必须大于0", "data": {}})
    
    with get_session() as session:
        team = session.query(Teams).filter(Teams.id == state.team_id).first()
        if not team:
            return TeamManageOutput(response_data={"code": 1, "msg": "团队不存在", "data": {}})
        
        balance_before = team.balance
        team.balance += amount
        team.total_consumed -= amount
        
        record = TeamConsumptionRecords(
            id=str(uuid.uuid4())[:16],
            team_id=state.team_id,
            user_id=state.user_id,
            username=state.username,
            amount=-amount,
            balance_before=balance_before,
            balance_after=team.balance,
            operation_type="refund",
            related_id=state.original_record_id,
            description=state.reason or "退款"
        )
        session.add(record)
        session.commit()
        
        return TeamManageOutput(
            response_data={"code": 0, "msg": "退款成功", "data": {"balance": team.balance}}
        )


def _get_records(state: TeamManageInput) -> TeamManageOutput:
    """查询消费记录"""
    with get_session() as session:
        start_date = datetime.now() - timedelta(days=state.days)
        
        query = session.query(TeamConsumptionRecords).filter(
            TeamConsumptionRecords.team_id == state.team_id,
            TeamConsumptionRecords.created_at >= start_date
        )
        
        if state.user_id:
            query = query.filter(TeamConsumptionRecords.user_id == state.user_id)
        
        records = query.order_by(TeamConsumptionRecords.created_at.desc()).limit(50).all()
        
        return TeamManageOutput(
            response_data={
                "code": 0,
                "msg": "查询成功",
                "data": {
                    "records": [
                        {
                            "id": r.id,
                            "user_id": r.user_id,
                            "username": r.username,
                            "amount": r.amount,
                            "operation_type": r.operation_type,
                            "description": r.description,
                            "created_at": r.created_at.isoformat() if r.created_at else None
                        }
                        for r in records
                    ]
                }
            }
        )


def _get_stats(state: TeamManageInput) -> TeamManageOutput:
    """查询消费统计"""
    with get_session() as session:
        start_date = datetime.now() - timedelta(days=state.days)
        
        consumption = session.query(func.sum(TeamConsumptionRecords.amount)).filter(
            TeamConsumptionRecords.team_id == state.team_id,
            TeamConsumptionRecords.operation_type == "consumption",
            TeamConsumptionRecords.created_at >= start_date
        ).scalar() or 0
        
        recharge = session.query(func.sum(TeamConsumptionRecords.amount)).filter(
            TeamConsumptionRecords.team_id == state.team_id,
            TeamConsumptionRecords.operation_type == "recharge",
            TeamConsumptionRecords.created_at >= start_date
        ).scalar() or 0
        
        team = session.query(Teams).filter(Teams.id == state.team_id).first()
        
        return TeamManageOutput(
            response_data={
                "code": 0,
                "msg": "查询成功",
                "data": {
                    "team_id": state.team_id,
                    "balance": team.balance if team else 0,
                    "consumption": consumption,
                    "recharge": abs(recharge),
                    "days": state.days
                }
            }
        )


def _get_member_stats(state: TeamManageInput) -> TeamManageOutput:
    """查询成员消费统计"""
    with get_session() as session:
        start_date = datetime.now() - timedelta(days=state.days)
        
        results = session.query(
            TeamConsumptionRecords.user_id,
            TeamConsumptionRecords.username,
            func.sum(TeamConsumptionRecords.amount).label('total')
        ).filter(
            TeamConsumptionRecords.team_id == state.team_id,
            TeamConsumptionRecords.operation_type == "consumption",
            TeamConsumptionRecords.created_at >= start_date
        ).group_by(
            TeamConsumptionRecords.user_id,
            TeamConsumptionRecords.username
        ).all()
        
        return TeamManageOutput(
            response_data={
                "code": 0,
                "msg": "查询成功",
                "data": {
                    "members": [
                        {"user_id": r.user_id, "username": r.username, "consumption": r.total}
                        for r in results
                    ]
                }
            }
        )
