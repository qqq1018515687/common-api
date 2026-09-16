import logging
from typing import Any, Optional

from coze_coding_utils.runtime_ctx.context import Context
from langchain_core.runnables import RunnableConfig
from langgraph.runtime import Runtime
from pydantic import BaseModel, Field

from storage.database.db import get_session
from storage.database.mars_special_quota_manager import (
    MarsSpecialQuotaError,
    MarsSpecialQuotaManager,
    WRITABLE_OPERATIONS,
)


logger = logging.getLogger(__name__)


class MarsSpecialQuotaInput(BaseModel):
    operation_type: Optional[str] = Field(default=None, description="操作类型")
    user_id: Optional[str] = Field(default=None, description="用户ID")
    task_id: Optional[str] = Field(default=None, description="任务ID")
    task_data: Optional[dict] = Field(default=None, description="创建任务数据")
    provider_task_id: Optional[str] = Field(default=None, description="供应商任务ID")
    provider_result: Optional[Any] = Field(default=None, description="任务结果")
    claimant_id: Optional[str] = Field(default=None, description="提交实例标识")
    claim_token: Optional[str] = Field(default=None, description="提交租约令牌")
    lease_seconds: Optional[int] = Field(default=None, description="提交租约秒数")
    error: Optional[str] = Field(default=None, description="明确失败错误")
    reason: Optional[str] = Field(default=None, description="状态原因")
    service_secret: Optional[str] = Field(default=None, description="服务密钥")


class MarsSpecialQuotaOutput(BaseModel):
    response_data: dict = Field(..., description="统一响应数据")


def mars_special_quota_node(
    state: MarsSpecialQuotaInput,
    config: RunnableConfig,
    runtime: Runtime[Context],
) -> MarsSpecialQuotaOutput:
    """
    title: 火星特供次数
    desc: 原子预占、核销或返还火星特供次数，并处理邀请永久次数奖励
    integrations: 数据库
    """
    ctx = runtime.context
    operation = str(state.operation_type or "").strip()
    if not state.user_id:
        return MarsSpecialQuotaOutput(
            response_data={"code": 400, "msg": "用户ID不能为空", "data": None}
        )
    if operation in WRITABLE_OPERATIONS and not MarsSpecialQuotaManager.verify_service_secret(state.service_secret):
        return MarsSpecialQuotaOutput(
            response_data={"code": 401, "msg": "service_secret 无效", "data": None}
        )

    db = get_session()
    try:
        if operation == "get_status":
            data = MarsSpecialQuotaManager.get_status(db, state.user_id)
        elif operation == "create_task":
            data = MarsSpecialQuotaManager.create_task(db, state.user_id, state.task_data or {})
        elif operation == "provider_accepted":
            if not state.task_id:
                raise MarsSpecialQuotaError("task_id 不能为空")
            data = MarsSpecialQuotaManager.provider_accepted(
                db,
                state.user_id,
                state.task_id,
                state.provider_task_id,
                state.provider_result,
                state.claim_token,
            )
        elif operation == "acquire_submission":
            if not state.task_id:
                raise MarsSpecialQuotaError("task_id 不能为空")
            data = MarsSpecialQuotaManager.acquire_submission(
                db,
                state.user_id,
                state.task_id,
                state.claimant_id,
                state.lease_seconds,
            )
        elif operation == "complete":
            if not state.task_id:
                raise MarsSpecialQuotaError("task_id 不能为空")
            data = MarsSpecialQuotaManager.complete(
                db, state.user_id, state.task_id, state.provider_task_id, state.provider_result
            )
        elif operation == "fail":
            if not state.task_id:
                raise MarsSpecialQuotaError("task_id 不能为空")
            data = MarsSpecialQuotaManager.fail(
                db, state.user_id, state.task_id, state.error, state.reason
            )
        elif operation == "mark_unknown":
            if not state.task_id:
                raise MarsSpecialQuotaError("task_id 不能为空")
            data = MarsSpecialQuotaManager.mark_unknown(
                db,
                state.user_id,
                state.task_id,
                state.provider_task_id,
                state.provider_result,
                state.reason,
            )
        else:
            raise MarsSpecialQuotaError(f"不支持的操作类型: {operation}")
        db.commit()
        return MarsSpecialQuotaOutput(
            response_data={"code": 0, "msg": "操作成功", "data": data}
        )
    except MarsSpecialQuotaError as exc:
        db.rollback()
        return MarsSpecialQuotaOutput(
            response_data={"code": exc.code, "msg": str(exc), "data": None}
        )
    except Exception as exc:
        db.rollback()
        logger.exception("火星特供次数操作失败: operation=%s user_id=%s", operation, state.user_id)
        return MarsSpecialQuotaOutput(
            response_data={"code": 500, "msg": "火星特供次数操作失败", "data": None}
        )
    finally:
        db.close()
