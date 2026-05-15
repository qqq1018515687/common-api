"""gold amounts to RMB decimal units

Revision ID: a1b2c3d4e5f7
Revises: 9b2c3d4e5f6a
Create Date: 2026-05-15 00:00:00.000000

This migration converts gold/team-gold amounts from integer gold credits
to real RMB yuan values with two decimals. Example: 40 -> 0.40.

Downgrade is intentionally lossy: it only restores integer column types and
does not multiply values by 100.
"""
from __future__ import annotations

import copy
import json
from decimal import Decimal, ROUND_HALF_UP
from typing import Any, Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "a1b2c3d4e5f7"
down_revision: Union[str, None] = "9b2c3d4e5f6a"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


GOLD_MODES = {"gold", "personal_gold", "team_gold"}
GOLD_CREDIT_TYPES = ("personal_gold", "team_gold")
MONEY_QUANT = Decimal("0.01")


def _divide_old_gold_amount(value: Any) -> Any:
    if value is None or isinstance(value, bool):
        return value

    if isinstance(value, (int, float, Decimal)):
        return float((Decimal(str(value)) / Decimal("100")).quantize(MONEY_QUANT, rounding=ROUND_HALF_UP))

    if isinstance(value, str):
        try:
            return float((Decimal(value) / Decimal("100")).quantize(MONEY_QUANT, rounding=ROUND_HALF_UP))
        except Exception:
            return value

    return value


def _json_loads(value: Any) -> Any:
    if isinstance(value, str):
        try:
            return json.loads(value)
        except Exception:
            return value
    return copy.deepcopy(value)


def _convert_fields(container: dict[str, Any], field_names: tuple[str, ...]) -> bool:
    changed = False
    for field in field_names:
        if field in container:
            container[field] = _divide_old_gold_amount(container[field])
            changed = True
    return changed


def _convert_billing_metadata(container: Any) -> bool:
    if not isinstance(container, dict):
        return False

    changed = False
    currency = container.get("currency")
    credit_type = container.get("credit_type")
    mode = container.get("mode")
    if currency == "gold" or credit_type in GOLD_MODES or mode in GOLD_MODES:
        changed = _convert_fields(container, ("amount", "price", "finalAmount", "final_amount")) or changed

    return changed


def _convert_deduction_result(value: Any) -> tuple[Any, bool]:
    data = _json_loads(value)
    if not isinstance(data, dict):
        return value, False

    changed = False
    if data.get("mode") in GOLD_MODES:
        changed = _convert_fields(data, (
            "amount",
            "preDeductedAmount",
            "finalDeductedAmount",
            "finalAmount",
            "final_amount",
            "refundAmount",
            "refundedAmount",
            "refund_amount",
        )) or changed

    return data, changed


def _convert_parameter_snapshot(value: Any) -> tuple[Any, bool]:
    data = _json_loads(value)
    if not isinstance(data, dict):
        return value, False

    changed = False

    pricing_snapshot = data.get("pricingSnapshot")
    if isinstance(pricing_snapshot, dict) and pricing_snapshot.get("mode") in GOLD_MODES:
        changed = _convert_fields(pricing_snapshot, (
            "finalAmount",
            "amount",
            "price",
            "modelPrice",
        )) or changed

    deduction_info = data.get("deductionInfo")
    if isinstance(deduction_info, dict) and deduction_info.get("mode") in GOLD_MODES:
        changed = _convert_fields(deduction_info, (
            "preDeductedAmount",
            "finalDeductedAmount",
            "amount",
        )) or changed

    changed = _convert_billing_metadata(data.get("billing_metadata")) or changed

    metadata = data.get("metadata")
    if isinstance(metadata, dict):
        changed = _convert_billing_metadata(metadata.get("billing_metadata")) or changed

    return data, changed


def _migrate_task_json() -> None:
    bind = op.get_bind()
    rows = bind.execute(sa.text(
        "SELECT id, deduction_result, parameter_snapshot "
        "FROM tasks "
        "WHERE deduction_result IS NOT NULL OR parameter_snapshot IS NOT NULL"
    )).mappings().all()

    update_stmt = sa.text(
        "UPDATE tasks "
        "SET deduction_result = :deduction_result, parameter_snapshot = :parameter_snapshot "
        "WHERE id = :id"
    ).bindparams(
        sa.bindparam("deduction_result", type_=sa.JSON),
        sa.bindparam("parameter_snapshot", type_=sa.JSON),
    )

    for row in rows:
        deduction_result, deduction_changed = _convert_deduction_result(row["deduction_result"])
        parameter_snapshot, snapshot_changed = _convert_parameter_snapshot(row["parameter_snapshot"])

        if deduction_changed or snapshot_changed:
            bind.execute(update_stmt, {
                "id": row["id"],
                "deduction_result": deduction_result,
                "parameter_snapshot": parameter_snapshot,
            })


def _table_exists(table_name: str) -> bool:
    return sa.inspect(op.get_bind()).has_table(table_name)


def upgrade() -> None:
    op.alter_column(
        "users",
        "gold_credits",
        existing_type=sa.Integer(),
        type_=sa.Numeric(12, 2),
        existing_nullable=True,
        server_default=sa.text("0.00"),
        postgresql_using="gold_credits::numeric(12, 2)",
    )
    op.execute("UPDATE users SET gold_credits = ROUND(gold_credits / 100.0, 2) WHERE gold_credits IS NOT NULL")

    op.alter_column(
        "teams",
        "balance",
        existing_type=sa.Integer(),
        type_=sa.Numeric(12, 2),
        existing_nullable=False,
        server_default=sa.text("0.00"),
        postgresql_using="balance::numeric(12, 2)",
    )
    op.alter_column(
        "teams",
        "total_consumed",
        existing_type=sa.Integer(),
        type_=sa.Numeric(12, 2),
        existing_nullable=False,
        server_default=sa.text("0.00"),
        postgresql_using="total_consumed::numeric(12, 2)",
    )
    op.execute("UPDATE teams SET balance = ROUND(balance / 100.0, 2), total_consumed = ROUND(total_consumed / 100.0, 2)")

    for column_name in ("amount", "balance_before", "balance_after"):
        op.alter_column(
            "team_consumption_records",
            column_name,
            existing_type=sa.BigInteger(),
            type_=sa.Numeric(12, 2),
            existing_nullable=(column_name != "amount"),
            postgresql_using=f"{column_name}::numeric(12, 2)",
        )
    op.execute(
        "UPDATE team_consumption_records "
        "SET amount = ROUND(amount / 100.0, 2), "
        "balance_before = ROUND(balance_before / 100.0, 2), "
        "balance_after = ROUND(balance_after / 100.0, 2)"
    )

    if _table_exists("billing_records"):
        for column_name in ("amount", "balance_before", "balance_after"):
            op.alter_column(
                "billing_records",
                column_name,
                existing_type=sa.BigInteger(),
                type_=sa.Numeric(12, 2),
                existing_nullable=(column_name != "amount"),
                postgresql_using=f"{column_name}::numeric(12, 2)",
            )
        op.execute(
            "UPDATE billing_records "
            "SET amount = ROUND(amount / 100.0, 2), "
            "balance_before = ROUND(balance_before / 100.0, 2), "
            "balance_after = ROUND(balance_after / 100.0, 2) "
            "WHERE credit_type IN ('personal_gold', 'team_gold')"
        )

    _migrate_task_json()


def downgrade() -> None:
    # Data downgrade is intentionally lossy. Values are not multiplied by 100.
    if _table_exists("billing_records"):
        op.alter_column(
            "billing_records",
            "amount",
            existing_type=sa.Numeric(12, 2),
            type_=sa.BigInteger(),
            existing_nullable=False,
            postgresql_using="ROUND(amount)::bigint",
        )
        for column_name in ("balance_before", "balance_after"):
            op.alter_column(
                "billing_records",
                column_name,
                existing_type=sa.Numeric(12, 2),
                type_=sa.BigInteger(),
                existing_nullable=True,
                postgresql_using=f"ROUND({column_name})::bigint",
            )

    op.alter_column(
        "team_consumption_records",
        "amount",
        existing_type=sa.Numeric(12, 2),
        type_=sa.BigInteger(),
        existing_nullable=False,
        postgresql_using="ROUND(amount)::bigint",
    )
    for column_name in ("balance_before", "balance_after"):
        op.alter_column(
            "team_consumption_records",
            column_name,
            existing_type=sa.Numeric(12, 2),
            type_=sa.BigInteger(),
            existing_nullable=True,
            postgresql_using=f"ROUND({column_name})::bigint",
        )

    op.alter_column(
        "teams",
        "balance",
        existing_type=sa.Numeric(12, 2),
        type_=sa.Integer(),
        existing_nullable=False,
        server_default=sa.text("0"),
        postgresql_using="ROUND(balance)::integer",
    )
    op.alter_column(
        "teams",
        "total_consumed",
        existing_type=sa.Numeric(12, 2),
        type_=sa.Integer(),
        existing_nullable=False,
        server_default=sa.text("0"),
        postgresql_using="ROUND(total_consumed)::integer",
    )
    op.alter_column(
        "users",
        "gold_credits",
        existing_type=sa.Numeric(12, 2),
        type_=sa.Integer(),
        existing_nullable=True,
        server_default=sa.text("0"),
        postgresql_using="ROUND(gold_credits)::integer",
    )
