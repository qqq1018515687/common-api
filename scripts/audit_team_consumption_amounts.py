"""Audit and optionally repair team consumption amounts.

Default mode is read-only. It reports:
- current team totals
- team_consumption_records net consumption
- amount=0 rows recoverable from balance_before/balance_after
- projected totals after repairing recoverable rows

Apply mode is intentionally guarded:
  python scripts/audit_team_consumption_amounts.py --apply --confirm I_UNDERSTAND

By default apply mode only repairs team_consumption_records.amount for rows where:
- operation_type is consumption or refund
- amount is 0
- balance_before and balance_after are present
- the balance delta is positive

It does not change teams.balance. It only updates teams.total_consumed when
--sync-team-total is also provided.
"""

from __future__ import annotations

import argparse
import json
import os
from datetime import datetime
from decimal import Decimal
from pathlib import Path
from typing import Any

from sqlalchemy import create_engine, text

try:
    from dotenv import load_dotenv
except Exception:  # pragma: no cover - production env may not need dotenv
    load_dotenv = None


CONFIRM_TOKEN = "I_UNDERSTAND"


def json_default(value: Any) -> Any:
    if isinstance(value, Decimal):
        return float(value)
    if hasattr(value, "isoformat"):
        return value.isoformat()
    return value


def load_environment(env_path: str | None) -> None:
    if load_dotenv is None:
        return
    if env_path:
        load_dotenv(env_path)
        return
    repo_env = Path(__file__).resolve().parents[1] / ".env"
    if repo_env.exists():
        load_dotenv(repo_env)


def fetch_rows(conn, sql: str, params: dict[str, Any] | None = None) -> list[dict[str, Any]]:
    return [dict(row._mapping) for row in conn.execute(text(sql), params or {})]


def fetch_scalar(conn, sql: str, params: dict[str, Any] | None = None) -> Any:
    return conn.execute(text(sql), params or {}).scalar()


def build_where_clause(team_id: str | None, prefix: str = "") -> tuple[str, dict[str, Any]]:
    if not team_id:
        return "", {}
    column = f"{prefix}team_id" if prefix else "team_id"
    return f" and {column} = :team_id", {"team_id": team_id}


def collect_report(conn, team_id: str | None, sample_limit: int) -> dict[str, Any]:
    team_filter, team_params = build_where_clause(team_id, "")
    b_team_filter, b_params = build_where_clause(team_id, "b.")

    teams = fetch_rows(
        conn,
        "select id, name, balance, total_consumed, member_count "
        "from teams where (:team_id is null or id = :team_id) order by id",
        {"team_id": team_id},
    )

    record_rollup = fetch_rows(
        conn,
        f"""
        select team_id, count(*) as record_count,
               sum(case
                     when operation_type = 'consumption' then abs(amount)
                     when operation_type = 'refund' then -amount
                     else 0
                   end) as net_consumption,
               sum(case when operation_type = 'recharge' then amount else 0 end) as recharge_total
        from team_consumption_records
        where 1=1 {team_filter}
        group by team_id
        order by team_id
        """,
        team_params,
    )

    recoverable = fetch_rows(
        conn,
        f"""
        select team_id, operation_type, count(*) as count,
               sum(case
                     when operation_type = 'consumption' then balance_before - balance_after
                     when operation_type = 'refund' then balance_after - balance_before
                     else 0
                   end) as recoverable_amount
        from team_consumption_records
        where amount = 0
          and operation_type in ('consumption', 'refund')
          and balance_before is not null
          and balance_after is not null
          and (
            (operation_type = 'consumption' and balance_before > balance_after)
            or (operation_type = 'refund' and balance_after > balance_before)
          )
          {team_filter}
        group by team_id, operation_type
        order by team_id, operation_type
        """,
        team_params,
    )

    irrecoverable_zero = fetch_rows(
        conn,
        f"""
        select team_id, operation_type, count(*) as count
        from team_consumption_records
        where amount = 0
          and operation_type in ('consumption', 'refund')
          and not (
            balance_before is not null
            and balance_after is not null
            and (
              (operation_type = 'consumption' and balance_before > balance_after)
              or (operation_type = 'refund' and balance_after > balance_before)
            )
          )
          {team_filter}
        group by team_id, operation_type
        order by team_id, operation_type
        """,
        team_params,
    )

    projected = fetch_rows(
        conn,
        f"""
        with current_net as (
          select team_id,
                 sum(case
                       when operation_type = 'consumption' then abs(amount)
                       when operation_type = 'refund' then -amount
                       else 0
                     end) as net_consumption
          from team_consumption_records
          where 1=1 {team_filter}
          group by team_id
        ),
        recoverable_net as (
          select team_id,
                 sum(case
                       when operation_type = 'consumption' then balance_before - balance_after
                       when operation_type = 'refund' then -(balance_after - balance_before)
                       else 0
                     end) as recoverable_net
          from team_consumption_records
          where amount = 0
            and operation_type in ('consumption', 'refund')
            and balance_before is not null
            and balance_after is not null
            and (
              (operation_type = 'consumption' and balance_before > balance_after)
              or (operation_type = 'refund' and balance_after > balance_before)
            )
            {team_filter}
          group by team_id
        )
        select t.id as team_id,
               t.total_consumed as stored_total_consumed,
               coalesce(c.net_consumption, 0) as current_record_net,
               coalesce(r.recoverable_net, 0) as recoverable_net,
               coalesce(c.net_consumption, 0) + coalesce(r.recoverable_net, 0) as projected_record_net,
               t.total_consumed - (coalesce(c.net_consumption, 0) + coalesce(r.recoverable_net, 0)) as gap_after_amount_repair
        from teams t
        left join current_net c on c.team_id = t.id
        left join recoverable_net r on r.team_id = t.id
        where (:team_id is null or t.id = :team_id)
        order by t.id
        """,
        {"team_id": team_id, **team_params},
    )

    billing_gaps = fetch_rows(
        conn,
        f"""
        select count(*) as missing_team_records_for_billing_deduct
        from billing_records b
        left join team_consumption_records t
          on t.related_id = b.id and t.operation_type = 'consumption'
        where b.credit_type = 'team_gold'
          and b.operation_type = 'deduct'
          and t.id is null
          {b_team_filter}
        """,
        b_params,
    )[0]

    member_projection = fetch_rows(
        conn,
        f"""
        select team_id, user_id, coalesce(max(username), '') as username,
               count(*) as record_count,
               sum(case
                     when operation_type = 'consumption' and amount <> 0 then abs(amount)
                     when operation_type = 'refund' and amount <> 0 then -amount
                     when operation_type = 'consumption'
                       and amount = 0 and balance_before > balance_after
                       then balance_before - balance_after
                     when operation_type = 'refund'
                       and amount = 0 and balance_after > balance_before
                       then -(balance_after - balance_before)
                     else 0
                   end) as projected_net_consumption,
               min(created_at) as first_record,
               max(created_at) as last_record
        from team_consumption_records
        where 1=1 {team_filter}
        group by team_id, user_id
        order by projected_net_consumption desc nulls last
        limit :sample_limit
        """,
        {**team_params, "sample_limit": sample_limit},
    )

    samples = fetch_rows(
        conn,
        f"""
        select id, team_id, user_id, username, operation_type, amount,
               balance_before, balance_after, description, created_at
        from team_consumption_records
        where amount = 0
          and operation_type in ('consumption', 'refund')
          and balance_before is not null
          and balance_after is not null
          and (
            (operation_type = 'consumption' and balance_before > balance_after)
            or (operation_type = 'refund' and balance_after > balance_before)
          )
          {team_filter}
        order by created_at asc
        limit :sample_limit
        """,
        {**team_params, "sample_limit": sample_limit},
    )

    return {
        "generated_at": datetime.utcnow().isoformat() + "Z",
        "mode": "dry_run",
        "team_filter": team_id,
        "teams": teams,
        "record_rollup": record_rollup,
        "recoverable_zero_amounts": recoverable,
        "irrecoverable_zero_amounts": irrecoverable_zero,
        "projected_totals": projected,
        "billing_link_gaps": billing_gaps,
        "member_projection_top": member_projection,
        "repair_samples": samples,
    }


def backup_rows(conn, path: str, team_id: str | None) -> None:
    team_filter, team_params = build_where_clause(team_id, "")
    data = {
        "generated_at": datetime.utcnow().isoformat() + "Z",
        "team_filter": team_id,
        "teams": fetch_rows(
            conn,
            "select * from teams where (:team_id is null or id = :team_id) order by id",
            {"team_id": team_id},
        ),
        "team_consumption_records": fetch_rows(
            conn,
            f"select * from team_consumption_records where 1=1 {team_filter} order by created_at, id",
            team_params,
        ),
    }
    Path(path).write_text(json.dumps(data, ensure_ascii=False, default=json_default, indent=2), encoding="utf-8")


def apply_amount_repair(conn, team_id: str | None) -> dict[str, int]:
    team_filter, team_params = build_where_clause(team_id, "")
    consumption_result = conn.execute(
        text(
            f"""
            update team_consumption_records
            set amount = -(balance_before - balance_after)
            where amount = 0
              and operation_type = 'consumption'
              and balance_before is not null
              and balance_after is not null
              and balance_before > balance_after
              {team_filter}
            """
        ),
        team_params,
    )
    refund_result = conn.execute(
        text(
            f"""
            update team_consumption_records
            set amount = balance_after - balance_before
            where amount = 0
              and operation_type = 'refund'
              and balance_before is not null
              and balance_after is not null
              and balance_after > balance_before
              {team_filter}
            """
        ),
        team_params,
    )
    return {
        "consumption_rows_updated": consumption_result.rowcount or 0,
        "refund_rows_updated": refund_result.rowcount or 0,
    }


def sync_team_total(conn, team_id: str | None) -> int:
    team_filter = "and t.id = :team_id" if team_id else ""
    team_params = {"team_id": team_id} if team_id else {}
    result = conn.execute(
        text(
            f"""
            with rollup as (
              select team_id,
                     sum(case
                           when operation_type = 'consumption' then abs(amount)
                           when operation_type = 'refund' then -amount
                           else 0
                         end) as net_consumption
              from team_consumption_records
              group by team_id
            )
            update teams t
            set total_consumed = coalesce(r.net_consumption, 0),
                updated_at = now()
            from rollup r
            where r.team_id = t.id {team_filter}
            """
        ),
        team_params,
    )
    return result.rowcount or 0


def main() -> None:
    parser = argparse.ArgumentParser(description="Audit team consumption amount consistency")
    parser.add_argument("--env", help="Path to .env file")
    parser.add_argument("--team-id", help="Limit audit/repair to one team")
    parser.add_argument("--sample-limit", type=int, default=20)
    parser.add_argument("--backup-out", help="Write a JSON backup before applying changes")
    parser.add_argument("--apply", action="store_true", help="Repair recoverable zero amount rows")
    parser.add_argument("--sync-team-total", action="store_true", help="After amount repair, set teams.total_consumed from records")
    parser.add_argument("--confirm", default="", help=f"Required token for --apply: {CONFIRM_TOKEN}")
    args = parser.parse_args()

    load_environment(args.env)
    db_url = os.getenv("PGDATABASE_URL")
    if not db_url:
        raise SystemExit("PGDATABASE_URL is not set")

    if args.apply and args.confirm != CONFIRM_TOKEN:
        raise SystemExit(f"--apply requires --confirm {CONFIRM_TOKEN}")

    engine = create_engine(db_url, pool_pre_ping=True)

    with engine.begin() as conn:
        report = collect_report(conn, args.team_id, args.sample_limit)

        if args.apply:
            if args.backup_out:
                backup_rows(conn, args.backup_out, args.team_id)
            report["mode"] = "apply"
            report["apply_result"] = apply_amount_repair(conn, args.team_id)
            if args.sync_team_total:
                report["team_total_rows_updated"] = sync_team_total(conn, args.team_id)
            report["post_apply_projected_totals"] = collect_report(conn, args.team_id, args.sample_limit)["projected_totals"]

        print(json.dumps(report, ensure_ascii=False, default=json_default, indent=2))


if __name__ == "__main__":
    main()
