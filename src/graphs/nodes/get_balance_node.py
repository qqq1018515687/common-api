import logging
from typing import Optional
from langchain_core.runnables import RunnableConfig
from langgraph.runtime import Runtime
from coze_coding_utils.runtime_ctx.context import Context

from graphs.state import GetBalanceInput, GetBalanceOutput
from storage.database.billing_manager import get_balance

logger = logging.getLogger(__name__)


def get_balance_node(state: GetBalanceInput, config: RunnableConfig, runtime: Runtime[Context]) -> GetBalanceOutput:
    """
    title: 查询余额
    desc: 查询用户的 personal_gold、personal_silver 和 team_gold 余额
    integrations: 数据库
    """
    ctx = runtime.context

    try:
        result = get_balance(state.user_id)
        return GetBalanceOutput(response_data=result)

    except Exception as e:
        logger.error(f"查询余额失败: {e}")
        return GetBalanceOutput(
            response_data={"code": 1, "msg": f"查询余额失败: {str(e)}", "data": None}
        )
