"""任务管理 API 路由"""
from typing import Optional, List, Any, Dict
from fastapi import APIRouter, Header, HTTPException, Query
import os
from pydantic import BaseModel, Field

from storage.database.db import get_session
from storage.database.task_manager import TaskManager, TaskCreate, TaskUpdate

router = APIRouter(prefix="/api/coze", tags=["tasks"])


class CreateTaskRequest(BaseModel):
    """创建任务请求"""
    id: str = Field(..., description="任务ID（前端生成的UUID）")
    user_id: str = Field(..., description="用户ID")
    team_id: Optional[str] = Field(default=None, description="团队ID")
    platform: str = Field(..., description="平台标识")
    platform_task_id: Optional[str] = Field(default=None, description="平台任务ID")
    type: str = Field(..., description="任务类型：image/video/audio")
    workflow_parameters: Optional[dict] = Field(default=None, description="工作流参数")
    parameter_snapshot: Optional[dict] = Field(default=None, description="完整参数快照")
    batch_id: Optional[str] = Field(default=None, description="批次ID")
    connection_mode: Optional[str] = Field(default="sse", description="连接模式")


class UpdateTaskRequest(BaseModel):
    """更新任务请求"""
    status: Optional[str] = Field(default=None, description="任务状态")
    platform_task_id: Optional[str] = Field(default=None, description="平台任务ID")
    result: Optional[dict] = Field(default=None, description="生成结果")
    result_fallback: Optional[dict] = Field(default=None, description="结果转存失败时保留的原始回退结果")
    error: Optional[str] = Field(default=None, description="错误信息")
    completed_at: Optional[int] = Field(default=None, description="完成时间")
    failed_at: Optional[int] = Field(default=None, description="失败时间")
    cancelled_at: Optional[int] = Field(default=None, description="取消时间")
    status_updated_at: Optional[int] = Field(default=None, description="状态更新时间")
    started_at: Optional[int] = Field(default=None, description="开始执行时间")
    workflow_parameters: Optional[dict] = Field(default=None, description="工作流参数")
    parameter_snapshot: Optional[dict] = Field(default=None, description="完整参数快照")
    connection_mode: Optional[str] = Field(default=None, description="连接模式")
    confirmation_state: Optional[str] = Field(default=None, description="结果确认状态：none/pending/confirmed")
    persistence_status: Optional[str] = Field(default=None, description="结果持久化状态：saving/saved/failed")
    persistence_error: Optional[str] = Field(default=None, description="结果持久化失败原因")
    user_friendly_message: Optional[str] = Field(default=None, description="用户友好提示")
    deduction_result: Optional[dict] = Field(default=None, description="扣费结果记录")
    elapsed_time_seconds: Optional[int] = Field(default=None, description="任务耗时秒数")
    deleted_image_urls: Optional[List[str]] = Field(default=None, description="已删除图片 URL 列表")
    final_reason: Optional[str] = Field(default=None, description="终态原因")
    cancellation_source: Optional[str] = Field(default=None, description="取消来源")


class TaskResponse(BaseModel):
    """任务响应"""
    id: str
    user_id: str
    team_id: Optional[str]
    platform: str
    platform_task_id: Optional[str]
    type: str
    status: str
    confirmation_state: Optional[str]
    created_at: int
    updated_at: int
    workflow_parameters: Optional[dict]
    parameter_snapshot: Optional[dict]
    result: Optional[dict]
    error: Optional[str]
    completed_at: Optional[int]
    batch_id: Optional[str]
    connection_mode: Optional[str]


class RecoverThirdPartyTaskRequest(BaseModel):
    task_id: str = Field(..., description="本地任务ID")
    platform: str = Field(..., description="平台标识")
    platform_task_id: str = Field(..., description="第三方平台任务ID")


class StaleRunningTasksRequest(BaseModel):
    """列出长期未更新的运行中任务请求"""
    stale_for_ms: int = Field(default=0, description="超过该时长(毫秒)未更新的运行中任务；0=不限时长")
    limit: int = Field(default=50, ge=1, le=200, description="返回条数上限")


def _is_inline_image_url(value: Any) -> bool:
    return isinstance(value, str) and value.startswith("data:image/")


def _extract_result_urls(value: Any) -> List[str]:
    urls: List[str] = []

    def visit(item: Any) -> None:
        if item is None:
            return
        if isinstance(item, str):
            if item:
                urls.append(item)
            return
        if isinstance(item, list):
            for child in item:
                visit(child)
            return
        if not isinstance(item, dict):
            return

        for key in ("fileUrl", "file_url", "url", "imageUrl", "image_url", "previewUrl", "preview_url", "thumbnailUrl", "thumbnail_url"):
            raw = item.get(key)
            if isinstance(raw, str) and raw:
                urls.append(raw)

        for key in ("imageUrls", "image_urls", "images", "files", "output", "outputs", "previewUrls", "preview_urls", "thumbnailUrls", "thumbnail_urls", "result", "data"):
            if key in item:
                visit(item.get(key))

    visit(value)
    deduped: List[str] = []
    seen = set()
    for url in urls:
        if url in seen:
            continue
        seen.add(url)
        deduped.append(url)
    return deduped


def _task_has_inline_result(task: Any) -> bool:
    result_sources = []
    if isinstance(getattr(task, "result", None), dict):
        result_sources.append(task.result)
    if isinstance(getattr(task, "result_fallback", None), dict):
        result_sources.append(task.result_fallback)

    for source in result_sources:
        if any(_is_inline_image_url(url) for url in _extract_result_urls(source)):
            return True
    return False


def _serialize_task(task: Any, task_mgr: TaskManager) -> Dict[str, Any]:
    return {
        "id": task.id,
        "user_id": task.user_id,
        "team_id": task.team_id,
        "platform": task.platform,
        "platform_task_id": task.platform_task_id,
        "type": task.type,
        "status": task.status,
        "confirmation_state": getattr(task, "confirmation_state", None),
        "pending_reason": task_mgr._pending_reason_from_snapshot(task.parameter_snapshot),
        "pending_since": task_mgr._pending_since_from_snapshot(task.parameter_snapshot),
        "gray_diagnostics": task_mgr._gray_diagnostics_from_snapshot(task.parameter_snapshot),
        "created_at": task.created_at,
        "updated_at": task.updated_at,
        "workflow_parameters": task.workflow_parameters,
        "parameter_snapshot": task.parameter_snapshot,
        "result": task.result,
        "result_fallback": getattr(task, "result_fallback", None),
        "persistence_status": getattr(task, "persistence_status", None),
        "persistence_error": getattr(task, "persistence_error", None),
        "error": task.error,
        "completed_at": task.completed_at,
        "failed_at": getattr(task, "failed_at", None),
        "cancelled_at": getattr(task, "cancelled_at", None),
        "status_updated_at": getattr(task, "status_updated_at", None),
        "batch_id": task.batch_id,
        "connection_mode": task.connection_mode,
        "deduction_result": getattr(task, "deduction_result", None),
        "user_friendly_message": getattr(task, "user_friendly_message", None),
        "has_inline_result": _task_has_inline_result(task),
    }


def _serialize_persist_pending_task(task: Any) -> Dict[str, Any]:
    return {
        "id": task.id,
        "user_id": task.user_id,
        "platform": task.platform,
        "status": task.status,
        "persistence_status": getattr(task, "persistence_status", None),
        "updated_at": task.updated_at,
        "has_inline_result": _task_has_inline_result(task),
    }


@router.post("/common")
@router.get("/common")
async def common_endpoint(
    action: str = Query(..., description="操作类型：create/update/delete/list/get"),
    task_id: Optional[str] = Query(None, description="任务ID"),
    user_id: Optional[str] = Query(None, description="用户ID"),
    team_id: Optional[str] = Query(None, description="团队ID"),
    status: Optional[str] = Query(None, description="任务状态"),
    page: int = Query(1, description="页码"),
    limit: int = Query(10, description="每页数量")
):
    """
    通用任务管理接口
    
    支持的操作：
    - create: 创建任务
    - update: 更新任务
    - delete: 删除任务
    - list: 查询任务列表
    - get: 获取单个任务详情
    """
    db = get_session()
    task_mgr = TaskManager()
    
    try:
        if action == "create":
            # 创建任务需要从请求体中获取数据
            # 由于这里使用的是 Query 参数，暂时返回错误提示
            # 实际使用时应该改为 @app.post("/api/coze/common") 从 request.json() 获取
            return {
                "success": False,
                "message": "请使用 POST /api/coze/tasks 接口创建任务"
            }
        
        elif action == "list":
            # 查询任务列表
            if not user_id:
                raise HTTPException(status_code=400, detail="缺少必要参数：user_id")
            
            # 计算分页偏移量
            skip = (page - 1) * limit
            
            # 构建过滤条件
            filters = {}
            if team_id:
                filters["team_id"] = team_id
            if status:
                filters["status"] = status
            
            # 查询任务列表
            tasks = task_mgr.get_tasks_by_user_id(
                db=db,
                user_id=user_id,
                status=status,
                skip=skip,
                limit=limit,
                **filters
            )
            
            # 统计总数
            total = task_mgr.count_tasks_by_user_id(db, user_id, status)
            
            # 转换为响应格式
            task_list = [
                {
                    "id": task.id,
                    "user_id": task.user_id,
                    "team_id": task.team_id,
                    "platform": task.platform,
                    "platform_task_id": task.platform_task_id,
                    "type": task.type,
                    "status": task.status,
                    "confirmation_state": getattr(task, "confirmation_state", None),
                    "pending_reason": task_mgr._pending_reason_from_snapshot(task.parameter_snapshot),
                    "pending_since": task_mgr._pending_since_from_snapshot(task.parameter_snapshot),
                    "gray_diagnostics": task_mgr._gray_diagnostics_from_snapshot(task.parameter_snapshot),
                    "created_at": task.created_at,
                    "updated_at": task.updated_at,
                    "workflow_parameters": task.workflow_parameters,
                    "parameter_snapshot": task.parameter_snapshot,
                    "result": task.result,
                    "error": task.error,
                    "completed_at": task.completed_at,
                    "batch_id": task.batch_id,
                    "connection_mode": task.connection_mode
                }
                for task in tasks
            ]
            
            return {
                "success": True,
                "message": "查询成功",
                "tasks": task_list,
                "total": total,
                "page": page,
                "limit": limit
            }
        
        elif action == "get":
            # 获取单个任务详情
            if not task_id:
                raise HTTPException(status_code=400, detail="缺少必要参数：task_id")
            
            task = task_mgr.get_task_by_id(db, task_id)
            if not task:
                raise HTTPException(status_code=404, detail="任务不存在")
            
            return {
                "success": True,
                "task": {
                    "id": task.id,
                    "user_id": task.user_id,
                    "team_id": task.team_id,
                    "platform": task.platform,
                    "platform_task_id": task.platform_task_id,
                    "type": task.type,
                    "status": task.status,
                    "confirmation_state": getattr(task, "confirmation_state", None),
                    "pending_reason": task_mgr._pending_reason_from_snapshot(task.parameter_snapshot),
                    "pending_since": task_mgr._pending_since_from_snapshot(task.parameter_snapshot),
                    "gray_diagnostics": task_mgr._gray_diagnostics_from_snapshot(task.parameter_snapshot),
                    "created_at": task.created_at,
                    "updated_at": task.updated_at,
                    "workflow_parameters": task.workflow_parameters,
                    "parameter_snapshot": task.parameter_snapshot,
                    "result": task.result,
                    "error": task.error,
                    "completed_at": task.completed_at,
                    "batch_id": task.batch_id,
                    "connection_mode": task.connection_mode
                }
            }
        
        else:
            raise HTTPException(status_code=400, detail=f"不支持的操作类型：{action}")
    
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"操作失败: {str(e)}")
    finally:
        db.close()


@router.post("/tasks")
async def create_task(request: CreateTaskRequest):
    """创建任务"""
    db = get_session()
    task_mgr = TaskManager()
    
    try:
        task_in = TaskCreate(
            id=request.id,
            user_id=request.user_id,
            team_id=request.team_id,
            platform=request.platform,
            platform_task_id=request.platform_task_id,
            type=request.type,
            workflow_parameters=request.workflow_parameters,
            parameter_snapshot=request.parameter_snapshot,
            batch_id=request.batch_id,
            connection_mode=request.connection_mode
        )
        
        task = task_mgr.create_task(db, task_in)
        
        return {
            "success": True,
            "message": "创建成功",
            "task": {
                "id": task.id,
                "user_id": task.user_id,
                "team_id": task.team_id,
                "platform": task.platform,
                "platform_task_id": task.platform_task_id,
                "type": task.type,
                "status": task.status,
                "confirmation_state": getattr(task, "confirmation_state", None),
                "pending_reason": task_mgr._pending_reason_from_snapshot(task.parameter_snapshot),
                "pending_since": task_mgr._pending_since_from_snapshot(task.parameter_snapshot),
                "gray_diagnostics": task_mgr._gray_diagnostics_from_snapshot(task.parameter_snapshot),
                "created_at": task.created_at,
                "updated_at": task.updated_at
            }
        }
    
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"创建任务失败: {str(e)}")
    finally:
        db.close()


@router.post("/common/task/recover-third-party")
async def recover_third_party_task(request: RecoverThirdPartyTaskRequest, authorization: Optional[str] = Header(default=None)):
    expected_token = os.getenv("COZE_BACKEND_TOKEN", "").strip()
    if expected_token:
        if not authorization or authorization != f"Bearer {expected_token}":
            raise HTTPException(status_code=401, detail="Invalid backend authorization")

    try:
        from utils.third_party_recovery import forward_third_party_recovery

        data = forward_third_party_recovery(
            request.task_id,
            request.platform,
            request.platform_task_id,
            auth_header=authorization,
        )
        return {"success": True, "result": data}
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"recover third party task failed: {exc}") from exc


@router.post("/common/task/stale-running")
async def list_stale_running_tasks(request: StaleRunningTasksRequest, authorization: Optional[str] = Header(default=None)):
    """仅后端授权的接口：列出长期未更新的运行中任务，供主流程后端补偿收尾。"""
    expected_token = os.getenv("COZE_BACKEND_TOKEN", "").strip()
    if expected_token:
        if not authorization or authorization != f"Bearer {expected_token}":
            raise HTTPException(status_code=401, detail="Invalid backend authorization")

    db = get_session()
    try:
        from storage.database.task_manager import TaskManager

        task_mgr = TaskManager()
        tasks = task_mgr.list_stale_running_tasks(
            db,
            stale_for_ms=request.stale_for_ms,
            limit=request.limit,
        )
        return {"success": True, "count": len(tasks), "tasks": tasks}
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"list stale running tasks failed: {exc}") from exc
    finally:
        db.close()


@router.get("/tasks/{task_id}")
async def get_task(task_id: str, authorization: Optional[str] = Header(default=None)):
    expected_token = os.getenv("COZE_BACKEND_TOKEN", "").strip()
    if expected_token:
        if not authorization or authorization != f"Bearer {expected_token}":
            raise HTTPException(status_code=401, detail="Invalid backend authorization")

    db = get_session()
    task_mgr = TaskManager()
    try:
        task = task_mgr.get_task_by_id(db, task_id)
        if not task:
            raise HTTPException(status_code=404, detail="任务不存在")
        return {"success": True, "task": _serialize_task(task, task_mgr)}
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"获取任务失败: {exc}") from exc
    finally:
        db.close()


@router.get("/common/task/persist-pending")
async def list_persist_pending_tasks(
    authorization: Optional[str] = Header(default=None),
    limit: int = Query(50, ge=1, le=200, description="返回条数上限"),
):
    expected_token = os.getenv("COZE_BACKEND_TOKEN", "").strip()
    if expected_token:
        if not authorization or authorization != f"Bearer {expected_token}":
            raise HTTPException(status_code=401, detail="Invalid backend authorization")

    db = get_session()
    task_mgr = TaskManager()
    try:
        from storage.database.shared.model import Tasks

        rows = (
            db.query(Tasks)
            .filter(
                Tasks.is_deleted.is_(False),
                Tasks.type == "image",
                Tasks.status.in_(["running", "completed"]),
            )
            .order_by(Tasks.updated_at.asc(), Tasks.id.asc())
            .limit(min(limit * 4, 800))
            .all()
        )
        tasks = []
        for task in rows:
            if not _task_has_inline_result(task):
                continue
            tasks.append(_serialize_persist_pending_task(task))
            if len(tasks) >= limit:
                break
        return {"success": True, "count": len(tasks), "tasks": tasks}
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"list persist pending tasks failed: {exc}") from exc
    finally:
        db.close()


@router.put("/tasks/{task_id}")
async def update_task(task_id: str, request: UpdateTaskRequest):
    """更新任务"""
    db = get_session()
    task_mgr = TaskManager()
    
    try:
        task_in = TaskUpdate(**request.model_dump(exclude_unset=True))
        
        task = task_mgr.update_task(db, task_id, task_in)
        
        if not task:
            raise HTTPException(status_code=404, detail="任务不存在")
        
        return {
            "success": True,
            "message": "更新成功",
            "task": {
                "id": task.id,
                "status": task.status,
                "confirmation_state": getattr(task, "confirmation_state", None),
                "pending_reason": task_mgr._pending_reason_from_snapshot(task.parameter_snapshot),
                "pending_since": task_mgr._pending_since_from_snapshot(task.parameter_snapshot),
                "gray_diagnostics": task_mgr._gray_diagnostics_from_snapshot(task.parameter_snapshot),
                "result": task.result,
                "error": task.error,
                "completed_at": task.completed_at,
                "updated_at": task.updated_at
            }
        }
    
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"更新任务失败: {str(e)}")
    finally:
        db.close()


@router.delete("/tasks/{task_id}")
async def delete_task(task_id: str):
    """删除任务"""
    db = get_session()
    task_mgr = TaskManager()
    
    try:
        success = task_mgr.delete_task(db, task_id)
        
        if not success:
            raise HTTPException(status_code=404, detail="任务不存在")
        
        return {
            "success": True,
            "message": "删除成功"
        }
    
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"删除任务失败: {str(e)}")
    finally:
        db.close()
