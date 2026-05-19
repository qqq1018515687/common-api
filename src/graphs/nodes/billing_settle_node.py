import logging
from typing import Optional
from langchain_core.runnables import RunnableConfig
from langgraph.runtime import Runtime
from coze_coding_utils.runtime_ctx.context import Context

from graphs.state import BillingSettleInput, BillingSettleOutput
from storage.database.billing_manager import settle

logger = logging.getLogger(__name__)


def billing_settle_node(state: BillingSettleInput, config: RunnableConfig, runtime: Runtime[Context]) -> BillingSettleOutput:
    """
    title: 结算
    desc: 任务完成后结算，只对 personal_silver 退差额（gold/team_gold 预扣即最终），支持幂等性
    integrations: 数据库
    """
    ctx = runtime.context

    try:
        if not state.user_id:
            return BillingSettleOutput(
                response_data={"code": 1, "error_code": "USER_NOT_FOUND", "msg": "用户ID不能为空", "data": None}
            )

        if not state.original_record_id:
            return BillingSettleOutput(
                response_data={"code": 1, "error_code": "ORIGINAL_RECORD_NOT_FOUND", "msg": "原扣费记录ID不能为空", "data": None}
            )

        if state.final_amount is None:
            return BillingSettleOutput(
                response_data={"code": 1, "error_code": "INVALID_AMOUNT", "msg": "结算金额不能为空", "data": None}
            )

        if not state.idempotency_key:
            return BillingSettleOutput(
                response_data={"code": 1, "error_code": "MISSING_IDEMPOTENCY_KEY", "msg": "idempotency_key 不能为空", "data": None}
            )

        if not state.service_secret:
            return BillingSettleOutput(
                response_data={"code": 1, "error_code": "UNAUTHORIZED", "msg": "service_secret 不能为空", "data": None}
            )

        result = settle(
            user_id=state.user_id,
            original_record_id=state.original_record_id,
            idempotency_key=state.idempotency_key,
            final_amount=state.final_amount,
            service_secret=state.service_secret,
            description=state.description,
            billing_metadata=state.billing_metadata,
            metadata=state.metadata,
        )
        return BillingSettleOutput(response_data=result)

    except Exception as e:
        logger.error(f"结算失败: {e}")
        return BillingSettleOutput(
            response_data={"code": 1, "error_code": "INTERNAL_ERROR", "msg": f"结算失败: {str(e)}", "data": None}
        )
