"""第三方渠道任务补偿核心逻辑（main 侧收敛链路）。

供两处复用：
- `src/api/tasks.py` 的 `/common/task/recover-third-party` HTTP 端点（外部手动触发）。
- `src/main.py` 的后台补偿线程（进程内直接调用，不走 HTTP 自环）。
"""
import os
import logging
from typing import Any, Dict, Optional

import requests

logger = logging.getLogger(__name__)

MAIN_STREAM_URL = "https://k33dqygqrw.coze.site/stream_run"


def build_recover_payload(
    task_id: str,
    platform: str,
    platform_task_id: str,
) -> Dict[str, Any]:
    """从本地任务补全 user_id / deduction_result，构造发往 main 的 recover 载荷。"""
    user_id = ""
    deduction_result = None
    try:
        from storage.database.db import get_session
        from storage.database.task_manager import TaskManager

        task_db = get_session()
        try:
            task_row = TaskManager().get_task_by_id(task_db, task_id)
            if task_row:
                user_id = str(task_row.user_id or "")
                deduction_result = task_row.deduction_result if isinstance(task_row.deduction_result, dict) else None
        finally:
            task_db.close()
    except Exception as exc:
        logger.warning("[third-party-recovery] 查询任务上下文失败: task_id=%s error=%s", task_id, exc)

    input_data: Dict[str, Any] = {
        "operation_type": "recover_third_party_task",
        "task_id": task_id,
        "platform": platform,
        "platform_task_id": platform_task_id,
    }
    if user_id:
        input_data["user_id"] = user_id
    if deduction_result:
        input_data["deduction_result"] = deduction_result
    return {"workflow_id": "workflow_02", "input": input_data}


def forward_third_party_recovery(
    task_id: str,
    platform: str,
    platform_task_id: str,
    auth_header: Optional[str] = None,
) -> Dict[str, Any]:
    """转发 recover 请求到 main 侧 `/stream_run`（common 直连 main，不走前端代理）。

    返回 main 的 JSON 结果。main 侧会在 `http_stream_run` 中对
    `input.operation_type == "recover_third_party_task"` 短路返回 JSON。
    """
    payload = build_recover_payload(task_id, platform, platform_task_id)

    token = os.getenv("COZE_BACKEND_TOKEN", "").strip()
    headers: Dict[str, str] = {"Content-Type": "application/json"}
    if auth_header:
        headers["Authorization"] = auth_header
    elif token:
        headers["Authorization"] = f"Bearer {token}"

    response = requests.post(
        MAIN_STREAM_URL,
        headers=headers,
        json=payload,
        timeout=120,
    )
    response.raise_for_status()
    return response.json() if response.content else {"success": True}
