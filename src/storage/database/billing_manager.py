import logging
import os
import uuid
import time
from typing import Optional, Dict, Any, List
from datetime import datetime

from sqlalchemy import text
from storage.database.db import get_session
from storage.database.shared.model import Users, Teams, TeamConsumptionRecords

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


def _make_error(code: str, message: str) -> Dict[str, Any]:
    """构造标准错误响应"""
    return {"code": 1, "error_code": code, "msg": message, "data": None}


def _make_success(data: Dict[str, Any], msg: str = "操作成功") -> Dict[str, Any]:
    """构造标准成功响应"""
    return {"code": 0, "msg": msg, "data": data}


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
                           amount: int, balance_before: int, balance_after: int,
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
            "personal_gold": user.gold_credits or 0,
            "personal_silver": user.silver_credits or 0,
        }

        # 查询团队余额
        if user.team_id:
            team = db.query(Teams).filter(Teams.id == user.team_id).first()
            if team:
                result_data["team_gold"] = team.balance or 0
                result_data["team_id"] = user.team_id
            else:
                result_data["team_gold"] = 0
                result_data["team_id"] = user.team_id
        else:
            result_data["team_gold"] = 0

        return _make_success(result_data, "查询成功")

    except Exception as e:
        logger.error(f"查询余额失败: {e}")
        return _make_error(INTERNAL_ERROR, f"查询余额失败: {str(e)}")
    finally:
        db.close()


def deduct(
    user_id: str,
    credit_type: str,
    amount: int,
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

    if amount <= 0:
        return _make_error(INVALID_AMOUNT, "扣费金额必须大于0")

    if credit_type not in ("personal_gold", "personal_silver", "team_gold"):
        return _make_error(INVALID_AMOUNT, f"不支持的 credit_type: {credit_type}")

    db = get_session()
    try:
        # 幂等性检查
        existing = _find_by_idempotency_key(db, idempotency_key)
        if existing:
            return _make_success({
                "record_id": existing["id"],
                "already_processed": True,
                "credit_type": existing["credit_type"],
                "amount": existing["amount"],
                "balance_before": existing["balance_before"],
                "balance_after": existing["balance_after"],
            }, "已处理（幂等）")

        # 查询用户
        user = db.query(Users).filter(Users.user_id == user_id).first()
        if not user:
            return _make_error(USER_NOT_FOUND, "用户不存在")

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
                        "workflow", "workflow_name", "model_display_name", "title"):
                _bv = billing_metadata.get(_bk)
                if _bv is not None:
                    billing_extra_data[_bk] = _bv
        if metadata and isinstance(metadata.get("billing_metadata"), dict):
            for _bk in ("platform", "selected_account", "provider", "model_name", "model_key",
                        "workflow", "workflow_name", "model_display_name", "title"):
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
            "amount": amount,
            "balance_before": balance_before,
            "balance_after": balance_after,
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
    amount: Optional[int] = None,
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

    if amount is not None and amount <= 0:
        return _make_error(INVALID_AMOUNT, "退款金额必须大于0")

    db = get_session()
    try:
        # 幂等性检查
        existing = _find_by_idempotency_key(db, idempotency_key)
        if existing:
            return _make_success({
                "record_id": existing["id"],
                "already_processed": True,
                "amount": existing["amount"],
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

        # 退款金额：默认全额
        refund_amount_val = amount if amount is not None else original["amount"]
        if refund_amount_val > original["amount"]:
            return _make_error(INVALID_AMOUNT,
                f"退款金额 {refund_amount_val} 超过原扣费金额 {original['amount']}")

        # 查询用户
        user = db.query(Users).filter(Users.user_id == user_id).first()
        if not user:
            return _make_error(USER_NOT_FOUND, "用户不存在")

        credit_type = original["credit_type"]
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
            "amount": refund_amount_val,
            "balance_before": balance_before,
            "balance_after": balance_after,
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
    final_amount: int,
    service_secret: str,
    description: Optional[str] = None,
) -> Dict[str, Any]:
    """
    结算：只对 personal_silver 退差额
    - gold 和 team_gold 预扣即最终，不退差额
    - final_amount < 原扣费金额时，差额退回 personal_silver
    - final_amount >= 原扣费金额时，不做操作
    - 幂等性：通过 idempotency_key 唯一约束保证
    """
    if not service_secret or not verify_service_secret(service_secret):
        return _make_error(UNAUTHORIZED, "service_secret 无效")

    if not idempotency_key:
        return _make_error(MISSING_IDEMPOTENCY_KEY, "idempotency_key 不能为空")

    if not original_record_id:
        return _make_error(ORIGINAL_RECORD_NOT_FOUND, "原扣费记录ID不能为空")

    if final_amount < 0:
        return _make_error(INVALID_AMOUNT, "结算金额不能为负数")

    db = get_session()
    try:
        # 幂等性检查
        existing = _find_by_idempotency_key(db, idempotency_key)
        if existing:
            return _make_success({
                "record_id": existing["id"],
                "already_processed": True,
                "amount": existing["amount"],
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

        original_amount = original["amount"]
        credit_type = original["credit_type"]

        # 计算差额
        diff = original_amount - final_amount
        if diff <= 0:
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
                description=description or "结算：无差额可退",
            )
            db.commit()

            return _make_success({
                "record_id": record_id,
                "original_amount": original_amount,
                "final_amount": final_amount,
                "refund_amount": 0,
                "credit_type": credit_type,
                "balance_before": user.silver_credits or 0,
                "balance_after": user.silver_credits or 0,
            }, "结算成功（无差额）")

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
            description=description or f"结算：退差额 {diff} 到银豆",
        )
        db.commit()

        return _make_success({
            "record_id": record_id,
            "original_amount": original_amount,
            "final_amount": final_amount,
            "refund_amount": diff,
            "refund_to": "personal_silver",
            "credit_type": credit_type,
            "balance_before": balance_before,
            "balance_after": balance_after,
        }, "结算成功")

    except Exception as e:
        db.rollback()
        logger.error(f"结算失败: {e}")
        return _make_error(INTERNAL_ERROR, f"结算失败: {str(e)}")
    finally:
        db.close()
