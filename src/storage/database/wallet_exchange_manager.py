import uuid
from decimal import Decimal
from typing import Any

from sqlalchemy import text

from storage.database.amounts import (
    amount_to_response_number,
    normalize_gold_amount,
    normalize_silver_amount,
)
from storage.database.billing_manager import _insert_billing_record
from storage.database.billing_manager import _validate_gold_schema_for_credit_type
from storage.database.db import get_session, to_epoch_ms
from storage.database.shared.model import Users, WalletExchangeRecords


EXCHANGE_RATE = 1000


def _normalize_integer_gold_amount(value: Any) -> Decimal:
    amount = normalize_gold_amount(value)
    if amount != amount.to_integral_value():
        raise ValueError("兑换金豆必须为整数")
    return amount


def _serialize_exchange(record: WalletExchangeRecords) -> dict[str, Any]:
    return {
        "id": record.id,
        "idempotency_key": record.idempotency_key,
        "user_id": record.user_id,
        "exchange_direction": record.exchange_direction,
        "gold_amount": amount_to_response_number("personal_gold", record.gold_amount),
        "silver_amount": amount_to_response_number("personal_silver", record.silver_amount),
        "exchange_rate": record.exchange_rate,
        "gold_balance_before": amount_to_response_number("personal_gold", record.gold_balance_before),
        "gold_balance_after": amount_to_response_number("personal_gold", record.gold_balance_after),
        "silver_balance_before": amount_to_response_number("personal_silver", record.silver_balance_before),
        "silver_balance_after": amount_to_response_number("personal_silver", record.silver_balance_after),
        "out_billing_record_id": record.out_billing_record_id,
        "in_billing_record_id": record.in_billing_record_id,
        "status": record.status,
        "description": record.description,
        "metadata": record.extra_data,
        "created_at": to_epoch_ms(record.created_at),
    }


def convert_gold_to_silver(*, user_id: str, amount: Any, idempotency_key: str) -> dict[str, Any]:
    if not user_id:
        raise ValueError("用户ID不能为空")
    if not idempotency_key:
        raise ValueError("idempotency_key 不能为空")

    gold_amount = _normalize_integer_gold_amount(amount)
    silver_amount = normalize_silver_amount(int(gold_amount) * EXCHANGE_RATE)

    db = get_session()
    try:
        schema_error = _validate_gold_schema_for_credit_type(db, "personal_gold")
        if schema_error:
            raise ValueError(schema_error.get("msg") or "金豆账本 schema 校验失败")

        existing = (
            db.query(WalletExchangeRecords)
            .filter(WalletExchangeRecords.idempotency_key == idempotency_key)
            .first()
        )
        if existing:
            return {"already_processed": True, **_serialize_exchange(existing)}

        user = db.query(Users).filter(Users.user_id == user_id).first()
        if not user:
            raise ValueError("用户不存在")

        result_row = db.execute(
            text(
                "UPDATE users SET gold_credits = gold_credits - :gold_amount, "
                "silver_credits = silver_credits + :silver_amount "
                "WHERE user_id = :user_id AND gold_credits >= :gold_amount "
                "RETURNING gold_credits + :gold_amount AS gold_before, gold_credits AS gold_after, "
                "silver_credits - :silver_amount AS silver_before, silver_credits AS silver_after"
            ),
            {
                "gold_amount": gold_amount,
                "silver_amount": silver_amount,
                "user_id": user_id,
            },
        ).fetchone()

        if not result_row:
            raise ValueError("个人金豆余额不足")

        gold_before, gold_after, silver_before, silver_after = result_row
        exchange_id = str(uuid.uuid4())
        out_record_id = str(uuid.uuid4())
        in_record_id = str(uuid.uuid4())
        description = f"金豆换银豆 {int(gold_amount)} -> {silver_amount}"
        metadata = {"exchange_direction": "gold_to_silver", "exchange_rate": EXCHANGE_RATE}

        _insert_billing_record(
            db=db,
            record_id=out_record_id,
            idempotency_key=f"{idempotency_key}:out",
            user_id=user_id,
            team_id=None,
            operation_type="exchange_out",
            credit_type="personal_gold",
            amount=gold_amount,
            balance_before=gold_before,
            balance_after=gold_after,
            related_id=exchange_id,
            task_id=None,
            description=description,
            extra_data=metadata,
        )
        _insert_billing_record(
            db=db,
            record_id=in_record_id,
            idempotency_key=f"{idempotency_key}:in",
            user_id=user_id,
            team_id=None,
            operation_type="exchange_in",
            credit_type="personal_silver",
            amount=silver_amount,
            balance_before=silver_before,
            balance_after=silver_after,
            related_id=exchange_id,
            task_id=None,
            description=description,
            extra_data=metadata,
        )

        exchange_record = WalletExchangeRecords(
            id=exchange_id,
            idempotency_key=idempotency_key,
            user_id=user_id,
            exchange_direction="gold_to_silver",
            gold_amount=gold_amount,
            silver_amount=silver_amount,
            exchange_rate=EXCHANGE_RATE,
            gold_balance_before=gold_before,
            gold_balance_after=gold_after,
            silver_balance_before=silver_before,
            silver_balance_after=silver_after,
            out_billing_record_id=out_record_id,
            in_billing_record_id=in_record_id,
            status="completed",
            description=description,
            extra_data=metadata,
        )
        db.add(exchange_record)
        db.commit()
        db.refresh(exchange_record)
        return _serialize_exchange(exchange_record)
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()


def list_exchange_records(*, user_id: str, limit: int = 20) -> dict[str, Any]:
    if not user_id:
        raise ValueError("用户ID不能为空")
    safe_limit = min(max(int(limit or 20), 1), 100)

    db = get_session()
    try:
        user = db.query(Users).filter(Users.user_id == user_id).first()
        if not user:
            raise ValueError("用户不存在")

        rows = (
            db.query(WalletExchangeRecords)
            .filter(WalletExchangeRecords.user_id == user_id)
            .order_by(WalletExchangeRecords.created_at.desc())
            .limit(safe_limit)
            .all()
        )
        return {"records": [_serialize_exchange(row) for row in rows]}
    finally:
        db.close()
