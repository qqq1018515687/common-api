import logging
from typing import Optional

from coze_coding_utils.runtime_ctx.context import Context
from langchain_core.runnables import RunnableConfig
from langgraph.runtime import Runtime
from pydantic import BaseModel, Field

from storage.database.mars_assistant_session_manager import (
    clear_session_state,
    get_session_state,
    upsert_session_state,
)

logger = logging.getLogger(__name__)


class MarsAssistantSessionInput(BaseModel):
    operation_type: Optional[str] = Field(default=None, description="get_state/upsert_state/clear_state")
    session_id: Optional[str] = Field(default=None, description="火星助手会话ID")
    user_id: Optional[str] = Field(default=None, description="用户ID")
    team_id: Optional[str] = Field(default=None, description="团队ID")
    task_state: Optional[dict] = Field(default=None, description="任务状态快照")
    image_asset_state: Optional[dict] = Field(default=None, description="图片资产状态快照")
    metadata: Optional[dict] = Field(default=None, description="扩展元数据")


class MarsAssistantSessionOutput(BaseModel):
    response_data: dict = Field(default={}, description="统一响应数据")


def _success(data: dict, msg: str = "操作成功") -> MarsAssistantSessionOutput:
    return MarsAssistantSessionOutput(response_data={"code": 0, "msg": msg, "data": data})


def _failure(msg: str, code: int = 1, error_code: str = "MARS_ASSISTANT_SESSION_ERROR") -> MarsAssistantSessionOutput:
    return MarsAssistantSessionOutput(response_data={"code": code, "error_code": error_code, "msg": msg, "data": None})


def mars_assistant_session_node(
    state: MarsAssistantSessionInput,
    config: RunnableConfig,
    runtime: Runtime[Context],
) -> MarsAssistantSessionOutput:
    runtime.context
    try:
        operation_type = state.operation_type or "get_state"
        if not state.session_id:
            return _failure("session_id 不能为空", error_code="SESSION_ID_REQUIRED")

        if operation_type == "get_state":
            data = get_session_state(state.session_id, user_id=state.user_id)
            return _success({"session": data}, "会话状态已获取")

        if operation_type == "upsert_state":
            if not state.user_id:
                return _failure("user_id 不能为空", error_code="USER_ID_REQUIRED")
            data = upsert_session_state(
                session_id=state.session_id,
                user_id=state.user_id,
                team_id=state.team_id,
                task_state=state.task_state,
                image_asset_state=state.image_asset_state,
                metadata=state.metadata,
            )
            return _success({"session": data}, "会话状态已保存")

        if operation_type == "clear_state":
            removed = clear_session_state(state.session_id, user_id=state.user_id)
            return _success({"removed": removed}, "会话状态已清理")

        return _failure(f"不支持的操作类型: {operation_type}", code=400, error_code="UNSUPPORTED_OPERATION")
    except Exception as exc:
        logger.error(f"Mars Assistant Session 操作失败: {exc}")
        return _failure(f"Mars Assistant Session 操作失败: {str(exc)}", code=500, error_code="INTERNAL_ERROR")
