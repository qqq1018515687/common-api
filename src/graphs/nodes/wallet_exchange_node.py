import logging
from typing import Optional

from coze_coding_utils.runtime_ctx.context import Context
from langchain_core.runnables import RunnableConfig
from langgraph.runtime import Runtime
from pydantic import BaseModel, Field

from storage.database.wallet_exchange_manager import convert_gold_to_silver, list_exchange_records

logger = logging.getLogger(__name__)


class WalletExchangeInput(BaseModel):
    operation_type: Optional[str] = Field(default=None, description="操作类型")
    user_id: Optional[str] = Field(default=None, description="用户ID")
    amount: Optional[float] = Field(default=None, description="兑换金额")
    idempotency_key: Optional[str] = Field(default=None, description="幂等键")
    limit: Optional[int] = Field(default=None, description="数量限制")


class WalletExchangeOutput(BaseModel):
    response_data: dict = Field(default={}, description="统一响应数据")


def wallet_exchange_node(
    state: WalletExchangeInput,
    config: RunnableConfig,
    runtime: Runtime[Context],
) -> WalletExchangeOutput:
    operation_type = state.operation_type or "list_exchange_records"
    try:
        if operation_type == "convert_gold_to_silver":
            data = convert_gold_to_silver(
                user_id=state.user_id or "",
                amount=state.amount,
                idempotency_key=state.idempotency_key or "",
            )
            return WalletExchangeOutput(
                response_data={"code": 0, "msg": "兑换成功", "data": data}
            )

        if operation_type == "list_exchange_records":
            data = list_exchange_records(
                user_id=state.user_id or "",
                limit=state.limit or 20,
            )
            return WalletExchangeOutput(
                response_data={"code": 0, "msg": "查询成功", "data": data}
            )

        return WalletExchangeOutput(
            response_data={"code": 400, "msg": f"不支持的操作类型: {operation_type}", "data": None}
        )
    except ValueError as exc:
        return WalletExchangeOutput(
            response_data={"code": 400, "msg": str(exc), "data": None}
        )
    except Exception as exc:
        logger.error("钱包兑换失败: %s", exc)
        return WalletExchangeOutput(
            response_data={"code": 500, "msg": f"钱包兑换失败: {exc}", "data": None}
        )
