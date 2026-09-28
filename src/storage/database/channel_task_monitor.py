"""根据最近的真实任务终态维护 T 版单模型波动通知。"""

from __future__ import annotations

import logging
import time
from collections import defaultdict
from dataclasses import dataclass
from typing import Literal

from sqlalchemy import func
from sqlalchemy.orm import Session

from storage.database.notification_manager import NotificationCreate, NotificationManager
from storage.database.shared.model import SystemNotifications, Tasks
from storage.database.task_manager import 工作流模型渠道映射


logger = logging.getLogger(__name__)

WINDOW_MS = 10 * 60 * 1000
RECOVERY_MS = 5 * 60 * 1000
MIN_ACTIVE_MS = 5 * 60 * 1000
MAX_EVENTS_PER_STATUS = 2000
NOTICE_PREFIX = "auto_model_status_"
MONITORED_MODELS = {
    model for model, channel in 工作流模型渠道映射.get("workflow_02", {}).items()
    if channel == "t"
}


@dataclass(frozen=True)
class TaskSignal:
    model: str
    label: str
    status: Literal["completed", "failed"]
    reason: str
    time_ms: int


def decide_action(signals: list[TaskSignal], active_since: int | None, now_ms: int) -> str | None:
    """仅在连续真实失败或稳定成功时切换状态；无样本保持原状。"""
    recent = sorted(
        (item for item in signals if now_ms - WINDOW_MS <= item.time_ms <= now_ms),
        key=lambda item: item.time_ms,
        reverse=True,
    )
    if active_since is None:
        if len(recent) >= 3 and all(
            item.status == "failed" and item.reason == "provider_failed"
            for item in recent[:3]
        ):
            return "alert"
        return None

    if now_ms - active_since < MIN_ACTIVE_MS:
        return None
    recovery = [item for item in recent if item.time_ms >= max(active_since, now_ms - RECOVERY_MS)]
    if len(recovery) >= 3 and all(item.status == "completed" for item in recovery[:3]) and not any(
        item.status == "failed" and item.reason == "provider_failed" for item in recovery
    ):
        return "recover"
    return None


def _read_signals(db: Session, now_ms: int) -> list[TaskSignal]:
    since = str(now_ms - WINDOW_MS)
    model_key = func.coalesce(
        func.json_extract_path_text(Tasks.workflow_parameters, "model_name"),
        func.json_extract_path_text(Tasks.parameter_snapshot, "workflowParams", "model_name"),
        func.json_extract_path_text(Tasks.parameter_snapshot, "modelValue"),
    )
    workflow_id = func.coalesce(
        func.json_extract_path_text(Tasks.parameter_snapshot, "workflowId"),
        func.json_extract_path_text(Tasks.workflow_parameters, "workflow_id"),
    )
    model_label = func.coalesce(
        func.json_extract_path_text(Tasks.parameter_snapshot, "modelName"),
        func.json_extract_path_text(Tasks.parameter_snapshot, "modelDisplayName"),
    )
    fields = (Tasks.id, Tasks.platform, Tasks.status, Tasks.final_reason, model_key, workflow_id, model_label)
    failed = (
        db.query(*fields, Tasks.failed_at)
        .filter(Tasks.status == "failed", Tasks.failed_at >= since, Tasks.platform == "tudou")
        .order_by(Tasks.failed_at.desc())
        .limit(MAX_EVENTS_PER_STATUS + 1)
        .all()
    )
    completed = (
        db.query(*fields, Tasks.completed_at)
        .filter(Tasks.status == "completed", Tasks.completed_at >= since, Tasks.platform == "tudou")
        .order_by(Tasks.completed_at.desc())
        .limit(MAX_EVENTS_PER_STATUS + 1)
        .all()
    )
    if len(failed) > MAX_EVENTS_PER_STATUS or len(completed) > MAX_EVENTS_PER_STATUS:
        raise RuntimeError("近期任务超过单轮监控上限，已跳过通知状态变更")

    signals: list[TaskSignal] = []
    for row in (*failed, *completed):
        task_id, platform, status, reason, model, workflow, label, terminal_time = row
        if platform != "tudou" or workflow != "workflow_02" or model not in MONITORED_MODELS:
            continue
        try:
            event_time = int(terminal_time)
        except (TypeError, ValueError):
            logger.warning("[channel-monitor] 任务终态时间无效: task_id=%s", task_id)
            continue
        safe_label = str(label or model).strip()[:64]
        signals.append(TaskSignal(model, safe_label, status, reason or "", event_time))
    return signals


def monitor_channel_tasks(db: Session, now_ms: int | None = None) -> dict[str, int]:
    """每次运行最多执行两次有索引的近期任务查询，只在状态切换时写通知。"""
    now = now_ms if now_ms is not None else int(time.time() * 1000)
    signals = _read_signals(db, now)
    grouped: dict[str, list[TaskSignal]] = defaultdict(list)
    for signal in signals:
        grouped[signal.model].append(signal)

    notices = {
        str(item.biz_key)[len(NOTICE_PREFIX):]: item
        for item in db.query(SystemNotifications)
        .filter(SystemNotifications.biz_key.like(f"{NOTICE_PREFIX}%"))
        .all()
    }
    result = {"signals": len(signals), "alerts": 0, "recoveries": 0}
    for model in grouped.keys() | notices.keys():
        notice = notices.get(model)
        active_since = int(notice.start_time) if notice and notice.is_active else None
        action = decide_action(grouped.get(model, []), active_since, now)
        if action == "alert":
            label = grouped[model][0].label
            success, _, error = NotificationManager.upsert_by_biz_key(
                db,
                f"{NOTICE_PREFIX}{model}",
                NotificationCreate(
                    type="warning",
                    title=f"T版 {label} 服务波动",
                    content=f"T版 {label} 近期连续生成失败，可能暂时无法正常使用。请稍后重试，或选择其他模型。",
                    priority="medium",
                    is_active=True,
                    start_time=now,
                    end_time=None,
                    dismissible=False,
                    target_audience="all",
                    created_by="system",
                    biz_key=f"{NOTICE_PREFIX}{model}",
                ),
            )
            if not success:
                raise RuntimeError(error or f"发布 {model} 波动通知失败")
            result["alerts"] += 1
            logger.warning("[channel-monitor] 发布模型波动通知: model=%s", model)
        elif action == "recover" and notice:
            success, error = NotificationManager.delete_notification(db, notice.id)
            if not success:
                raise RuntimeError(error or f"关闭 {model} 波动通知失败")
            result["recoveries"] += 1
            logger.info("[channel-monitor] 模型任务恢复，关闭波动通知: model=%s", model)
    return result
