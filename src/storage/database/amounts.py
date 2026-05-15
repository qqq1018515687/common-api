from decimal import Decimal, InvalidOperation, ROUND_HALF_UP
from typing import Any, Optional


GOLD_AMOUNT_QUANT = Decimal("0.01")


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
