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
