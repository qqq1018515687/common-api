import logging
from typing import Any, Optional

from coze_coding_utils.runtime_ctx.context import Context
from langchain_core.runnables import RunnableConfig
from langgraph.runtime import Runtime
from pydantic import BaseModel, Field

from storage.database import finance_center_manager

logger = logging.getLogger(__name__)

# 允许的资金中心操作（均为 admin-only 只读操作）
ADMIN_OPERATIONS = {"overview", "orders", "order_summary", "risk_exceptions"}


class FinanceCenterInput(BaseModel):
    """资金中心只读查询节点的输入"""
    operation_type: Optional[str] = Field(default=None, description="操作类型：overview/orders/order_summary/risk_exceptions")
    user_id: Optional[str] = Field(default=None, description="当前用户ID")
    operator_role: Optional[str] = Field(default=None, description="操作者角色：admin/administrator/管理员 才可访问")
    operator_user_id: Optional[str] = Field(default=None, description="管理员ID")
    days: Optional[int] = Field(default=None, description="总览/风控扫描的最近天数（默认7）")
    status: Optional[str] = Field(default=None, description="订单状态筛选（orders）")
    channel: Optional[str] = Field(default=None, description="渠道筛选（orders）")
    source_type: Optional[str] = Field(default=None, description="来源类型筛选（orders）：paid/manual/compensation")
    reversal_status: Optional[str] = Field(default=None, description="冲正状态筛选（orders）：pending/approved/rejected/completed")
    search: Optional[str] = Field(default=None, description="订单搜索词（order_no 或 external_order_id 模糊匹配）")
    team_id: Optional[str] = Field(default=None, description="团队ID筛选（orders）")
    start_time: Optional[object] = Field(default=None, description="起始时间（datetime/epoch ms，按订单支付时间过滤）")
    end_time: Optional[object] = Field(default=None, description="结束时间（datetime/epoch ms）")
    page: Optional[int] = Field(default=None, description="页码（orders，默认 1）")
    limit: Optional[int] = Field(default=None, description="每页数量（orders，默认 50）")


class FinanceCenterOutput(BaseModel):
    """资金中心只读查询节点的输出"""
    response_data: dict = Field(default={}, description="统一响应数据")


def _success(data: Any, msg: str = "操作成功") -> FinanceCenterOutput:
    return FinanceCenterOutput(response_data={"code": 0, "msg": msg, "data": data})


def _failure(message: str, code: int = 400) -> FinanceCenterOutput:
    return FinanceCenterOutput(response_data={"code": code, "msg": message, "data": None})


def _is_admin(state: FinanceCenterInput) -> bool:
    return (state.operator_role or "").strip().lower() in {"admin", "administrator", "管理员"}


def finance_center_node(
    state: FinanceCenterInput,
    config: RunnableConfig,
    runtime: Runtime[Context],
) -> FinanceCenterOutput:
    """
    title: 资金中心
    desc: 只读聚合资金中心数据：今日概览、每日趋势、充值订单分页查询、订单状态汇总与实时风控异常扫描。全量 admin-only。
    integrations: 数据库
    """
    # 上下文仅用于日志/追踪，本节点为只读聚合，不读写任务状态
    ctx = runtime.context

    operation_type = (state.operation_type or "overview").strip()
    if operation_type not in ADMIN_OPERATIONS:
        return _failure(f"不支持的资金中心操作: {operation_type}")

    if not _is_admin(state):
        return _failure("无权访问资金中心", 403)

    try:
        if operation_type == "overview":
            data = finance_center_manager.overview(days=state.days)
        elif operation_type == "orders":
            data = finance_center_manager.orders_query(
                status=state.status,
                channel=state.channel,
                source_type=state.source_type,
                reversal_status=state.reversal_status,
                user_id=state.user_id,
                team_id=state.team_id,
                search=state.search,
                start_time=state.start_time,
                end_time=state.end_time,
                page=state.page or 1,
                limit=state.limit or 50,
            )
        elif operation_type == "order_summary":
            data = finance_center_manager.order_summary()
        else:  # risk_exceptions
            data = finance_center_manager.risk_exceptions(days=state.days)
        return _success(data, "操作成功")
    except Exception as exc:
        logger.exception("资金中心操作失败(%s)", operation_type)
        return _failure(f"资金中心操作失败: {str(exc)}", 500)
