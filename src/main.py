import argparse
import asyncio
import json
import traceback
import logging
from typing import Any, Dict, Iterable, AsyncIterable, AsyncGenerator, Optional
import threading
import contextvars
import cozeloop
import uvicorn
import time
from fastapi import FastAPI, File, Form, Header, HTTPException, Request, UploadFile
from fastapi.responses import StreamingResponse, JSONResponse, Response
from langchain_core.runnables import RunnableConfig
from langgraph.graph import StateGraph, END
from langgraph.graph.state import CompiledStateGraph

from coze_coding_utils.runtime_ctx.context import new_context, Context
from utils.helper import graph_helper
from utils.log.node_log import LOG_FILE
from utils.log.write_log import setup_logging, request_context
from utils.log.config import LOG_LEVEL
from utils.messages.server import (
    create_message_end_dict,
    create_message_error_dict,
    MESSAGE_END_CODE_CANCELED,
)
from storage.s3.s3_storage import S3SyncStorage
from storage.storage_manager import get_storage_manager, StorageCategory
from storage.database.db import get_session
from storage.database.ops_briefing_manager import OpsBriefingIngestInput, OpsBriefingManager, OpsDailyBriefingSaveInput
import os
import requests

setup_logging(
    log_file=LOG_FILE,
    max_bytes=100 * 1024 * 1024, # 100MB
    backup_count=5,
    log_level=LOG_LEVEL,
    use_json_format=True,
    console_output=True
)

logger = logging.getLogger(__name__)
from utils.helper.agent_helper import (
    to_stream_input,
    to_client_message,
    agent_iter_server_messages,
)
from utils.log.parser import LangGraphParser
from utils.log.err_trace import extract_core_stack
from utils.log.loop_trace import init_run_config, init_agent_config


# 超时配置常量
TIMEOUT_SECONDS = 900  # 15分钟
THIRD_PARTY_TASK_RECOVERY_INTERVAL = 30
THIRD_PARTY_TASK_RECOVERY_STALE_MS = 45 * 1000
THIRD_PARTY_TASK_RESULT_CONFIRM_TIMEOUT_MS = 5 * 60 * 1000  # 已确认建单但结果未回流，5分钟后强制失败并退款
# submitted_unconfirmed 专用：2分钟内必须确认是否拿到了真实平台任务号。
# 这个超时只用于“确认建单”，不是用于“等待最终生成完成”。
THIRD_PARTY_TASK_SUBMIT_CONFIRM_TIMEOUT_MS = 2 * 60 * 1000
THIRD_PARTY_TASK_RECOVERY_BATCH_SIZE = 50

class GraphService:
    def __init__(self):
        if not graph_helper.is_agent_proj():
            self.graph = graph_helper.get_graph_instance("graphs.graph")

        # 用于跟踪正在运行的任务（使用asyncio.Task）
        self.running_tasks: Dict[str, asyncio.Task] = {}


    def _get_graph(self, ctx=Context):
        if graph_helper.is_agent_proj():
            return graph_helper.get_agent_instance("agents.agent", ctx)
        else:
            return self.graph
    
    
    @staticmethod
    def _sse_event(data: Any) -> str:
        return f"event: message\ndata: {json.dumps(data, ensure_ascii=False, default=str)}\n\n"

    # 流式运行（原始迭代器）：本地调用使用
    def stream(self, payload: Dict[str, Any], run_config: RunnableConfig, ctx=Context) -> Iterable[Any]:
        client_msg, session_id = to_client_message(payload)
        run_config["recursion_limit"] = 100
        run_config["configurable"] = {"thread_id": session_id}
        stream_input = to_stream_input(client_msg)
        t0 = time.time()
        try:
            items = self._get_graph(ctx).stream(stream_input, stream_mode="messages", config=run_config, context=ctx)
            server_msgs_iter = agent_iter_server_messages(
                items,
                session_id=client_msg.session_id,
                query_msg_id=client_msg.local_msg_id,
                local_msg_id=client_msg.local_msg_id,
                run_id=ctx.run_id,
                log_id=ctx.logid,
            )
            for sm in server_msgs_iter:
                yield sm.dict()
        except asyncio.CancelledError:
            logger.info(f"Stream cancelled for run_id: {ctx.run_id}")
            end_msg = create_message_end_dict(
                code=MESSAGE_END_CODE_CANCELED,
                message="Stream execution cancelled",
                session_id=client_msg.session_id,
                query_msg_id=client_msg.local_msg_id,
                log_id=ctx.logid,
                time_cost_ms=int((time.time() - t0) * 1000),
                reply_id="",
                sequence_id=1,
            )
            yield end_msg
            raise
        except Exception as ex:
            error_msg = create_message_error_dict(
                code="exception",
                message=str(ex),
                session_id=client_msg.session_id,
                query_msg_id=client_msg.local_msg_id,
                log_id=ctx.logid,
                reply_id="",
                sequence_id=1,
                local_msg_id=client_msg.local_msg_id,
            )
            yield error_msg

    # 同步运行：本地/HTTP 通用
    async def run(self, payload: Dict[str, Any], ctx=None) -> Dict[str, Any]:
        if ctx is None:
            ctx = new_context("run")

        run_id = ctx.run_id
        logger.info(f"Starting run with run_id: {run_id}")

        try:
            graph = self._get_graph(ctx)
            # custom tracer
            run_config = init_run_config(graph, ctx)
            run_config["configurable"] = {"thread_id": ctx.run_id}

            # 直接调用，LangGraph会在当前任务上下文中执行
            # 如果当前任务被取消，LangGraph的执行也会被取消
            return await graph.ainvoke(payload, config=run_config, context=ctx)

        except asyncio.CancelledError:
            logger.info(f"Run {run_id} was cancelled")
            return {"status": "cancelled", "run_id": run_id, "message": "Execution was cancelled"}
        except Exception as e:
            # 记录详细的错误信息和堆栈跟踪
            logger.error(f"Error in GraphService.run: {str(e)}\nTraceback:\n{extract_core_stack()}")
            # 重新抛出异常，让上层捕获并处理
            raise
        finally:
            # 清理任务记录
            self.running_tasks.pop(run_id, None)

    # 流式运行（SSE 格式化）：HTTP 路由使用
    async def stream_sse(self, payload: Dict[str, Any], ctx=None) -> AsyncGenerator[str, None]:
        if ctx is None:
            ctx = new_context(method="stream_sse")

        run_id = ctx.run_id
        logger.info(f"Starting stream with run_id: {run_id}")
        graph = self._get_graph(ctx)
        if graph_helper.is_agent_proj():
            run_config = init_agent_config(graph, ctx)
        else:
            run_config = init_run_config(graph, ctx)  # vibeflow

        try:
            async for chunk in self.astream(payload, graph, run_config=run_config, ctx=ctx):
                yield self._sse_event(chunk)
        finally:
            # 清理任务记录
            self.running_tasks.pop(run_id, None)
            cozeloop.flush()

    # 取消执行 - 使用asyncio的标准方式
    def cancel_run(self, run_id: str, ctx: Optional[Context] = None) -> Dict[str, Any]:
        """
        取消指定run_id的执行

        使用asyncio.Task.cancel()来取消任务,这是标准的Python异步取消机制。
        LangGraph会在节点之间检查CancelledError,实现优雅的取消。
        """
        logger.info(f"Attempting to cancel run_id: {run_id}")

        # 查找对应的任务
        if run_id in self.running_tasks:
            task = self.running_tasks[run_id]
            if not task.done():
                # 使用asyncio的标准取消机制
                # 这会在下一个await点抛出CancelledError
                task.cancel()
                logger.info(f"Cancellation requested for run_id: {run_id}")
                return {
                    "status": "success",
                    "run_id": run_id,
                    "message": "Cancellation signal sent, task will be cancelled at next await point"
                }
            else:
                logger.info(f"Task already completed for run_id: {run_id}")
                return {
                    "status": "already_completed",
                    "run_id": run_id,
                    "message": "Task has already completed"
                }
        else:
            logger.warning(f"No active task found for run_id: {run_id}")
            return {
                "status": "not_found",
                "run_id": run_id,
                "message": "No active task found with this run_id. Task may have already completed or run_id is invalid."
            }

    # 运行指定节点：本地/HTTP 通用
    async def run_node(self, node_id: str, payload: Dict[str, Any], ctx=None) -> Any:
        if ctx is None or Context.run_id == "":
            ctx = new_context(method="node_run")

        node_func, input_cls, output_cls = graph_helper.get_graph_node_func_with_inout(self.graph.get_graph(), node_id)
        if node_func is None or input_cls is None:
            raise KeyError(f"node_id '{node_id}' not found")
        assert self.graph is not None, "Graph is not initialized"
        parser = LangGraphParser(self.graph)
        metadata = parser.get_node_metadata(node_id) or {}

        _g = StateGraph(input_cls, input_schema=input_cls, output_schema=output_cls)
        _g.add_node("sn", node_func, metadata=metadata)
        _g.set_entry_point("sn")
        _g.add_edge("sn", END)
        _graph = _g.compile()

        run_config = init_run_config(_graph, ctx)
        return await _graph.ainvoke(payload, config=run_config)

    # 获取工作流的出入参Schema
    def graph_inout_schema(self) -> Any:
        if graph_helper.is_agent_proj():
            return {"input_schema": {}, "output_schema": {}}
        _graph_input = self.graph.get_input_schema()
        _graph_output = self.graph.get_output_schema()

        return {"input_schema": _graph_input.model_json_schema(), "output_schema": _graph_output.model_json_schema()}

    async def astream(self, payload: Dict[str, Any], graph: CompiledStateGraph, run_config: RunnableConfig, ctx=Context) -> AsyncIterable[Any]:
        client_msg, session_id = to_client_message(payload)
        run_config["recursion_limit"] = 100
        run_config["configurable"] = {"thread_id": session_id}
        stream_input = to_stream_input(client_msg)

        # 使用后台线程拉取同步流，并通过事件循环安全地推送到异步队列
        loop = asyncio.get_running_loop()
        q: asyncio.Queue = asyncio.Queue()
        context = contextvars.copy_context()
        start_time = time.time()
        def producer():
            try:
                items = graph.stream(stream_input, stream_mode="messages", config=run_config, context=ctx)
                server_msgs_iter = agent_iter_server_messages(
                    items,
                    session_id=client_msg.session_id,
                    query_msg_id=client_msg.local_msg_id,
                    local_msg_id=client_msg.local_msg_id,
                    run_id=ctx.run_id,
                    log_id=ctx.logid,
                )
                last_seq = 0
                for sm in server_msgs_iter:
                    # 主动检查执行时间，及时中断
                    if time.time() - start_time > TIMEOUT_SECONDS:
                        logger.error(f"Agent execution timeout after {TIMEOUT_SECONDS}s for run_id: {ctx.run_id}")
                        timeout_msg = create_message_end_dict(
                            code="TIMEOUT",
                            message=f"Execution timeout: exceeded {TIMEOUT_SECONDS} seconds",
                            session_id=client_msg.session_id,
                            query_msg_id=client_msg.local_msg_id,
                            log_id=ctx.logid,
                            time_cost_ms=int((time.time() - start_time) * 1000),
                            reply_id=getattr(sm, 'reply_id', ''),
                            sequence_id=last_seq + 1,
                        )
                        loop.call_soon_threadsafe(q.put_nowait, timeout_msg)
                        return
                    loop.call_soon_threadsafe(q.put_nowait, sm.dict())
                    last_seq = sm.sequence_id
            except Exception as ex:
                end_msg = create_message_end_dict(
                    code="exception",
                    message=str(ex),
                    session_id=client_msg.session_id,
                    query_msg_id=client_msg.local_msg_id,
                    log_id=ctx.logid,
                    time_cost_ms=int((time.time() - start_time) * 1000),
                    reply_id="",
                    sequence_id=last_seq + 1,
                )
                loop.call_soon_threadsafe(q.put_nowait, end_msg)
            finally:
                loop.call_soon_threadsafe(q.put_nowait, None)

        threading.Thread(target=lambda: context.run(producer), daemon=True).start()

        try:
            while True:
                item = await q.get()
                if item is None:
                    break
                yield item
        except asyncio.CancelledError:
            logger.info(f"Stream cancelled for run_id: {ctx.run_id}")
            raise


service = GraphService()
app = FastAPI()
第三方任务补偿停止事件 = threading.Event()
第三方任务补偿线程: Optional[threading.Thread] = None

# 导入并注册任务管理 API 路由
from api.tasks import router as tasks_router
app.include_router(tasks_router)


SENSITIVE_LOG_KEYS = {
    "password",
    "password_hash",
    "code",
    "access_key",
    "access_key_id",
    "access_key_secret",
    "token",
}

MAX_MULTIPART_UPLOAD_BYTES = 30 * 1024 * 1024
MAX_BACKEND_PERSIST_UPLOAD_BYTES = 60 * 1024 * 1024
ALLOWED_MULTIPART_UPLOAD_TYPES = {
    "image/png",
    "image/jpeg",
    "image/jpg",
    "image/webp",
    "image/gif",
    "image/bmp",
}


def require_backend_authorization(authorization: Optional[str]) -> None:
    expected_token = os.getenv("COZE_BACKEND_TOKEN", "")
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Missing backend authorization")
    if not expected_token:
        logger.warning("COZE_BACKEND_TOKEN is not configured; relying on upstream gateway authorization")
        return
    expected_header = f"Bearer {expected_token}"
    if authorization != expected_header:
        raise HTTPException(status_code=401, detail="Invalid backend authorization")


def normalize_multipart_upload_category(category: Optional[str]) -> str:
    if category == StorageCategory.TEMP:
        return StorageCategory.TEMP
    if category == StorageCategory.AVATAR:
        return StorageCategory.AVATAR
    return StorageCategory.UPLOAD


def normalize_multipart_metadata(metadata_text: Optional[str]) -> Dict[str, Any]:
    if not metadata_text:
        return {}
    try:
        parsed = json.loads(metadata_text)
    except json.JSONDecodeError as exc:
        raise HTTPException(status_code=400, detail="Invalid metadata JSON") from exc
    if not isinstance(parsed, dict):
        raise HTTPException(status_code=400, detail="metadata must be an object")
    return {
        str(key): value
        for key, value in parsed.items()
        if isinstance(key, str) and value is not None
    }


def is_backend_persist_upload(metadata: Dict[str, Any]) -> bool:
    source = str(metadata.get("source") or "").strip().lower()
    return source == "tudou_server_persist"


def _force_fail_stale_pending_task(task: Any, task_mgr: Any, db: Any) -> None:
    """将 pending 超时的第三方任务强制置失败并尝试退款（绕过 update_task 守卫）。"""
    try:
        from storage.database.task_manager import TaskManager

        force_mgr = task_mgr if isinstance(task_mgr, TaskManager) else TaskManager()
        snapshot = task.parameter_snapshot if isinstance(task.parameter_snapshot, dict) else {}
        pending_reason = str(snapshot.get("pendingReason") or "").strip()
        task_status = str(getattr(task, "status", "") or "").strip().lower()
        if task_status == "submitted_unconfirmed":
            fail_message = "任务提交超时，系统未确认平台是否已建单，已结束并退款"
            error_message = f"第三方平台提交确认超时: {pending_reason}" if pending_reason else "第三方平台提交确认超时"
        else:
            fail_message = "结果确认超时，任务已强制结束并退款"
            error_message = f"第三方平台结果确认超时: {pending_reason}" if pending_reason else "第三方平台结果确认超时"
        forced = force_mgr.force_fail_third_party_task(
            db,
            task.id,
            error=error_message,
            user_friendly_message=fail_message,
        )
        if not forced:
            return
        logger.info(
            "[third-party-recovery] 强制失败超时任务: task_id=%s platform=%s",
            task.id,
            task.platform,
        )
    except Exception as exc:
        logger.error("[third-party-recovery] 强制失败任务异常: task_id=%s error=%s", task.id, exc)
        return

    try:
        deduction = task.deduction_result if isinstance(task.deduction_result, dict) else {}
        original_record_id = str(
            deduction.get("billing_record_id")
            or deduction.get("team_record_id")
            or ""
        ).strip()
        if not original_record_id:
            logger.warning("[third-party-recovery] 任务无扣费记录，跳过退款: task_id=%s", task.id)
            return

        from storage.database.billing_manager import refund as billing_refund

        user_id = str(task.user_id or "").strip()
        if not user_id:
            logger.warning("[third-party-recovery] 任务无 user_id，跳过退款: task_id=%s", task.id)
            return

        result = billing_refund(
            user_id=user_id,
            original_record_id=original_record_id,
            idempotency_key=f"recover-force-fail:{task.id}",
            service_secret=os.getenv("SERVICE_SECRET", ""),
            metadata={
                "platform": task.platform,
                "recovery": "stale_pending_force_fail",
                "refund_reason": "channel_failed",
            },
        )
        logger.info("[third-party-recovery] 强制失败退款结果: task_id=%s result=%s", task.id, result)
    except Exception as exc:
        logger.error("[third-party-recovery] 强制失败退款异常: task_id=%s error=%s", task.id, exc)


def _trigger_third_party_task_recovery() -> None:
    db = get_session()
    try:
        from storage.database.task_manager import TaskManager

        task_mgr = TaskManager()
        repaired_failed_tasks = task_mgr.backfill_failed_terminal_time(
            db,
            limit=THIRD_PARTY_TASK_RECOVERY_BATCH_SIZE,
            platforms=list(THIRD_PARTY_PLATFORMS),
        )
        if repaired_failed_tasks > 0:
            logger.info(
                "[third-party-recovery] 自动补齐 failed_at 成功: repaired=%s",
                repaired_failed_tasks,
            )
        stale_tasks = task_mgr.list_pending_third_party_tasks(
            db,
            limit=THIRD_PARTY_TASK_RECOVERY_BATCH_SIZE,
            older_than_ms=THIRD_PARTY_TASK_RECOVERY_STALE_MS,
        )
    except Exception:
        db.close()
        raise

    if not stale_tasks:
        db.close()
        return

    now_ms = int(time.time() * 1000)
    result_confirm_timeout_ms = THIRD_PARTY_TASK_RESULT_CONFIRM_TIMEOUT_MS
    for task in stale_tasks:
        platform_task_id = str(task.platform_task_id or "").strip()

        # 防御：已取消/已删除任务不参与补偿，避免被强制失败覆盖终态
        task_status = str(getattr(task, "status", "") or "").strip().lower()
        if task_status == "cancelled" or getattr(task, "is_deleted", False):
            logger.info("[third-party-recovery] 跳过已取消/已删除任务: task_id=%s", task.id)
            continue

        # 结果确认中（pending）且超过硬超时阈值 → 直接强制失败并退款，不再转发 recover
        confirmation_pending = getattr(task, "confirmation_state", None) == "pending"
        if not confirmation_pending:
            snapshot = task.parameter_snapshot if isinstance(task.parameter_snapshot, dict) else {}
            confirmation_pending = snapshot.get("confirmationState") == "pending"

        task_updated_ms = 0
        try:
            task_updated_ms = int(str(getattr(task, "updated_at", "") or "0")[:13])
        except (TypeError, ValueError):
            task_updated_ms = 0
        pending_duration_ms = (now_ms - task_updated_ms) if task_updated_ms else 0

        is_submit_unconfirmed_task = task_status == "submitted_unconfirmed"
        # 无法恢复查询的任务（sync 提交模式：无真实平台 task_id）不能转发 recover 恢复；
        # submitted_unconfirmed 则是“2分钟内确认是否拿到真实平台任务号”的单独窗口。
        is_unrecoverable_task = (
            not platform_task_id
            or platform_task_id.startswith("tudou_sync:")
            or platform_task_id.startswith("pending:")
        )
        effective_hard_timeout_ms = (
            THIRD_PARTY_TASK_SUBMIT_CONFIRM_TIMEOUT_MS
            if is_submit_unconfirmed_task
            else result_confirm_timeout_ms
        )

        if confirmation_pending and pending_duration_ms >= effective_hard_timeout_ms:
            _force_fail_stale_pending_task(task, task_mgr, db)
            continue

        if is_unrecoverable_task:
            continue

        try:
            from utils.third_party_recovery import forward_third_party_recovery

            result = forward_third_party_recovery(
                task.id,
                task.platform,
                platform_task_id,
            )
            # 平台确认失败 → 强制终态（绕过 confirmation 守卫）+ 退款
            if isinstance(result, dict) and int(result.get("code", -1)) == 805:
                _force_fail_stale_pending_task(task, task_mgr, db)
                continue
            # 用户主动取消（code=806）→ main 已把任务收敛为 cancelled，不退款，直接跳过
            if isinstance(result, dict) and int(result.get("code", -1)) == 806:
                logger.info("[third-party-recovery] 用户取消任务已收敛为 cancelled: task_id=%s", task.id)
                continue
            # 平台任务已不存在（code=807，即 APIKEY_TASK_NOT_FOUND）
            # → 若任务已取消保持 cancelled；否则按平台终态收敛为 failed，避免挂死
            if isinstance(result, dict) and int(result.get("code", -1)) == 807:
                current_status = str(getattr(task, "status", "") or "").strip().lower()
                if current_status == "cancelled":
                    logger.info("[third-party-recovery] cancelled 任务保持终态: task_id=%s", task.id)
                    continue
                _force_fail_stale_pending_task(task, task_mgr, db)
                continue
            logger.info("[third-party-recovery] 触发任务补偿完成: task_id=%s result=%s", task.id, result)
        except Exception as exc:
            logger.warning("[third-party-recovery] 调用任务补偿异常: task_id=%s error=%s", task.id, exc)
    db.close()


def _third_party_task_recovery_loop() -> None:
    logger.info("[third-party-recovery] 后台补偿线程已启动")
    while not 第三方任务补偿停止事件.wait(THIRD_PARTY_TASK_RECOVERY_INTERVAL):
        try:
            _trigger_third_party_task_recovery()
        except Exception as exc:
            logger.error("[third-party-recovery] 后台补偿执行失败: %s", exc)
    logger.info("[third-party-recovery] 后台补偿线程已停止")


@app.on_event("startup")
def startup_third_party_task_recovery() -> None:
    global 第三方任务补偿线程
    if 第三方任务补偿线程 and 第三方任务补偿线程.is_alive():
        return
    第三方任务补偿停止事件.clear()
    第三方任务补偿线程 = threading.Thread(target=_third_party_task_recovery_loop, daemon=True)
    第三方任务补偿线程.start()


@app.on_event("shutdown")
def shutdown_third_party_task_recovery() -> None:
    第三方任务补偿停止事件.set()


@app.post("/upload")
async def http_multipart_upload(
    file: UploadFile = File(...),
    category: Optional[str] = Form(default=StorageCategory.UPLOAD),
    metadata: Optional[str] = Form(default=None),
    authorization: Optional[str] = Header(default=None),
) -> Dict[str, Any]:
    """
    二进制文件上传入口，供主站服务端转发插件图片使用。
    只接受后端 Bearer token，不暴露给插件端直接调用。
    """
    require_backend_authorization(authorization)

    content_type = (file.content_type or "application/octet-stream").lower()
    if content_type not in ALLOWED_MULTIPART_UPLOAD_TYPES:
        raise HTTPException(status_code=400, detail=f"Unsupported content type: {content_type}")

    content = await file.read()
    if not content:
        raise HTTPException(status_code=400, detail="Uploaded file is empty")
    upload_metadata = normalize_multipart_metadata(metadata)
    max_upload_bytes = MAX_BACKEND_PERSIST_UPLOAD_BYTES if is_backend_persist_upload(upload_metadata) else MAX_MULTIPART_UPLOAD_BYTES

    if len(content) > max_upload_bytes:
        raise HTTPException(status_code=413, detail="Uploaded file is too large")

    upload_category = normalize_multipart_upload_category(category)
    file_name = file.filename or "upload"

    logger.info(
        "Received multipart upload: "
        f"filename={file_name}, content_type={content_type}, size={len(content)}, category={upload_category}, source={upload_metadata.get('source')}, limit={max_upload_bytes}"
    )

    try:
        storage_mgr = get_storage_manager()
        upload_result = storage_mgr.upload_with_category(
            file_content=content,
            file_name=file_name,
            category=upload_category,
            content_type=content_type,
            acl=None,
            metadata=upload_metadata,
        )
    except Exception as exc:
        logger.error(f"Multipart upload failed: {exc}", exc_info=True)
        raise HTTPException(status_code=500, detail="Multipart upload failed") from exc

    return {
        "success": True,
        "message": "文件上传成功",
        "public_url": upload_result["url"],
        "file_key": upload_result["file_key"],
        "category": upload_result["category"],
        "expires_at": upload_result.get("expires_at"),
    }


def redact_sensitive_payload(value: Any) -> Any:
    if isinstance(value, dict):
        redacted = {}
        for key, item in value.items():
            if str(key).lower() in SENSITIVE_LOG_KEYS:
                redacted[key] = "***"
            else:
                redacted[key] = redact_sensitive_payload(item)
        return redacted
    if isinstance(value, list):
        return [redact_sensitive_payload(item) for item in value]
    return value


def safe_body_for_log(body_text: str) -> str:
    try:
        data = json.loads(body_text)
    except Exception:
        return "<invalid-json body omitted>"
    return json.dumps(redact_sensitive_payload(data), ensure_ascii=False)


def is_ops_briefing_payload(payload: Any) -> bool:
    return isinstance(payload, dict) and payload.get("call_type") == "ops_briefing"


async def handle_ops_briefing(payload: Dict[str, Any], authorization: Optional[str]) -> Dict[str, Any]:
    require_backend_authorization(authorization)
    input_data = payload.get("input") if isinstance(payload.get("input"), dict) else {}
    operation_type = input_data.get("operation_type")
    db = get_session()
    try:
        if operation_type == "ingest":
            ingest = OpsBriefingIngestInput.model_validate(input_data)
            success, data, error = OpsBriefingManager.ingest_raw_items(db, ingest)
            return {"success": success, "response_data": {"data": data, "msg": error or "ok"}}

        if operation_type == "generate":
            success, data, error = OpsBriefingManager.generate_briefing(
                db,
                input_data.get("briefing_date") if isinstance(input_data.get("briefing_date"), str) else None,
            )
            return {"success": success, "response_data": {"data": data, "msg": error or "ok"}}

        if operation_type == "save_briefing":
            briefing_input = OpsDailyBriefingSaveInput.model_validate(input_data.get("briefing") if isinstance(input_data.get("briefing"), dict) else input_data)
            success, data, error = OpsBriefingManager.save_briefing(db, briefing_input)
            return {"success": success, "response_data": {"data": data, "msg": error or "ok"}}

        if operation_type == "get_today" or operation_type == "get_by_date":
            success, data, error = OpsBriefingManager.get_briefing(
                db,
                input_data.get("briefing_date") if isinstance(input_data.get("briefing_date"), str) else None,
            )
            return {"success": success, "response_data": {"data": data, "msg": error or "ok"}}

        if operation_type == "list_raw":
            data = OpsBriefingManager.list_raw_items(
                db,
                input_data.get("briefing_date") if isinstance(input_data.get("briefing_date"), str) else None,
            )
            return {"success": True, "response_data": {"data": data, "msg": "ok"}}

        raise HTTPException(status_code=400, detail=f"Unsupported ops briefing operation: {operation_type}")
    finally:
        db.close()


@app.post("/run")
async def http_run(request: Request) -> Dict[str, Any]:
    global result
    raw_body = await request.body()
    try:
        body_text = raw_body.decode("utf-8")
    except Exception as e:
        body_text = str(raw_body)
        raise HTTPException(status_code=400,
                            detail=f"Invalid JSON format, traceback: {traceback.format_exc()}, error: {e}")

    ctx = new_context(method="run", headers=request.headers)
    run_id = ctx.run_id
    request_context.set(ctx)
    safe_body_text = safe_body_for_log(body_text)

    logger.info(
        f"Received request for /run: "
        f"run_id={run_id}, "
        f"query={dict(request.query_params)}, "
        f"body={safe_body_text}"
    )

    try:
        payload = await request.json()

        if is_ops_briefing_payload(payload):
            return await handle_ops_briefing(payload, request.headers.get("authorization"))

        # 创建任务并记录 - 这是关键，让我们可以通过run_id取消任务
        task = asyncio.create_task(service.run(payload, ctx))
        service.running_tasks[run_id] = task

        try:
            result = await asyncio.wait_for(task, timeout=float(TIMEOUT_SECONDS))
        except asyncio.TimeoutError:
            logger.error(f"Run execution timeout after {TIMEOUT_SECONDS}s for run_id: {run_id}")
            task.cancel()
            try:
                result = await task
            except asyncio.CancelledError:
                return {
                    "status": "timeout", 
                    "run_id": run_id, 
                    "message": f"Execution timeout: exceeded {TIMEOUT_SECONDS} seconds"
                }

        if not result:
            result = {}
        if isinstance(result, dict):
            result["run_id"] = run_id
        return result

    except json.JSONDecodeError as e:
        logger.error(f"JSON decode error in http_run: {e}, traceback: {traceback.format_exc()}")
        raise HTTPException(status_code=400, detail=f"Invalid JSON format, {extract_core_stack()}")

    except asyncio.CancelledError:
        logger.info(f"Request cancelled for run_id: {run_id}")
        result = {"status": "cancelled", "run_id": run_id, "message": "Execution was cancelled"}
        return result

    except Exception as e:
        logger.error(f"Unexpected error in http_run: {e}, traceback: {traceback.format_exc()}", exc_info=True)
        raise HTTPException(status_code=500, detail=extract_core_stack())
    finally:
        cozeloop.flush()


@app.post("/stream_run")
async def http_stream_run(request: Request):
    ctx = new_context(method="stream_run", headers=request.headers)
    request_context.set(ctx)
    raw_body = await request.body()
    try:
        body_text = raw_body.decode("utf-8")
    except Exception as e:
        body_text = str(raw_body)
        raise HTTPException(status_code=400,
                            detail=f"Invalid JSON format, traceback: {extract_core_stack()}, error: {e}")

    run_id = ctx.run_id
    safe_body_text = safe_body_for_log(body_text)
    logger.info(
        f"Received request for /stream_run: "
        f"run_id={run_id}, "
        f"query={dict(request.query_params)}, "
        f"body={safe_body_text}"
    )

    try:
        payload = await request.json()
    except json.JSONDecodeError as e:
        logger.error(f"JSON decode error in http_stream_run: {e}, traceback: {traceback.format_exc()}")
        raise HTTPException(status_code=400, detail=f"Invalid JSON format:{extract_core_stack()}")

    # 包装stream_sse为可取消的任务
    async def cancellable_stream():
        # 将真正的流式任务登记到 running_tasks，确保 /cancel 能定位到它
        task = asyncio.current_task()
        if task:
            service.running_tasks[run_id] = task
            logger.info(f"Registered streaming task for run_id: {run_id}")

        client_msg, _ = to_client_message(payload)
        t0 = time.time()

        try:
            async for chunk in service.stream_sse(payload, ctx):
                yield chunk
        except asyncio.CancelledError:
            logger.info(f"Stream cancelled for run_id: {run_id}")
            end_msg = create_message_end_dict(
                code=MESSAGE_END_CODE_CANCELED,
                message="Stream cancelled by user",
                session_id=client_msg.session_id,
                query_msg_id=client_msg.local_msg_id,
                log_id=ctx.logid,
                time_cost_ms=int((time.time() - t0) * 1000),
                reply_id="",
                sequence_id=1,
            )
            yield service._sse_event(end_msg)
            raise
        except Exception as ex:
            logger.error(f"Unexpected error in http_stream_run: {ex}, traceback: {traceback.format_exc()}")
            error_msg = create_message_error_dict(
                code="exception",
                message=str(ex),
                session_id=client_msg.session_id,
                query_msg_id=client_msg.local_msg_id,
                log_id=ctx.logid,
                reply_id="",
                sequence_id=1,
                local_msg_id=client_msg.local_msg_id,
            )
            yield service._sse_event(error_msg)

    # 注意：StreamingResponse会在后台运行generator
    response = StreamingResponse(cancellable_stream(), media_type="text/event-stream")
    return response

@app.post("/cancel/{run_id}")
async def http_cancel(run_id: str, request: Request):
    """
    取消指定run_id的执行

    使用asyncio.Task.cancel()实现取消,这是Python标准的异步任务取消机制。
    LangGraph会在节点之间的await点检查CancelledError,实现优雅取消。
    """
    ctx = new_context(method="cancel", headers=request.headers)
    request_context.set(ctx)
    logger.info(f"Received cancel request for run_id: {run_id}")
    result = service.cancel_run(run_id, ctx)
    return result


@app.post(path="/node_run/{node_id}")
async def http_node_run(node_id: str, request: Request):
    raw_body = await request.body()
    try:
        body_text = raw_body.decode("utf-8")
    except UnicodeDecodeError:
        body_text = str(raw_body)
        raise HTTPException(status_code=400, detail="Invalid JSON format")
    ctx = new_context(method="node_run", headers=request.headers)
    request_context.set(ctx)
    safe_body_text = safe_body_for_log(body_text)
    logger.info(
        f"Received request for /node_run/{node_id}: "
        f"query={dict(request.query_params)}, "
        f"body={safe_body_text}",
    )

    try:
        payload = await request.json()
    except json.JSONDecodeError as e:
        logger.error(f"JSON decode error in http_node_run: {e}, traceback: {traceback.format_exc()}")
        raise HTTPException(status_code=400, detail=f"Invalid JSON format:{extract_core_stack()}")
    try:
        return await service.run_node(node_id, payload, ctx)
    except KeyError:
        raise HTTPException(status_code=404,
                            detail=f"node_id '{node_id}' not found or input miss required fields, traceback: {extract_core_stack()}")
    except Exception as e:
        logger.error(f"Unexpected error in http_node_run: {e}, traceback: {traceback.format_exc()}", exc_info=True)
        raise HTTPException(status_code=500, detail=extract_core_stack())
    finally:
        cozeloop.flush()


@app.get("/health")
async def health_check():
    try:
        # 这里可以添加更多的健康检查逻辑
        return {
            "status": "ok",
            "message": "Service is running",
        }
    except Exception as e:
        raise HTTPException(status_code=503, detail=str(e))


@app.get("/avatar/{file_key:path}")
async def get_avatar(file_key: str):
    """
    代理访问用户头像文件
    参数：file_key - 对象存储的文件key
    """
    try:
        # 初始化存储客户端
        storage = S3SyncStorage(
            endpoint_url=os.getenv("COZE_BUCKET_ENDPOINT_URL"),
            access_key=os.getenv("COZE_ACCESS_KEY", ""),
            secret_key=os.getenv("COZE_SECRET_KEY", ""),
            bucket_name=os.getenv("COZE_BUCKET_NAME"),
            region=os.getenv("COZE_BUCKET_REGION", "cn-beijing"),
        )

        # 从对象存储读取文件
        file_content = storage.read_file(file_key=file_key)

        # 根据 file_key 判断 Content-Type
        if file_key.endswith('.png'):
            content_type = 'image/png'
        elif file_key.endswith('.jpg') or file_key.endswith('.jpeg'):
            content_type = 'image/jpeg'
        elif file_key.endswith('.gif'):
            content_type = 'image/gif'
        elif file_key.endswith('.webp'):
            content_type = 'image/webp'
        else:
            content_type = 'application/octet-stream'

        # 返回文件内容
        return Response(content=file_content, media_type=content_type)

    except Exception as e:
        logger.error(f"Error getting avatar: {e}")
        raise HTTPException(status_code=404, detail=f"Avatar not found: {str(e)}")


@app.get(path="/graph_parameter")
async def http_graph_inout_parameter(request: Request):
    return service.graph_inout_schema()

def parse_args():
    parser = argparse.ArgumentParser(description="Start FastAPI server")
    parser.add_argument("-m", type=str, default="http", help="Run mode, support http,flow,node")
    parser.add_argument("-n", type=str, default="", help="Node ID for single node run")
    parser.add_argument("-p", type=int, default=5000, help="HTTP server port")
    parser.add_argument("-i", type=str, default="", help="Input JSON string for flow/node mode")
    return parser.parse_args()


def parse_input(input_str: str) -> Dict[str, Any]:
    """Parse input string, support both JSON string and plain text"""
    if not input_str:
        return {"text": "你好"}

    # Try to parse as JSON first
    try:
        return json.loads(input_str)
    except json.JSONDecodeError:
        # If not valid JSON, treat as plain text
        return {"text": input_str}

def start_http_server(port):
    workers = 1
    reload = False
    if graph_helper.is_dev_env():
        reload = True

    logger.info(f"Start HTTP Server, Port: {port}, Workers: {workers}")
    # 使用 main:app 作为模块路径
    uvicorn.run("main:app", host="0.0.0.0", port=port, reload=reload, workers=workers)

if __name__ == "__main__":
    args = parse_args()
    if args.m == "http":
        start_http_server(args.p)
    elif args.m == "flow":
        payload = parse_input(args.i)
        result = asyncio.run(service.run(payload))
        print(json.dumps(result, ensure_ascii=False, indent=2))
    elif args.m == "node" and args.n:
        payload = parse_input(args.i)
        result = asyncio.run(service.run_node(args.n, payload))
        print(json.dumps(result, ensure_ascii=False, indent=2))
    elif args.m == "agent":
        for chunk in service.stream(
                {
                    "type": "query",
                    "session_id": "1",
                    "message": "你好",
                    "content": {
                        "query": {
                            "prompt": [
                                {
                                    "type": "text",
                                    "content": {"text": "现在几点了？请调用工具获取当前时间"},
                                }
                            ]
                        }
                    },
                },
                run_config={"configurable": {"session_id": "1"}}
        ):
            print(chunk)
