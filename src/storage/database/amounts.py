from decimal import Decimal, InvalidOperation, ROUND_HALF_UP
from typing import Any, Optional


GOLD_AMOUNT_QUANT = Decimal("0.01")
GOLD_DECIMAL_COLUMNS = (
    ("users", "gold_credits"),
    ("teams", "balance"),
    ("teams", "total_consumed"),
    ("team_consumption_records", "amount"),
    ("team_consumption_records", "balance_before"),
    ("team_consumption_records", "balance_after"),
    ("billing_records", "amount"),
    ("billing_records", "balance_before"),
    ("billing_records", "balance_after"),
)


def normalize_gold_amount(value: Any, *, allow_zero: bool = False) -> Decimal:
    """Normalize gold/team-gold amounts as RMB yuan with two decimal places."""
    try:
        amount = Decimal(str(value)).quantize(GOLD_AMOUNT_QUANT, rounding=ROUND_HALF_UP)
    except (InvalidOperation, TypeError, ValueError):
        raise ValueError("金豆金额格式无效")

    if not amount.is_finite():
        raise ValueError("金豆金额格式无效")
    if amount < 0 or (amount == 0 and not allow_zero):
        raise ValueError("金豆金额必须大于0")

    return amount


def normalize_silver_amount(value: Any, *, allow_zero: bool = False) -> int:
    """Normalize silver amounts as integer credits. Silver is not RMB."""
    try:
        amount = Decimal(str(value))
    except (InvalidOperation, TypeError, ValueError):
        raise ValueError("银豆金额格式无效")

    if not amount.is_finite():
        raise ValueError("银豆金额格式无效")
    if amount != amount.to_integral_value():
        raise ValueError("银豆金额必须为整数")
    if amount < 0 or (amount == 0 and not allow_zero):
        raise ValueError("银豆金额必须大于0")

    return int(amount)


def normalize_amount_for_credit_type(
    credit_type: str,
    value: Any,
    *,
    allow_zero: bool = False,
) -> Decimal | int:
    if credit_type in ("personal_gold", "team_gold"):
        return normalize_gold_amount(value, allow_zero=allow_zero)
    if credit_type == "personal_silver":
        return normalize_silver_amount(value, allow_zero=allow_zero)
    raise ValueError(f"不支持的 credit_type: {credit_type}")


def gold_amount_to_number(value: Optional[Any]) -> float:
    if value is None:
        return 0.0
    return float(Decimal(str(value)).quantize(GOLD_AMOUNT_QUANT, rounding=ROUND_HALF_UP))


def silver_amount_to_number(value: Optional[Any]) -> int:
    if value is None:
        return 0
    return int(Decimal(str(value)).to_integral_value())


def amount_to_response_number(credit_type: str, value: Optional[Any]) -> float | int:
    if credit_type in ("personal_gold", "team_gold"):
        return gold_amount_to_number(value)
    return silver_amount_to_number(value)


def gold_amount_schema_mismatches(db: Any) -> list[str]:
    from sqlalchemy import text

    rows = db.execute(text(
        """
        SELECT table_name, column_name, data_type, numeric_scale
        FROM information_schema.columns
        WHERE table_schema = 'public'
          AND (
            (table_name = 'users' AND column_name = 'gold_credits')
            OR (table_name = 'teams' AND column_name IN ('balance', 'total_consumed'))
            OR (table_name = 'team_consumption_records' AND column_name IN ('amount', 'balance_before', 'balance_after'))
            OR (table_name = 'billing_records' AND column_name IN ('amount', 'balance_before', 'balance_after'))
          )
        """
    )).mappings().all()
    actual = {
        (row["table_name"], row["column_name"]): row
        for row in rows
    }

    mismatches: list[str] = []
    for table_name, column_name in GOLD_DECIMAL_COLUMNS:
        row = actual.get((table_name, column_name))
        if row is None:
            mismatches.append(f"{table_name}.{column_name}: missing")
            continue
        if row["data_type"] != "numeric" or row["numeric_scale"] != 2:
            mismatches.append(
                f"{table_name}.{column_name}: {row['data_type']} scale={row['numeric_scale']}"
            )

    return mismatches


def assert_gold_amount_schema(db: Any) -> None:
    mismatches = gold_amount_schema_mismatches(db)
    if mismatches:
        joined = ", ".join(mismatches)
        raise RuntimeError(
            "Gold amount schema mismatch. Run migration a1b2c3d4e5f7 before billing writes: "
            f"{joined}"
        )
