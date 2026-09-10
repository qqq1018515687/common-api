import logging
from typing import Optional

from coze_coding_utils.runtime_ctx.context import Context
from langchain_core.runnables import RunnableConfig
from langgraph.runtime import Runtime
from pydantic import BaseModel, Field

from storage.database.mars_assistant_session_manager import (
    clear_session_state,
    create_agent_run,
    get_agent_run,
    get_attachment_detail,
    get_session_state,
    list_attachment_chunks,
    list_agent_runs,
    list_session_attachments,
    list_session_artifacts,
    patch_session_state,
    update_agent_run,
    upsert_attachment,
    upsert_attachment_content,
    upsert_session_state,
    upsert_session_artifact,
)

logger = logging.getLogger(__name__)


class MarsAssistantSessionInput(BaseModel):
    operation_type: Optional[str] = Field(default=None, description="会话、附件、产物和 Agent Run 操作类型")
    session_id: Optional[str] = Field(default=None, description="火星助手会话ID")
    user_id: Optional[str] = Field(default=None, description="用户ID")
    team_id: Optional[str] = Field(default=None, description="团队ID")
    metadata: Optional[dict] = Field(default=None, description="扩展元数据")
    message_id: Optional[str] = Field(default=None, description="消息ID")
    file_name: Optional[str] = Field(default=None, description="附件文件名")
    artifact_id: Optional[str] = Field(default=None, description="产物ID")
    artifact_type: Optional[str] = Field(default=None, description="产物类型")
    artifact_role: Optional[str] = Field(default=None, description="产物角色")
    url: Optional[str] = Field(default=None, description="产物URL")
    file_key: Optional[str] = Field(default=None, description="文件Key")
    source_artifact_id: Optional[str] = Field(default=None, description="来源产物ID")
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
    provided_fields: Optional[list[str]] = Field(default=None, description="请求中显式提供的字段名")


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
        artifact_payload = metadata.get("artifact") if isinstance(metadata.get("artifact"), dict) else {}
        run_payload = metadata.get("run") if isinstance(metadata.get("run"), dict) else {}
        if not state.session_id:
            return _failure("session_id 不能为空", error_code="SESSION_ID_REQUIRED")

        if operation_type == "get_state":
            if not state.user_id:
                return _failure("user_id 不能为空", error_code="USER_ID_REQUIRED")
            data = get_session_state(state.session_id, user_id=state.user_id)
            return _success({"session": data}, "会话状态已获取")

        if operation_type == "list_artifacts":
            if not state.user_id:
                return _failure("user_id 不能为空", error_code="USER_ID_REQUIRED")
            data = list_session_artifacts(state.session_id, user_id=state.user_id)
            return _success({"artifacts": data}, "会话产物已获取")

        if operation_type == "list_attachments":
            if not state.user_id:
                return _failure("user_id 不能为空", error_code="USER_ID_REQUIRED")
            data = list_session_attachments(state.session_id, user_id=state.user_id)
            return _success({"attachments": data}, "会话附件已获取")

        if operation_type == "get_attachment":
            if not state.user_id:
                return _failure("user_id 不能为空", error_code="USER_ID_REQUIRED")
            attachment_id = state.attachment_id or metadata.get("attachment_id")
            if not attachment_id:
                return _failure("attachment_id 不能为空", error_code="ATTACHMENT_ID_REQUIRED")
            attachment, content, chunks = get_attachment_detail(
                attachment_id,
                session_id=state.session_id,
                user_id=state.user_id,
            )
            return _success({"attachment": attachment, "content": content, "chunks": chunks}, "附件详情已获取")

        if operation_type == "create_run":
            if not state.user_id:
                return _failure("user_id 不能为空", error_code="USER_ID_REQUIRED")
            run_id = run_payload.get("run_id") or run_payload.get("id")
            idempotency_key = run_payload.get("idempotency_key")
            status = run_payload.get("status")
            if not run_id:
                return _failure("run.id 不能为空", error_code="RUN_ID_REQUIRED")
            if not idempotency_key:
                return _failure("run.idempotency_key 不能为空", error_code="IDEMPOTENCY_KEY_REQUIRED")
            if not status:
                return _failure("run.status 不能为空", error_code="RUN_STATUS_REQUIRED")
            data = create_agent_run(
                run_id=run_id,
                conversation_id=state.session_id,
                user_id=state.user_id,
                team_id=run_payload.get("team_id", state.team_id),
                model=run_payload.get("model"),
                provider=run_payload.get("provider"),
                provider_task_id=run_payload.get("provider_task_id"),
                status=status,
                idempotency_key=idempotency_key,
                continuation_of_run_id=run_payload.get("continuation_of_run_id"),
                tool_name=run_payload.get("tool_name"),
                tool_arguments=run_payload.get("tool_arguments"),
                input_resources=run_payload.get("input_resources"),
                result_artifact_ids=run_payload.get("result_artifact_ids"),
                error=run_payload.get("error"),
                created_at=run_payload.get("created_at"),
                completed_at=run_payload.get("completed_at"),
            )
            return _success({"run": data}, "Agent Run 已创建")

        if operation_type == "get_run":
            if not state.user_id:
                return _failure("user_id 不能为空", error_code="USER_ID_REQUIRED")
            run_id = run_payload.get("run_id") or run_payload.get("id")
            if not run_id:
                return _failure("run.id 不能为空", error_code="RUN_ID_REQUIRED")
            data = get_agent_run(run_id, conversation_id=state.session_id, user_id=state.user_id)
            return _success({"run": data}, "Agent Run 已获取")

        if operation_type == "update_run":
            if not state.user_id:
                return _failure("user_id 不能为空", error_code="USER_ID_REQUIRED")
            run_id = run_payload.get("run_id") or run_payload.get("id")
            updates = run_payload.get("updates")
            if not run_id:
                return _failure("run.id 不能为空", error_code="RUN_ID_REQUIRED")
            if not isinstance(updates, dict) or not updates:
                return _failure("run.updates 不能为空", error_code="RUN_UPDATES_REQUIRED")
            data = update_agent_run(
                run_id=run_id,
                conversation_id=state.session_id,
                user_id=state.user_id,
                updates=updates,
            )
            return _success({"run": data}, "Agent Run 已更新")

        if operation_type == "list_runs":
            if not state.user_id:
                return _failure("user_id 不能为空", error_code="USER_ID_REQUIRED")
            data = list_agent_runs(
                state.session_id,
                user_id=state.user_id,
                status=run_payload.get("status"),
                tool_name=run_payload.get("tool_name"),
                limit=int(run_payload.get("limit") or 100),
            )
            return _success({"runs": data}, "Agent Run 列表已获取")

        if operation_type == "upsert_state":
            if not state.user_id:
                return _failure("user_id 不能为空", error_code="USER_ID_REQUIRED")
            data = upsert_session_state(
                session_id=state.session_id,
                user_id=state.user_id,
                team_id=state.team_id,
                metadata=state.metadata,
            )
            return _success({"session": data}, "会话状态已保存")

        if operation_type == "patch_state":
            if not state.user_id:
                return _failure("user_id 不能为空", error_code="USER_ID_REQUIRED")
            update_fields = set(state.provided_fields or []) & {"metadata"}
            data = patch_session_state(
                session_id=state.session_id,
                user_id=state.user_id,
                team_id=state.team_id,
                metadata=state.metadata,
                update_fields=update_fields,
            )
            return _success({"session": data}, "会话状态已更新")

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
                source_artifact_id=state.source_artifact_id if state.source_artifact_id is not None else artifact_payload.get("source_artifact_id"),
                metadata=artifact_payload.get("metadata") if isinstance(artifact_payload.get("metadata"), dict) else {},
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
                metadata=attachment_payload.get("metadata") if isinstance(attachment_payload.get("metadata"), dict) else {},
                created_at=state.created_at if state.created_at is not None else attachment_payload.get("created_at"),
            )
            return _success({"attachment": data}, "会话附件已保存")

        if operation_type == "upsert_attachment_content":
            attachment_payload = metadata.get("attachment") if isinstance(metadata.get("attachment"), dict) else {}
            attachment_id = state.attachment_id or attachment_payload.get("attachment_id") or attachment_payload.get("id")
            if not state.user_id:
                return _failure("user_id 不能为空", error_code="USER_ID_REQUIRED")
            if not attachment_id:
                return _failure("attachment_id 不能为空", error_code="ATTACHMENT_ID_REQUIRED")
            data = upsert_attachment_content(
                attachment_id=attachment_id,
                session_id=state.session_id,
                user_id=state.user_id,
                full_text=state.full_text if state.full_text is not None else attachment_payload.get("full_text"),
                summary=state.summary if state.summary is not None else attachment_payload.get("summary"),
                structured_json=state.structured_json if state.structured_json is not None else attachment_payload.get("structured_json"),
                page_count=state.page_count if state.page_count is not None else attachment_payload.get("page_count"),
                sheet_count=state.sheet_count if state.sheet_count is not None else attachment_payload.get("sheet_count"),
                chunks=state.chunks if state.chunks is not None else attachment_payload.get("chunks"),
            )
            return _success({"content": data, "chunks": list_attachment_chunks(attachment_id)}, "附件解析结果已保存")

        if operation_type == "clear_state":
            if not state.user_id:
                return _failure("user_id 不能为空", error_code="USER_ID_REQUIRED")
            removed = clear_session_state(state.session_id, user_id=state.user_id)
            return _success({"removed": removed}, "会话状态已清理")

        return _failure(f"不支持的操作类型: {operation_type}", code=400, error_code="UNSUPPORTED_OPERATION")
    except Exception as exc:
        logger.error(f"Mars Assistant Session 操作失败: {exc}")
        return _failure(f"Mars Assistant Session 操作失败: {str(exc)}", code=500, error_code="INTERNAL_ERROR")
