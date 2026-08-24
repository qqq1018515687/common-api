from __future__ import annotations

import time
import json
from typing import Optional

from sqlalchemy import text

from storage.database.db import get_engine


def _now_ms() -> int:
    return int(time.time() * 1000)


def ensure_mars_assistant_session_table() -> None:
    with get_engine().begin() as conn:
        conn.execute(text("""
            CREATE TABLE IF NOT EXISTS mars_assistant_sessions (
                session_id VARCHAR(64) PRIMARY KEY,
                user_id VARCHAR(64) NOT NULL,
                team_id VARCHAR(64),
                task_state JSONB,
                image_asset_state JSONB,
                metadata JSONB,
                created_at BIGINT NOT NULL,
                updated_at BIGINT NOT NULL
            )
        """))
        conn.execute(text("CREATE INDEX IF NOT EXISTS idx_mars_assistant_sessions_user_updated ON mars_assistant_sessions(user_id, updated_at DESC)"))
        conn.execute(text("CREATE INDEX IF NOT EXISTS idx_mars_assistant_sessions_team_updated ON mars_assistant_sessions(team_id, updated_at DESC)"))


def ensure_mars_assistant_message_table() -> None:
    with get_engine().begin() as conn:
        conn.execute(text("""
            CREATE TABLE IF NOT EXISTS mars_assistant_messages (
                id VARCHAR(64) PRIMARY KEY,
                session_id VARCHAR(64) NOT NULL,
                user_id VARCHAR(64) NOT NULL,
                team_id VARCHAR(64),
                role VARCHAR(16) NOT NULL,
                content TEXT,
                status VARCHAR(20),
                model VARCHAR(64),
                error TEXT,
                attachment_ids JSONB,
                quoted_message JSONB,
                skill_payload JSONB,
                metadata JSONB,
                created_at BIGINT NOT NULL,
                updated_at BIGINT NOT NULL
            )
        """))
        conn.execute(text("CREATE INDEX IF NOT EXISTS idx_mars_assistant_messages_session_created ON mars_assistant_messages(session_id, created_at ASC)"))
        conn.execute(text("CREATE INDEX IF NOT EXISTS idx_mars_assistant_messages_user_created ON mars_assistant_messages(user_id, created_at ASC)"))


def ensure_mars_assistant_artifact_table() -> None:
    with get_engine().begin() as conn:
        conn.execute(text("""
            CREATE TABLE IF NOT EXISTS mars_assistant_artifacts (
                id VARCHAR(64) PRIMARY KEY,
                session_id VARCHAR(64) NOT NULL,
                message_id VARCHAR(64),
                user_id VARCHAR(64) NOT NULL,
                team_id VARCHAR(64),
                artifact_type VARCHAR(32) NOT NULL,
                artifact_role VARCHAR(32),
                url TEXT,
                file_key VARCHAR(512),
                prompt TEXT,
                source_artifact_id VARCHAR(64),
                source_image_url TEXT,
                metadata JSONB,
                created_at BIGINT NOT NULL,
                updated_at BIGINT NOT NULL
            )
        """))
        conn.execute(text("CREATE INDEX IF NOT EXISTS idx_mars_assistant_artifacts_session_created ON mars_assistant_artifacts(session_id, created_at ASC)"))
        conn.execute(text("CREATE INDEX IF NOT EXISTS idx_mars_assistant_artifacts_message ON mars_assistant_artifacts(message_id)"))


def get_session_state(session_id: str, user_id: Optional[str] = None) -> Optional[dict]:
    ensure_mars_assistant_session_table()
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
    task_state: Optional[dict] = None,
    image_asset_state: Optional[dict] = None,
    metadata: Optional[dict] = None,
) -> dict:
    ensure_mars_assistant_session_table()
    now = _now_ms()
    with get_engine().begin() as conn:
        conn.execute(
            text("""
                INSERT INTO mars_assistant_sessions
                    (session_id, user_id, team_id, task_state, image_asset_state, metadata, created_at, updated_at)
                VALUES
                    (:session_id, :user_id, :team_id, CAST(:task_state AS JSONB), CAST(:image_asset_state AS JSONB), CAST(:metadata AS JSONB), :created_at, :updated_at)
                ON CONFLICT (session_id) DO UPDATE SET
                    user_id = EXCLUDED.user_id,
                    team_id = EXCLUDED.team_id,
                    task_state = EXCLUDED.task_state,
                    image_asset_state = EXCLUDED.image_asset_state,
                    metadata = EXCLUDED.metadata,
                    updated_at = EXCLUDED.updated_at
            """),
            {
                "session_id": session_id,
                "user_id": user_id,
                "team_id": team_id,
                "task_state": json.dumps(task_state, ensure_ascii=False),
                "image_asset_state": json.dumps(image_asset_state, ensure_ascii=False),
                "metadata": json.dumps(metadata, ensure_ascii=False),
                "created_at": now,
                "updated_at": now,
            },
        )
        row = conn.execute(
            text("SELECT * FROM mars_assistant_sessions WHERE session_id = :session_id"),
            {"session_id": session_id},
        ).mappings().first()
        return dict(row)


def clear_session_state(session_id: str, user_id: Optional[str] = None) -> bool:
    ensure_mars_assistant_session_table()
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


def list_session_messages(session_id: str, user_id: Optional[str] = None) -> list[dict]:
    ensure_mars_assistant_message_table()
    owner_clause = " AND user_id = :user_id" if user_id else ""
    params = {"session_id": session_id}
    if user_id:
        params["user_id"] = user_id
    with get_engine().begin() as conn:
        rows = conn.execute(
            text(f"SELECT * FROM mars_assistant_messages WHERE session_id = :session_id{owner_clause} ORDER BY created_at ASC"),
            params,
        ).mappings().all()
        return [dict(row) for row in rows]


def list_session_artifacts(session_id: str, user_id: Optional[str] = None) -> list[dict]:
    ensure_mars_assistant_artifact_table()
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


def upsert_session_message(
    *,
    message_id: str,
    session_id: str,
    user_id: str,
    team_id: Optional[str] = None,
    role: str,
    content: Optional[str] = None,
    status: Optional[str] = None,
    model: Optional[str] = None,
    error: Optional[str] = None,
    attachment_ids: Optional[list] = None,
    quoted_message: Optional[dict] = None,
    skill_payload: Optional[dict] = None,
    metadata: Optional[dict] = None,
    created_at: Optional[int] = None,
) -> dict:
    ensure_mars_assistant_message_table()
    now = _now_ms()
    created_at = created_at or now
    with get_engine().begin() as conn:
        conn.execute(
            text("""
                INSERT INTO mars_assistant_messages
                    (id, session_id, user_id, team_id, role, content, status, model, error, attachment_ids, quoted_message, skill_payload, metadata, created_at, updated_at)
                VALUES
                    (:id, :session_id, :user_id, :team_id, :role, :content, :status, :model, :error, CAST(:attachment_ids AS JSONB), CAST(:quoted_message AS JSONB), CAST(:skill_payload AS JSONB), CAST(:metadata AS JSONB), :created_at, :updated_at)
                ON CONFLICT (id) DO UPDATE SET
                    session_id = EXCLUDED.session_id,
                    user_id = EXCLUDED.user_id,
                    team_id = EXCLUDED.team_id,
                    role = EXCLUDED.role,
                    content = EXCLUDED.content,
                    status = EXCLUDED.status,
                    model = EXCLUDED.model,
                    error = EXCLUDED.error,
                    attachment_ids = EXCLUDED.attachment_ids,
                    quoted_message = EXCLUDED.quoted_message,
                    skill_payload = EXCLUDED.skill_payload,
                    metadata = EXCLUDED.metadata,
                    updated_at = EXCLUDED.updated_at
            """),
            {
                "id": message_id,
                "session_id": session_id,
                "user_id": user_id,
                "team_id": team_id,
                "role": role,
                "content": content,
                "status": status,
                "model": model,
                "error": error,
                "attachment_ids": json.dumps(attachment_ids, ensure_ascii=False),
                "quoted_message": json.dumps(quoted_message, ensure_ascii=False),
                "skill_payload": json.dumps(skill_payload, ensure_ascii=False),
                "metadata": json.dumps(metadata, ensure_ascii=False),
                "created_at": created_at,
                "updated_at": now,
            },
        )
        row = conn.execute(
            text("SELECT * FROM mars_assistant_messages WHERE id = :id"),
            {"id": message_id},
        ).mappings().first()
        return dict(row)


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
    prompt: Optional[str] = None,
    source_artifact_id: Optional[str] = None,
    source_image_url: Optional[str] = None,
    metadata: Optional[dict] = None,
    created_at: Optional[int] = None,
) -> dict:
    ensure_mars_assistant_artifact_table()
    now = _now_ms()
    created_at = created_at or now
    with get_engine().begin() as conn:
        conn.execute(
            text("""
                INSERT INTO mars_assistant_artifacts
                    (id, session_id, message_id, user_id, team_id, artifact_type, artifact_role, url, file_key, prompt, source_artifact_id, source_image_url, metadata, created_at, updated_at)
                VALUES
                    (:id, :session_id, :message_id, :user_id, :team_id, :artifact_type, :artifact_role, :url, :file_key, :prompt, :source_artifact_id, :source_image_url, CAST(:metadata AS JSONB), :created_at, :updated_at)
                ON CONFLICT (id) DO UPDATE SET
                    session_id = EXCLUDED.session_id,
                    message_id = EXCLUDED.message_id,
                    user_id = EXCLUDED.user_id,
                    team_id = EXCLUDED.team_id,
                    artifact_type = EXCLUDED.artifact_type,
                    artifact_role = EXCLUDED.artifact_role,
                    url = EXCLUDED.url,
                    file_key = EXCLUDED.file_key,
                    prompt = EXCLUDED.prompt,
                    source_artifact_id = EXCLUDED.source_artifact_id,
                    source_image_url = EXCLUDED.source_image_url,
                    metadata = EXCLUDED.metadata,
                    updated_at = EXCLUDED.updated_at
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
                "prompt": prompt,
                "source_artifact_id": source_artifact_id,
                "source_image_url": source_image_url,
                "metadata": json.dumps(metadata, ensure_ascii=False),
                "created_at": created_at,
                "updated_at": now,
            },
        )
        row = conn.execute(
            text("SELECT * FROM mars_assistant_artifacts WHERE id = :id"),
            {"id": artifact_id},
        ).mappings().first()
        return dict(row)
