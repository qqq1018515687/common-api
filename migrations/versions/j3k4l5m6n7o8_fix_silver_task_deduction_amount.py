"""fix silver task deduction amount

Revision ID: j3k4l5m6n7o8
Revises: i2j3k4l5m6n7
Create Date: 2026-07-21 00:00:00.000000

"""
from __future__ import annotations

import copy
import json
from decimal import Decimal, InvalidOperation
from typing import Any, Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "j3k4l5m6n7o8"
down_revision: Union[str, Sequence[str], None] = "i2j3k4l5m6n7"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _json_loads(value: Any) -> Any:
    if isinstance(value, str):
        try:
            return json.loads(value)
        except Exception:
            return value
    return copy.deepcopy(value)


def _valid_decimal(value: Any) -> Decimal | None:
    if value in (None, "") or isinstance(value, bool):
        return None
    try:
        amount = Decimal(str(value))
    except (InvalidOperation, ValueError):
        return None
    if amount < 0:
        return None
    return amount


def _same_amount(left: Any, right: Any) -> bool:
    left_amount = _valid_decimal(left)
    right_amount = _valid_decimal(right)
    return left_amount is not None and right_amount is not None and left_amount == right_amount


def _is_personal_silver_settled(value: Any) -> tuple[dict[str, Any] | None, Decimal | None]:
    data = _json_loads(value)
    if not isinstance(data, dict):
        return None, None
    if data.get("mode") != "personal_silver" or data.get("status") != "settled":
        return None, None
    final_amount = _valid_decimal(data.get("final_amount"))
    if final_amount is None or final_amount <= 0:
        return None, None
    if _same_amount(data.get("amount"), data.get("final_amount")):
        return None, None
    return data, final_amount


def upgrade() -> None:
    """把历史银豆已结算任务的展示扣费额从预扣费修正为最终消耗额。"""

    bind = op.get_bind()
    rows = bind.execute(sa.text(
        "SELECT id, deduction_result FROM tasks "
        "WHERE deduction_result IS NOT NULL"
    )).mappings().all()

    update_stmt = sa.text(
        "UPDATE tasks SET deduction_result = :deduction_result WHERE id = :id"
    ).bindparams(sa.bindparam("deduction_result", type_=sa.JSON))

    for row in rows:
        deduction_result, final_amount = _is_personal_silver_settled(row["deduction_result"])
        if deduction_result is None or final_amount is None:
            continue
        original_amount = deduction_result.get("amount")
        deduction_result["pre_deduct_amount"] = original_amount
        deduction_result["amount"] = int(final_amount) if final_amount == final_amount.to_integral_value() else float(final_amount)
        bind.execute(update_stmt, {
            "id": row["id"],
            "deduction_result": deduction_result,
        })


def downgrade() -> None:
    """恢复本迁移记录的预扣费展示额。"""

    bind = op.get_bind()
    rows = bind.execute(sa.text(
        "SELECT id, deduction_result FROM tasks "
        "WHERE deduction_result IS NOT NULL"
    )).mappings().all()

    update_stmt = sa.text(
        "UPDATE tasks SET deduction_result = :deduction_result WHERE id = :id"
    ).bindparams(sa.bindparam("deduction_result", type_=sa.JSON))

    for row in rows:
        data = _json_loads(row["deduction_result"])
        if not isinstance(data, dict) or "pre_deduct_amount" not in data:
            continue
        data["amount"] = data.pop("pre_deduct_amount")
        bind.execute(update_stmt, {
            "id": row["id"],
            "deduction_result": data,
        })
