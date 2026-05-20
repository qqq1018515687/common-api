"""Persistent Agent Run storage for creation-agent recovery."""

from __future__ import annotations

import json
import time
import uuid
from typing import Any, Optional

from sqlalchemy import text

from storage.database.db import get_engine


TERMINAL_STEP_STATUSES = {"completed", "failed", "cancelled"}


def _now_ms() -> int:
    return int(time.time() * 1000)


def _json_dumps(value: Any) -> Optional[str]:
    if value is None:
        return None
    return json.dumps(value, ensure_ascii=False)


def _json_loads(value: Any, fallback: Any = None) -> Any:
    if value is None:
        return fallback
    if isinstance(value, str):
        try:
            return json.loads(value)
        except Exception:
            return fallback
    return value


def ensure_agent_run_tables() -> None:
    """Create Agent Run tables lazily so deployment does not depend on a manual migration."""
    with get_engine().begin() as conn:
        conn.execute(text("""
            CREATE TABLE IF NOT EXISTS agent_runs (
                id VARCHAR(64) PRIMARY KEY,
                user_id VARCHAR(64) NOT NULL,
                team_id VARCHAR(64),
                status VARCHAR(24) NOT NULL DEFAULT 'pending',
                plan_type VARCHAR(32),
                prompt TEXT,
                plan JSONB,
                assets JSONB,
                preferences JSONB,
                current_step_id VARCHAR(64),
                completed_steps JSONB NOT NULL DEFAULT '[]'::jsonb,
                metadata JSONB,
                error TEXT,
                created_at BIGINT NOT NULL,
                updated_at BIGINT NOT NULL,
                completed_at BIGINT
            )
        """))
        conn.execute(text("""
            CREATE TABLE IF NOT EXISTS agent_run_steps (
                id VARCHAR(128) PRIMARY KEY,
                run_id VARCHAR(64) NOT NULL REFERENCES agent_runs(id) ON DELETE CASCADE,
                step_id VARCHAR(64) NOT NULL,
                step_index INTEGER NOT NULL,
                status VARCHAR(24) NOT NULL DEFAULT 'pending',
                title TEXT,
                target JSONB,
                prompt TEXT,
                task_id VARCHAR(64),
                input_data JSONB,
                result JSONB,
                error TEXT,
                output_assets JSONB,
                requires_confirmation BOOLEAN NOT NULL DEFAULT FALSE,
                metadata JSONB,
                created_at BIGINT NOT NULL,
                updated_at BIGINT NOT NULL,
                started_at BIGINT,
                completed_at BIGINT,
                UNIQUE (run_id, step_id)
            )
        """))
        conn.execute(text("CREATE INDEX IF NOT EXISTS idx_agent_runs_user_updated ON agent_runs(user_id, updated_at DESC)"))
        conn.execute(text("CREATE INDEX IF NOT EXISTS idx_agent_runs_team_updated ON agent_runs(team_id, updated_at DESC)"))
        conn.execute(text("CREATE INDEX IF NOT EXISTS idx_agent_runs_status ON agent_runs(status)"))
        conn.execute(text("CREATE INDEX IF NOT EXISTS idx_agent_run_steps_run_index ON agent_run_steps(run_id, step_index)"))
        conn.execute(text("CREATE INDEX IF NOT EXISTS idx_agent_run_steps_task ON agent_run_steps(task_id)"))


def _run_from_row(row: Any) -> dict:
    data = dict(row)
    data["plan"] = _json_loads(data.get("plan"), {})
    data["assets"] = _json_loads(data.get("assets"), [])
    data["preferences"] = _json_loads(data.get("preferences"), {})
    data["completed_steps"] = _json_loads(data.get("completed_steps"), [])
    data["metadata"] = _json_loads(data.get("metadata"), {})
    return data


def _step_from_row(row: Any) -> dict:
    data = dict(row)
    data["target"] = _json_loads(data.get("target"), {})
    data["input_data"] = _json_loads(data.get("input_data"), {})
    data["result"] = _json_loads(data.get("result"), {})
    data["output_assets"] = _json_loads(data.get("output_assets"), [])
    data["metadata"] = _json_loads(data.get("metadata"), {})
    return data


def _get_run_with_steps(conn: Any, run_id: str) -> Optional[dict]:
    run_row = conn.execute(
        text("SELECT * FROM agent_runs WHERE id = :run_id"),
        {"run_id": run_id},
    ).mappings().first()
    if not run_row:
        return None

    step_rows = conn.execute(
        text("SELECT * FROM agent_run_steps WHERE run_id = :run_id ORDER BY step_index ASC"),
        {"run_id": run_id},
    ).mappings().all()

    run = _run_from_row(run_row)
    run["steps"] = [_step_from_row(row) for row in step_rows]
    return run


def _normalise_step(step: dict, index: int) -> dict:
    step_id = step.get("step_id") or step.get("id") or f"step_{index + 1}"
    step_index = step.get("order") or step.get("step_index") or step.get("index") or (index + 1)
    requires_confirmation = bool(step.get("requires_confirmation"))
    return {
        "id": f"{step_id}:{uuid.uuid4().hex[:12]}",
        "step_id": str(step_id),
        "step_index": int(step_index),
        "status": str(step.get("status") or ("confirming" if requires_confirmation else "pending")),
        "title": step.get("title"),
        "target": step.get("target"),
        "prompt": step.get("prompt"),
        "task_id": step.get("task_id"),
        "input_data": step.get("input_data"),
        "result": step.get("result"),
        "error": step.get("error"),
        "output_assets": step.get("output_assets"),
        "requires_confirmation": requires_confirmation,
        "metadata": step.get("metadata"),
    }


def create_run(
    *,
    user_id: str,
    run_id: Optional[str] = None,
    team_id: Optional[str] = None,
    status: Optional[str] = None,
    plan_type: Optional[str] = None,
    prompt: Optional[str] = None,
    plan: Optional[dict] = None,
    steps: Optional[list[dict]] = None,
    assets: Optional[list[dict]] = None,
    preferences: Optional[dict] = None,
    metadata: Optional[dict] = None,
) -> dict:
    ensure_agent_run_tables()
    if not user_id:
        raise ValueError("user_id is required")

    now = _now_ms()
    run_id = run_id or f"agent_run_{uuid.uuid4().hex}"
    plan_steps = steps or (plan or {}).get("steps") or []
    normalised_steps = [
        _normalise_step(step, index)
        for index, step in enumerate(plan_steps)
        if isinstance(step, dict)
    ]
    first_step_id = normalised_steps[0]["step_id"] if normalised_steps else None
    run_status = status or ("confirming" if any(step["requires_confirmation"] for step in normalised_steps) else "pending")

    with get_engine().begin() as conn:
        conn.execute(
            text("""
                INSERT INTO agent_runs
                    (id, user_id, team_id, status, plan_type, prompt, plan, assets, preferences,
                     current_step_id, completed_steps, metadata, created_at, updated_at)
                VALUES
                    (:id, :user_id, :team_id, :status, :plan_type, :prompt,
                     CAST(:plan AS JSONB), CAST(:assets AS JSONB), CAST(:preferences AS JSONB),
                     :current_step_id, CAST(:completed_steps AS JSONB), CAST(:metadata AS JSONB),
                     :created_at, :updated_at)
                ON CONFLICT (id) DO UPDATE SET
                    user_id = EXCLUDED.user_id,
                    team_id = EXCLUDED.team_id,
                    status = EXCLUDED.status,
                    plan_type = EXCLUDED.plan_type,
                    prompt = EXCLUDED.prompt,
                    plan = EXCLUDED.plan,
                    assets = EXCLUDED.assets,
                    preferences = EXCLUDED.preferences,
                    current_step_id = EXCLUDED.current_step_id,
                    metadata = EXCLUDED.metadata,
                    updated_at = EXCLUDED.updated_at
            """),
            {
                "id": run_id,
                "user_id": user_id,
                "team_id": team_id,
                "status": run_status,
                "plan_type": plan_type,
                "prompt": prompt,
                "plan": _json_dumps(plan or {}),
                "assets": _json_dumps(assets or []),
                "preferences": _json_dumps(preferences or {}),
                "current_step_id": first_step_id,
                "completed_steps": _json_dumps([]),
                "metadata": _json_dumps(metadata or {}),
                "created_at": now,
                "updated_at": now,
            },
        )

        for step in normalised_steps:
            conn.execute(
                text("""
                    INSERT INTO agent_run_steps
                        (id, run_id, step_id, step_index, status, title, target, prompt, task_id,
                         input_data, result, error, output_assets, requires_confirmation, metadata,
                         created_at, updated_at)
                    VALUES
                        (:id, :run_id, :step_id, :step_index, :status, :title, CAST(:target AS JSONB),
                         :prompt, :task_id, CAST(:input_data AS JSONB), CAST(:result AS JSONB),
                         :error, CAST(:output_assets AS JSONB), :requires_confirmation,
                         CAST(:metadata AS JSONB), :created_at, :updated_at)
                    ON CONFLICT (run_id, step_id) DO UPDATE SET
                        step_index = EXCLUDED.step_index,
                        status = EXCLUDED.status,
                        title = EXCLUDED.title,
                        target = EXCLUDED.target,
                        prompt = EXCLUDED.prompt,
                        task_id = EXCLUDED.task_id,
                        input_data = EXCLUDED.input_data,
                        result = EXCLUDED.result,
                        error = EXCLUDED.error,
                        output_assets = EXCLUDED.output_assets,
                        requires_confirmation = EXCLUDED.requires_confirmation,
                        metadata = EXCLUDED.metadata,
                        updated_at = EXCLUDED.updated_at
                """),
                {
                    **step,
                    "run_id": run_id,
                    "target": _json_dumps(step.get("target") or {}),
                    "input_data": _json_dumps(step.get("input_data") or {}),
                    "result": _json_dumps(step.get("result") or {}),
                    "output_assets": _json_dumps(step.get("output_assets") or []),
                    "metadata": _json_dumps(step.get("metadata") or {}),
                    "created_at": now,
                    "updated_at": now,
                },
            )

        run = _get_run_with_steps(conn, run_id)
        return run or {"id": run_id, "steps": []}


def get_run(run_id: str, user_id: Optional[str] = None) -> Optional[dict]:
    ensure_agent_run_tables()
    with get_engine().connect() as conn:
        run = _get_run_with_steps(conn, run_id)
        if run and user_id and run.get("user_id") != user_id:
            return None
        return run


def list_runs(
    *,
    user_id: Optional[str] = None,
    team_id: Optional[str] = None,
    status: Optional[str] = None,
    limit: Optional[int] = None,
) -> dict:
    ensure_agent_run_tables()
    if not user_id and not team_id:
        raise ValueError("user_id or team_id is required")

    params: dict[str, Any] = {"limit": min(max(int(limit or 20), 1), 100)}
    where = []
    if user_id:
        where.append("user_id = :user_id")
        params["user_id"] = user_id
    if team_id:
        where.append("team_id = :team_id")
        params["team_id"] = team_id
    if status:
        where.append("status = :status")
        params["status"] = status

    sql = f"""
        SELECT id FROM agent_runs
        WHERE {' AND '.join(where)}
        ORDER BY updated_at DESC
        LIMIT :limit
    """

    with get_engine().connect() as conn:
        rows = conn.execute(text(sql), params).mappings().all()
        runs = [
            run for row in rows
            if (run := _get_run_with_steps(conn, row["id"])) is not None
        ]
    return {"runs": runs, "total": len(runs)}


def update_run(run_id: str, updates: dict, user_id: Optional[str] = None) -> Optional[dict]:
    ensure_agent_run_tables()
    if not updates:
        return get_run(run_id, user_id=user_id)

    allowed_fields = {
        "status": "status",
        "plan_type": "plan_type",
        "prompt": "prompt",
        "current_step_id": "current_step_id",
        "error": "error",
        "completed_at": "completed_at",
    }
    json_fields = {
        "plan": "plan",
        "assets": "assets",
        "preferences": "preferences",
        "completed_steps": "completed_steps",
        "metadata": "metadata",
    }
    assignments = []
    params: dict[str, Any] = {"run_id": run_id, "updated_at": _now_ms(), "user_id": user_id}

    for input_key, column in allowed_fields.items():
        if input_key in updates:
            assignments.append(f"{column} = :{input_key}")
            params[input_key] = updates[input_key]

    for input_key, column in json_fields.items():
        if input_key in updates:
            if input_key == "metadata":
                assignments.append(f"{column} = COALESCE({column}, '{{}}'::jsonb) || CAST(:{input_key} AS JSONB)")
            else:
                assignments.append(f"{column} = CAST(:{input_key} AS JSONB)")
            params[input_key] = _json_dumps(updates[input_key])

    if not assignments:
        return get_run(run_id, user_id=user_id)

    assignments.append("updated_at = :updated_at")
    owner_clause = " AND user_id = :user_id" if user_id else ""

    with get_engine().begin() as conn:
        result = conn.execute(
            text(f"UPDATE agent_runs SET {', '.join(assignments)} WHERE id = :run_id{owner_clause}"),
            params,
        )
        if user_id and result.rowcount == 0:
            return None
        run = _get_run_with_steps(conn, run_id)
        if run and user_id and run.get("user_id") != user_id:
            return None
        return run


def _recompute_run_state(conn: Any, run_id: str) -> None:
    rows = conn.execute(
        text("SELECT step_id, status, step_index FROM agent_run_steps WHERE run_id = :run_id ORDER BY step_index ASC"),
        {"run_id": run_id},
    ).mappings().all()
    if not rows:
        return

    statuses = [row["status"] for row in rows]
    completed_steps = [row["step_id"] for row in rows if row["status"] == "completed"]
    current_step_id = next((row["step_id"] for row in rows if row["status"] not in {"completed", "cancelled"}), None)

    if any(status == "failed" for status in statuses):
        run_status = "failed"
    elif all(status == "completed" for status in statuses):
        run_status = "completed"
    elif all(status == "cancelled" for status in statuses):
        run_status = "cancelled"
    elif any(status == "confirming" for status in statuses):
        run_status = "confirming"
    elif any(status in {"running", "submitted"} for status in statuses):
        run_status = "running"
    else:
        run_status = "pending"

    now = _now_ms()
    completed_at = now if run_status in TERMINAL_STEP_STATUSES else None
    conn.execute(
        text("""
            UPDATE agent_runs
            SET status = :status,
                current_step_id = :current_step_id,
                completed_steps = CAST(:completed_steps AS JSONB),
                updated_at = :updated_at,
                completed_at = COALESCE(:completed_at, completed_at)
            WHERE id = :run_id
        """),
        {
            "run_id": run_id,
            "status": run_status,
            "current_step_id": current_step_id,
            "completed_steps": _json_dumps(completed_steps),
            "updated_at": now,
            "completed_at": completed_at,
        },
    )


def update_step(
    *,
    run_id: str,
    step_id: str,
    updates: dict,
    user_id: Optional[str] = None,
) -> Optional[dict]:
    ensure_agent_run_tables()
    if not run_id or not step_id:
        raise ValueError("run_id and step_id are required")

    if user_id:
        existing = get_run(run_id, user_id=user_id)
        if not existing:
            return None

    allowed_fields = {
        "status": "status",
        "title": "title",
        "prompt": "prompt",
        "task_id": "task_id",
        "error": "error",
    }
    json_fields = {
        "target": "target",
        "input_data": "input_data",
        "result": "result",
        "output_assets": "output_assets",
        "metadata": "metadata",
    }
    params: dict[str, Any] = {"run_id": run_id, "step_id": step_id, "updated_at": _now_ms()}
    assignments = []

    for input_key, column in allowed_fields.items():
        if input_key in updates:
            assignments.append(f"{column} = :{input_key}")
            params[input_key] = updates[input_key]

    for input_key, column in json_fields.items():
        if input_key in updates:
            if input_key == "metadata":
                assignments.append(f"{column} = COALESCE({column}, '{{}}'::jsonb) || CAST(:{input_key} AS JSONB)")
            else:
                assignments.append(f"{column} = CAST(:{input_key} AS JSONB)")
            params[input_key] = _json_dumps(updates[input_key])

    status = updates.get("status")
    if status in {"running", "submitted"}:
        assignments.append("started_at = COALESCE(started_at, :started_at)")
        params["started_at"] = _now_ms()
    if status in TERMINAL_STEP_STATUSES:
        assignments.append("completed_at = COALESCE(completed_at, :completed_at)")
        params["completed_at"] = _now_ms()

    assignments.append("updated_at = :updated_at")

    with get_engine().begin() as conn:
        conn.execute(
            text(f"""
                UPDATE agent_run_steps
                SET {', '.join(assignments)}
                WHERE run_id = :run_id AND step_id = :step_id
            """),
            params,
        )
        _recompute_run_state(conn, run_id)
        return _get_run_with_steps(conn, run_id)
