import logging
import json
import os
import uuid
import time
from decimal import Decimal
from typing import Optional, Dict, Any, List
from datetime import datetime, timedelta, timezone

from sqlalchemy import text
from storage.database.db import get_session
from storage.database.shared.model import BillingRecords, Users, Teams, TeamConsumptionRecords
from storage.database.amounts import (
    amount_to_response_number,
    assert_gold_amount_schema,
    gold_amount_to_number,
    normalize_amount_for_credit_type,
    normalize_gold_amount,
    normalize_silver_amount,
    silver_amount_to_number,
)

logger = logging.getLogger(__name__)

# 常量定义
SERVICE_SECRET = os.getenv("BILLING_SERVICE_SECRET", "")


def _build_consumption_title(
    billing_metadata: Optional[Dict[str, Any]] = None,
    metadata: Optional[Dict[str, Any]] = None,
    description: Optional[str] = None,
) -> str:
    """
    从 billing_metadata / metadata / description 构建团队消费记录标题
    优先级：
      1. metadata.billing_metadata.title
      2. billing_metadata.title
      3. description
      4. workflow_name + " · " + model_display_name
      5. "团队消费扣费"
    """
    # 优先级1：metadata.billing_metadata.title
    if metadata and isinstance(metadata, dict):
        nested_bm = metadata.get("billing_metadata")
        if nested_bm and isinstance(nested_bm, dict):
            title = nested_bm.get("title")
            if title and isinstance(title, str) and title.strip():
                return title.strip()

    # 优先级2：billing_metadata.title
    if billing_metadata and isinstance(billing_metadata, dict):
        title = billing_metadata.get("title")
        if title and isinstance(title, str) and title.strip():
            return title.strip()

    # 优先级3：description
    if description and isinstance(description, str) and description.strip():
        return description.strip()

    # 优先级4：workflow_name + model_display_name（从 billing_metadata 或 metadata.billing_metadata）
    source_bm = billing_metadata
    if (not source_bm or not isinstance(source_bm, dict)) and metadata and isinstance(metadata, dict):
        source_bm = metadata.get("billing_metadata")
    if source_bm and isinstance(source_bm, dict):
        workflow_name = source_bm.get("workflow_name")
        model_display_name = source_bm.get("model_display_name")
        parts: list = []
        if workflow_name and isinstance(workflow_name, str) and workflow_name.strip():
            parts.append(workflow_name.strip())
        if model_display_name and isinstance(model_display_name, str) and model_display_name.strip():
            parts.append(model_display_name.strip())
        if parts:
            return " · ".join(parts)

    # 优先级5：最终 fallback
    return "团队消费扣费"


def _extract_team_record_metadata(
    billing_metadata: Optional[Dict[str, Any]] = None,
    metadata: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """从 billing_metadata / metadata.billing_metadata 提取需要存入 team_consumption_records.metadata 的字段"""
    keys_to_extract = [
        "task_id", "billing_task_id", "workflow", "workflow_id",
        "workflow_name", "model_key", "model_display_name",
        "source", "task_type", "currency", "number",
        "agent_run_id", "agent_step_id", "agent_step_index",
        "agent_plan_type", "agent_model_preference",
    ]
    result: Dict[str, Any] = {}

    # 优先从 metadata.billing_metadata 提取
    if metadata and isinstance(metadata, dict):
        nested_bm = metadata.get("billing_metadata")
        if nested_bm and isinstance(nested_bm, dict):
            for key in keys_to_extract:
                value = nested_bm.get(key)
                if value is not None:
                    result[key] = value

    # 再从 billing_metadata 补充（不覆盖已有值）
    if billing_metadata and isinstance(billing_metadata, dict):
        for key in keys_to_extract:
            if key not in result:
                value = billing_metadata.get(key)
                if value is not None:
                    result[key] = value

    return result
PERSONAL_SILVER_MIN = -50  # 银豆最低余额

# 错误码
INVALID_AMOUNT = "INVALID_AMOUNT"
MISSING_IDEMPOTENCY_KEY = "MISSING_IDEMPOTENCY_KEY"
UNAUTHORIZED = "UNAUTHORIZED"
USER_NOT_FOUND = "USER_NOT_FOUND"
TEAM_NOT_FOUND = "TEAM_NOT_FOUND"
INSUFFICIENT_BALANCE = "INSUFFICIENT_BALANCE"
ORIGINAL_RECORD_NOT_FOUND = "ORIGINAL_RECORD_NOT_FOUND"
ALREADY_REFUNDED = "ALREADY_REFUNDED"
INTERNAL_ERROR = "INTERNAL_ERROR"
IDEMPOTENCY_CONFLICT = "IDEMPOTENCY_CONFLICT"
BLTCY_REFUND_NOT_ALLOWED = "BLTCY_REFUND_NOT_ALLOWED"
SCHEMA_MISMATCH = "SCHEMA_MISMATCH"
BILLING_AMOUNT_MISMATCH = "BILLING_AMOUNT_MISMATCH"


def _make_error(code: str, message: str) -> Dict[str, Any]:
    """构造标准错误响应"""
    return {"code": 1, "error_code": code, "msg": message, "data": None}


def _make_success(data: Dict[str, Any], msg: str = "操作成功") -> Dict[str, Any]:
    """构造标准成功响应"""
    return {"code": 0, "msg": msg, "data": data}


def _validate_gold_schema_for_credit_type(db, credit_type: str) -> Optional[Dict[str, Any]]:
    if credit_type not in ("personal_gold", "team_gold"):
        return None

    try:
        assert_gold_amount_schema(db)
    except RuntimeError as exc:
        logger.error("Gold amount schema mismatch before billing write: %s", exc)
        return _make_error(SCHEMA_MISMATCH, str(exc))

    return None


def _extract_billing_metadata_amount(
    billing_metadata: Optional[Dict[str, Any]] = None,
    metadata: Optional[Dict[str, Any]] = None,
) -> Any:
    if metadata and isinstance(metadata, dict):
        nested_bm = metadata.get("billing_metadata")
        if isinstance(nested_bm, dict) and nested_bm.get("amount") is not None:
            return nested_bm.get("amount")

    if billing_metadata and isinstance(billing_metadata, dict):
        return billing_metadata.get("amount")

    return None


def _validate_gold_billing_metadata_amount(
    credit_type: str,
    amount: Decimal | int,
    billing_metadata: Optional[Dict[str, Any]] = None,
    metadata: Optional[Dict[str, Any]] = None,
) -> Optional[Dict[str, Any]]:
    if credit_type not in ("personal_gold", "team_gold"):
        return None

    metadata_amount = _extract_billing_metadata_amount(
        billing_metadata=billing_metadata,
        metadata=metadata,
    )
    if metadata_amount is None:
        return _make_error(
            BILLING_AMOUNT_MISMATCH,
            "金豆扣费缺少 billing_metadata.amount，已阻止写账",
        )

    try:
        expected_amount = normalize_gold_amount(metadata_amount)
    except ValueError as exc:
        return _make_error(BILLING_AMOUNT_MISMATCH, f"billing_metadata.amount 无效: {exc}")

    if expected_amount != amount:
        logger.error(
            "Gold billing amount mismatch: credit_type=%s request_amount=%s metadata_amount=%s",
            credit_type,
            amount,
            expected_amount,
        )
        return _make_error(
            BILLING_AMOUNT_MISMATCH,
            f"金豆扣费金额不一致：请求金额 {amount}，元数据金额 {expected_amount}",
        )

    return None


def _to_epoch_ms(dt_val: Optional[datetime]) -> Optional[int]:
    """将 datetime 转成前端统一使用的 13 位毫秒时间戳。"""
    if not dt_val:
        return None
    if dt_val.tzinfo is None:
        dt_val = dt_val.replace(tzinfo=timezone(timedelta(hours=8)))
    return int(dt_val.timestamp() * 1000)


def verify_service_secret(secret: str) -> bool:
    """验证 service_secret"""
    return secret == SERVICE_SECRET


def _is_bltcy_record(
    billing_metadata: Optional[Dict[str, Any]] = None,
    metadata: Optional[Dict[str, Any]] = None,
    original_extra_data: Optional[Dict[str, Any]] = None,
) -> bool:
    """
    检查是否为 bltcy 任务记录，bltcy 任务不可退款。
    匹配规则：任一数据源中包含以下字段之一即为 bltcy：
    - platform = "bltcy"
    - selected_account = "bltcy"
    - provider = "bltcy"
    - model_name = "model6"
    - model_key = "model6"
    """
    bltcy_keys = {"platform", "selected_account", "provider"}
    model_keys = {"model_name", "model_key"}
    bltcy_model_value = "model6"

    sources: List[Dict[str, Any]] = []
    if billing_metadata:
        sources.append(billing_metadata)
    if metadata:
        # 优先检查 metadata.billing_metadata
        nested_bm = metadata.get("billing_metadata")
        if isinstance(nested_bm, dict):
            sources.append(nested_bm)
        sources.append(metadata)
    if original_extra_data:
        sources.append(original_extra_data)

    for src in sources:
        for key in bltcy_keys:
            val = src.get(key)
            if isinstance(val, str) and val.lower() == "bltcy":
                return True
        for key in model_keys:
            val = src.get(key)
            if isinstance(val, str) and val == bltcy_model_value:
                return True
    return False


def _insert_billing_record(db, record_id: str, idempotency_key: str, user_id: str,
                           team_id: Optional[str], operation_type: str, credit_type: str,
                           amount: Decimal | int, balance_before: Decimal | int, balance_after: Decimal | int,
                           related_id: Optional[str] = None, task_id: Optional[str] = None,
                           description: Optional[str] = None, extra_data: Optional[Dict[str, Any]] = None,
                           status: str = "completed") -> None:
    """通过原生 SQL 插入 billing_records 记录"""
    import json as _json
    db.execute(text(
        "INSERT INTO billing_records "
        "(id, idempotency_key, user_id, team_id, operation_type, credit_type, "
        "amount, balance_before, balance_after, related_id, task_id, description, "
        "extra_data, status, created_at) "
        "VALUES (:id, :idempotency_key, :user_id, :team_id, :operation_type, :credit_type, "
        ":amount, :balance_before, :balance_after, :related_id, :task_id, :description, "
        ":extra_data, :status, now())"
    ), {
        "id": record_id,
        "idempotency_key": idempotency_key,
        "user_id": user_id,
        "team_id": team_id,
        "operation_type": operation_type,
        "credit_type": credit_type,
        "amount": amount,
        "balance_before": balance_before,
        "balance_after": balance_after,
        "related_id": related_id,
        "task_id": task_id,
        "description": description,
        "extra_data": _json.dumps(extra_data) if extra_data else None,
        "status": status,
    })


def _find_by_idempotency_key(db, idempotency_key: str) -> Optional[Dict[str, Any]]:
    """通过 idempotency_key 查询 billing_records"""
    row = db.execute(text(
        "SELECT id, credit_type, amount, balance_before, balance_after, operation_type "
        "FROM billing_records WHERE idempotency_key = :key"
    ), {"key": idempotency_key}).fetchone()
    if row:
        return {
            "id": row[0],
            "credit_type": row[1],
            "amount": row[2],
            "balance_before": row[3],
            "balance_after": row[4],
            "operation_type": row[5],
        }
    return None


def _find_deduct_record(db, record_id: str) -> Optional[Dict[str, Any]]:
    """查找原始 deduct 记录"""
    row = db.execute(text(
        "SELECT id, user_id, credit_type, amount, task_id, status, extra_data "
        "FROM billing_records WHERE id = :id AND operation_type = 'deduct'"
    ), {"id": record_id}).fetchone()
    if row:
        raw_extra = row[6]
        if isinstance(raw_extra, str):
            try:
                parsed_extra = json.loads(raw_extra)
            except Exception:
                parsed_extra = None
        elif isinstance(raw_extra, dict):
            parsed_extra = raw_extra
        else:
            parsed_extra = None
        return {
            "id": row[0],
            "user_id": row[1],
            "credit_type": row[2],
            "amount": row[3],
            "task_id": row[4],
            "status": row[5],
            "extra_data": parsed_extra,
        }
    return None


def _has_existing_refund(db, original_record_id: str) -> bool:
    """检查是否已有针对同一 original_record_id 的退款"""
    row = db.execute(text(
        "SELECT id FROM billing_records "
        "WHERE related_id = :rid AND operation_type = 'refund' AND status = 'completed' "
        "LIMIT 1"
    ), {"rid": original_record_id}).fetchone()
    return row is not None


def _has_existing_settle(db, original_record_id: str) -> bool:
    """检查是否已有针对同一 original_record_id 的结算"""
    row = db.execute(text(
        "SELECT id FROM billing_records "
        "WHERE related_id = :rid AND operation_type = 'settle' AND status = 'completed' "
        "LIMIT 1"
    ), {"rid": original_record_id}).fetchone()
    return row is not None


def get_balance(user_id: str) -> Dict[str, Any]:
    """查询用户余额（personal_gold + personal_silver + team_gold）"""
    db = get_session()
    try:
        user = db.query(Users).filter(Users.user_id == user_id).first()
        if not user:
            return _make_error(USER_NOT_FOUND, "用户不存在")

        result_data: Dict[str, Any] = {
            "user_id": user_id,
            "personal_gold": gold_amount_to_number(user.gold_credits),
            "personal_silver": silver_amount_to_number(user.silver_credits),
        }

        # 查询团队余额
        if user.team_id:
            team = db.query(Teams).filter(Teams.id == user.team_id).first()
            if team:
                result_data["team_gold"] = gold_amount_to_number(team.balance)
                result_data["team_id"] = user.team_id
            else:
                result_data["team_gold"] = 0.0
                result_data["team_id"] = user.team_id
        else:
            result_data["team_gold"] = 0.0

        return _make_success(result_data, "查询成功")

    except Exception as e:
        logger.error(f"查询余额失败: {e}")
        return _make_error(INTERNAL_ERROR, f"查询余额失败: {str(e)}")
    finally:
        db.close()


def list_records(
    user_id: Optional[str] = None,
    team_id: Optional[str] = None,
    credit_type: Optional[str] = None,
    days: Optional[int] = None,
    limit: Optional[int] = None,
    operator_role: Optional[str] = None,
    service_secret: Optional[str] = None,
) -> Dict[str, Any]:
    """
    查询 billing_records 明细。
    - 管理后台可通过 operator_role=admin 查询
    - 服务端也可通过 service_secret 查询
    - 只读操作，不修改余额或账单状态
    """
    is_admin = (operator_role or "").lower() == "admin"
    has_service_access = bool(service_secret) and verify_service_secret(service_secret)
    if not is_admin and not has_service_access:
        return _make_error(UNAUTHORIZED, "无权查询账单记录")

    try:
        safe_days = min(max(1, int(days or 30)), 365)
    except (TypeError, ValueError):
        safe_days = 30

    try:
        safe_limit = min(max(1, int(limit or 200)), 500)
    except (TypeError, ValueError):
        safe_limit = 200

    start_time = datetime.utcnow() - timedelta(days=safe_days)
    db = get_session()
    try:
        query = (
            db.query(BillingRecords, Users.username)
            .outerjoin(Users, BillingRecords.user_id == Users.user_id)
            .filter(BillingRecords.created_at >= start_time)
        )

        if user_id:
            query = query.filter(BillingRecords.user_id == user_id)
        if team_id:
            query = query.filter(BillingRecords.team_id == team_id)
        if credit_type:
            query = query.filter(BillingRecords.credit_type == credit_type)

        rows = (
            query
            .order_by(BillingRecords.created_at.desc())
            .limit(safe_limit)
            .all()
        )

        records = [
            {
                "record_id": record.id,
                "id": record.id,
                "user_id": record.user_id,
                "username": username,
                "team_id": record.team_id,
                "operation_type": record.operation_type,
                "credit_type": record.credit_type,
                "amount": amount_to_response_number(record.credit_type, record.amount),
                "balance_before": amount_to_response_number(record.credit_type, record.balance_before),
                "balance_after": amount_to_response_number(record.credit_type, record.balance_after),
                "related_id": record.related_id,
                "task_id": record.task_id,
                "description": record.description,
                "status": record.status,
                "created_at": _to_epoch_ms(record.created_at),
                "extra_data": record.extra_data,
            }
            for record, username in rows
        ]

        return _make_success({
            "records": records,
            "total": len(records),
            "days": safe_days,
            "limit": safe_limit,
        }, "查询成功")

    except Exception as e:
        logger.error(f"查询账单记录失败: {e}")
        return _make_error(INTERNAL_ERROR, f"查询账单记录失败: {str(e)}")
    finally:
        db.close()


def deduct(
    user_id: str,
    credit_type: str,
    amount: Decimal | int | float,
    idempotency_key: str,
    service_secret: str,
    task_id: Optional[str] = None,
    description: Optional[str] = None,
    extra_data: Optional[Dict[str, Any]] = None,
    billing_metadata: Optional[Dict[str, Any]] = None,
    metadata: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """
    原子扣费
    - personal_gold: 不能扣成负数
    - personal_silver: 最低到 -50
    - team_gold: 不能扣成负数，需同步写入 team_consumption_records
    - 幂等性：通过 idempotency_key 唯一约束保证
    - billing_metadata: main 透传的元数据，用于生成团队消费记录标题
    - metadata: 通用元数据（含 billing_metadata 嵌套结构），优先级高于 billing_metadata
    """
    # 参数校验
    if not service_secret or not verify_service_secret(service_secret):
        return _make_error(UNAUTHORIZED, "service_secret 无效")

    if not idempotency_key:
        return _make_error(MISSING_IDEMPOTENCY_KEY, "idempotency_key 不能为空")

    if credit_type not in ("personal_gold", "personal_silver", "team_gold"):
        return _make_error(INVALID_AMOUNT, f"不支持的 credit_type: {credit_type}")

    try:
        amount = normalize_amount_for_credit_type(credit_type, amount)
    except ValueError as exc:
        return _make_error(INVALID_AMOUNT, str(exc))

    amount_error = _validate_gold_billing_metadata_amount(
        credit_type=credit_type,
        amount=amount,
        billing_metadata=billing_metadata,
        metadata=metadata,
    )
    if amount_error:
        return amount_error

    db = get_session()
    try:
        # 幂等性检查
        existing = _find_by_idempotency_key(db, idempotency_key)
        if existing:
            return _make_success({
                "record_id": existing["id"],
                "already_processed": True,
                "credit_type": existing["credit_type"],
                "amount": amount_to_response_number(existing["credit_type"], existing["amount"]),
                "balance_before": amount_to_response_number(existing["credit_type"], existing["balance_before"]),
                "balance_after": amount_to_response_number(existing["credit_type"], existing["balance_after"]),
            }, "已处理（幂等）")

        # 查询用户
        user = db.query(Users).filter(Users.user_id == user_id).first()
        if not user:
            return _make_error(USER_NOT_FOUND, "用户不存在")

        schema_error = _validate_gold_schema_for_credit_type(db, credit_type)
        if schema_error:
            return schema_error

        record_id = str(uuid.uuid4())

        if credit_type == "personal_gold":
            result_row = db.execute(text(
                "UPDATE users SET gold_credits = gold_credits - :amount "
                "WHERE user_id = :user_id AND gold_credits >= :amount "
                "RETURNING gold_credits + :amount AS before_val, gold_credits AS after_val"
            ), {"amount": amount, "user_id": user_id}).fetchone()

            if not result_row:
                db.rollback()
                current = user.gold_credits or 0
                return _make_error(INSUFFICIENT_BALANCE,
                    f"金豆余额不足，当前: {current}，需要: {amount}")

            balance_before = result_row[0]
            balance_after = result_row[1]

        elif credit_type == "personal_silver":
            result_row = db.execute(text(
                "UPDATE users SET silver_credits = silver_credits - :amount "
                "WHERE user_id = :user_id AND silver_credits - :amount >= :min_val "
                "RETURNING silver_credits + :amount AS before_val, silver_credits AS after_val"
            ), {"amount": amount, "user_id": user_id, "min_val": PERSONAL_SILVER_MIN}).fetchone()

            if not result_row:
                db.rollback()
                current = user.silver_credits or 0
                return _make_error(INSUFFICIENT_BALANCE,
                    f"银豆余额不足，当前: {current}，最低: {PERSONAL_SILVER_MIN}，需要扣: {amount}")

            balance_before = result_row[0]
            balance_after = result_row[1]

        elif credit_type == "team_gold":
            if not user.team_id:
                return _make_error(TEAM_NOT_FOUND, "用户未加入任何团队")

            team = db.query(Teams).filter(Teams.id == user.team_id).first()
            if not team:
                return _make_error(TEAM_NOT_FOUND, "团队不存在")

            result_row = db.execute(text(
                "UPDATE teams SET balance = balance - :amount, "
                "total_consumed = total_consumed + :amount, "
                "updated_at = now() "
                "WHERE id = :team_id AND balance >= :amount "
                "RETURNING balance + :amount AS before_val, balance AS after_val"
            ), {"amount": amount, "team_id": user.team_id}).fetchone()

            if not result_row:
                db.rollback()
                current = team.balance or 0
                return _make_error(INSUFFICIENT_BALANCE,
                    f"团队金豆余额不足，当前: {current}，需要: {amount}")

            balance_before = result_row[0]
            balance_after = result_row[1]

            # 同步写入 team_consumption_records
            consumption_record_id = str(uuid.uuid4())
            consumption_title = _build_consumption_title(
                billing_metadata=billing_metadata,
                metadata=metadata,
                description=description,
            )
            consumption_extra_data = _extract_team_record_metadata(
                billing_metadata=billing_metadata,
                metadata=metadata,
            )
            consumption_record = TeamConsumptionRecords(
                id=consumption_record_id,
                team_id=user.team_id,
                user_id=user_id,
                username=user.username,
                amount=-amount,
                balance_before=balance_before,
                balance_after=balance_after,
                operation_type="consumption",
                related_id=record_id,
                description=consumption_title,
                extra_data=consumption_extra_data if consumption_extra_data else None,
            )
            db.add(consumption_record)

        # 写入 billing_records（将 billing_metadata 关键字段存入 extra_data，供 refund 时校验）
        billing_extra_data = extra_data or {}
        if billing_metadata:
            for _bk in ("platform", "selected_account", "provider", "model_name", "model_key",
                        "workflow", "workflow_name", "model_display_name", "title",
                        "agent_run_id", "agent_step_id", "agent_step_index",
                        "agent_plan_type", "agent_model_preference"):
                _bv = billing_metadata.get(_bk)
                if _bv is not None:
                    billing_extra_data[_bk] = _bv
        if metadata and isinstance(metadata.get("billing_metadata"), dict):
            for _bk in ("platform", "selected_account", "provider", "model_name", "model_key",
                        "workflow", "workflow_name", "model_display_name", "title",
                        "agent_run_id", "agent_step_id", "agent_step_index",
                        "agent_plan_type", "agent_model_preference"):
                _bv = metadata["billing_metadata"].get(_bk)
                if _bv is not None:
                    billing_extra_data[_bk] = _bv
        _insert_billing_record(
            db=db,
            record_id=record_id,
            idempotency_key=idempotency_key,
            user_id=user_id,
            team_id=user.team_id if credit_type == "team_gold" else None,
            operation_type="deduct",
            credit_type=credit_type,
            amount=amount,
            balance_before=balance_before,
            balance_after=balance_after,
            task_id=task_id,
            description=description,
            extra_data=billing_extra_data if billing_extra_data else None,
        )
        db.commit()

        return _make_success({
            "record_id": record_id,
            "credit_type": credit_type,
            "amount": amount_to_response_number(credit_type, amount),
            "balance_before": amount_to_response_number(credit_type, balance_before),
            "balance_after": amount_to_response_number(credit_type, balance_after),
        }, "扣费成功")

    except Exception as e:
        db.rollback()
        logger.error(f"扣费失败: {e}")
        return _make_error(INTERNAL_ERROR, f"扣费失败: {str(e)}")
    finally:
        db.close()


def refund(
    user_id: str,
    original_record_id: str,
    idempotency_key: str,
    service_secret: str,
    amount: Optional[Decimal | int | float] = None,
    description: Optional[str] = None,
    billing_metadata: Optional[Dict[str, Any]] = None,
    metadata: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """
    退款：必须找到原始 deduct 记录，不能重复退款
    - 退全款（amount=None）或部分退款（amount 指定）
    - 幂等性：通过 idempotency_key 唯一约束保证
    - 同时检查是否已有针对同一 original_record_id 的退款
    - billing_metadata: main 透传的元数据，用于生成团队退款记录标题
    - metadata: 通用元数据（含 billing_metadata 嵌套结构），优先级高于 billing_metadata
    """
    if not service_secret or not verify_service_secret(service_secret):
        return _make_error(UNAUTHORIZED, "service_secret 无效")

    if not idempotency_key:
        return _make_error(MISSING_IDEMPOTENCY_KEY, "idempotency_key 不能为空")

    if not original_record_id:
        return _make_error(ORIGINAL_RECORD_NOT_FOUND, "原扣费记录ID不能为空")

    db = get_session()
    try:
        # 幂等性检查
        existing = _find_by_idempotency_key(db, idempotency_key)
        if existing:
            return _make_success({
                "record_id": existing["id"],
                "already_processed": True,
                "credit_type": existing["credit_type"],
                "amount": amount_to_response_number(existing["credit_type"], existing["amount"]),
                "balance_before": amount_to_response_number(existing["credit_type"], existing["balance_before"]),
                "balance_after": amount_to_response_number(existing["credit_type"], existing["balance_after"]),
            }, "已处理（幂等）")

        # 查找原始 deduct 记录
        original = _find_deduct_record(db, original_record_id)
        if not original:
            return _make_error(ORIGINAL_RECORD_NOT_FOUND, "原扣费记录不存在")

        # 检查是否已退款
        if _has_existing_refund(db, original_record_id):
            return _make_error(ALREADY_REFUNDED, "该记录已退款，不能重复退款")

        # bltcy 任务退款保护
        original_extra = original.get("extra_data")
        if not isinstance(original_extra, dict):
            original_extra = None
        if _is_bltcy_record(
            billing_metadata=billing_metadata,
            metadata=metadata,
            original_extra_data=original_extra,
        ):
            return _make_error(BLTCY_REFUND_NOT_ALLOWED, "bltcy tasks are non-refundable")

        credit_type = original["credit_type"]

        schema_error = _validate_gold_schema_for_credit_type(db, credit_type)
        if schema_error:
            return schema_error

        try:
            original_amount = normalize_amount_for_credit_type(credit_type, original["amount"])
            refund_amount_val = normalize_amount_for_credit_type(credit_type, amount) if amount is not None else original_amount
        except ValueError as exc:
            return _make_error(INVALID_AMOUNT, str(exc))

        if refund_amount_val > original_amount:
            return _make_error(INVALID_AMOUNT,
                f"退款金额 {refund_amount_val} 超过原扣费金额 {original['amount']}")

        # 查询用户
        user = db.query(Users).filter(Users.user_id == user_id).first()
        if not user:
            return _make_error(USER_NOT_FOUND, "用户不存在")

        record_id = str(uuid.uuid4())

        if credit_type == "personal_gold":
            result_row = db.execute(text(
                "UPDATE users SET gold_credits = gold_credits + :amount "
                "WHERE user_id = :user_id "
                "RETURNING gold_credits - :amount AS before_val, gold_credits AS after_val"
            ), {"amount": refund_amount_val, "user_id": user_id}).fetchone()

            if not result_row:
                db.rollback()
                return _make_error(INTERNAL_ERROR, "退款失败：用户更新失败")

            balance_before = result_row[0]
            balance_after = result_row[1]

        elif credit_type == "personal_silver":
            result_row = db.execute(text(
                "UPDATE users SET silver_credits = silver_credits + :amount "
                "WHERE user_id = :user_id "
                "RETURNING silver_credits - :amount AS before_val, silver_credits AS after_val"
            ), {"amount": refund_amount_val, "user_id": user_id}).fetchone()

            if not result_row:
                db.rollback()
                return _make_error(INTERNAL_ERROR, "退款失败：用户更新失败")

            balance_before = result_row[0]
            balance_after = result_row[1]

        elif credit_type == "team_gold":
            if not user.team_id:
                return _make_error(TEAM_NOT_FOUND, "用户未加入任何团队")

            result_row = db.execute(text(
                "UPDATE teams SET balance = balance + :amount, "
                "total_consumed = total_consumed - :amount, "
                "updated_at = now() "
                "WHERE id = :team_id "
                "RETURNING balance - :amount AS before_val, balance AS after_val"
            ), {"amount": refund_amount_val, "team_id": user.team_id}).fetchone()

            if not result_row:
                db.rollback()
                return _make_error(INTERNAL_ERROR, "退款失败：团队更新失败")

            balance_before = result_row[0]
            balance_after = result_row[1]

            # 同步写入 team_consumption_records
            consumption_record_id = str(uuid.uuid4())
            refund_base_title = _build_consumption_title(
                billing_metadata=billing_metadata,
                metadata=metadata,
                description=description,
            )
            refund_title = refund_base_title.replace("扣费", "退款").replace("消费", "退款")
            consumption_extra_data = _extract_team_record_metadata(
                billing_metadata=billing_metadata,
                metadata=metadata,
            )
            consumption_record = TeamConsumptionRecords(
                id=consumption_record_id,
                team_id=user.team_id,
                user_id=user_id,
                username=user.username,
                amount=refund_amount_val,
                balance_before=balance_before,
                balance_after=balance_after,
                operation_type="refund",
                related_id=original_record_id,
                description=refund_title,
                extra_data=consumption_extra_data if consumption_extra_data else None,
            )
            db.add(consumption_record)

        else:
            return _make_error(INVALID_AMOUNT, f"不支持的 credit_type: {credit_type}")

        # 写入 billing_records
        _insert_billing_record(
            db=db,
            record_id=record_id,
            idempotency_key=idempotency_key,
            user_id=user_id,
            team_id=user.team_id if credit_type == "team_gold" else None,
            operation_type="refund",
            credit_type=credit_type,
            amount=refund_amount_val,
            balance_before=balance_before,
            balance_after=balance_after,
            related_id=original_record_id,
            task_id=original.get("task_id"),
            description=description or "退款",
        )
        db.commit()

        return _make_success({
            "record_id": record_id,
            "credit_type": credit_type,
            "amount": amount_to_response_number(credit_type, refund_amount_val),
            "balance_before": amount_to_response_number(credit_type, balance_before),
            "balance_after": amount_to_response_number(credit_type, balance_after),
            "original_record_id": original_record_id,
        }, "退款成功")

    except Exception as e:
        db.rollback()
        logger.error(f"退款失败: {e}")
        return _make_error(INTERNAL_ERROR, f"退款失败: {str(e)}")
    finally:
        db.close()


def settle(
    user_id: str,
    original_record_id: str,
    idempotency_key: str,
    final_amount: Decimal | int | float,
    service_secret: str,
    description: Optional[str] = None,
    billing_metadata: Optional[Dict[str, Any]] = None,
    metadata: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """
    结算：只对 personal_silver 做差额处理
    - gold 和 team_gold 预扣即最终，不退差额
    - final_amount < 原扣费金额时，差额退回 personal_silver
    - final_amount > 原扣费金额时，补扣 personal_silver 差额
    - 幂等性：通过 idempotency_key 唯一约束保证
    """
    if not service_secret or not verify_service_secret(service_secret):
        return _make_error(UNAUTHORIZED, "service_secret 无效")

    if not idempotency_key:
        return _make_error(MISSING_IDEMPOTENCY_KEY, "idempotency_key 不能为空")

    if not original_record_id:
        return _make_error(ORIGINAL_RECORD_NOT_FOUND, "原扣费记录ID不能为空")

    db = get_session()
    try:
        # 幂等性检查
        existing = _find_by_idempotency_key(db, idempotency_key)
        if existing:
            return _make_success({
                "record_id": existing["id"],
                "already_processed": True,
                "credit_type": existing["credit_type"],
                "amount": amount_to_response_number(existing["credit_type"], existing["amount"]),
                "balance_before": amount_to_response_number(existing["credit_type"], existing["balance_before"]),
                "balance_after": amount_to_response_number(existing["credit_type"], existing["balance_after"]),
            }, "已处理（幂等）")

        # 查找原始 deduct 记录
        original = _find_deduct_record(db, original_record_id)
        if not original:
            return _make_error(ORIGINAL_RECORD_NOT_FOUND, "原扣费记录不存在")

        # 检查是否已结算
        if _has_existing_settle(db, original_record_id):
            return _make_error(ALREADY_REFUNDED, "该记录已结算，不能重复结算")

        # 查询用户
        user = db.query(Users).filter(Users.user_id == user_id).first()
        if not user:
            return _make_error(USER_NOT_FOUND, "用户不存在")

        credit_type = original["credit_type"]
        schema_error = _validate_gold_schema_for_credit_type(db, credit_type)
        if schema_error:
            return schema_error

        try:
            original_amount = normalize_amount_for_credit_type(credit_type, original["amount"])
        except ValueError as exc:
            return _make_error(INVALID_AMOUNT, str(exc))

        settle_title = description
        if not settle_title and (billing_metadata or metadata):
            settle_title = _build_consumption_title(
                billing_metadata=billing_metadata,
                metadata=metadata,
                description=description,
            )
        settle_extra_data = _extract_team_record_metadata(
            billing_metadata=billing_metadata,
            metadata=metadata,
        )

        if credit_type != "personal_silver":
            record_id = str(uuid.uuid4())
            if credit_type == "team_gold" and user.team_id:
                team = db.query(Teams).filter(Teams.id == user.team_id).first()
                current_balance = team.balance if team else 0
            else:
                current_balance = user.gold_credits or 0

            _insert_billing_record(
                db=db,
                record_id=record_id,
                idempotency_key=idempotency_key,
                user_id=user_id,
                team_id=user.team_id if credit_type == "team_gold" else None,
                operation_type="settle",
                credit_type=credit_type,
                amount=normalize_gold_amount(0, allow_zero=True),
                balance_before=current_balance,
                balance_after=current_balance,
                related_id=original_record_id,
                task_id=original.get("task_id"),
                description=settle_title or "结算：金豆预扣即最终",
                extra_data=settle_extra_data if settle_extra_data else None,
            )
            db.commit()

            return _make_success({
                "record_id": record_id,
                "original_amount": amount_to_response_number(credit_type, original_amount),
                "final_amount": amount_to_response_number(credit_type, original_amount),
                "refund_amount": 0.0,
                "credit_type": credit_type,
                "balance_before": amount_to_response_number(credit_type, current_balance),
                "balance_after": amount_to_response_number(credit_type, current_balance),
            }, "结算成功（金豆预扣即最终）")

        try:
            final_amount = normalize_silver_amount(final_amount, allow_zero=True)
        except ValueError as exc:
            return _make_error(INVALID_AMOUNT, str(exc))

        # 计算差额。diff > 0 退差额；diff < 0 补扣差额。
        diff = original_amount - final_amount
        if diff == 0:
            # 无差额可退
            record_id = str(uuid.uuid4())
            _insert_billing_record(
                db=db,
                record_id=record_id,
                idempotency_key=idempotency_key,
                user_id=user_id,
                team_id=user.team_id if credit_type == "team_gold" else None,
                operation_type="settle",
                credit_type=credit_type,
                amount=0,
                balance_before=user.silver_credits or 0,
                balance_after=user.silver_credits or 0,
                related_id=original_record_id,
                task_id=original.get("task_id"),
                description=settle_title or "结算：无差额可退",
                extra_data=settle_extra_data if settle_extra_data else None,
            )
            db.commit()

            return _make_success({
                "record_id": record_id,
                "original_amount": amount_to_response_number(credit_type, original_amount),
                "final_amount": amount_to_response_number(credit_type, final_amount),
                "refund_amount": 0,
                "credit_type": credit_type,
                "balance_before": amount_to_response_number(credit_type, user.silver_credits or 0),
                "balance_after": amount_to_response_number(credit_type, user.silver_credits or 0),
            }, "结算成功（无差额）")

        if diff < 0:
            extra_amount = abs(diff)
            result_row = db.execute(text(
                "UPDATE users SET silver_credits = silver_credits - :amount "
                "WHERE user_id = :user_id AND silver_credits - :amount >= :min_val "
                "RETURNING silver_credits + :amount AS before_val, silver_credits AS after_val"
            ), {
                "amount": extra_amount,
                "user_id": user_id,
                "min_val": PERSONAL_SILVER_MIN,
            }).fetchone()

            if not result_row:
                db.rollback()
                current_balance = user.silver_credits or 0
                return _make_error(
                    INSUFFICIENT_BALANCE,
                    f"银豆余额不足，无法补扣结算差额。当前余额：{current_balance}，需补扣：{extra_amount}"
                )

            balance_before = result_row[0]
            balance_after = result_row[1]

            record_id = str(uuid.uuid4())
            _insert_billing_record(
                db=db,
                record_id=record_id,
                idempotency_key=idempotency_key,
                user_id=user_id,
                team_id=None,
                operation_type="settle",
                credit_type=credit_type,
                amount=extra_amount,
                balance_before=balance_before,
                balance_after=balance_after,
                related_id=original_record_id,
                task_id=original.get("task_id"),
                description=settle_title or f"结算：补扣差额 {extra_amount} 银豆",
                extra_data=settle_extra_data if settle_extra_data else None,
            )
            db.commit()

            return _make_success({
                "record_id": record_id,
                "original_amount": amount_to_response_number(credit_type, original_amount),
                "final_amount": amount_to_response_number(credit_type, final_amount),
                "extra_deduct_amount": amount_to_response_number(credit_type, extra_amount),
                "credit_type": credit_type,
                "balance_before": amount_to_response_number(credit_type, balance_before),
                "balance_after": amount_to_response_number(credit_type, balance_after),
            }, "结算成功（补扣差额）")

        # 有差额，退回到 personal_silver
        result_row = db.execute(text(
            "UPDATE users SET silver_credits = silver_credits + :amount "
            "WHERE user_id = :user_id "
            "RETURNING silver_credits - :amount AS before_val, silver_credits AS after_val"
        ), {"amount": diff, "user_id": user_id}).fetchone()

        if not result_row:
            db.rollback()
            return _make_error(INTERNAL_ERROR, "结算失败：用户更新失败")

        balance_before = result_row[0]
        balance_after = result_row[1]

        record_id = str(uuid.uuid4())
        _insert_billing_record(
            db=db,
            record_id=record_id,
            idempotency_key=idempotency_key,
            user_id=user_id,
            team_id=user.team_id if credit_type == "team_gold" else None,
            operation_type="settle",
            credit_type=credit_type,
            amount=diff,
            balance_before=balance_before,
            balance_after=balance_after,
            related_id=original_record_id,
            task_id=original.get("task_id"),
            description=settle_title or f"结算：退差额 {diff} 到银豆",
            extra_data=settle_extra_data if settle_extra_data else None,
        )
        db.commit()

        return _make_success({
            "record_id": record_id,
            "original_amount": amount_to_response_number(credit_type, original_amount),
            "final_amount": amount_to_response_number(credit_type, final_amount),
            "refund_amount": amount_to_response_number(credit_type, diff),
            "refund_to": "personal_silver",
            "credit_type": credit_type,
            "balance_before": amount_to_response_number(credit_type, balance_before),
            "balance_after": amount_to_response_number(credit_type, balance_after),
        }, "结算成功")

    except Exception as e:
        db.rollback()
        logger.error(f"结算失败: {e}")
        return _make_error(INTERNAL_ERROR, f"结算失败: {str(e)}")
    finally:
        db.close()
