import logging
from typing import Optional

from coze_coding_utils.runtime_ctx.context import Context
from langchain_core.runnables import RunnableConfig
from langgraph.runtime import Runtime
from pydantic import BaseModel, Field

from storage.database.mars_assistant_session_manager import (
    clear_session_state,
    get_session_state,
    list_session_artifacts,
    list_session_messages,
    upsert_session_state,
    upsert_session_message,
    upsert_session_artifact,
)

logger = logging.getLogger(__name__)


class MarsAssistantSessionInput(BaseModel):
    operation_type: Optional[str] = Field(default=None, description="get_state/upsert_state/clear_state/list_messages/upsert_message/list_artifacts/upsert_artifact")
    session_id: Optional[str] = Field(default=None, description="火星助手会话ID")
    user_id: Optional[str] = Field(default=None, description="用户ID")
    team_id: Optional[str] = Field(default=None, description="团队ID")
    task_state: Optional[dict] = Field(default=None, description="任务状态快照")
    image_asset_state: Optional[dict] = Field(default=None, description="图片资产状态快照")
    metadata: Optional[dict] = Field(default=None, description="扩展元数据")
    message_id: Optional[str] = Field(default=None, description="消息ID")
    role: Optional[str] = Field(default=None, description="消息角色")
    content: Optional[str] = Field(default=None, description="消息内容")
    status: Optional[str] = Field(default=None, description="消息状态")
    model: Optional[str] = Field(default=None, description="模型ID")
    error: Optional[str] = Field(default=None, description="错误信息")
    attachment_ids: Optional[list] = Field(default=None, description="附件ID列表")
    quoted_message: Optional[dict] = Field(default=None, description="引用消息")
    skill_payload: Optional[dict] = Field(default=None, description="技能负载")
    artifact_id: Optional[str] = Field(default=None, description="产物ID")
    artifact_type: Optional[str] = Field(default=None, description="产物类型")
    artifact_role: Optional[str] = Field(default=None, description="产物角色")
    url: Optional[str] = Field(default=None, description="产物URL")
    file_key: Optional[str] = Field(default=None, description="文件Key")
    prompt: Optional[str] = Field(default=None, description="提示词")
    source_artifact_id: Optional[str] = Field(default=None, description="来源产物ID")
    source_image_url: Optional[str] = Field(default=None, description="来源图片URL")
    created_at: Optional[int] = Field(default=None, description="创建时间")


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
        metadata = state.metadata if isinstance(state.metadata, dict) else {}
        message_payload = metadata.get("message") if isinstance(metadata.get("message"), dict) else {}
        artifact_payload = metadata.get("artifact") if isinstance(metadata.get("artifact"), dict) else {}
        if not state.session_id:
            return _failure("session_id 不能为空", error_code="SESSION_ID_REQUIRED")

        if operation_type == "get_state":
            data = get_session_state(state.session_id, user_id=state.user_id)
            return _success({"session": data}, "会话状态已获取")

        if operation_type == "list_messages":
            data = list_session_messages(state.session_id, user_id=state.user_id)
            return _success({"messages": data}, "会话消息已获取")

        if operation_type == "list_artifacts":
            data = list_session_artifacts(state.session_id, user_id=state.user_id)
            return _success({"artifacts": data}, "会话产物已获取")

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

        if operation_type == "upsert_message":
            message_id = state.message_id or message_payload.get("message_id") or message_payload.get("id")
            role = state.role or message_payload.get("role")
            if not state.user_id:
                return _failure("user_id 不能为空", error_code="USER_ID_REQUIRED")
            if not message_id:
                return _failure("message_id 不能为空", error_code="MESSAGE_ID_REQUIRED")
            if not role:
                return _failure("role 不能为空", error_code="ROLE_REQUIRED")
            data = upsert_session_message(
                message_id=message_id,
                session_id=state.session_id,
                user_id=state.user_id,
                team_id=state.team_id,
                role=role,
                content=state.content if state.content is not None else message_payload.get("content"),
                status=state.status if state.status is not None else message_payload.get("status"),
                model=state.model if state.model is not None else message_payload.get("model"),
                error=state.error if state.error is not None else message_payload.get("error"),
                attachment_ids=state.attachment_ids if state.attachment_ids is not None else message_payload.get("attachment_ids"),
                quoted_message=state.quoted_message if state.quoted_message is not None else message_payload.get("quoted_message"),
                skill_payload=state.skill_payload if state.skill_payload is not None else message_payload.get("skill_payload"),
                metadata=message_payload.get("metadata") if isinstance(message_payload.get("metadata"), dict) else metadata,
                created_at=state.created_at if state.created_at is not None else message_payload.get("created_at"),
            )
            return _success({"message": data}, "会话消息已保存")

        if operation_type == "upsert_artifact":
            artifact_id = state.artifact_id or artifact_payload.get("artifact_id") or artifact_payload.get("id")
            artifact_type = state.artifact_type or artifact_payload.get("artifact_type")
            if not state.user_id:
                return _failure("user_id 不能为空", error_code="USER_ID_REQUIRED")
            if not artifact_id:
                return _failure("artifact_id 不能为空", error_code="ARTIFACT_ID_REQUIRED")
            if not artifact_type:
                return _failure("artifact_type 不能为空", error_code="ARTIFACT_TYPE_REQUIRED")
            data = upsert_session_artifact(
                artifact_id=artifact_id,
                session_id=state.session_id,
                message_id=state.message_id if state.message_id is not None else artifact_payload.get("message_id"),
                user_id=state.user_id,
                team_id=state.team_id,
                artifact_type=artifact_type,
                artifact_role=state.artifact_role if state.artifact_role is not None else artifact_payload.get("artifact_role"),
                url=state.url if state.url is not None else artifact_payload.get("url"),
                file_key=state.file_key if state.file_key is not None else artifact_payload.get("file_key"),
                prompt=state.prompt if state.prompt is not None else artifact_payload.get("prompt"),
                source_artifact_id=state.source_artifact_id if state.source_artifact_id is not None else artifact_payload.get("source_artifact_id"),
                source_image_url=state.source_image_url if state.source_image_url is not None else artifact_payload.get("source_image_url"),
                metadata=artifact_payload.get("metadata") if isinstance(artifact_payload.get("metadata"), dict) else metadata,
                created_at=state.created_at if state.created_at is not None else artifact_payload.get("created_at"),
            )
            return _success({"artifact": data}, "会话产物已保存")

        if operation_type == "clear_state":
            removed = clear_session_state(state.session_id, user_id=state.user_id)
            return _success({"removed": removed}, "会话状态已清理")

        return _failure(f"不支持的操作类型: {operation_type}", code=400, error_code="UNSUPPORTED_OPERATION")
    except Exception as exc:
        logger.error(f"Mars Assistant Session 操作失败: {exc}")
        return _failure(f"Mars Assistant Session 操作失败: {str(exc)}", code=500, error_code="INTERNAL_ERROR")
