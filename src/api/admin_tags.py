"""
标签池管理 API 接口

提供标签池的完整管理功能：
- 分析标签使用情况
- 应用标签更新
- 激活/回滚版本
- 查看版本历史
- 查看当前标签池
"""

from fastapi import APIRouter, Query, HTTPException
from pydantic import BaseModel, Field
from typing import Optional, List, Dict

router = APIRouter(prefix="/admin/tags", tags=["Tag Management"])


class AnalyzeTagsRequest(BaseModel):
    """标签分析请求"""
    days: int = Field(30, description="分析近N天的数据")
    analyze_all: bool = Field(False, description="分析所有历史数据")
    min_task_count: int = Field(3, description="最小任务数阈值")
    min_confidence: float = Field(0.7, description="最小置信度阈值")


class ApplyUpdatesRequest(BaseModel):
    """应用更新请求"""
    suggestions: List[Dict] = Field(..., description="建议列表")
    activate_immediately: bool = Field(True, description="是否立即激活新版本")
    batch_retag: bool = Field(True, description="是否批量重打标")
    batch_size: int = Field(100, description="批量大小")


class ActivateVersionRequest(BaseModel):
    """激活版本请求"""
    version: int = Field(..., description="版本号")
    pool_type: str = Field("scene", description="标签池类型：scene/product")


class RollbackVersionRequest(BaseModel):
    """回滚版本请求"""
    target_version: int = Field(..., description="目标版本号")
    pool_type: str = Field("scene", description="标签池类型：scene/product")


class CreateNewVersionRequest(BaseModel):
    """创建新版本请求"""
    pool_type: str = Field(..., description="标签池类型：scene/product")
    tags: List[Dict] = Field(..., description="标签列表")
    created_by: Optional[str] = Field(None, description="创建者ID")


@router.post("/analyze")
async def analyze_tags_api(request: AnalyzeTagsRequest):
    """分析标签使用情况"""
    from scripts.analyze_tags_enhanced import analyze_tags
    
    report, suggestions = analyze_tags(
        days=request.days,
        analyze_all=request.analyze_all,
        min_task_count=request.min_task_count,
        min_confidence=request.min_confidence
    )
    
    return {
        "success": True,
        "data": {
            "report": report,
            "suggestions": suggestions
        }
    }


@router.post("/apply-updates")
async def apply_updates_api(request: ApplyUpdatesRequest):
    """应用标签更新"""
    from scripts.analyze_tags_enhanced import apply_updates
    
    result = apply_updates(
        suggestions=request.suggestions,
        activate_immediately=request.activate_immediately,
        batch_retag=request.batch_retag,
        batch_size=request.batch_size
    )
    
    return {
        "success": result["success"],
        "data": result
    }


@router.post("/activate-version")
async def activate_version_api(request: ActivateVersionRequest):
    """激活指定版本的标签池"""
    from storage.database.tag_pool_manager import TagPoolManager
    
    success = TagPoolManager.activate_version(
        pool_type=request.pool_type,
        version=request.version,
        activated_by="admin"  # 这里应该是实际的用户ID
    )
    
    if not success:
        raise HTTPException(status_code=404, detail="版本不存在")
    
    return {
        "success": True,
        "message": f"版本 {request.version} 已激活",
        "data": {
            "pool_type": request.pool_type,
            "version": request.version
        }
    }


@router.post("/rollback")
async def rollback_version_api(request: RollbackVersionRequest):
    """回滚到指定版本"""
    from storage.database.tag_pool_manager import TagPoolManager
    
    success = TagPoolManager.rollback_version(
        pool_type=request.pool_type,
        target_version=request.target_version,
        activated_by="admin"  # 这里应该是实际的用户ID
    )
    
    if not success:
        raise HTTPException(status_code=404, detail="目标版本不存在")
    
    return {
        "success": True,
        "message": f"已回滚到版本 {request.target_version}",
        "data": {
            "pool_type": request.pool_type,
            "target_version": request.target_version
        }
    }


@router.get("/versions")
async def get_versions(pool_type: str = Query("scene", description="标签池类型：scene/product")):
    """获取版本历史"""
    from storage.database.tag_pool_manager import TagPoolManager
    
    versions = TagPoolManager.get_version_history(pool_type)
    
    return {
        "success": True,
        "data": {
            "pool_type": pool_type,
            "versions": versions
        }
    }


@router.get("/changes")
async def get_changes(
    pool_type: str = Query("scene", description="标签池类型：scene/product"),
    limit: int = Query(50, description="返回记录数限制")
):
    """获取变更历史"""
    from storage.database.tag_pool_manager import TagPoolManager
    
    changes = TagPoolManager.get_change_history(pool_type, limit)
    
    return {
        "success": True,
        "data": {
            "pool_type": pool_type,
            "changes": changes
        }
    }


@router.get("/current-pool")
async def get_current_pool(pool_type: Optional[str] = Query(None, description="标签池类型：scene/product（不传则返回所有）")):
    """获取当前激活的标签池"""
    from storage.database.tag_pool_manager import TagPoolManager
    
    if pool_type:
        pool = TagPoolManager.get_tags(pool_type)
        return {
            "success": True,
            "data": {
                pool_type: pool
            }
        }
    else:
        scene_pool = TagPoolManager.get_tags("scene")
        product_pool = TagPoolManager.get_tags("product")
        
        return {
            "success": True,
            "data": {
                "scene": scene_pool,
                "product": product_pool
            }
        }


@router.post("/create-version")
async def create_new_version_api(request: CreateNewVersionRequest):
    """创建新的标签池版本"""
    from storage.database.tag_pool_manager import TagPoolManager
    
    result = TagPoolManager.create_new_version(
        pool_type=request.pool_type,
        tags=request.tags,
        created_by=request.created_by
    )
    
    return {
        "success": True,
        "message": f"新版本 {result['version']} 已创建",
        "data": result
    }


@router.get("/active-version")
async def get_active_version(pool_type: str = Query("scene", description="标签池类型：scene/product")):
    """获取当前激活的版本号"""
    from storage.database.tag_pool_manager import TagPoolManager
    
    version = TagPoolManager.get_active_version(pool_type)
    
    return {
        "success": True,
        "data": {
            "pool_type": pool_type,
            "version": version
        }
    }
