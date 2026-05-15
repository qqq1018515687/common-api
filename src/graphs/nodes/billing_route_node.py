import logging
from typing import Optional
from langchain_core.runnables import RunnableConfig
from langgraph.runtime import Runtime
from coze_coding_utils.runtime_ctx.context import Context

from graphs.state import BillingRouteInput, BillingRouteOutput

logger = logging.getLogger(__name__)


def billing_route_node(state: BillingRouteInput, config: RunnableConfig, runtime: Runtime[Context]) -> BillingRouteOutput:
    """
    title: 资金扣费路由
    desc: 根据 operation_type 分发到对应的资金扣费子节点（get_balance/deduct/refund/settle/list_records）
    integrations:
    """
    ctx = runtime.context

    operation_type = state.operation_type

    if not operation_type:
        return BillingRouteOutput(
            operation_type="get_balance",
            user_id=state.user_id,
            filter_user_id=state.filter_user_id,
            team_id=state.team_id,
            credit_type=state.credit_type,
            amount=state.amount,
            days=state.days,
            limit=state.limit,
            idempotency_key=state.idempotency_key,
            service_secret=state.service_secret,
            task_id=state.task_id,
            description=state.description,
            original_record_id=state.original_record_id,
            final_amount=state.final_amount,
            operator_role=state.operator_role,
            operator_user_id=state.operator_user_id,
            billing_metadata=state.billing_metadata,
            metadata=state.metadata,
        )

    return BillingRouteOutput(
        operation_type=operation_type,
        user_id=state.user_id,
        filter_user_id=state.filter_user_id,
        team_id=state.team_id,
        credit_type=state.credit_type,
        amount=state.amount,
        days=state.days,
        limit=state.limit,
        idempotency_key=state.idempotency_key,
        service_secret=state.service_secret,
        task_id=state.task_id,
        description=state.description,
        original_record_id=state.original_record_id,
        final_amount=state.final_amount,
        operator_role=state.operator_role,
        operator_user_id=state.operator_user_id,
        billing_metadata=state.billing_metadata,
        metadata=state.metadata,
    )


def route_by_billing_operation_type(state: BillingRouteOutput) -> str:
    """
    title: 根据 billing 操作类型路由
    desc: 根据 operation_type 将请求路由到具体的资金操作节点
    """
    operation_type = state.operation_type

    if operation_type == "get_balance":
        return "查询余额"
    elif operation_type == "deduct":
        return "扣费"
    elif operation_type == "refund":
        return "退款"
    elif operation_type == "settle":
        return "结算"
    elif operation_type in ("list_records", "get_records"):
        return "账单记录"
    else:
        return "查询余额"  # 默认
