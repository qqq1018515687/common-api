import logging
from typing import Optional
from langchain_core.runnables import RunnableConfig
from langgraph.runtime import Runtime
from coze_coding_utils.runtime_ctx.context import Context
from pydantic import BaseModel, Field

from storage.database.billing_manager import list_records

logger = logging.getLogger(__name__)


class BillingRecordsInput(BaseModel):
    """账单记录查询节点的输入"""
    operation_type: Optional[str] = Field(default=None, description="操作类型：list_records/get_records")
    user_id: Optional[str] = Field(default=None, description="用户ID")
    filter_user_id: Optional[str] = Field(default=None, description="筛选用户ID，优先于 user_id")
    team_id: Optional[str] = Field(default=None, description="团队ID")
    credit_type: Optional[str] = Field(default=None, description="资金类型：personal_gold/personal_silver/team_gold")
    days: Optional[int] = Field(default=None, description="查询最近N天")
    limit: Optional[int] = Field(default=None, description="返回数量上限")
    service_secret: Optional[str] = Field(default=None, description="服务密钥")
    operator_role: Optional[str] = Field(default=None, description="操作者角色")


class BillingRecordsOutput(BaseModel):
    """账单记录查询节点的输出"""
    response_data: dict = Field(default={}, description="统一响应数据")


def billing_records_node(
    state: BillingRecordsInput,
    config: RunnableConfig,
    runtime: Runtime[Context],
) -> BillingRecordsOutput:
    """
    title: 账单记录
    desc: 只读查询 billing_records 明细，供管理后台查看个人金豆、银豆和团队金豆扣费流水
    integrations: 数据库
    """
    ctx = runtime.context

    try:
        query_user_id = state.filter_user_id or state.user_id
        result = list_records(
            user_id=query_user_id,
            team_id=state.team_id,
            credit_type=state.credit_type,
            days=state.days,
            limit=state.limit,
            service_secret=state.service_secret,
            operator_role=state.operator_role,
        )
        return BillingRecordsOutput(response_data=result)

    except Exception as e:
        logger.error(f"查询账单记录失败: {e}")
        return BillingRecordsOutput(
            response_data={"code": 1, "error_code": "INTERNAL_ERROR", "msg": f"查询账单记录失败: {str(e)}", "data": None}
        )
