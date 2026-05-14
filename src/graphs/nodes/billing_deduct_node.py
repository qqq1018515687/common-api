import logging
from typing import Optional
from langchain_core.runnables import RunnableConfig
from langgraph.runtime import Runtime
from coze_coding_utils.runtime_ctx.context import Context

from graphs.state import BillingDeductInput, BillingDeductOutput
from storage.database.billing_manager import deduct

logger = logging.getLogger(__name__)


def billing_deduct_node(state: BillingDeductInput, config: RunnableConfig, runtime: Runtime[Context]) -> BillingDeductOutput:
    """
    title: 扣费
    desc: 从用户指定资金类型中原子扣费，支持幂等性，personal_gold 不能扣成负数，personal_silver 最低到 -50，team_gold 不能扣成负数
    integrations: 数据库
    """
    ctx = runtime.context

    try:
        if not state.user_id:
            return BillingDeductOutput(
                response_data={"code": 1, "error_code": "USER_NOT_FOUND", "msg": "用户ID不能为空", "data": None}
            )

        if not state.credit_type:
            return BillingDeductOutput(
                response_data={"code": 1, "error_code": "INVALID_AMOUNT", "msg": "资金类型不能为空", "data": None}
            )

        if not state.amount or state.amount <= 0:
            return BillingDeductOutput(
                response_data={"code": 1, "error_code": "INVALID_AMOUNT", "msg": "扣费金额必须大于0", "data": None}
            )

        if not state.idempotency_key:
            return BillingDeductOutput(
                response_data={"code": 1, "error_code": "MISSING_IDEMPOTENCY_KEY", "msg": "idempotency_key 不能为空", "data": None}
            )

        if not state.service_secret:
            return BillingDeductOutput(
                response_data={"code": 1, "error_code": "UNAUTHORIZED", "msg": "service_secret 不能为空", "data": None}
            )

        result = deduct(
            user_id=state.user_id,
            credit_type=state.credit_type,
            amount=state.amount,
            idempotency_key=state.idempotency_key,
            service_secret=state.service_secret,
            task_id=state.task_id,
            description=state.description,
            billing_metadata=state.billing_metadata,
        )
        return BillingDeductOutput(response_data=result)

    except Exception as e:
        logger.error(f"扣费失败: {e}")
        return BillingDeductOutput(
            response_data={"code": 1, "error_code": "INTERNAL_ERROR", "msg": f"扣费失败: {str(e)}", "data": None}
        )
