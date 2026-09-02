import logging
from typing import Optional

from coze_coding_utils.runtime_ctx.context import Context
from langchain_core.runnables import RunnableConfig
from langgraph.runtime import Runtime
from pydantic import BaseModel, Field

from storage.database.mars_assistant_session_manager import (
    clear_session_state,
    get_attachment,
    get_attachment_detail,
    get_attachment_content,
    get_session_state,
    list_attachment_chunks,
    list_session_attachments,
    list_session_artifacts,
    list_session_messages,
    upsert_attachment,
    upsert_attachment_content,
    upsert_session_state,
    upsert_session_message,
    upsert_session_artifact,
)

logger = logging.getLogger(__name__)


class MarsAssistantSessionInput(BaseModel):
    operation_type: Optional[str] = Field(default=None, description="get_state/upsert_state/clear_state/list_messages/upsert_message/list_artifacts/upsert_artifact/list_attachments/get_attachment/upsert_attachment/upsert_attachment_content")
    session_id: Optional[str] = Field(default=None, description="火星助手会话ID")
    user_id: Optional[str] = Field(default=None, description="用户ID")
    team_id: Optional[str] = Field(default=None, description="团队ID")
    task_state: Optional[dict] = Field(default=None, description="任务状态快照")
    image_asset_state: Optional[dict] = Field(default=None, description="图片资产状态快照")
    metadata: Optional[dict] = Field(default=None, description="扩展元数据")
    message_id: Optional[str] = Field(default=None, description="消息ID")
    file_name: Optional[str] = Field(default=None, description="附件文件名")
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
    attachment_id: Optional[str] = Field(default=None, description="附件ID")
    mime_type: Optional[str] = Field(default=None, description="附件 MIME 类型")
    kind: Optional[str] = Field(default=None, description="附件类型")
    size: Optional[int] = Field(default=None, description="附件大小")
    storage_provider: Optional[str] = Field(default=None, description="存储提供方")
    storage_key: Optional[str] = Field(default=None, description="存储 key")
    public_url: Optional[str] = Field(default=None, description="公开 URL")
    expires_at: Optional[int] = Field(default=None, description="URL 过期时间")
    parse_status: Optional[str] = Field(default=None, description="解析状态")
    parse_error: Optional[str] = Field(default=None, description="解析错误")
    text_preview: Optional[str] = Field(default=None, description="文本预览")
    full_text: Optional[str] = Field(default=None, description="解析全文")
    summary: Optional[str] = Field(default=None, description="解析摘要")
    structured_json: Optional[dict] = Field(default=None, description="结构化解析结果")
    page_count: Optional[int] = Field(default=None, description="页数")
    sheet_count: Optional[int] = Field(default=None, description="sheet 数")
    chunks: Optional[list] = Field(default=None, description="附件分块结果")


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

        if operation_type == "list_attachments":
            data = list_session_attachments(state.session_id, user_id=state.user_id)
            return _success({"attachments": data}, "会话附件已获取")

        if operation_type == "get_attachment":
            attachment_id = state.attachment_id or metadata.get("attachment_id")
            if not attachment_id:
                return _failure("attachment_id 不能为空", error_code="ATTACHMENT_ID_REQUIRED")
            attachment, content, chunks = get_attachment_detail(
                attachment_id,
                session_id=state.session_id,
                user_id=state.user_id,
            )
            return _success({"attachment": attachment, "content": content, "chunks": chunks}, "附件详情已获取")

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

        if operation_type == "upsert_attachment":
            attachment_payload = metadata.get("attachment") if isinstance(metadata.get("attachment"), dict) else {}
            attachment_id = state.attachment_id or attachment_payload.get("attachment_id") or attachment_payload.get("id")
            if not state.user_id:
                return _failure("user_id 不能为空", error_code="USER_ID_REQUIRED")
            if not attachment_id:
                return _failure("attachment_id 不能为空", error_code="ATTACHMENT_ID_REQUIRED")
            name = state.file_name or attachment_payload.get("name") or attachment_payload.get("file_name")
            mime_type = state.mime_type or attachment_payload.get("mime_type") or attachment_payload.get("mimeType")
            kind = state.kind or attachment_payload.get("kind")
            size = state.size if state.size is not None else attachment_payload.get("size")
            if not name or not mime_type or not kind or size is None:
                return _failure("附件基础字段不完整", error_code="ATTACHMENT_FIELDS_REQUIRED")
            data = upsert_attachment(
                attachment_id=attachment_id,
                session_id=state.session_id,
                user_id=state.user_id,
                team_id=state.team_id,
                name=name,
                mime_type=mime_type,
                kind=kind,
                size=int(size),
                storage_provider=state.storage_provider or attachment_payload.get("storage_provider"),
                storage_key=state.storage_key or attachment_payload.get("storage_key"),
                public_url=state.public_url or attachment_payload.get("public_url"),
                file_key=state.file_key if state.file_key is not None else attachment_payload.get("file_key"),
                expires_at=state.expires_at if state.expires_at is not None else attachment_payload.get("expires_at"),
                parse_status=state.parse_status or attachment_payload.get("parse_status") or 'pending',
                parse_error=state.parse_error if state.parse_error is not None else attachment_payload.get("parse_error"),
                text_preview=state.text_preview if state.text_preview is not None else attachment_payload.get("text_preview"),
                metadata=attachment_payload.get("metadata") if isinstance(attachment_payload.get("metadata"), dict) else metadata,
                created_at=state.created_at if state.created_at is not None else attachment_payload.get("created_at"),
            )
            return _success({"attachment": data}, "会话附件已保存")

        if operation_type == "upsert_attachment_content":
            attachment_payload = metadata.get("attachment") if isinstance(metadata.get("attachment"), dict) else {}
            attachment_id = state.attachment_id or attachment_payload.get("attachment_id") or attachment_payload.get("id")
            if not attachment_id:
                return _failure("attachment_id 不能为空", error_code="ATTACHMENT_ID_REQUIRED")
            data = upsert_attachment_content(
                attachment_id=attachment_id,
                full_text=state.full_text if state.full_text is not None else attachment_payload.get("full_text"),
                summary=state.summary if state.summary is not None else attachment_payload.get("summary"),
                structured_json=state.structured_json if state.structured_json is not None else attachment_payload.get("structured_json"),
                page_count=state.page_count if state.page_count is not None else attachment_payload.get("page_count"),
                sheet_count=state.sheet_count if state.sheet_count is not None else attachment_payload.get("sheet_count"),
                chunks=state.chunks if state.chunks is not None else attachment_payload.get("chunks"),
            )
            return _success({"content": data, "chunks": list_attachment_chunks(attachment_id)}, "附件解析结果已保存")

        if operation_type == "clear_state":
            removed = clear_session_state(state.session_id, user_id=state.user_id)
            return _success({"removed": removed}, "会话状态已清理")

        return _failure(f"不支持的操作类型: {operation_type}", code=400, error_code="UNSUPPORTED_OPERATION")
    except Exception as exc:
        logger.error(f"Mars Assistant Session 操作失败: {exc}")
        return _failure(f"Mars Assistant Session 操作失败: {str(exc)}", code=500, error_code="INTERNAL_ERROR")
