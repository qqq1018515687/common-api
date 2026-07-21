import hashlib
import os
import secrets
import uuid
from datetime import datetime, timezone
from decimal import Decimal
from typing import Any, Optional

from sqlalchemy import text

from storage.database.amounts import amount_to_response_number, gold_amount_to_number, normalize_gold_amount
from storage.database.billing_manager import _insert_billing_record
from storage.database.db import get_session, to_epoch_ms
from storage.database.shared.model import (
    RechargeCodeBatches,
    RechargeCodes,
    RechargeRedemptions,
    TeamConsumptionRecords,
    Teams,
    Users,
)


UNIVERSAL_CREDIT_TYPE = "gold"
VALID_CREDIT_TYPES = {UNIVERSAL_CREDIT_TYPE, "personal_gold", "team_gold"}
VALID_REDEEM_TARGETS = {"personal_gold", "team_gold"}
VALID_CHANNELS = {"wechat", "xianyu", "manual", "campaign", "compensation"}
CODE_ALPHABET = "ABCDEFGHJKLMNPQRSTUVWXYZ23456789"


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _to_epoch_ms(value: Optional[datetime]) -> Optional[int]:
    return to_epoch_ms(value) if value else None


def _normalize_text(value: Optional[str], *, max_len: int = 255) -> Optional[str]:
    if not isinstance(value, str):
        return None
    text_value = value.strip()
    return text_value[:max_len] if text_value else None


def _normalize_channel(value: Optional[str]) -> Optional[str]:
    channel = _normalize_text(value, max_len=32)
    if not channel:
        return None
    return channel if channel in VALID_CHANNELS else "manual"


def _parse_expires_at(value: Any) -> Optional[datetime]:
    if value in (None, ""):
        return None
    if isinstance(value, datetime):
        return value if value.tzinfo else value.replace(tzinfo=timezone.utc)
    if isinstance(value, (int, float)):
        timestamp = float(value)
        if timestamp > 10_000_000_000:
            timestamp = timestamp / 1000
        return datetime.fromtimestamp(timestamp, tz=timezone.utc)
    if isinstance(value, str):
        text_value = value.strip()
        if not text_value:
            return None
        parsed = datetime.fromisoformat(text_value.replace("Z", "+00:00"))
        return parsed if parsed.tzinfo else parsed.replace(tzinfo=timezone.utc)
    raise ValueError("过期时间格式无效")


def normalize_code(raw_code: str) -> str:
    return "".join(ch for ch in raw_code.strip().upper() if ch.isalnum())


def hash_code(raw_code: str) -> str:
    normalized = normalize_code(raw_code)
    if len(normalized) < 16:
        raise ValueError("兑换码格式无效")
    pepper = os.getenv("RECHARGE_CODE_PEPPER") or os.getenv("SERVICE_SECRET") or os.getenv("BILLING_SERVICE_SECRET") or ""
    return hashlib.sha256(f"{pepper}:{normalized}".encode("utf-8")).hexdigest()


def _format_code(raw: str) -> str:
    return "HX-" + "-".join(raw[index:index + 4] for index in range(0, len(raw), 4))


def _generate_code() -> str:
    raw = "".join(secrets.choice(CODE_ALPHABET) for _ in range(16))
    return _format_code(raw)


def _resolve_redeem_credit_type(code_credit_type: str, target_credit_type: Optional[str]) -> str:
    if code_credit_type in VALID_REDEEM_TARGETS:
        return code_credit_type
    if code_credit_type == UNIVERSAL_CREDIT_TYPE:
        return target_credit_type if target_credit_type in VALID_REDEEM_TARGETS else "personal_gold"
    raise ValueError("不支持的兑换码类型")


def _serialize_batch(batch: RechargeCodeBatches) -> dict[str, Any]:
    return {
        "id": batch.id,
        "name": batch.name,
        "credit_type": batch.credit_type,
        "amount": gold_amount_to_number(batch.amount),
        "code_count": batch.code_count,
        "status": batch.status,
        "channel": batch.channel,
        "expires_at": _to_epoch_ms(batch.expires_at),
        "note": batch.note,
        "created_by": batch.created_by,
        "created_at": _to_epoch_ms(batch.created_at),
        "updated_at": _to_epoch_ms(batch.updated_at),
    }


def _serialize_code(code: RechargeCodes) -> dict[str, Any]:
    return {
        "id": code.id,
        "batch_id": code.batch_id,
        "code_suffix": code.code_suffix,
        "credit_type": code.credit_type,
        "amount": gold_amount_to_number(code.amount),
        "status": code.status,
        "used_by": code.used_by,
        "used_team_id": code.used_team_id,
        "used_at": _to_epoch_ms(code.used_at),
        "billing_record_id": code.billing_record_id,
        "team_record_id": code.team_record_id,
        "expires_at": _to_epoch_ms(code.expires_at),
        "created_by": code.created_by,
        "created_at": _to_epoch_ms(code.created_at),
        "updated_at": _to_epoch_ms(code.updated_at),
    }


def _serialize_redemption(record: RechargeRedemptions) -> dict[str, Any]:
    return {
        "id": record.id,
        "code_id": record.code_id,
        "user_id": record.user_id,
        "team_id": record.team_id,
        "credit_type": record.credit_type,
        "amount": gold_amount_to_number(record.amount),
        "balance_before": gold_amount_to_number(record.balance_before),
        "balance_after": gold_amount_to_number(record.balance_after),
        "billing_record_id": record.billing_record_id,
        "team_record_id": record.team_record_id,
        "status": record.status,
        "error_message": record.error_message,
        "metadata": record.extra_data,
        "created_at": _to_epoch_ms(record.created_at),
    }


def create_batch(
    *,
    name: str,
    credit_type: str,
    amount: Any,
    code_count: int,
    created_by: str,
    channel: Optional[str] = None,
    expires_at: Any = None,
    note: Optional[str] = None,
) -> dict[str, Any]:
    batch_name = _normalize_text(name, max_len=100)
    if not batch_name:
        raise ValueError("批次名称不能为空")
    if credit_type not in VALID_CREDIT_TYPES:
        raise ValueError("兑换码类型无效")
    amount_value = normalize_gold_amount(amount)
    safe_count = int(code_count or 0)
    if safe_count < 1 or safe_count > 500:
        raise ValueError("单次生成数量必须在 1 到 500 之间")
    if not created_by:
        raise ValueError("创建管理员不能为空")

    expires_at_value = _parse_expires_at(expires_at)
    if expires_at_value and expires_at_value <= _now():
        raise ValueError("过期时间必须晚于当前时间")

    db = get_session()
    try:
        batch_id = str(uuid.uuid4())
        batch = RechargeCodeBatches(
            id=batch_id,
            name=batch_name,
            credit_type=credit_type,
            amount=amount_value,
            code_count=safe_count,
            channel=_normalize_channel(channel),
            expires_at=expires_at_value,
            note=_normalize_text(note, max_len=2000),
            created_by=created_by,
        )
        db.add(batch)

        plain_codes: list[dict[str, str]] = []
        used_hashes: set[str] = set()
        for _ in range(safe_count):
            for _attempt in range(20):
                plain_code = _generate_code()
                code_hash = hash_code(plain_code)
                if code_hash not in used_hashes and not db.query(RechargeCodes.id).filter(RechargeCodes.code_hash == code_hash).first():
                    used_hashes.add(code_hash)
                    break
            else:
                raise RuntimeError("兑换码生成冲突，请重试")

            code_id = str(uuid.uuid4())
            normalized_code = normalize_code(plain_code)
            db.add(RechargeCodes(
                id=code_id,
                batch_id=batch_id,
                code_hash=code_hash,
                code_suffix=normalized_code[-6:],
                credit_type=credit_type,
                amount=amount_value,
                expires_at=expires_at_value,
                created_by=created_by,
            ))
            plain_codes.append({"id": code_id, "code": plain_code})

        db.commit()
        db.refresh(batch)
        return {
            "batch": _serialize_batch(batch),
            "codes": plain_codes,
        }
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()


def list_batches(*, status: Optional[str] = None, limit: int = 100) -> dict[str, Any]:
    safe_limit = min(max(1, int(limit or 100)), 500)
    db = get_session()
    try:
        query = db.query(RechargeCodeBatches)
        if status:
            query = query.filter(RechargeCodeBatches.status == status)
        batches = query.order_by(RechargeCodeBatches.created_at.desc()).limit(safe_limit).all()
        return {"batches": [_serialize_batch(batch) for batch in batches]}
    finally:
        db.close()


def list_codes(
    *,
    batch_id: Optional[str] = None,
    status: Optional[str] = None,
    search: Optional[str] = None,
    user_id: Optional[str] = None,
    limit: int = 200,
) -> dict[str, Any]:
    safe_limit = min(max(1, int(limit or 200)), 500)
    db = get_session()
    try:
        query = db.query(RechargeCodes)
        if batch_id:
            query = query.filter(RechargeCodes.batch_id == batch_id)
        if status:
            query = query.filter(RechargeCodes.status == status)
        if user_id:
            query = query.filter(RechargeCodes.used_by == user_id)
        search_text = _normalize_text(search, max_len=64)
        if search_text:
            normalized = normalize_code(search_text)
            query = query.filter(RechargeCodes.code_suffix.ilike(f"%{normalized[-6:]}%"))
        codes = query.order_by(RechargeCodes.created_at.desc()).limit(safe_limit).all()
        return {"codes": [_serialize_code(code) for code in codes]}
    finally:
        db.close()


def disable_code(*, code_id: str) -> dict[str, Any]:
    db = get_session()
    try:
        code = db.query(RechargeCodes).filter(RechargeCodes.id == code_id).first()
        if not code:
            raise ValueError("兑换码不存在")
        if code.status == "used":
            raise ValueError("已兑换的兑换码不能禁用")
        code.status = "disabled"
        code.updated_at = _now()
        db.commit()
        db.refresh(code)
        return {"code": _serialize_code(code)}
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()


def disable_batch(*, batch_id: str) -> dict[str, Any]:
    db = get_session()
    try:
        batch = db.query(RechargeCodeBatches).filter(RechargeCodeBatches.id == batch_id).first()
        if not batch:
            raise ValueError("兑换码批次不存在")
        batch.status = "disabled"
        batch.updated_at = _now()
        updated = db.query(RechargeCodes).filter(
            RechargeCodes.batch_id == batch_id,
            RechargeCodes.status == "unused",
        ).update({"status": "disabled", "updated_at": _now()}, synchronize_session=False)
        db.commit()
        db.refresh(batch)
        return {"batch": _serialize_batch(batch), "disabled_count": updated}
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()


def redeem(*, raw_code: str, user_id: str, target_credit_type: Optional[str] = None) -> dict[str, Any]:
    if not user_id:
        raise ValueError("用户未登录")
    code_hash = hash_code(raw_code)
    now_value = _now()

    db = get_session()
    try:
        code = db.query(RechargeCodes).filter(RechargeCodes.code_hash == code_hash).with_for_update().first()
        if not code:
            raise ValueError("兑换码无效或不可用")
        batch = db.query(RechargeCodeBatches).filter(RechargeCodeBatches.id == code.batch_id).first()
        if not batch or batch.status != "active":
            raise ValueError("兑换码无效或不可用")
        if code.status != "unused":
            raise ValueError("兑换码无效或不可用")
        if code.expires_at and code.expires_at <= now_value:
            code.status = "expired"
            code.updated_at = now_value
            db.commit()
            raise ValueError("兑换码无效或不可用")

        user = db.query(Users).filter(Users.user_id == user_id).with_for_update().first()
        if not user:
            raise ValueError("用户不存在")
        if user.account_status and user.account_status != "active":
            raise ValueError("当前账号不可用，不能兑换")

        amount = Decimal(str(code.amount))
        redemption_id = str(uuid.uuid4())
        billing_record_id = None
        team_record_id = None
        team_id = None

        redeem_credit_type = _resolve_redeem_credit_type(code.credit_type, target_credit_type)

        if redeem_credit_type == "personal_gold":
            row = db.execute(text(
                "UPDATE users SET gold_credits = gold_credits + :amount "
                "WHERE user_id = :user_id "
                "RETURNING gold_credits - :amount AS before_val, gold_credits AS after_val"
            ), {"amount": amount, "user_id": user_id}).fetchone()
            if not row:
                raise ValueError("用户不存在")
            balance_before = row[0]
            balance_after = row[1]
            billing_record_id = str(uuid.uuid4())
            _insert_billing_record(
                db=db,
                record_id=billing_record_id,
                idempotency_key=f"recharge_code:{code.id}",
                user_id=user_id,
                team_id=None,
                operation_type="recharge",
                credit_type="personal_gold",
                amount=amount,
                balance_before=balance_before,
                balance_after=balance_after,
                related_id=code.id,
                description=f"兑换码充值 · {batch.name}",
                extra_data={"batch_id": batch.id, "code_suffix": code.code_suffix, "channel": batch.channel},
            )
        elif redeem_credit_type == "team_gold":
            if not user.team_id:
                raise ValueError("当前账号未加入团队，不能兑换团队金豆码")
            team = db.query(Teams).filter(Teams.id == user.team_id).with_for_update().first()
            if not team or team.status != "active":
                raise ValueError("当前团队不存在或不可用")
            row = db.execute(text(
                "UPDATE teams SET balance = balance + :amount, updated_at = now() "
                "WHERE id = :team_id "
                "RETURNING balance - :amount AS before_val, balance AS after_val"
            ), {"amount": amount, "team_id": user.team_id}).fetchone()
            if not row:
                raise ValueError("团队不存在")
            balance_before = row[0]
            balance_after = row[1]
            team_id = user.team_id
            team_record_id = str(uuid.uuid4())
            db.add(TeamConsumptionRecords(
                id=team_record_id,
                team_id=team_id,
                user_id=user_id,
                username=user.username,
                amount=amount,
                balance_before=balance_before,
                balance_after=balance_after,
                operation_type="recharge",
                related_id=code.id,
                description=f"兑换码充值 · {batch.name}",
                extra_data={"batch_id": batch.id, "code_suffix": code.code_suffix, "channel": batch.channel},
            ))
        else:
            raise ValueError("不支持的兑换码类型")

        code.status = "used"
        code.used_by = user_id
        code.used_team_id = team_id
        code.used_at = now_value
        code.billing_record_id = billing_record_id
        code.team_record_id = team_record_id
        code.updated_at = now_value

        redemption = RechargeRedemptions(
            id=redemption_id,
            code_id=code.id,
            user_id=user_id,
            team_id=team_id,
            credit_type=redeem_credit_type,
            amount=amount,
            balance_before=balance_before,
            balance_after=balance_after,
            billing_record_id=billing_record_id,
            team_record_id=team_record_id,
            extra_data={"batch_id": batch.id, "code_suffix": code.code_suffix},
        )
        db.add(redemption)
        db.commit()
        db.refresh(code)
        db.refresh(redemption)
        return {
            "code": _serialize_code(code),
            "redemption": _serialize_redemption(redemption),
            "credit_type": redeem_credit_type,
            "amount": amount_to_response_number(redeem_credit_type, amount),
            "balance_before": amount_to_response_number(redeem_credit_type, balance_before),
            "balance_after": amount_to_response_number(redeem_credit_type, balance_after),
        }
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()


def list_redemptions(*, user_id: Optional[str] = None, team_id: Optional[str] = None, limit: int = 100) -> dict[str, Any]:
    safe_limit = min(max(1, int(limit or 100)), 500)
    db = get_session()
    try:
        query = db.query(RechargeRedemptions)
        if user_id:
            query = query.filter(RechargeRedemptions.user_id == user_id)
        if team_id:
            query = query.filter(RechargeRedemptions.team_id == team_id)
        records = query.order_by(RechargeRedemptions.created_at.desc()).limit(safe_limit).all()
        return {"redemptions": [_serialize_redemption(record) for record in records]}
    finally:
        db.close()
