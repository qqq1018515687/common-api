#!/usr/bin/env python3
"""Backfill data before the platform applies automatic schema changes."""

import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))


def _load_db_url() -> str:
    try:
        from storage.database.db import get_db_url

        return get_db_url()
    except Exception as exc:
        print(f"[predeploy-schema] skip: database URL is not available: {exc}")
        return ""


def _column_exists(conn, table_name: str, column_name: str) -> bool:
    from sqlalchemy import text

    result = conn.execute(
        text(
            """
            select 1
            from information_schema.columns
            where table_schema = current_schema()
              and table_name = :table_name
              and column_name = :column_name
            limit 1
            """
        ),
        {"table_name": table_name, "column_name": column_name},
    )
    return result.scalar_one_or_none() == 1


def main() -> int:
    db_url = os.getenv("PGDATABASE_URL") or _load_db_url()
    if not db_url:
        print("[predeploy-schema] skip: PGDATABASE_URL is empty")
        return 0

    from sqlalchemy import create_engine, text

    engine = create_engine(db_url, pool_pre_ping=True)
    with engine.begin() as conn:
        if _column_exists(conn, "tasks", "platform_task_id"):
            result = conn.execute(
                text(
                    """
                    update tasks
                    set platform_task_id = concat('pending:', id)
                    where platform_task_id is null
                    """
                )
            )
            conn.execute(text("alter table tasks alter column platform_task_id drop not null"))
            print(f"[predeploy-schema] backfilled tasks.platform_task_id rows: {result.rowcount}")
        else:
            print("[predeploy-schema] skip: tasks.platform_task_id does not exist")

        if _column_exists(conn, "users", "tier"):
            conn.execute(text("alter table users alter column tier type varchar(32)"))
            conn.execute(text("alter table users alter column tier set default 'commercial_registered'"))
            print("[predeploy-schema] ensured users.tier varchar(32)")
        else:
            print("[predeploy-schema] skip: users.tier does not exist")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
