from __future__ import annotations

import math
import time
import json
from typing import Optional

from sqlalchemy import text

from storage.database.db import get_engine


def _now_ms() -> int:
    return int(time.time() * 1000)


def _compact_image_tool_arguments(value: object) -> dict:
    if not isinstance(value, dict):
        return {}
    compact = {}
    for key in ("requestedImageCount", "sequenceStart"):
        item = value.get(key)
        if isinstance(item, int) and not isinstance(item, bool) and item > 0:
            compact[key] = item
    for key in ("requestedAspectRatio", "model"):
        item = value.get(key)
        if isinstance(item, str) and item.strip():
            compact[key] = item.strip()
    return compact


def _compact_session_metadata(value: object) -> dict:
    if not isinstance(value, dict):
        return {}
    return {
        key: value[key]
        for key in ("activeEditBaseArtifactId", "latestGeneratedArtifactId")
        if isinstance(value.get(key), str) and value[key].strip()
    }


def _compact_artifact_metadata(value: object) -> dict:
    if not isinstance(value, dict):
        return {}
    compact = {}
    if isinstance(value.get("runId"), str) and value["runId"].strip():
        compact["runId"] = value["runId"].strip()
    if isinstance(value.get("sequence"), int) and not isinstance(value["sequence"], bool) and value["sequence"] > 0:
        compact["sequence"] = value["sequence"]
    if isinstance(value.get("frameIndex"), int) and not isinstance(value["frameIndex"], bool) and value["frameIndex"] > 0:
        compact["frameIndex"] = value["frameIndex"]
    if isinstance(value.get("frameTitle"), str) and value["frameTitle"].strip():
        compact["frameTitle"] = value["frameTitle"].strip()
    frame = value.get("frame")
    if isinstance(frame, dict):
        compact_frame = {}
        if isinstance(frame.get("index"), int) and not isinstance(frame["index"], bool) and frame["index"] > 0:
            compact_frame["index"] = frame["index"]
        if isinstance(frame.get("title"), str) and frame["title"].strip():
            compact_frame["title"] = frame["title"].strip()
        if compact_frame:
            compact["frame"] = compact_frame
    return compact


def _compact_attachment_metadata(value: object) -> dict:
    if not isinstance(value, dict):
        return {}
    compact = {}
    summary = value.get("summary")
    if isinstance(summary, str) and summary.strip():
        compact["summary"] = summary.strip()
    content_length = value.get("contentLength")
    if isinstance(content_length, int) and not isinstance(content_length, bool) and content_length >= 0:
        compact["contentLength"] = content_length
    return compact


def _require_owned_resource(conn, *, resource_type: str, resource_id: str, conversation_id: str, user_id: str) -> None:
    table_name = "mars_assistant_attachments" if resource_type == "attachment" else "mars_assistant_artifacts"
    id_column = "id"
    session_column = "session_id"
    row = conn.execute(
        text(f"SELECT {id_column} FROM {table_name} WHERE {id_column} = :resource_id AND {session_column} = :conversation_id AND user_id = :user_id"),
        {"resource_id": resource_id, "conversation_id": conversation_id, "user_id": user_id},
    ).mappings().first()
    if not row:
        raise ValueError("Run 引用资源不属于当前用户和会话")


def create_agent_run(
    *,
    run_id: str,
    conversation_id: str,
    user_id: str,
    idempotency_key: str,
    status: str,
    team_id: Optional[str] = None,
    model: Optional[str] = None,
    provider: Optional[str] = None,
    provider_task_id: Optional[str] = None,
    continuation_of_run_id: Optional[str] = None,
    tool_name: Optional[str] = None,
    tool_arguments: Optional[dict] = None,
    input_resources: Optional[list] = None,
    result_artifact_ids: Optional[list] = None,
    error: Optional[dict] = None,
    created_at: Optional[int] = None,
    completed_at: Optional[int] = None,
) -> dict:
    now = _now_ms()
    if tool_name != "generate_images":
        raise ValueError("只允许创建 generate_images Run")
    tool_arguments = _compact_image_tool_arguments(tool_arguments)
    if input_resources is not None and not isinstance(input_resources, list):
        raise ValueError("Run 输入资源格式无效")
    if result_artifact_ids is not None and not isinstance(result_artifact_ids, list):
        raise ValueError("Run 结果产物格式无效")
    with get_engine().begin() as conn:
        if continuation_of_run_id:
            parent = conn.execute(
                text("""
                    SELECT id FROM mars_agent_runs
                    WHERE id = :continuation_of_run_id
                      AND conversation_id = :conversation_id
                      AND user_id = :user_id
                """),
                {
                    "continuation_of_run_id": continuation_of_run_id,
                    "conversation_id": conversation_id,
                    "user_id": user_id,
                },
            ).mappings().first()
            if not parent:
                raise ValueError("continuation_of_run_id 不属于当前用户和会话")
        compact_input_resources = []
        for resource in input_resources or []:
            if not isinstance(resource, dict):
                raise ValueError("Run 输入资源格式无效")
            resource_type = resource.get("resource_type")
            resource_id = resource.get("resource_id")
            if resource_type not in {"attachment", "artifact"} or not isinstance(resource_id, str):
                raise ValueError("Run 输入资源格式无效")
            _require_owned_resource(
                conn,
                resource_type=resource_type,
                resource_id=resource_id,
                conversation_id=conversation_id,
                user_id=user_id,
            )
            binding_role = resource.get("binding_role")
            compact_input_resources.append({
                "resource_type": resource_type,
                "resource_id": resource_id,
                "binding_role": binding_role if isinstance(binding_role, str) else "general_reference",
            })
        compact_result_artifact_ids = []
        for artifact_id in result_artifact_ids or []:
            if not isinstance(artifact_id, str):
                raise ValueError("Run 结果产物格式无效")
            _require_owned_resource(
                conn,
                resource_type="artifact",
                resource_id=artifact_id,
                conversation_id=conversation_id,
                user_id=user_id,
            )
            compact_result_artifact_ids.append(artifact_id)
        row = conn.execute(
            text("""
                INSERT INTO mars_agent_runs
                    (id, conversation_id, user_id, team_id, model, provider, provider_task_id,
                     status, idempotency_key, continuation_of_run_id, tool_name, tool_arguments,
                     input_resources, result_artifact_ids, error, created_at, updated_at, completed_at)
                SELECT
                    :id, :conversation_id, :user_id, :team_id, :model, :provider, :provider_task_id,
                    :status, :idempotency_key, :continuation_of_run_id, :tool_name,
                    CAST(:tool_arguments AS JSONB), CAST(:input_resources AS JSONB),
                    CAST(:result_artifact_ids AS JSONB), CAST(:error AS JSONB),
                    :created_at, :updated_at, :completed_at
                FROM mars_assistant_sessions
                WHERE session_id = :conversation_id AND user_id = :user_id
                ON CONFLICT (user_id, conversation_id, idempotency_key) DO UPDATE SET
                    idempotency_key = EXCLUDED.idempotency_key
                RETURNING *
            """),
            {
                "id": run_id,
                "conversation_id": conversation_id,
                "user_id": user_id,
                "team_id": team_id,
                "model": model,
                "provider": provider,
                "provider_task_id": provider_task_id,
                "status": status,
                "idempotency_key": idempotency_key,
                "continuation_of_run_id": continuation_of_run_id,
                "tool_name": tool_name,
                "tool_arguments": json.dumps(tool_arguments, ensure_ascii=False),
                "input_resources": json.dumps(compact_input_resources, ensure_ascii=False),
                "result_artifact_ids": json.dumps(compact_result_artifact_ids, ensure_ascii=False),
                "error": json.dumps(error, ensure_ascii=False),
                "created_at": created_at or now,
                "updated_at": now,
                "completed_at": completed_at,
            },
        ).mappings().first()
        if not row:
            raise PermissionError("会话不存在或无权访问")
        return dict(row)


def get_agent_run(run_id: str, *, conversation_id: str, user_id: str) -> Optional[dict]:
    with get_engine().begin() as conn:
        row = conn.execute(
            text("""
                SELECT r.*
                FROM mars_agent_runs r
                INNER JOIN mars_assistant_sessions s
                    ON s.session_id = r.conversation_id AND s.user_id = r.user_id
                WHERE r.id = :run_id
                  AND r.conversation_id = :conversation_id
                  AND r.user_id = :user_id
            """),
            {"run_id": run_id, "conversation_id": conversation_id, "user_id": user_id},
        ).mappings().first()
        return dict(row) if row else None


def update_agent_run(
    *,
    run_id: str,
    conversation_id: str,
    user_id: str,
    updates: dict,
) -> dict:
    field_sql = {
        "team_id": "team_id = :team_id",
        "model": "model = :model",
        "provider": "provider = :provider",
        "provider_task_id": "provider_task_id = :provider_task_id",
        "status": "status = :status",
        "result_artifact_ids": "result_artifact_ids = CAST(:result_artifact_ids AS JSONB)",
        "error": "error = CAST(:error AS JSONB)",
        "completed_at": "completed_at = :completed_at",
    }
    unsupported_fields = set(updates) - set(field_sql)
    if unsupported_fields:
        raise ValueError(f"不支持的 run 更新字段: {', '.join(sorted(unsupported_fields))}")
    selected_fields = [field for field in field_sql if field in updates]
    if not selected_fields:
        raise ValueError("run 更新字段不能为空")
    result_artifact_ids = updates.get("result_artifact_ids")
    if "result_artifact_ids" in updates and not isinstance(result_artifact_ids, list):
        raise ValueError("Run 结果产物格式无效")
    params = {
        "run_id": run_id,
        "conversation_id": conversation_id,
        "user_id": user_id,
        "updated_at": _now_ms(),
        **{field: updates[field] for field in selected_fields},
    }
    for field in ("result_artifact_ids", "error"):
        if field in selected_fields:
            params[field] = json.dumps(updates[field], ensure_ascii=False)
    assignments = [field_sql[field] for field in selected_fields]
    assignments.append("updated_at = :updated_at")
    with get_engine().begin() as conn:
        compact_result_artifact_ids = []
        for artifact_id in result_artifact_ids or []:
            if not isinstance(artifact_id, str):
                raise ValueError("Run 结果产物格式无效")
            _require_owned_resource(
                conn,
                resource_type="artifact",
                resource_id=artifact_id,
                conversation_id=conversation_id,
                user_id=user_id,
            )
            compact_result_artifact_ids.append(artifact_id)
        if "result_artifact_ids" in selected_fields:
            params["result_artifact_ids"] = json.dumps(compact_result_artifact_ids, ensure_ascii=False)
        row = conn.execute(
            text(f"""
                UPDATE mars_agent_runs r
                SET {', '.join(assignments)}
                FROM mars_assistant_sessions s
                WHERE r.id = :run_id
                  AND r.conversation_id = :conversation_id
                  AND r.user_id = :user_id
                  AND s.session_id = r.conversation_id
                  AND s.user_id = r.user_id
                RETURNING r.*
            """),
            params,
        ).mappings().first()
        if not row:
            raise PermissionError("Run 不存在或无权访问")
        return dict(row)


def list_agent_runs(
    conversation_id: str,
    *,
    user_id: str,
    status: Optional[str] = None,
    tool_name: Optional[str] = None,
    limit: int = 100,
) -> list[dict]:
    status_clause = " AND r.status = :status" if status else ""
    tool_clause = " AND r.tool_name = :tool_name" if tool_name else ""
    params = {
        "conversation_id": conversation_id,
        "user_id": user_id,
        "status": status,
        "tool_name": tool_name,
        "limit": max(1, min(limit, 300)),
    }
    with get_engine().begin() as conn:
        rows = conn.execute(
            text(f"""
                SELECT r.*
                FROM mars_agent_runs r
                INNER JOIN mars_assistant_sessions s
                    ON s.session_id = r.conversation_id AND s.user_id = r.user_id
                WHERE r.conversation_id = :conversation_id AND r.user_id = :user_id{status_clause}{tool_clause}
                ORDER BY r.created_at DESC
                LIMIT :limit
            """),
            params,
        ).mappings().all()
        return [dict(row) for row in rows]


def list_session_attachments(session_id: str, user_id: Optional[str] = None) -> list[dict]:
    owner_clause = " AND user_id = :user_id" if user_id else ""
    params = {"session_id": session_id}
    if user_id:
        params["user_id"] = user_id
    with get_engine().begin() as conn:
        rows = conn.execute(
            text(f"SELECT * FROM mars_assistant_attachments WHERE session_id = :session_id{owner_clause} ORDER BY created_at ASC"),
            params,
        ).mappings().all()
        return [dict(row) for row in rows]


def get_attachment(attachment_id: str, user_id: Optional[str] = None) -> Optional[dict]:
    owner_clause = " AND user_id = :user_id" if user_id else ""
    params = {"attachment_id": attachment_id}
    if user_id:
        params["user_id"] = user_id
    with get_engine().begin() as conn:
        row = conn.execute(
            text(f"SELECT * FROM mars_assistant_attachments WHERE id = :attachment_id{owner_clause}"),
            params,
        ).mappings().first()
        return dict(row) if row else None


def get_attachment_detail(
    attachment_id: str,
    *,
    session_id: str,
    user_id: Optional[str] = None,
) -> tuple[Optional[dict], Optional[dict], list[dict]]:
    owner_clause = " AND a.user_id = :user_id" if user_id else ""
    params = {
        "attachment_id": attachment_id,
        "session_id": session_id,
    }
    if user_id:
        params["user_id"] = user_id

    with get_engine().begin() as conn:
        attachment_row = conn.execute(
            text(f"SELECT a.* FROM mars_assistant_attachments a WHERE a.id = :attachment_id AND a.session_id = :session_id{owner_clause}"),
            params,
        ).mappings().first()
        if not attachment_row:
            return None, None, []

        content_row = conn.execute(
            text(f"""
                SELECT c.*
                FROM mars_assistant_attachment_contents c
                INNER JOIN mars_assistant_attachments a ON a.id = c.attachment_id
                WHERE c.attachment_id = :attachment_id
                  AND a.session_id = :session_id{owner_clause}
            """),
            params,
        ).mappings().first()

        chunk_rows = conn.execute(
            text(f"""
                SELECT ch.*
                FROM mars_assistant_attachment_chunks ch
                INNER JOIN mars_assistant_attachments a ON a.id = ch.attachment_id
                WHERE ch.attachment_id = :attachment_id
                  AND a.session_id = :session_id{owner_clause}
                ORDER BY ch.chunk_index ASC
            """),
            params,
        ).mappings().all()

        return (
            dict(attachment_row),
            dict(content_row) if content_row else None,
            [dict(row) for row in chunk_rows],
        )


def get_attachment_content(attachment_id: str) -> Optional[dict]:
    with get_engine().begin() as conn:
        row = conn.execute(
            text("SELECT * FROM mars_assistant_attachment_contents WHERE attachment_id = :attachment_id"),
            {"attachment_id": attachment_id},
        ).mappings().first()
        return dict(row) if row else None


def list_attachment_chunks(attachment_id: str) -> list[dict]:
    with get_engine().begin() as conn:
        rows = conn.execute(
            text("SELECT * FROM mars_assistant_attachment_chunks WHERE attachment_id = :attachment_id ORDER BY chunk_index ASC"),
            {"attachment_id": attachment_id},
        ).mappings().all()
        return [dict(row) for row in rows]


def upsert_attachment(
    *,
    attachment_id: str,
    session_id: str,
    user_id: str,
    name: str,
    mime_type: str,
    kind: str,
    size: int,
    team_id: Optional[str] = None,
    storage_provider: Optional[str] = None,
    storage_key: Optional[str] = None,
    public_url: Optional[str] = None,
    file_key: Optional[str] = None,
    expires_at: Optional[int] = None,
    parse_status: str = 'pending',
    parse_error: Optional[str] = None,
    text_preview: Optional[str] = None,
    metadata: Optional[dict] = None,
    created_at: Optional[int] = None,
) -> dict:
    now = _now_ms()
    created_at = created_at or now
    with get_engine().begin() as conn:
        row = conn.execute(
            text("""
                INSERT INTO mars_assistant_attachments
                    (id, session_id, user_id, team_id, name, mime_type, kind, size, storage_provider, storage_key, public_url, file_key, expires_at, parse_status, parse_error, text_preview, metadata, created_at, updated_at)
                SELECT
                    :id, :session_id, :user_id, :team_id, :name, :mime_type, :kind, :size, :storage_provider, :storage_key, :public_url, :file_key, :expires_at, :parse_status, :parse_error, :text_preview, CAST(:metadata AS JSONB), :created_at, :updated_at
                FROM mars_assistant_sessions
                WHERE session_id = :session_id AND user_id = :user_id
                ON CONFLICT (id) DO UPDATE SET
                    team_id = EXCLUDED.team_id,
                    name = EXCLUDED.name,
                    mime_type = EXCLUDED.mime_type,
                    kind = EXCLUDED.kind,
                    size = EXCLUDED.size,
                    storage_provider = EXCLUDED.storage_provider,
                    storage_key = EXCLUDED.storage_key,
                    public_url = EXCLUDED.public_url,
                    file_key = EXCLUDED.file_key,
                    expires_at = EXCLUDED.expires_at,
                    parse_status = EXCLUDED.parse_status,
                    parse_error = EXCLUDED.parse_error,
                    text_preview = EXCLUDED.text_preview,
                    metadata = EXCLUDED.metadata,
                    updated_at = EXCLUDED.updated_at
                WHERE mars_assistant_attachments.user_id = EXCLUDED.user_id
                  AND mars_assistant_attachments.session_id = EXCLUDED.session_id
                RETURNING *
            """),
            {
                "id": attachment_id,
                "session_id": session_id,
                "user_id": user_id,
                "team_id": team_id,
                "name": name,
                "mime_type": mime_type,
                "kind": kind,
                "size": size,
                "storage_provider": storage_provider,
                "storage_key": storage_key,
                "public_url": public_url,
                "file_key": file_key,
                "expires_at": expires_at,
                "parse_status": parse_status,
                "parse_error": parse_error,
                "text_preview": text_preview,
                "metadata": json.dumps(_compact_attachment_metadata(metadata), ensure_ascii=False),
                "created_at": created_at,
                "updated_at": now,
            },
        ).mappings().first()
        if not row:
            raise PermissionError("附件不存在或无权访问")
        return dict(row)


def upsert_attachment_content(
    *,
    attachment_id: str,
    session_id: str,
    user_id: str,
    full_text: Optional[str],
    summary: Optional[str],
    structured_json: Optional[dict],
    page_count: Optional[int] = None,
    sheet_count: Optional[int] = None,
    chunks: Optional[list[dict]] = None,
) -> dict:
    now = _now_ms()
    with get_engine().begin() as conn:
        attachment = conn.execute(
            text("""
                SELECT id
                FROM mars_assistant_attachments
                WHERE id = :attachment_id
                  AND session_id = :session_id
                  AND user_id = :user_id
                FOR UPDATE
            """),
            {
                "attachment_id": attachment_id,
                "session_id": session_id,
                "user_id": user_id,
            },
        ).mappings().first()
        if not attachment:
            raise PermissionError("附件不存在或无权访问")
        row = conn.execute(
            text("""
                INSERT INTO mars_assistant_attachment_contents
                    (attachment_id, full_text, summary, structured_json, page_count, sheet_count, updated_at)
                VALUES
                    (:attachment_id, :full_text, :summary, CAST(:structured_json AS JSONB), :page_count, :sheet_count, :updated_at)
                ON CONFLICT (attachment_id) DO UPDATE SET
                    full_text = EXCLUDED.full_text,
                    summary = EXCLUDED.summary,
                    structured_json = EXCLUDED.structured_json,
                    page_count = EXCLUDED.page_count,
                    sheet_count = EXCLUDED.sheet_count,
                    updated_at = EXCLUDED.updated_at
            """),
            {
                "attachment_id": attachment_id,
                "full_text": full_text,
                "summary": summary,
                "structured_json": json.dumps(structured_json, ensure_ascii=False),
                "page_count": page_count,
                "sheet_count": sheet_count,
                "updated_at": now,
            },
        )
        conn.execute(
            text("DELETE FROM mars_assistant_attachment_chunks WHERE attachment_id = :attachment_id"),
            {"attachment_id": attachment_id},
        )
        for index, chunk in enumerate(chunks or []):
            chunk_text = str(chunk.get('chunk_text') or '').strip()
            if not chunk_text:
                continue
            conn.execute(
                text("""
                    INSERT INTO mars_assistant_attachment_chunks
                        (id, attachment_id, chunk_index, chunk_text, source_type, source_label, page_number, sheet_name, token_estimate, created_at)
                    VALUES
                        (:id, :attachment_id, :chunk_index, :chunk_text, :source_type, :source_label, :page_number, :sheet_name, :token_estimate, :created_at)
                """),
                {
                    "id": f"{attachment_id}_{index}",
                    "attachment_id": attachment_id,
                    "chunk_index": index,
                    "chunk_text": chunk_text,
                    "source_type": chunk.get('source_type'),
                    "source_label": chunk.get('source_label'),
                    "page_number": chunk.get('page_number'),
                    "sheet_name": chunk.get('sheet_name'),
                    "token_estimate": chunk.get('token_estimate') or math.ceil(len(chunk_text) / 4),
                    "created_at": now,
                },
            )
        row = conn.execute(
            text("SELECT * FROM mars_assistant_attachment_contents WHERE attachment_id = :attachment_id"),
            {"attachment_id": attachment_id},
        ).mappings().first()
        return dict(row)


def get_session_state(session_id: str, user_id: Optional[str] = None) -> Optional[dict]:
    owner_clause = " AND user_id = :user_id" if user_id else ""
    params = {"session_id": session_id}
    if user_id:
        params["user_id"] = user_id
    with get_engine().begin() as conn:
        row = conn.execute(
            text(f"SELECT * FROM mars_assistant_sessions WHERE session_id = :session_id{owner_clause}"),
            params,
        ).mappings().first()
        return dict(row) if row else None


def upsert_session_state(
    *,
    session_id: str,
    user_id: str,
    team_id: Optional[str] = None,
    metadata: Optional[dict] = None,
) -> dict:
    now = _now_ms()
    compact_metadata = _compact_session_metadata(metadata)
    with get_engine().begin() as conn:
        row = conn.execute(
            text("""
                INSERT INTO mars_assistant_sessions
                    (session_id, user_id, team_id, metadata, created_at, updated_at)
                VALUES
                    (:session_id, :user_id, :team_id, CAST(:metadata AS JSONB), :created_at, :updated_at)
                ON CONFLICT (session_id) DO UPDATE SET
                    team_id = EXCLUDED.team_id,
                    metadata = COALESCE(EXCLUDED.metadata, '{}'::jsonb),
                    updated_at = EXCLUDED.updated_at
                WHERE mars_assistant_sessions.user_id = EXCLUDED.user_id
                RETURNING *
            """),
            {
                "session_id": session_id,
                "user_id": user_id,
                "team_id": team_id,
                "metadata": json.dumps(compact_metadata, ensure_ascii=False) if compact_metadata else None,
                "created_at": now,
                "updated_at": now,
            },
        ).mappings().first()
        if not row:
            raise PermissionError("会话不存在或无权访问")
        return dict(row)


def patch_session_state(
    *,
    session_id: str,
    user_id: str,
    team_id: Optional[str] = None,
    metadata: Optional[dict] = None,
    update_fields: set[str],
) -> dict:
    now = _now_ms()
    compact_metadata = _compact_session_metadata(metadata)
    field_sql = {
        "metadata": "metadata = CASE WHEN jsonb_typeof(mars_assistant_sessions.metadata) = 'object' THEN jsonb_strip_nulls(jsonb_build_object('activeEditBaseArtifactId', mars_assistant_sessions.metadata->'activeEditBaseArtifactId', 'latestGeneratedArtifactId', mars_assistant_sessions.metadata->'latestGeneratedArtifactId')) ELSE '{}'::jsonb END || CAST(:metadata AS JSONB)",
    }
    assignments = [field_sql[field] for field in field_sql if field in update_fields]
    assignments.extend([
        "team_id = COALESCE(:team_id, mars_assistant_sessions.team_id)",
        "updated_at = :updated_at",
    ])
    with get_engine().begin() as conn:
        row = conn.execute(
            text(f"""
                INSERT INTO mars_assistant_sessions
                    (session_id, user_id, team_id, metadata, created_at, updated_at)
                VALUES
                    (:session_id, :user_id, :team_id, CAST(:metadata AS JSONB), :created_at, :updated_at)
                ON CONFLICT (session_id) DO UPDATE SET
                    {', '.join(assignments)}
                WHERE mars_assistant_sessions.user_id = EXCLUDED.user_id
                RETURNING *
            """),
            {
                "session_id": session_id,
                "user_id": user_id,
                "team_id": team_id,
                "metadata": json.dumps(compact_metadata, ensure_ascii=False),
                "created_at": now,
                "updated_at": now,
            },
        ).mappings().first()
        if not row:
            raise PermissionError("会话不存在或无权访问")
        return dict(row)


def clear_session_state(session_id: str, user_id: Optional[str] = None) -> bool:
    owner_clause = " AND user_id = :user_id" if user_id else ""
    params = {"session_id": session_id}
    if user_id:
        params["user_id"] = user_id
    with get_engine().begin() as conn:
        result = conn.execute(
            text(f"DELETE FROM mars_assistant_sessions WHERE session_id = :session_id{owner_clause}"),
            params,
        )
        return bool(result.rowcount)


def list_session_artifacts(session_id: str, user_id: Optional[str] = None) -> list[dict]:
    owner_clause = " AND user_id = :user_id" if user_id else ""
    params = {"session_id": session_id}
    if user_id:
        params["user_id"] = user_id
    with get_engine().begin() as conn:
        rows = conn.execute(
            text(f"SELECT * FROM mars_assistant_artifacts WHERE session_id = :session_id{owner_clause} ORDER BY created_at ASC"),
            params,
        ).mappings().all()
        return [dict(row) for row in rows]


def upsert_session_artifact(
    *,
    artifact_id: str,
    session_id: str,
    user_id: str,
    team_id: Optional[str] = None,
    artifact_type: str,
    artifact_role: Optional[str] = None,
    message_id: Optional[str] = None,
    url: Optional[str] = None,
    file_key: Optional[str] = None,
    source_artifact_id: Optional[str] = None,
    metadata: Optional[dict] = None,
    created_at: Optional[int] = None,
) -> dict:
    now = _now_ms()
    created_at = created_at or now
    with get_engine().begin() as conn:
        if source_artifact_id:
            _require_owned_resource(
                conn,
                resource_type="artifact",
                resource_id=source_artifact_id,
                conversation_id=session_id,
                user_id=user_id,
            )
        row = conn.execute(
            text("""
                INSERT INTO mars_assistant_artifacts
                    (id, session_id, message_id, user_id, team_id, artifact_type, artifact_role, url, file_key, source_artifact_id, metadata, created_at, updated_at)
                SELECT
                    :id, :session_id, :message_id, :user_id, :team_id, :artifact_type, :artifact_role, :url, :file_key, :source_artifact_id, CAST(:metadata AS JSONB), :created_at, :updated_at
                FROM mars_assistant_sessions
                WHERE session_id = :session_id AND user_id = :user_id
                ON CONFLICT (id) DO UPDATE SET
                    message_id = EXCLUDED.message_id,
                    team_id = EXCLUDED.team_id,
                    artifact_type = EXCLUDED.artifact_type,
                    artifact_role = EXCLUDED.artifact_role,
                    url = EXCLUDED.url,
                    file_key = EXCLUDED.file_key,
                    source_artifact_id = EXCLUDED.source_artifact_id,
                    metadata = EXCLUDED.metadata,
                    updated_at = EXCLUDED.updated_at
                WHERE mars_assistant_artifacts.user_id = EXCLUDED.user_id
                  AND mars_assistant_artifacts.session_id = EXCLUDED.session_id
                RETURNING *
            """),
            {
                "id": artifact_id,
                "session_id": session_id,
                "message_id": message_id,
                "user_id": user_id,
                "team_id": team_id,
                "artifact_type": artifact_type,
                "artifact_role": artifact_role,
                "url": url,
                "file_key": file_key,
                "source_artifact_id": source_artifact_id,
                "metadata": json.dumps(_compact_artifact_metadata(metadata), ensure_ascii=False),
                "created_at": created_at,
                "updated_at": now,
            },
        ).mappings().first()
        if not row:
            raise PermissionError("产物不存在或无权访问")
        return dict(row)
