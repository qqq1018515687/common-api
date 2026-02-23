"""任务管理 API 路由"""
from typing import Optional, List
from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel, Field

from src.storage.database.db import get_session
from src.storage.database.task_manager import TaskManager, TaskCreate, TaskUpdate

router = APIRouter(prefix="/api/coze", tags=["tasks"])


class CreateTaskRequest(BaseModel):
    """创建任务请求"""
    id: str = Field(..., description="任务ID（前端生成的UUID）")
    user_id: str = Field(..., description="用户ID")
    team_id: Optional[str] = Field(default=None, description="团队ID")
    platform: str = Field(..., description="平台标识")
    platform_task_id: str = Field(..., description="平台任务ID")
    type: str = Field(..., description="任务类型：image/video/audio")
    workflow_parameters: Optional[dict] = Field(default=None, description="工作流参数")
    parameter_snapshot: Optional[dict] = Field(default=None, description="完整参数快照")
    batch_id: Optional[str] = Field(default=None, description="批次ID")
    connection_mode: Optional[str] = Field(default="sse", description="连接模式")


class UpdateTaskRequest(BaseModel):
    """更新任务请求"""
    status: Optional[str] = Field(default=None, description="任务状态")
    result: Optional[dict] = Field(default=None, description="生成结果")
    error: Optional[str] = Field(default=None, description="错误信息")
    completed_at: Optional[int] = Field(default=None, description="完成时间")


class TaskResponse(BaseModel):
    """任务响应"""
    id: str
    user_id: str
    team_id: Optional[str]
    platform: str
    platform_task_id: str
    type: str
    status: str
    created_at: int
    updated_at: int
    workflow_parameters: Optional[dict]
    parameter_snapshot: Optional[dict]
    result: Optional[dict]
    error: Optional[str]
    completed_at: Optional[int]
    batch_id: Optional[str]
    connection_mode: Optional[str]


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
                "created_at": task.created_at,
                "updated_at": task.updated_at
            }
        }
    
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"创建任务失败: {str(e)}")
    finally:
        db.close()


@router.put("/tasks/{task_id}")
async def update_task(task_id: str, request: UpdateTaskRequest):
    """更新任务"""
    db = get_session()
    task_mgr = TaskManager()
    
    try:
        task_in = TaskUpdate(
            status=request.status,
            result=request.result,
            error=request.error,
            completed_at=request.completed_at
        )
        
        task = task_mgr.update_task(db, task_id, task_in)
        
        if not task:
            raise HTTPException(status_code=404, detail="任务不存在")
        
        return {
            "success": True,
            "message": "更新成功",
            "task": {
                "id": task.id,
                "status": task.status,
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
