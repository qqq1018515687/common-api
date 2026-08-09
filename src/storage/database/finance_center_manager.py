import logging
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional

from sqlalchemy import text

from storage.database.amounts import gold_amount_to_number
from storage.database.billing_manager import get_balance
from storage.database.db import get_session

logger = logging.getLogger(__name__)

# 上海固定时区（+08:00，不依赖运行环境）
SHANGHAI_TZ = timezone(timedelta(hours=8))

# 充值订单 source_type 分账口径（与前端/其他后端全局统一）
# - paid / paid_commercial：商业收入
# - manual：人工补款
# - compensation：补偿赠送
COMMERCIAL_SOURCE_TYPES = ("paid", "paid_commercial")
MANUAL_SOURCE_TYPES = ("manual",)
COMPENSATION_SOURCE_TYPES = ("compensation",)

# 各风险规则默认阈值
DEFAULT_THRESHOLDS = {
    "high_redeem_failures": 8,          # 同用户近1小时内兑换失败次数闸限
    "same_code_reuse": 3,               # 同 code_hash 失败出现次数闸限
    "issued_not_redeemed_days": 2,      # 已发码未兑换超过 N 天视为异常
    "deduct_unsettled_hours": 2,        # 扣费完成超过 N 小时仍未退款/结算
    "team_spend_spike_multiplier": 3,   # 团队日消费超过 7 日均值 N 倍
    "large_manual_order_amount": 1000,  # 人工/补偿大额订单金额闸限
}

# 各风险规则默认风险等级（前端风控页展示用，后端为唯一真源）
RISK_LEVELS = {
    "high_redeem_failures": "high",
    "same_code_reuse": "high",
    "paid_not_issued_orders": "high",
    "issued_not_redeemed_orders": "medium",
    "deduct_unsettled": "high",
    "team_spend_spike": "medium",
    "large_manual_order": "medium",
    "redeemed_no_ledger": "high",
}

ORDER_STATUS_COUNTS = ["paid", "issued", "redeemed", "refunded", "reversed", "cancelled", "exception", "pending_payment"]


def to_epoch_ms(dt_val: Optional[datetime]) -> Optional[int]:
    """将 DB 返回的 naive datetime 安全转为 13 位毫秒时间戳。

    背景：仓库里 created_at 等时间列底层返回的是 naive datetime，其值即北京
    （Asia/Shanghai）本地墙钟时刻，无 tzinfo。若按 UTC 解释会凭空偏移 8 小时。
    这里统一把 naive datetime 视为 Asia/Shanghai 再转 UTC epoch，保证时间戳正确。
    """
    if dt_val is None:
        return None
    if dt_val.tzinfo is None:
        dt_val = dt_val.replace(tzinfo=SHANGHAI_TZ)
    return int(dt_val.timestamp() * 1000)


def _shanghai_now_naive() -> datetime:
    """当前时间（Asia/Shanghai 墙钟 naive，与 DB 存储口径一致）。"""
    return datetime.now(SHANGHAI_TZ).replace(tzinfo=None)


def _shanghai_today_bounds() -> tuple[datetime, datetime]:
    """今天（Asia/Shanghai）的 [开始, 结束) naive 时间窗口。"""
    now_naive = _shanghai_now_naive()
    start = now_naive.replace(hour=0, minute=0, second=0, microsecond=0)
    return start, start + timedelta(days=1)


def _trend_window_start(days: int) -> datetime:
    """trend 窗口起点（上海当天往前 days-1 天的 00:00，含今天）。"""
    start_today, _ = _shanghai_today_bounds()
    return start_today - timedelta(days=max(int(days or 7) - 1, 0))


def _clamp_days(days: Optional[int]) -> int:
    try:
        return min(max(int(days or 7), 1), 90)
    except (TypeError, ValueError):
        return 7


def _rows(db, sql_string: str, params: Dict[str, Any]) -> List[Dict[str, Any]]:
    """执行只读 SQL 并返回 dict 行列表。"""
    return [dict(row) for row in db.execute(text(sql_string), params).mappings().all()]


def _scalar_sum(db, sql_string: str, params: Dict[str, Any]) -> float:
    """执行只读汇总 SQL，取 v 列的数值金额（无行返回 0）。"""
    rows = _rows(db, sql_string, params)
    if not rows:
        return 0.0
    return gold_amount_to_number(rows[0].get("v"))


def _section(code: str, title: str, total: int, samples: List[Any]) -> Dict[str, Any]:
    """构造风控异常节结构。同时输出 items（前端展示用）与 samples（兼容旧字段别名）。"""
    items = list(samples or [])[:5]
    return {
        "code": code,
        "title": title,
        "level": RISK_LEVELS.get(code, "medium"),
        "total": total,
        "samples": items,
        "items": items,
    }


def overview(days: int = 7) -> Dict[str, Any]:
    """资金中心总览：今日指标 + 最近 N 天（Asia/Shanghai 日历日）每日趋势。

    口径铁律（SQL 层实现，前端/后端全局统一）：
    - 消费总额 ONLY 统计 billing_records：deduct 计消费、refund 计退款；
      team_consumption_records 是团队视图账，绝不合入消费主数字，仅作为
      团队视角单独字段返回。
    - 充值/收入从订单层 recharge_orders 按 source_type 分账：
      paid/paid_commercial 商业收入、manual 人工补款、compensation 补偿赠送。
    - 收入确认排除资金已回退的订单：status NOT IN ('reversed','refunded','cancelled')，
      避免「收了钱又冲正/退款/取消」的订单在收入和 net 中二次占位。
    - 到账 credited 从 recharge_redemptions.amount 统计。
    - 退款 = billing_records refund 金额 + recharge_orders refunded 金额（各自独立字段）。
      冲正（reversed）产生的退款仅走 billing_records refund，不再计入订单层 refunded，
      避免同一笔冲正在两个来源被重复统计。
    - net = recharge_paid + recharge_manual - consumption + refund。
    """
    safe_days = _clamp_days(days)
    today_start, today_end = _shanghai_today_bounds()
    trend_start = _trend_window_start(safe_days)

    db = get_session()
    try:
        # ---------- 今日充值订单分账（按 paid 时间，无 paid_at 回退 created_at） ----------
        # 收入口径：仅统计仍有资金意义的订单状态，排除已冲正/已退款/已取消的订单，
        # 避免「收了钱又扣回」的订单同时霸占收入与退款两个方向。
        order_rows = _rows(db, """
            SELECT source_type,
                   SUM(amount_paid) AS total_paid,
                   COUNT(*)         AS order_cnt
            FROM recharge_orders
            WHERE status NOT IN ('reversed', 'refunded', 'cancelled')
              AND COALESCE(paid_at, created_at) >= :start
              AND COALESCE(paid_at, created_at) <  :end
            GROUP BY source_type
        """, {"start": today_start, "end": today_end})
        order_map = {r["source_type"]: r for r in order_rows}
        recharge_paid = 0.0
        recharge_manual = 0.0
        recharge_compensation = 0.0
        order_count = 0
        for stype, bucket in order_map.items():
            order_count += int(bucket.get("order_cnt") or 0)
            total_paid = gold_amount_to_number(bucket.get("total_paid"))
            if stype in COMMERCIAL_SOURCE_TYPES:
                recharge_paid += total_paid
            elif stype in MANUAL_SOURCE_TYPES:
                recharge_manual += total_paid
            elif stype in COMPENSATION_SOURCE_TYPES:
                recharge_compensation += total_paid

        # 今日到账（recharge_redemptions）
        credited_today = _scalar_sum(db, """
            SELECT SUM(amount) AS v FROM recharge_redemptions
            WHERE created_at >= :start AND created_at < :end
        """, {"start": today_start, "end": today_end})

        # 今日消费（billing_records deduct，completed）
        consumption_today = _scalar_sum(db, """
            SELECT SUM(amount) AS v FROM billing_records
            WHERE operation_type = 'deduct' AND status = 'completed'
              AND created_at >= :start AND created_at < :end
        """, {"start": today_start, "end": today_end})

        # 今日退款 = billing refund + recharge_orders refunded（不含冲正订单，冲正走 billing refund 与 reversal）
        billing_refund_today = _scalar_sum(db, """
            SELECT SUM(amount) AS v FROM billing_records
            WHERE operation_type = 'refund' AND status = 'completed'
              AND created_at >= :start AND created_at < :end
        """, {"start": today_start, "end": today_end})
        order_refund_today = _scalar_sum(db, """
            SELECT SUM(amount_paid) AS v FROM recharge_orders
            WHERE status = 'refunded'
              AND COALESCE(refunded_at, created_at) >= :start
              AND COALESCE(refunded_at, created_at) <  :end
        """, {"start": today_start, "end": today_end})

        # 今日兑换用户数 / 消费用户数
        redeem_user_rows = _rows(db, """
            SELECT COUNT(DISTINCT user_id) AS c FROM recharge_redemptions
            WHERE created_at >= :start AND created_at < :end
        """, {"start": today_start, "end": today_end})
        redeem_user_today = int(redeem_user_rows[0].get("c") or 0) if redeem_user_rows else 0
        consume_user_rows = _rows(db, """
            SELECT COUNT(DISTINCT user_id) AS c FROM billing_records
            WHERE operation_type = 'deduct' AND status = 'completed'
              AND created_at >= :start AND created_at < :end
        """, {"start": today_start, "end": today_end})
        consume_user_today = int(consume_user_rows[0].get("c") or 0) if consume_user_rows else 0

        # 今日已支付未发码订单数
        pni_rows = _rows(db, """
            SELECT COUNT(*) AS c FROM recharge_orders
            WHERE status = 'paid' AND issued_code_count = 0
              AND COALESCE(paid_at, created_at) >= :start
              AND COALESCE(paid_at, created_at) <  :end
        """, {"start": today_start, "end": today_end})
        paid_not_issued_today = int(pni_rows[0].get("c") or 0) if pni_rows else 0

        reversal_pending_rows = _rows(db, """
            SELECT COUNT(*) AS c FROM recharge_reversal_requests
            WHERE status = 'pending'
        """, {})
        reversal_pending_today = int(reversal_pending_rows[0].get("c") or 0) if reversal_pending_rows else 0

        reversal_completed_rows = _rows(db, """
            SELECT COUNT(*) AS c FROM recharge_reversal_requests
            WHERE status = 'completed'
              AND resolved_at >= :start AND resolved_at < :end
        """, {"start": today_start, "end": today_end})
        reversal_completed_today = int(reversal_completed_rows[0].get("c") or 0) if reversal_completed_rows else 0

        reversal_refund_rows = _rows(db, """
            SELECT SUM(refund_amount) AS v FROM recharge_orders
            WHERE status IN ('reversed', 'refunded')
              AND refunded_at >= :start AND refunded_at < :end
              AND note LIKE :flag
        """, {"start": today_start, "end": today_end, "flag": '%冲正完成:%'})
        reversal_refund_today = gold_amount_to_number(reversal_refund_rows[0].get("v")) if reversal_refund_rows else 0.0

        # 团队视图账（仅返回金额，绝不 与消费主数字相加）
        team_view = _scalar_sum(db, """
            SELECT SUM(amount) AS v FROM team_consumption_records
            WHERE operation_type = 'consumption'
              AND created_at >= :start AND created_at < :end
        """, {"start": today_start, "end": today_end})

        refund_total = billing_refund_today + order_refund_today
        net_today = recharge_paid + recharge_manual - consumption_today + refund_total

        today = {
            "date": today_start.strftime("%Y-%m-%d"),
            "recharge_paid": round(recharge_paid, 2),
            "recharge_manual": round(recharge_manual, 2),
            "recharge_compensation": round(recharge_compensation, 2),
            "credited": round(credited_today, 2),
            "consumption": round(consumption_today, 2),
            "refund": round(refund_total, 2),
            "refund_billing": round(billing_refund_today, 2),
            "refund_order": round(order_refund_today, 2),
            "net": round(net_today, 2),
            "order_count": int(order_count),
            "redeem_user_count": int(redeem_user_today),
            "consume_user_count": int(consume_user_today),
            "paid_not_issued_count": int(paid_not_issued_today),
            "reversal_pending_count": int(reversal_pending_today),
            "reversal_completed_count": int(reversal_completed_today),
            "reversal_refund_amount": round(reversal_refund_today, 2),
            # 团队视角独立字段（团队可用余额变动总和，金额为负表示消费）
            "team_consumption_records_sum": round(team_view, 2),
        }

        trend = _compute_trend(db, trend_start, safe_days)
        return {"days": safe_days, "today": today, "trend": trend}
    except Exception:
        logger.exception("资金中心总览查询失败")
        raise
    finally:
        db.close()


def _compute_trend(db, window_start: datetime, days: int) -> List[Dict[str, Any]]:
    """按上海日历日聚合近 days 天趋势。

    注意：DB 中 created_at 存储的即上海墙钟 naive，直接 to_char(created_at) 即本地日，
    不再做任何 time zone 转换，从根本上避免 8 小时偏移。
    """
    recharge_rows = _rows(db, """
        SELECT to_char(COALESCE(paid_at, created_at), 'YYYY-MM-DD') AS d,
               SUM(amount_paid) AS v
        FROM recharge_orders
        WHERE COALESCE(paid_at, created_at) >= :start
          AND status NOT IN ('reversed', 'refunded', 'cancelled')
        GROUP BY d
    """, {"start": window_start})

    # 净额口径：仅计入商业收入(paid/paid_commercial)与人工(manual)，
    # 补偿(campaign/compensation)不计入 net，与 overview.today 统一。
    # 同时排除已冲正/已退款/已取消订单，避免已扣回资金在净额中二次占位。
    net_recharge_rows = _rows(db, """
        SELECT to_char(COALESCE(paid_at, created_at), 'YYYY-MM-DD') AS d,
               SUM(amount_paid) AS v
        FROM recharge_orders
        WHERE COALESCE(paid_at, created_at) >= :start
          AND source_type IN ('paid', 'paid_commercial', 'manual')
          AND status NOT IN ('reversed', 'refunded', 'cancelled')
        GROUP BY d
    """, {"start": window_start})

    credited_rows = _rows(db, """
        SELECT to_char(created_at, 'YYYY-MM-DD') AS d, SUM(amount) AS v
        FROM recharge_redemptions
        WHERE created_at >= :start
        GROUP BY d
    """, {"start": window_start})

    consumption_rows = _rows(db, """
        SELECT to_char(created_at, 'YYYY-MM-DD') AS d, SUM(amount) AS v
        FROM billing_records
        WHERE operation_type = 'deduct' AND status = 'completed'
          AND created_at >= :start
        GROUP BY d
    """, {"start": window_start})

    refund_rows = _rows(db, """
        SELECT d, SUM(v) AS v FROM (
            SELECT to_char(created_at, 'YYYY-MM-DD') AS d, amount AS v
            FROM billing_records
            WHERE operation_type = 'refund' AND status = 'completed'
              AND created_at >= :start_b
            UNION ALL
            SELECT to_char(COALESCE(refunded_at, created_at), 'YYYY-MM-DD') AS d, amount_paid AS v
            FROM recharge_orders
            WHERE status = 'refunded' AND COALESCE(refunded_at, created_at) >= :start_o
        ) sub GROUP BY d
    """, {"start_b": window_start, "start_o": window_start})

    recharge_map = {r["d"]: gold_amount_to_number(r.get("v")) for r in recharge_rows}
    net_recharge_map = {r["d"]: gold_amount_to_number(r.get("v")) for r in net_recharge_rows}
    credited_map = {r["d"]: gold_amount_to_number(r.get("v")) for r in credited_rows}
    consumption_map = {r["d"]: gold_amount_to_number(r.get("v")) for r in consumption_rows}
    refund_map = {r["d"]: gold_amount_to_number(r.get("v")) for r in refund_rows}

    result: List[Dict[str, Any]] = []
    for i in range(days):
        day = (window_start + timedelta(days=i)).strftime("%Y-%m-%d")
        recharge = recharge_map.get(day, 0.0)
        net_recharge = net_recharge_map.get(day, 0.0)
        credited = credited_map.get(day, 0.0)
        consumption = consumption_map.get(day, 0.0)
        refund = refund_map.get(day, 0.0)
        result.append({
            "date": day,
            "recharge": round(recharge, 2),
            "credited": round(credited, 2),
            "consumption": round(consumption, 2),
            "refund": round(refund, 2),
            "net": round(net_recharge - consumption + refund, 2),
        })
    return result


def _coerce_time(value: Any) -> Optional[datetime]:
    """把节点传来的时间参数（datetime / epoch ms(int,float,str) / 'YYYY-MM-DD HH:MM:SS'）转成 naive datetime。

    时间解释均视为上海墙钟（与 DB 存储口径一致）。
    """
    if value is None or value == "":
        return None
    if isinstance(value, datetime):
        return value.replace(tzinfo=None) if value.tzinfo else value
    if isinstance(value, (int, float)):
        if value > 10_000_000_000:  # 毫秒
            value = value / 1000
        return datetime.fromtimestamp(float(value), tz=SHANGHAI_TZ).replace(tzinfo=None)
    if isinstance(value, str):
        text_value = value.strip()
        for fmt in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%d %H:%M", "%Y-%m-%d"):
            try:
                return datetime.strptime(text_value, fmt)
            except ValueError:
                continue
        raise ValueError(f"无法解析的时间参数: {value}")
    raise ValueError(f"无法解析的时间参数: {value}")


def orders_query(
    status: Optional[str] = None,
    channel: Optional[str] = None,
    source_type: Optional[str] = None,
    reversal_status: Optional[str] = None,
    user_id: Optional[str] = None,
    team_id: Optional[str] = None,
    search: Optional[str] = None,
    start_time: Any = None,
    end_time: Any = None,
    page: int = 1,
    limit: int = 50,
) -> Dict[str, Any]:
    """recharge_orders 多条件分页只读查询。

    支持 status / channel / source_type / reversal_status / user_id / team_id / search(order_no 或
    external_order_id 模糊) / start_time / end_time（时间窗按 paid 时间）/
    page / limit。每行序列化：order_signal + created/paid/issued/redeemed/
    refunded/cancelled 时间为 epoch ms，金额为 number。返回 {orders,total,page,limit}。
    """
    try:
        safe_page = max(int(page or 1), 1)
        safe_limit = min(max(int(limit or 50), 1), 200)
    except (TypeError, ValueError):
        safe_page, safe_limit = 1, 50

    # 时间参数统一转成 naive datetime（上海墙钟口径）
    start_dt = _coerce_time(start_time)
    end_dt = _coerce_time(end_time)

    where: List[str] = ["1 = 1"]
    params: Dict[str, Any] = {}
    join_sql = ""
    if status:
        where.append("status = :status")
        params["status"] = status
    if channel:
        where.append("channel = :channel")
        params["channel"] = channel
    if source_type:
        where.append("source_type = :source_type")
        params["source_type"] = source_type
    if reversal_status:
        join_sql = " LEFT JOIN recharge_reversal_requests rrr ON rrr.order_id = recharge_orders.id "
        where.append("rrr.status = :reversal_status")
        params["reversal_status"] = reversal_status
    if user_id:
        where.append("user_id = :user_id")
        params["user_id"] = user_id
    if team_id:
        where.append("team_id = :team_id")
        params["team_id"] = team_id
    if search:
        where.append("(order_no LIKE :search OR external_order_id LIKE :search)")
        params["search"] = f"%{search}%"
    if start_dt:
        where.append("COALESCE(paid_at, created_at) >= :start_time")
        params["start_time"] = start_dt
    if end_dt:
        where.append("COALESCE(paid_at, created_at) < :end_time")
        params["end_time"] = end_dt
    where_sql = " AND ".join(where)

    db = get_session()
    try:
        total_sql = f"SELECT COUNT(DISTINCT recharge_orders.id) AS c FROM recharge_orders {join_sql} WHERE {where_sql}"
        total_rows = _rows(db, total_sql, params)
        total = int(total_rows[0].get("c") or 0) if total_rows else 0

        page_sql = (
            f"SELECT recharge_orders.* FROM recharge_orders {join_sql} WHERE {where_sql} "
            "ORDER BY COALESCE(paid_at, created_at) DESC LIMIT :limit OFFSET :offset"
        )
        rows = _rows(db, page_sql, {**params, "limit": safe_limit, "offset": (safe_page - 1) * safe_limit})

        orders = []
        for r in rows:
            orders.append({
                "id": r.get("id"),
                "order_signal": _order_signal(r),
                "order_no": r.get("order_no"),
                "external_order_id": r.get("external_order_id"),
                "user_id": r.get("user_id"),
                "team_id": r.get("team_id"),
                "channel": r.get("channel"),
                "source_type": r.get("source_type"),
                "status": r.get("status"),
                "amount_paid": gold_amount_to_number(r.get("amount_paid")),
                "credited_amount": gold_amount_to_number(r.get("credited_amount")),
                "refund_amount": gold_amount_to_number(r.get("refund_amount")),
                "issued_code_count": r.get("issued_code_count") or 0,
                "created_at": to_epoch_ms(r.get("created_at")),
                "paid_at": to_epoch_ms(r.get("paid_at")),
                "issued_at": to_epoch_ms(r.get("issued_at")),
                "redeemed_at": to_epoch_ms(r.get("redeemed_at")),
                "refunded_at": to_epoch_ms(r.get("refunded_at")),
                "cancelled_at": to_epoch_ms(r.get("cancelled_at")),
            })

        return {"orders": orders, "total": total, "page": safe_page, "limit": safe_limit}
    except Exception:
        logger.exception("充值订单查询失败")
        raise
    finally:
        db.close()


def _order_signal(row: Dict[str, Any]) -> Dict[str, Any]:
    """订单摘要信号：把关键业务状态压实到小对象，方便前端一眼识别。"""
    return {
        "package_name": row.get("package_name"),
        "currency": row.get("currency"),
        "refunded": row.get("status") == "refunded",
        "reversed": row.get("status") == "reversed",
        "waiting_issue": row.get("status") == "paid" and (row.get("issued_code_count") or 0) == 0,
    }


def order_summary() -> Dict[str, Any]:
    """按 status 汇总 recharge_orders 各状态订单数 + 专项布尔口径。

    统一前端契约：顶层字段直接平铺（paid/issued/redeemed/refunded/cancelled/
    exception/pending_payment/total/paid_not_issued/issued_not_redeemed），
    前端按扁平字段解析，不再依赖 summary_by_status 嵌套结构。
    """
    db = get_session()
    try:
        rows = _rows(db, "SELECT status, COUNT(*) AS c FROM recharge_orders GROUP BY status", {})
        counts = {r["status"]: int(r["c"]) for r in rows}

        # 专项口径：paid 但未发码 / issued 未兑换
        pni_rows = _rows(db, """
            SELECT COUNT(*) AS c FROM recharge_orders WHERE status = 'paid' AND issued_code_count = 0
        """, {})
        out_rows = _rows(db, "SELECT COUNT(*) AS c FROM recharge_orders WHERE status = 'issued'", {})
        paid_not_issued = int(pni_rows[0].get("c") or 0) if pni_rows else 0
        issued_not_redeemed = int(out_rows[0].get("c") or 0) if out_rows else 0

        return {
            "paid": counts.get("paid", 0),
            "issued": counts.get("issued", 0),
            "redeemed": counts.get("redeemed", 0),
            "refunded": counts.get("refunded", 0),
            "reversed": counts.get("reversed", 0),
            "cancelled": counts.get("cancelled", 0),
            "exception": counts.get("exception", 0),
            "pending_payment": counts.get("pending_payment", 0),
            "total": sum(counts.values()),
            "paid_not_issued": paid_not_issued,
            "issued_not_redeemed": issued_not_redeemed,
            "summary_by_status": {s: counts.get(s, 0) for s in ORDER_STATUS_COUNTS},
        }
    except Exception:
        logger.exception("订单状态汇总查询失败")
        raise
    finally:
        db.close()


def risk_exceptions(
    days: int = 7,
    thresholds: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """实时风控异常扫描（只读，绝不写表）。

    返回 {generated_at, sections}，sections 每项 {code,title,total,samples[<=5]}。
    无异常时 total=0 且 samples=[]，节仍然保留在数组中。
    各规则阈值可由 thresholds 覆盖，默认见 DEFAULT_THRESHOLDS。
    """
    now_naive = _shanghai_now_naive()
    sections: List[Dict[str, Any]] = []

    db = get_session()
    try:
        # 1) 高频失败（同用户近 1h）
        fail_thr = int(_safe_threshold(thresholds, "high_redeem_failures"))
        fail_since = now_naive - timedelta(hours=1)
        fail_rows = _rows(db, """
            SELECT user_id, COUNT(*) AS cnt, MAX(created_at) AS last_at
            FROM recharge_failed_attempts
            WHERE created_at >= :since AND user_id IS NOT NULL
            GROUP BY user_id HAVING COUNT(*) >= :thr
            ORDER BY cnt DESC LIMIT 5
        """, {"since": fail_since, "thr": fail_thr})
        fail_total_rows = _rows(db, """
            SELECT COUNT(*) AS c FROM (
                SELECT user_id FROM recharge_failed_attempts
                WHERE created_at >= :since AND user_id IS NOT NULL
                GROUP BY user_id HAVING COUNT(*) >= :thr
            ) t
        """, {"since": fail_since, "thr": fail_thr})
        fail_total = int(fail_total_rows[0].get("c") or 0) if fail_total_rows else 0
        sections.append(_section(
            code="high_redeem_failures",
            title="高频兑换失败",
            total=fail_total,
            samples=[{"user_id": r["user_id"], "count": int(r["cnt"]), "last_at": to_epoch_ms(r["last_at"])} for r in fail_rows],
        ))

        # 2) 同一 code_hash 复用（全量历史）
        reuse_thr = int(_safe_threshold(thresholds, "same_code_reuse"))
        reuse_rows = _rows(db, """
            SELECT code_hash, COUNT(*) AS cnt, MAX(created_at) AS last_at
            FROM recharge_failed_attempts
            WHERE code_hash IS NOT NULL
            GROUP BY code_hash HAVING COUNT(*) >= :thr
            ORDER BY cnt DESC LIMIT 5
        """, {"thr": reuse_thr})
        reuse_total_rows = _rows(db, """
            SELECT COUNT(*) AS c FROM (
                SELECT code_hash FROM recharge_failed_attempts
                WHERE code_hash IS NOT NULL GROUP BY code_hash HAVING COUNT(*) >= :thr
            ) t
        """, {"thr": reuse_thr})
        reuse_total = int(reuse_total_rows[0].get("c") or 0) if reuse_total_rows else 0
        sections.append(_section(
            code="same_code_reuse",
            title="兑换码重复尝试",
            total=reuse_total,
            samples=[{"code_hash": r["code_hash"], "count": int(r["cnt"]), "last_at": to_epoch_ms(r["last_at"])} for r in reuse_rows],
        ))

        # 3) 已支付未发码订单
        pni_rows = _rows(db, """
            SELECT id, order_no, user_id, amount_paid, paid_at
            FROM recharge_orders WHERE status = 'paid' AND issued_code_count = 0
            ORDER BY COALESCE(paid_at, created_at) DESC LIMIT 5
        """, {})
        pni_total_rows = _rows(db, """
            SELECT COUNT(*) AS c FROM recharge_orders WHERE status = 'paid' AND issued_code_count = 0
        """, {})
        pni_total = int(pni_total_rows[0].get("c") or 0) if pni_total_rows else 0
        sections.append(_section(
            code="paid_not_issued_orders",
            title="已支付未发码订单",
            total=pni_total,
            samples=[
                {"order_id": r["id"], "order_no": r["order_no"], "user_id": r["user_id"],
                 "amount_paid": gold_amount_to_number(r["amount_paid"]), "paid_at": to_epoch_ms(r["paid_at"])}
                for r in pni_rows
            ],
        ))

        # 4) 已发码超过 N 天未兑换（按发码时间判断，未发码回落 created_at）
        overdue_days = int(_safe_threshold(thresholds, "issued_not_redeemed_days"))
        cutoff_days = now_naive - timedelta(days=overdue_days)
        issued_rows = _rows(db, """
            SELECT id, order_no, user_id, issued_at, created_at
            FROM recharge_orders WHERE status = 'issued'
              AND COALESCE(issued_at, created_at) <= :cutoff
            ORDER BY COALESCE(issued_at, created_at) ASC LIMIT 5
        """, {"cutoff": cutoff_days})
        issued_total_rows = _rows(db, """
            SELECT COUNT(*) AS c FROM recharge_orders WHERE status = 'issued'
              AND COALESCE(issued_at, created_at) <= :cutoff
        """, {"cutoff": cutoff_days})
        issued_total = int(issued_total_rows[0].get("c") or 0) if issued_total_rows else 0
        sections.append(_section(
            code="issued_not_redeemed_orders",
            title="已发码多日未兑换",
            total=issued_total,
            samples=[
                {"order_id": r["id"], "order_no": r["order_no"], "user_id": r["user_id"],
                 "issued_at": to_epoch_ms(r["issued_at"]), "created_at": to_epoch_ms(r["created_at"])}
                for r in issued_rows
            ],
        ))

        # 5) 扣费完成超 N 小时仍未退款/结算（related_id 无对应 refund/settle 的完成记录）
        unsettle_hours = _safe_threshold(thresholds, "deduct_unsettled_hours")
        deduct_cutoff = now_naive - timedelta(hours=unsettle_hours)
        unsettled_rows = _rows(db, """
            SELECT b.id, b.user_id, b.amount, b.credit_type, b.task_id, b.created_at
            FROM billing_records b
            WHERE b.operation_type = 'deduct' AND b.status = 'completed'
              AND b.created_at <= :cutoff
              AND NOT EXISTS (
                  SELECT 1 FROM billing_records r
                  WHERE r.related_id = b.id AND r.operation_type IN ('refund', 'settle')
                    AND r.status = 'completed'
              )
            ORDER BY b.created_at DESC LIMIT 5
        """, {"cutoff": deduct_cutoff})
        deduct_total_rows = _rows(db, """
            SELECT COUNT(*) AS c FROM billing_records b
            WHERE b.operation_type = 'deduct' AND b.status = 'completed'
              AND b.created_at <= :cutoff
              AND NOT EXISTS (
                  SELECT 1 FROM billing_records r
                  WHERE r.related_id = b.id AND r.operation_type IN ('refund', 'settle')
                    AND r.status = 'completed'
              )
        """, {"cutoff": deduct_cutoff})
        deduct_total = int(deduct_total_rows[0].get("c") or 0) if deduct_total_rows else 0
        sections.append(_section(
            code="deduct_unsettled",
            title="扣费未完成结算",
            total=deduct_total,
            samples=[
                {"record_id": r["id"], "user_id": r["user_id"], "credit_type": r["credit_type"],
                 "amount": gold_amount_to_number(r["amount"]), "task_id": r["task_id"],
                 "created_at": to_epoch_ms(r["created_at"])}
                for r in unsettled_rows
            ],
        ))

        # 6) 团队近 7 天某日支出超均值 * N
        spike_days = _clamp_days(days)
        spike_window = _trend_window_start(spike_days)
        spike_multiplier = _safe_threshold(thresholds, "team_spend_spike_multiplier")
        team_rows = _rows(db, """
            SELECT team_id, to_char(created_at, 'YYYY-MM-DD') AS day,
                   SUM(-amount) AS day_spend
            FROM team_consumption_records
            WHERE operation_type = 'consumption' AND created_at >= :start AND team_id IS NOT NULL
            GROUP BY team_id, day
        """, {"start": spike_window})
        team_agg: Dict[str, Dict[str, Any]] = {}
        for r in team_rows:
            tid = r["team_id"]
            agg = team_agg.setdefault(tid, {"total": 0.0, "days": {}})
            spend = gold_amount_to_number(r["day_spend"])
            agg["total"] += spend
            agg["days"][r["day"]] = spend
        spike_samples: List[Dict[str, Any]] = []
        spike_total = 0
        for tid, agg in team_agg.items():
            avg = agg["total"] / max(len(agg["days"]), 1)
            for day, spend in agg["days"].items():
                if avg > 0 and spend > avg * spike_multiplier:
                    spike_total += 1
                    if len(spike_samples) < 5:
                        spike_samples.append({"team_id": tid, "date": day, "amount": round(spend, 2)})
        sections.append(_section(
            code="team_spend_spike",
            title="团队异常突增消费",
            total=spike_total,
            samples=spike_samples,
        ))

        # 7) 人工/补偿类型大额订单
        large_thr = _safe_threshold(thresholds, "large_manual_order_amount")
        large_rows = _rows(db, """
            SELECT id, order_no, user_id, channel, source_type, amount_paid, paid_at
            FROM recharge_orders
            WHERE source_type IN ('manual', 'compensation') AND amount_paid > :thr
            ORDER BY amount_paid DESC LIMIT 5
        """, {"thr": large_thr})
        large_total_rows = _rows(db, """
            SELECT COUNT(*) AS c FROM recharge_orders
            WHERE source_type IN ('manual', 'compensation') AND amount_paid > :thr
        """, {"thr": large_thr})
        large_total = int(large_total_rows[0].get("c") or 0) if large_total_rows else 0
        sections.append(_section(
            code="large_manual_order",
            title="人工/补偿大额订单",
            total=large_total,
            samples=[
                {"order_id": r["id"], "order_no": r["order_no"], "user_id": r["user_id"],
                 "channel": r["channel"], "source_type": r["source_type"],
                 "amount_paid": gold_amount_to_number(r["amount_paid"]), "paid_at": to_epoch_ms(r["paid_at"])}
                for r in large_rows
            ],
        ))

        # 8) 已兑换但主账/团队账未写入（双空）
        ledger_rows = _rows(db, """
            SELECT id, code_id, user_id, team_id, amount, created_at
            FROM recharge_redemptions
            WHERE status = 'completed' AND billing_record_id IS NULL AND team_record_id IS NULL
            ORDER BY created_at DESC LIMIT 5
        """, {})
        ledger_total_rows = _rows(db, """
            SELECT COUNT(*) AS c FROM recharge_redemptions
            WHERE status = 'completed' AND billing_record_id IS NULL AND team_record_id IS NULL
        """, {})
        ledger_total = int(ledger_total_rows[0].get("c") or 0) if ledger_total_rows else 0
        sections.append(_section(
            code="redeemed_no_ledger",
            title="已兑换未入账",
            total=ledger_total,
            samples=[
                {"redemption_id": r["id"], "code_id": r["code_id"], "user_id": r["user_id"],
                 "team_id": r["team_id"], "amount": gold_amount_to_number(r["amount"])}
                for r in ledger_rows
            ],
        ))

        reversal_pending_rows = _rows(db, """
            SELECT order_id, order_no, requested_by, created_at, reason
            FROM recharge_reversal_requests
            WHERE status = 'pending'
            ORDER BY created_at ASC LIMIT 5
        """, {})
        reversal_pending_total_rows = _rows(db, """
            SELECT COUNT(*) AS c FROM recharge_reversal_requests
            WHERE status = 'pending'
        """, {})
        reversal_pending_total = int(reversal_pending_total_rows[0].get("c") or 0) if reversal_pending_total_rows else 0
        sections.append(_section(
            code="reversal_pending_review",
            title="待审批冲正申请",
            total=reversal_pending_total,
            samples=[
                {"order_id": r["order_id"], "order_no": r["order_no"], "requested_by": r["requested_by"],
                 "created_at": to_epoch_ms(r["created_at"]), "reason": r["reason"]}
                for r in reversal_pending_rows
            ],
        ))

        reversal_approved_rows = _rows(db, """
            SELECT order_id, order_no, resolved_by, resolved_at, resolution_note
            FROM recharge_reversal_requests
            WHERE status = 'approved'
            ORDER BY resolved_at DESC NULLS LAST, created_at DESC LIMIT 5
        """, {})
        reversal_approved_total_rows = _rows(db, """
            SELECT COUNT(*) AS c FROM recharge_reversal_requests
            WHERE status = 'approved'
        """, {})
        reversal_approved_total = int(reversal_approved_total_rows[0].get("c") or 0) if reversal_approved_total_rows else 0
        sections.append(_section(
            code="reversal_approved_unfinished",
            title="已批准未执行冲正",
            total=reversal_approved_total,
            samples=[
                {"order_id": r["order_id"], "order_no": r["order_no"], "resolved_by": r["resolved_by"],
                 "resolved_at": to_epoch_ms(r["resolved_at"]), "resolution_note": r["resolution_note"]}
                for r in reversal_approved_rows
            ],
        ))

        return {"generated_at": to_epoch_ms(now_naive), "sections": sections}
    except Exception:
        logger.exception("风控异常扫描失败")
        raise
    finally:
        db.close()



def _safe_threshold(thresholds: Optional[Dict[str, Any]], key: str) -> float:
    return float((thresholds or {}).get(key, DEFAULT_THRESHOLDS[key]))
