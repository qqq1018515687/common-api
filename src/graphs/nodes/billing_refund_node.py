import logging
from typing import Optional
from langchain_core.runnables import RunnableConfig
from langgraph.runtime import Runtime
from coze_coding_utils.runtime_ctx.context import Context

from graphs.state import BillingRefundInput, BillingRefundOutput
from storage.database.billing_manager import refund

logger = logging.getLogger(__name__)


def billing_refund_node(state: BillingRefundInput, config: RunnableConfig, runtime: Runtime[Context]) -> BillingRefundOutput:
    """
    title: 退款
    desc: 退回原扣费记录的金额，必须关联原始 deduct 记录，不能重复退款，支持幂等性
    integrations: 数据库
    """
    ctx = runtime.context

    try:
        if not state.user_id:
            return BillingRefundOutput(
                response_data={"code": 1, "error_code": "USER_NOT_FOUND", "msg": "用户ID不能为空", "data": None}
            )

        if not state.original_record_id:
            return BillingRefundOutput(
                response_data={"code": 1, "error_code": "ORIGINAL_RECORD_NOT_FOUND", "msg": "原扣费记录ID不能为空", "data": None}
            )

        if not state.idempotency_key:
            return BillingRefundOutput(
                response_data={"code": 1, "error_code": "MISSING_IDEMPOTENCY_KEY", "msg": "idempotency_key 不能为空", "data": None}
            )

        if not state.service_secret:
            return BillingRefundOutput(
                response_data={"code": 1, "error_code": "UNAUTHORIZED", "msg": "service_secret 不能为空", "data": None}
            )

        result = refund(
            user_id=state.user_id,
            original_record_id=state.original_record_id,
            idempotency_key=state.idempotency_key,
            service_secret=state.service_secret,
            amount=state.amount,
            description=state.description,
            billing_metadata=state.billing_metadata,
            metadata=state.metadata,
        )
        return BillingRefundOutput(response_data=result)

    except Exception as e:
        logger.error(f"退款失败: {e}")
        return BillingRefundOutput(
            response_data={"code": 1, "error_code": "INTERNAL_ERROR", "msg": f"退款失败: {str(e)}", "data": None}
        )
