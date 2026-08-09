"""充值订单数据层管理器。

提供充值订单（recharge_orders）与兑换失败审计（recharge_failed_attempts）的
访问与管理能力。每个公开函数自带 session 并保证 try/except/rollback/finally close。

- 订单面额真源：amount_paid；实际入账：credited_amount（按已兑码金额累加）。
- 状态口径：pending_payment -> paid（已付未发码）-> issued（已发码未全兑）
  -> redeemed（全量兑换），终态 out: refunded（未核销订单手动退款状态，无余额扣回）
  / reversed（已核销订单账务冲正，已真实扣回余额）/ cancelled / exception。
- 冲正现金流：complete_reversal_request 会把订单置为 reversed 并写 billing/team
  退款流水；reversed 与 refunded 语义互斥,财务聚合按状态区分,禁止混为一谈。
"""
import logging
import secrets
import string
import uuid
from datetime import datetime, timezone, timedelta
from decimal import Decimal
from typing import Any, Optional

from sqlalchemy import func, or_

from storage.database.amounts import gold_amount_to_number, normalize_gold_amount
from storage.database.billing_manager import _insert_billing_record
from storage.database.db import get_session
from storage.database.shared.model import RechargeCodes, RechargeFailedAttempts, RechargeOrders, RechargeReversalRequests, TeamConsumptionRecords, Teams, Users


logger = logging.getLogger(__name__)

SHANGHAI_TZ = timezone(timedelta(hours=8))

VALID_SOURCE_TYPES = {"paid", "manual", "compensation", "campaign"}
VALID_CHANNELS = {"wechat", "xianyu", "manual", "campaign", "compensation", "ldxp"}
VALID_STATUS = {"pending_payment", "paid", "issued", "redeemed", "refunded", "cancelled", "exception", "reversed"}
REFUNDABLE_STATUS = {"pending_payment", "paid", "issued"}
REDEEMED_STATUS = {"paid", "issued", "redeemed"}  # 订单允许继续累加进度/更新状态的状态

DEFAULT_LIMIT = 50
MAX_LIMIT = 500


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _to_epoch_ms(value: Optional[datetime]) -> Optional[int]:
    """将 datetime 转为 13 位毫秒时间戳。

    naive datetime 视为 Asia/Shanghai（因为 PG 返回的 TIMESTAMPTZ
    在客户端时区下表现为 naive 本地时间），与 billing_manager._to_epoch_ms 一致。
    """
    if not value:
        return None
    if value.tzinfo is None:
        value = value.replace(tzinfo=SHANGHAI_TZ)
    return int(value.timestamp() * 1000)


def _normalize_text(value: Optional[str], *, max_len: int = 255) -> Optional[str]:
    if not isinstance(value, str):
        return None
    text_value = value.strip()
    return text_value[:max_len] if text_value else None


def _serialize_code(code: RechargeCodes) -> dict[str, Any]:
    """序列化单个兑换码（供订单明细展示使用）。"""
    return {
        "id": code.id,
        "batch_id": code.batch_id,
        "order_id": code.order_id,
        "code_suffix": code.code_suffix,
        "credit_type": code.credit_type,
        "amount": gold_amount_to_number(code.amount),
        "status": code.status,
        "used_by": code.used_by,
        "used_team_id": code.used_team_id,
        "used_at": _to_epoch_ms(code.used_at),
        "expires_at": _to_epoch_ms(code.expires_at),
        "created_at": _to_epoch_ms(code.created_at),
        "updated_at": _to_epoch_ms(code.updated_at),
    }


def _serialize_order(order: RechargeOrders, codes: Optional[list[RechargeCodes]] = None) -> dict[str, Any]:
    """订单序列化：金额转 number、时间转 epoch ms。"""
    data: dict[str, Any] = {
        "id": order.id,
        "order_no": order.order_no,
        "user_id": order.user_id,
        "team_id": order.team_id,
        "package_id": order.package_id,
        "package_name": order.package_name,
        "amount_paid": gold_amount_to_number(order.amount_paid),
        "credited_amount": gold_amount_to_number(order.credited_amount),
        "currency": order.currency,
        "channel": order.channel,
        "source_type": order.source_type,
        "status": order.status,
        "external_order_id": order.external_order_id,
        "external_ref": order.external_ref,
        "paid_at": _to_epoch_ms(order.paid_at),
        "issued_at": _to_epoch_ms(order.issued_at),
        "redeemed_at": _to_epoch_ms(order.redeemed_at),
        "refunded_at": _to_epoch_ms(order.refunded_at),
        "cancelled_at": _to_epoch_ms(order.cancelled_at),
        "issued_code_count": order.issued_code_count,
        "refund_amount": gold_amount_to_number(order.refund_amount),
        "operator_id": order.operator_id,
        "note": order.note,
        "metadata": order.extra_data,
        "created_at": _to_epoch_ms(order.created_at),
        "updated_at": _to_epoch_ms(order.updated_at),
    }
    if codes is not None:
        data["codes"] = [_serialize_code(code) for code in codes]
    return data


def _serialize_reversal_request(request: RechargeReversalRequests) -> dict[str, Any]:
    return {
        "requested": True,
        "reason": request.reason,
        "status": request.status,
        "requested_at": _to_epoch_ms(request.created_at),
        "requested_by": request.requested_by,
        "resolved_at": _to_epoch_ms(request.resolved_at),
        "resolved_by": request.resolved_by,
        "resolution_note": request.resolution_note,
    }


def _serialize_order_with_reversal(db, order: RechargeOrders, *, codes: Optional[list[RechargeCodes]] = None) -> dict[str, Any]:
    data = _serialize_order(order, codes=codes)
    reversal = db.query(RechargeReversalRequests).filter(RechargeReversalRequests.order_id == order.id).first()
    if reversal:
        data["reversal_request"] = _serialize_reversal_request(reversal)
    return data


def _generate_order_no(db) -> str:
    """生成订单号：RFR + 年月日时分秒(UTC) + 4 位随机大写字符。

    冲突时重试最多 10 次。
    """
    order_no = None
    for _attempt in range(10):
        tail = "".join(secrets.choice(string.ascii_uppercase + string.digits) for _ in range(4))
        candidate = "RFR" + datetime.now(timezone.utc).strftime("%y%m%d%H%M%S") + tail
        exists = db.query(RechargeOrders.id).filter(RechargeOrders.order_no == candidate).first()
        if not exists:
            order_no = candidate
            break
    if not order_no:
        raise RuntimeError("订单号生成冲突，请重试")
    return order_no


def _sanitize_page(page: Any) -> int:
    try:
        value = int(page or 1)
    except (TypeError, ValueError):
        value = 1
    return max(1, value)


def _sanitize_limit(limit: Any, default: int = DEFAULT_LIMIT) -> int:
    try:
        value = int(limit or default)
    except (TypeError, ValueError):
        value = default
    return min(max(1, value), MAX_LIMIT)


def _parse_date_bound(value: Any, *, is_end: bool) -> Optional[datetime]:
    """把前端传入的日期筛选值转换成用于数据库比较的 datetime。

    支持两种格式：
    - 毫秒时间戳（int/float）
    - 字符串日期 "YYYY-MM-DD"，按 **Asia/Shanghai** 本地日期换算：
      start_time 取当天 00:00、end_time 取当天 23:59:59（均为上海本地时间，非 UTC）。
    标注：数据列存 UTC，此处换算后以 UTC 时间参与过滤，保证日期边界正确。
    """
    if value in (None, ""):
        return None
    if isinstance(value, (int, float)):
        ts = float(value)
        if ts > 10_000_000_000:
            ts = ts / 1000
        return datetime.fromtimestamp(ts, tz=timezone.utc)
    if isinstance(value, str):
        text_value = value.strip()
        if not text_value:
            return None
        parts = text_value.split("T")[0].split(" ")[0]
        date_parts = parts.split("-")
        if len(date_parts) == 3:
            try:
                year, month, day = int(date_parts[0]), int(date_parts[1]), int(date_parts[2])
            except ValueError:
                raise ValueError("日期格式无效，应为 YYYY-MM-DD")
            shanghai_local = datetime(year, month, day, 23, 59, 59 if is_end else 0, 0, 0, tzinfo=SHANGHAI_TZ)
            # 上海本地时间换算成对应 UTC 时刻参与库内过滤
            return shanghai_local.astimezone(timezone.utc)
        try:
            parsed = datetime.fromisoformat(text_value.replace("Z", "+00:00"))
        except ValueError:
            raise ValueError("日期格式无效")
        return parsed if parsed.tzinfo else parsed.replace(tzinfo=SHANGHAI_TZ).astimezone(timezone.utc)
    raise ValueError("日期格式无效")


def _payment_time_expr():
    """统一订单时间筛选口径：优先 paid_at，无值回退 created_at。"""
    return func.coalesce(RechargeOrders.paid_at, RechargeOrders.created_at)


def create_order(
    *,
    user_id: Optional[str] = None,
    team_id: Optional[str] = None,
    package_id: Optional[str] = None,
    package_name: Optional[str] = None,
    amount_paid: Any,
    channel: str = "manual",
    source_type: str = "paid",
    external_order_id: Optional[str] = None,
    external_ref: Optional[str] = None,
    operator_id: Optional[str] = None,
    note: Optional[str] = None,
    status: str = "paid",
) -> dict[str, Any]:
    """创建充值订单（团队管理直达）。

    - 校验面额 > 0、source_type/channel/status 枚举合法。
    - external_order_id 若已登记过则直接返回该已有订单，防止重复建单。
    - 订单号 RFR + yymmddHHMMSS + 4 位随机大写，冲突重试最多 10 次。
    - status 命中 REDEEMED_STATUS 时补齐 paid_at = now。
    """
    amount_value = normalize_gold_amount(amount_paid)
    source_value = (source_type or "paid").strip().lower()
    if source_value not in VALID_SOURCE_TYPES:
        raise ValueError("订单来源类型无效")
    channel_value = (channel or "manual").strip().lower()
    if channel_value not in VALID_CHANNELS:
        raise ValueError("订单渠道无效")
    status_value = (status or "paid").strip().lower()
    if status_value not in VALID_STATUS:
        raise ValueError("订单状态无效")

    ext_order_id = _normalize_text(external_order_id, max_len=128)
    ext_ref = _normalize_text(external_ref, max_len=255)
    order_note = _normalize_text(note, max_len=2000)
    package_name_value = _normalize_text(package_name, max_len=100)

    db = get_session()
    try:
        # 防重复建单：外部单号已登记则返回已有订单
        if ext_order_id:
            existing = db.query(RechargeOrders).filter(RechargeOrders.external_order_id == ext_order_id).first()
            if existing:
                return {
                    "code": 1,
                    "msg": "外部订单已登记",
                    "order": _serialize_order(existing),
                    "order_id": existing.id,
                }

        order_id = str(uuid.uuid4())
        order_no = _generate_order_no()
        now_value = _now()
        order = RechargeOrders(
            id=order_id,
            order_no=order_no,
            user_id=_normalize_text(user_id, max_len=36),
            team_id=_normalize_text(team_id, max_len=64),
            package_id=_normalize_text(package_id, max_len=64),
            package_name=package_name_value,
            amount_paid=amount_value,
            credited_amount=None,
            currency="CNY",
            channel=channel_value,
            source_type=source_value,
            status=status_value,
            external_order_id=ext_order_id,
            external_ref=ext_ref,
            paid_at=now_value if status_value in REDEEMED_STATUS else None,
            issued_code_count=0,
            refund_amount=None,
            operator_id=_normalize_text(operator_id, max_len=64),
            note=order_note,
        )
        db.add(order)
        db.commit()
        db.refresh(order)
        return {
            "code": 0,
            "msg": "订单创建成功",
            "order": _serialize_order(order),
            "order_id": order_id,
            "order_no": order_no,
        }
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()


def get_order(order_id: str) -> dict[str, Any]:
    """按订单 ID 查询订单明细，返回订单 + 关联兑换码列表。"""
    if not order_id:
        raise ValueError("订单ID不能为空")
    db = get_session()
    try:
        order = db.query(RechargeOrders).filter(RechargeOrders.id == order_id).first()
        if not order:
            return {"code": 1, "msg": "订单不存在", "order": None, "codes": []}
        codes = db.query(RechargeCodes).filter(RechargeCodes.order_id == order_id).order_by(RechargeCodes.created_at.asc()).all()
        order_data = _serialize_order_with_reversal(db, order, codes=codes)
        return {
            "code": 0,
            "msg": "查询成功",
            "order": order_data,
            "codes": [_serialize_code(code) for code in codes],
        }
    finally:
        db.close()


def get_order_by_no(order_no: str) -> dict[str, Any]:
    """按订单号查询订单明细（含关联兑换码列表）。"""
    order_no_value = _normalize_text(order_no, max_len=40)
    if not order_no_value:
        raise ValueError("订单号不能为空")
    db = get_session()
    try:
        order = db.query(RechargeOrders).filter(RechargeOrders.order_no == order_no_value).first()
        if not order:
            return {"code": 1, "msg": "订单不存在", "order": None, "codes": []}
        return get_order(order.id)
    finally:
        db.close()


def list_orders(
    *,
    status: Optional[str] = None,
    channel: Optional[str] = None,
    source_type: Optional[str] = None,
    user_id: Optional[str] = None,
    search: Optional[str] = None,
    start_time: Any = None,
    end_time: Any = None,
    page: Any = 1,
    limit: Any = DEFAULT_LIMIT,
    reversal_status: Optional[str] = None,
) -> dict[str, Any]:
    """分页查询订单列表，按统一订单时间倒序。

    时间口径统一为：优先 paid_at，无值回退 created_at。
    start_time/end_time 按 **Asia/Shanghai** 本地日期过滤（见 _parse_date 标注）。
    """
    safe_page = _sanitize_page(page)
    safe_limit = _sanitize_limit(limit)
    start_dt = _parse_date_bound(start_time, is_end=False)
    end_dt = _parse_date_bound(end_time, is_end=True)
    status_value = (status or "").strip().lower() or None
    channel_value = (channel or "").strip().lower() or None
    source_value = (source_type or "").strip().lower() or None
    reversal_value = (reversal_status or "").strip().lower() or None
    user_value = _normalize_text(user_id, max_len=36)
    search_text = _normalize_text(search, max_len=64)

    db = get_session()
    try:
        query = db.query(RechargeOrders)
        排序时间 = _payment_time_expr()
        if reversal_value:
            query = query.join(RechargeReversalRequests, RechargeReversalRequests.order_id == RechargeOrders.id)
        if status_value:
            query = query.filter(RechargeOrders.status == status_value)
        if channel_value:
            query = query.filter(RechargeOrders.channel == channel_value)
        if source_value:
            query = query.filter(RechargeOrders.source_type == source_value)
        if reversal_value:
            query = query.filter(RechargeReversalRequests.status == reversal_value)
        if user_value:
            query = query.filter(RechargeOrders.user_id == user_value)
        if search_text:
            like = f"%{search_text}%"
            query = query.filter(or_(RechargeOrders.order_no.ilike(like), RechargeOrders.package_name.ilike(like)))
        if start_dt:
            query = query.filter(排序时间 >= start_dt)
        if end_dt:
            query = query.filter(排序时间 <= end_dt)

        total = query.count()
        rows = (
            query
            .order_by(排序时间.desc())
            .offset((safe_page - 1) * safe_limit)
            .limit(safe_limit)
            .all()
        )
        return {
            "orders": [_serialize_order_with_reversal(db, order) for order in rows],
            "total": total,
            "page": safe_page,
            "limit": safe_limit,
        }
    finally:
        db.close()


def list_order_summary() -> dict[str, Any]:
    """按订单状态口径返回统计。

    paid=已付未发码（status='paid'）、issued=已发码未全兑（status='issued'）、
    redeemed/cancelled/exception 各自独立计数，total 为订单总数。
    """
    db = get_session()
    try:
        total = db.query(func.count(RechargeOrders.id)).scalar() or 0
        rows = (
            db.query(RechargeOrders.status, func.count(RechargeOrders.id))
            .group_by(RechargeOrders.status)
            .all()
        )
        counts = {row[0]: int(row[1]) for row in rows}
        return {
            "paid": counts.get("paid", 0),
            "issued": counts.get("issued", 0),
            "redeemed": counts.get("redeemed", 0),
            "refunded": counts.get("refunded", 0),
            "cancelled": counts.get("cancelled", 0),
            "exception": counts.get("exception", 0),
            "pending_payment": counts.get("pending_payment", 0),
            "total": total,
        }
    finally:
        db.close()


def update_order_progress(db, code: RechargeCodes) -> dict[str, Any]:
    """内部函数：某个兑换码核销成功后，推进该订单入账进度。

    - 需在 redeem 使用的**同一个 db session** 内调用（传入 db 参数，不自建 session）。
    - credited_amount 累加已核销码的 amount。
    - 统计该订单 used 码数 vs issued_code_count：
      - 已兑码数 >= 发码数 => status='redeemed'、redeemed_at=now
      - 否则 => status='issued'，且 issued_at 为空时补 now。
    - 不在这里 commit，由外层（recharge_code_manager.redeem）在同一事务提交时保存。
    返回更新后的订单序列化结果。
    """
    order_id = getattr(code, "order_id", None)
    if not order_id:
        return {"code": 1, "msg": "兑换码未绑定订单，跳过", "order": None}
    order = db.query(RechargeOrders).filter(RechargeOrders.id == order_id).first()
    if not order:
        return {"code": 1, "msg": "订单不存在", "order": None}

    amount = Decimal(str(code.amount or 0))
    credited_before = Decimal(str(order.credited_amount or 0))
    credited_after = credited_before + amount
    order.credited_amount = credited_after

    used_count = (
        db.query(func.count(RechargeCodes.id))
        .filter(RechargeCodes.order_id == order_id, RechargeCodes.status == "used")
        .scalar()
        or 0
    )
    issued_count = int(order.issued_code_count or 0)
    now_value = _now()
    if used_count >= issued_count and used_count > 0:
        order.status = "redeemed"
        order.redeemed_at = now_value
    else:
        order.status = "issued"
        if order.issued_at is None:
            order.issued_at = now_value
    order.updated_at = now_value
    return {"code": 0, "msg": "订单进度已更新", "order": _serialize_order(order)}


def refund_order(
    *,
    order_id: str,
    operator_id: Optional[str] = None,
    reason: Optional[str] = None,
    amount: Any = None,
) -> dict[str, Any]:
    """退款订单（订单状态管理，不构成财务退款闭环）。

    仅当 status 在 {pending_payment, paid, issued} 且没有已全兑退款记录时可转 refunded：
    - 若订单已有任何「已使用」的兑换码，则**拒绝**退款——因为用户已实际入账金豆，
      此处的订单级退款并不会有余额扣回；必须走对账/冲正流程而非直接标 refunded。
    - 校验订单退款金额（默认取 credited_amount，为空时用 amount_paid）。
    - 同订单 status='unused' 的码批量置为 'disabled'（防止后续被兑）。
    """
    if not order_id:
        raise ValueError("订单ID不能为空")
    db = get_session()
    try:
        order = db.query(RechargeOrders).filter(RechargeOrders.id == order_id).with_for_update().first()
        if not order:
            raise ValueError("订单不存在")
        if order.status not in REFUNDABLE_STATUS:
            raise ValueError(f"当前订单状态不可退款: {order.status}")
        if order.refunded_at is not None or order.refund_amount is not None:
            raise ValueError("该订单已有退款记录，禁止重复退款")

        # 已兑换的金豆已入账，直接改订单状态会造成账实不符 => 拒绝
        used_count = (
            db.query(func.count(RechargeCodes.id))
            .filter(RechargeCodes.order_id == order_id, RechargeCodes.status == "used")
            .scalar()
            or 0
        )
        if used_count > 0:
            raise ValueError(
                "该订单已发生兑换（金豆已入账），不能直接标记退款；请联系运营走账务冲正流程"
            )

        refund_value = amount
        if refund_value is None:
            refund_value = order.amount_paid
        refund_decimal = normalize_gold_amount(refund_value)

        now_value = _now()
        order.status = "refunded"
        order.refunded_at = now_value
        order.refund_amount = refund_decimal
        order.updated_at = now_value
        if operator_id:
            order.operator_id = _normalize_text(operator_id, max_len=64)
        if reason:
            reason_text = _normalize_text(reason, max_len=2000)
            order.note = f"{order.note}\n退款原因: {reason_text}" if order.note else f"退款原因: {reason_text}"

        # 禁用本订单仍 unused 的码，防止退款后再回收
        disabled = (
            db.query(RechargeCodes)
            .filter(RechargeCodes.order_id == order_id, RechargeCodes.status == "unused")
            .update({"status": "disabled", "updated_at": now_value}, synchronize_session=False)
        )
        db.commit()
        db.refresh(order)
        return {
            "code": 0,
            "msg": "订单退款成功（仅订单状态，不含已入账金豆扣回）",
            "order": _serialize_order(order),
            "disabled_codes": disabled,
        }
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()


def cancel_order(
    *,
    order_id: str,
    operator_id: Optional[str] = None,
    reason: Optional[str] = None,
) -> dict[str, Any]:
    """取消订单：仅当该订单未发生过任何兑换（无 used 码）时允许。

    取消后同步把该订单 unused 码置为 disabled。
    """
    if not order_id:
        raise ValueError("订单ID不能为空")
    db = get_session()
    try:
        order = db.query(RechargeOrders).filter(RechargeOrders.id == order_id).with_for_update().first()
        if not order:
            raise ValueError("订单不存在")
        used_count = (
            db.query(func.count(RechargeCodes.id))
            .filter(RechargeCodes.order_id == order_id, RechargeCodes.status == "used")
            .scalar()
            or 0
        )
        if used_count > 0:
            raise ValueError("该订单已发生兑换，不能取消")

        now_value = _now()
        order.status = "cancelled"
        order.cancelled_at = now_value
        order.updated_at = now_value
        if operator_id:
            order.operator_id = _normalize_text(operator_id, max_len=64)
        if reason:
            reason_text = _normalize_text(reason, max_len=2000)
            order.note = f"{order.note}\n取消原因: {reason_text}" if order.note else f"取消原因: {reason_text}"

        disabled = (
            db.query(RechargeCodes)
            .filter(RechargeCodes.order_id == order_id, RechargeCodes.status == "unused")
            .update({"status": "disabled", "updated_at": now_value}, synchronize_session=False)
        )
        db.commit()
        db.refresh(order)
        return {
            "code": 0,
            "msg": "订单取消成功",
            "order": _serialize_order(order),
            "disabled_codes": disabled,
        }
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()


def record_failed_attempt(
    *,
    user_id: Optional[str] = None,
    ip: Optional[str] = None,
    code_hash: Optional[str] = None,
    code_suffix: Optional[str] = None,
    reason_type: str = "unknown",
    reason: Optional[str] = None,
) -> Optional[str]:
    """记录一次兑换失败尝试（防刷/风控审计）。

    独立 session、原子一次写入；任何异常都不上抛，仅打日志，
    可安全地被兑换流程在失败分支调用。
    """
    record_id = str(uuid.uuid4())
    db = get_session()
    try:
        db.add(RechargeFailedAttempts(
            id=record_id,
            user_id=_normalize_text(user_id, max_len=36),
            ip=_normalize_text(ip, max_len=64),
            code_hash=_normalize_text(code_hash, max_len=128),
            code_suffix=_normalize_text(code_suffix, max_len=12),
            reason_type=(reason_type or "unknown").strip()[:32],
            reason=_normalize_text(reason, max_len=255),
        ))
        db.commit()
        return record_id
    except Exception as exc:
        db.rollback()
        logger.error("记录兑换失败尝试异常: %s", exc, exc_info=True)
        return None
    finally:
        db.close()


def create_reversal_request(*, order_id: str, requested_by: Optional[str], reason: str) -> dict[str, Any]:
    if not order_id:
        raise ValueError("订单ID不能为空")
    reason_text = _normalize_text(reason, max_len=2000)
    if not reason_text:
        raise ValueError("冲正原因不能为空")

    db = get_session()
    try:
        order = db.query(RechargeOrders).filter(RechargeOrders.id == order_id).with_for_update().first()
        if not order:
            raise ValueError("订单不存在")
        if order.status != 'redeemed':
            raise ValueError("仅已核销订单可申请冲正")

        existing = db.query(RechargeReversalRequests).filter(RechargeReversalRequests.order_id == order_id).first()
        if existing:
            return {
                "code": 0,
                "msg": "冲正申请已存在",
                "order": {
                    **_serialize_order(order),
                    "reversal_request": _serialize_reversal_request(existing)
                }
            }

        now_value = _now()
        request = RechargeReversalRequests(
            id=str(uuid.uuid4()),
            order_id=order.id,
            order_no=order.order_no,
            user_id=order.user_id,
            team_id=order.team_id,
            requested_by=_normalize_text(requested_by, max_len=64),
            reason=reason_text,
            status='pending',
            created_at=now_value,
            updated_at=now_value,
        )
        db.add(request)
        db.commit()
        db.refresh(request)
        return {
            "code": 0,
            "msg": "冲正申请已提交",
            "order": {
                **_serialize_order(order),
                "reversal_request": _serialize_reversal_request(request)
            }
        }
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()


def review_reversal_request(
    *,
    order_id: str,
    action: str,
    resolved_by: Optional[str],
    resolution_note: Optional[str],
) -> dict[str, Any]:
    if not order_id:
        raise ValueError("订单ID不能为空")
    action_value = (action or "").strip().lower()
    if action_value not in {"approve", "reject"}:
        raise ValueError("冲正处理动作无效")
    note_text = _normalize_text(resolution_note, max_len=2000)
    if not note_text:
        raise ValueError("处理备注不能为空")

    db = get_session()
    try:
        order = db.query(RechargeOrders).filter(RechargeOrders.id == order_id).with_for_update().first()
        if not order:
            raise ValueError("订单不存在")

        request = db.query(RechargeReversalRequests).filter(RechargeReversalRequests.order_id == order_id).with_for_update().first()
        if not request:
            raise ValueError("该订单还没有冲正申请")
        if request.status == "completed":
            raise ValueError("该冲正申请已完成，不能重复处理")
        if request.status == "rejected" and action_value == "reject":
            raise ValueError("该冲正申请已驳回")
        if request.status == "approved" and action_value == "approve":
            raise ValueError("该冲正申请已批准")

        now_value = _now()
        request.status = "approved" if action_value == "approve" else "rejected"
        request.resolved_by = _normalize_text(resolved_by, max_len=64)
        request.resolution_note = note_text
        request.resolved_at = now_value
        request.updated_at = now_value

        db.commit()
        db.refresh(request)
        db.refresh(order)
        return {
            "code": 0,
            "msg": "冲正申请处理成功",
            "order": {
                **_serialize_order(order),
                "reversal_request": _serialize_reversal_request(request)
            }
        }
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()


def complete_reversal_request(
    *,
    order_id: str,
    resolved_by: Optional[str],
    resolution_note: Optional[str],
) -> dict[str, Any]:
    if not order_id:
        raise ValueError("订单ID不能为空")
    note_text = _normalize_text(resolution_note, max_len=2000)
    if not note_text:
        raise ValueError("完成冲正必须填写处理备注")

    db = get_session()
    try:
        order = db.query(RechargeOrders).filter(RechargeOrders.id == order_id).with_for_update().first()
        if not order:
            raise ValueError("订单不存在")

        request = db.query(RechargeReversalRequests).filter(RechargeReversalRequests.order_id == order_id).with_for_update().first()
        if not request:
            raise ValueError("该订单还没有冲正申请")
        if request.status == "completed":
            raise ValueError("该冲正申请已完成")
        if request.status != "approved":
            raise ValueError("仅已批准的冲正申请可执行完成")

        codes = db.query(RechargeCodes).filter(RechargeCodes.order_id == order_id).with_for_update().all()
        used_codes = [code for code in codes if code.status == "used"]
        if not used_codes:
            raise ValueError("该订单没有已核销兑换码，不能执行冲正完成")

        now_value = _now()
        reversed_total = Decimal("0")
        refunded_billing_records: list[str] = []
        refunded_team_records: list[str] = []

        for code in used_codes:
            amount = Decimal(str(code.amount or 0))
            if amount <= 0:
                continue

            if code.billing_record_id:
                user = db.query(Users).filter(Users.user_id == code.used_by).with_for_update().first()
                if not user:
                    raise ValueError(f"兑换用户不存在: {code.used_by}")
                before_val = Decimal(str(user.gold_credits or 0))
                after_val = before_val - amount
                if after_val < 0:
                    raise ValueError(f"用户余额不足，不能冲正: {code.used_by}")
                user.gold_credits = after_val

                refund_record_id = str(uuid.uuid4())
                _insert_billing_record(
                    db=db,
                    record_id=refund_record_id,
                    idempotency_key=f"reversal:refund:billing:{code.id}",
                    user_id=code.used_by,
                    team_id=None,
                    operation_type="refund",
                    credit_type="personal_gold",
                    amount=amount,
                    balance_before=before_val,
                    balance_after=after_val,
                    related_id=code.billing_record_id,
                    description=f"充值冲正退款 · {order.order_no or order.id}",
                    extra_data={
                        "source": "reversal_request",
                        "order_id": order.id,
                        "order_no": order.order_no,
                        "code_id": code.id,
                        "request_id": request.id,
                    },
                )
                refunded_billing_records.append(refund_record_id)

            elif code.team_record_id:
                if not code.used_team_id:
                    raise ValueError("团队兑换码缺少 used_team_id，不能冲正")
                team = db.query(Teams).filter(Teams.id == code.used_team_id).with_for_update().first()
                if not team:
                    raise ValueError(f"团队不存在: {code.used_team_id}")
                before_val = Decimal(str(team.balance or 0))
                after_val = before_val - amount
                if after_val < 0:
                    raise ValueError(f"团队余额不足，不能冲正: {code.used_team_id}")
                team.balance = after_val
                current_total_consumed = Decimal(str(team.total_consumed or 0))
                team.total_consumed = current_total_consumed - amount
                team.updated_at = now_value

                team_record_id = str(uuid.uuid4())
                db.add(TeamConsumptionRecords(
                    id=team_record_id,
                    team_id=code.used_team_id,
                    user_id=code.used_by or order.user_id or "system",
                    username=None,
                    amount=-amount,
                    balance_before=before_val,
                    balance_after=after_val,
                    operation_type="refund",
                    related_id=code.team_record_id,
                    description=f"充值冲正退款 · {order.order_no or order.id}",
                    extra_data={
                        "source": "reversal_request",
                        "order_id": order.id,
                        "order_no": order.order_no,
                        "code_id": code.id,
                        "request_id": request.id,
                    },
                ))
                refunded_team_records.append(team_record_id)

            else:
                raise ValueError("兑换码缺少账单关联，不能执行冲正")

            code.status = "disabled"
            code.updated_at = now_value
            reversed_total += amount

        order.status = "reversed"
        order.refunded_at = now_value
        order.refund_amount = reversed_total
        order.updated_at = now_value
        order.operator_id = _normalize_text(resolved_by, max_len=64) or order.operator_id
        if note_text:
            order.note = f"{order.note}\n冲正完成: {note_text}" if order.note else f"冲正完成: {note_text}"

        request.status = "completed"
        request.resolved_by = _normalize_text(resolved_by, max_len=64)
        request.resolution_note = note_text
        request.resolved_at = now_value
        request.updated_at = now_value

        db.commit()
        db.refresh(order)
        db.refresh(request)
        return {
            "code": 0,
            "msg": "冲正执行完成",
            "order": {
                **_serialize_order(order),
                "reversal_request": _serialize_reversal_request(request)
            },
            "reversed_amount": gold_amount_to_number(reversed_total),
            "refunded_billing_records": refunded_billing_records,
            "refunded_team_records": refunded_team_records,
        }
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()


def preview_reversal_request(*, order_id: str) -> dict[str, Any]:
    if not order_id:
        raise ValueError("订单ID不能为空")

    db = get_session()
    try:
        order = db.query(RechargeOrders).filter(RechargeOrders.id == order_id).first()
        if not order:
            raise ValueError("订单不存在")

        request = db.query(RechargeReversalRequests).filter(RechargeReversalRequests.order_id == order_id).first()
        if not request:
            raise ValueError("该订单还没有冲正申请")

        codes = db.query(RechargeCodes).filter(RechargeCodes.order_id == order_id).all()
        used_codes = [code for code in codes if code.status == "used"]

        preview_items: list[dict[str, Any]] = []
        total_amount = Decimal("0")
        all_ok = True

        for code in used_codes:
            amount = Decimal(str(code.amount or 0))
            total_amount += amount
            item: dict[str, Any] = {
                "code_id": code.id,
                "code_suffix": code.code_suffix,
                "amount": gold_amount_to_number(amount),
                "target_type": "personal" if code.billing_record_id else "team" if code.team_record_id else "unknown",
                "target_id": code.used_by if code.billing_record_id else code.used_team_id,
                "balance_ok": False,
                "balance_before": None,
                "balance_after": None,
                "message": None,
            }

            if code.billing_record_id:
                user = db.query(Users).filter(Users.user_id == code.used_by).first()
                before_val = Decimal(str(user.gold_credits or 0)) if user else Decimal("0")
                after_val = before_val - amount
                item["balance_before"] = gold_amount_to_number(before_val)
                item["balance_after"] = gold_amount_to_number(after_val)
                item["balance_ok"] = bool(user) and after_val >= 0
                item["message"] = None if item["balance_ok"] else "个人余额不足，执行时会失败"
            elif code.team_record_id:
                team = db.query(Teams).filter(Teams.id == code.used_team_id).first()
                before_val = Decimal(str(team.balance or 0)) if team else Decimal("0")
                after_val = before_val - amount
                item["balance_before"] = gold_amount_to_number(before_val)
                item["balance_after"] = gold_amount_to_number(after_val)
                item["balance_ok"] = bool(team) and after_val >= 0
                item["message"] = None if item["balance_ok"] else "团队余额不足，执行时会失败"
            else:
                item["message"] = "缺少账单关联，执行时会失败"

            if not item["balance_ok"]:
                all_ok = False
            preview_items.append(item)

        return {
            "code": 0,
            "msg": "冲正预检成功",
            "order": {
                **_serialize_order(order),
                "reversal_request": _serialize_reversal_request(request),
            },
            "preview": {
                "all_balance_ok": all_ok,
                "used_code_count": len(used_codes),
                "total_amount": gold_amount_to_number(total_amount),
                "items": preview_items,
            },
        }
    finally:
        db.close()
