import logging
from typing import Optional

from coze_coding_utils.runtime_ctx.context import Context
from langchain_core.runnables import RunnableConfig
from langgraph.runtime import Runtime
from pydantic import BaseModel, Field

from storage.database.db import get_session
from storage.database.referral_manager import bind_referral_code, get_or_create_profile

logger = logging.getLogger(__name__)


class ReferralManagementInput(BaseModel):
    operation_type: Optional[str] = Field(default=None, description="操作类型")
    user_id: Optional[str] = Field(default=None, description="用户ID")
    referral_code: Optional[str] = Field(default=None, description="推荐码")


class ReferralManagementOutput(BaseModel):
    response_data: dict = Field(default={}, description="统一响应数据")


def referral_management_node(
    state: ReferralManagementInput,
    config: RunnableConfig,
    runtime: Runtime[Context],
) -> ReferralManagementOutput:
    operation_type = state.operation_type or "get_my_referral"
    db = get_session()
    try:
        if not state.user_id:
            return ReferralManagementOutput(
                response_data={"code": 400, "msg": "用户ID不能为空", "data": None}
            )

        if operation_type == "get_my_referral":
            data = get_or_create_profile(db, state.user_id)
            db.commit()
            return ReferralManagementOutput(
                response_data={"code": 0, "msg": "查询成功", "data": data}
            )

        if operation_type == "bind_referral_code":
            data = bind_referral_code(db, state.user_id, state.referral_code or "")
            db.commit()
            return ReferralManagementOutput(
                response_data={"code": 0, "msg": "绑定成功", "data": data}
            )

        return ReferralManagementOutput(
            response_data={"code": 400, "msg": f"不支持的操作类型: {operation_type}", "data": None}
        )
    except ValueError as exc:
        db.rollback()
        return ReferralManagementOutput(
            response_data={"code": 400, "msg": str(exc), "data": None}
        )
    except Exception as exc:
        db.rollback()
        logger.error("推荐管理失败: %s", exc)
        return ReferralManagementOutput(
            response_data={"code": 500, "msg": f"推荐管理失败: {exc}", "data": None}
        )
    finally:
        db.close()
