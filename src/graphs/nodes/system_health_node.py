"""系统健康状态检查节点"""
import logging
import threading
from typing import Dict, Any
from langchain_core.runnables import RunnableConfig
from langgraph.runtime import Runtime
from coze_coding_utils.runtime_ctx.context import Context
from pydantic import BaseModel, Field

logger = logging.getLogger(__name__)


class SystemHealthInput(BaseModel):
    """系统健康检查节点的输入"""
    check_type: str = Field(default="basic", description="检查类型：basic/basic/full")


class SystemHealthOutput(BaseModel):
    """系统健康检查节点的输出"""
    result: Dict[str, Any] = Field(..., description="检查结果")


def system_health_node(
    state: SystemHealthInput,
    config: RunnableConfig,
    runtime: Runtime[Context]
) -> SystemHealthOutput:
    """
    title: 系统健康检查
    desc: 检查系统资源使用情况（内存、线程、CPU、数据库连接等）
    integrations: 
    """
    ctx = runtime.context
    
    try:
        from utils.resource_monitor import get_resource_stats, check_resource_warning
        from storage.database.db import get_engine
        
        # 获取资源统计
        stats = get_resource_stats()
        warning_result = check_resource_warning()
        
        # 获取数据库连接池状态
        try:
            engine = get_engine()
            pool = engine.pool
            db_stats = {
                "pool_size": pool.size(),           # 连接池大小
                "checked_out": pool.checkedout(),    # 已签出的连接数
                "overflow": pool.overflow(),         # 溢出连接数
                "checked_in": pool.checkedin(),      # 已签入的连接数
            }
            # 计算使用中的连接数
            db_stats["active_connections"] = db_stats["checked_out"] + db_stats["overflow"]
        except Exception as e:
            logger.warning(f"获取数据库连接池状态失败: {e}")
            db_stats = {
                "pool_size": -1,
                "checked_out": -1,
                "overflow": -1,
                "checked_in": -1,
                "active_connections": -1,
                "error": str(e)
            }
        
        # 获取运行中的任务数（从 main.py 的 service 获取）
        try:
            from main import service
            running_tasks_count = len(service.running_tasks)
            running_tasks_info = {
                "count": running_tasks_count,
                "warning": running_tasks_count > 50  # 超过50个任务视为异常
            }
        except Exception as e:
            logger.warning(f"获取运行任务数失败: {e}")
            running_tasks_info = {
                "count": -1,
                "warning": False,
                "error": str(e)
            }
        
        # 合并统计
        all_stats = {
            **stats,
            "db_connections": db_stats,
            "running_tasks": running_tasks_info
        }
        
        # 扩展告警列表
        warnings = list(warning_result["warnings"])
        
        # 数据库连接告警
        if db_stats.get("active_connections", 0) > 80:  # 超过80个连接
            warnings.append(f"数据库连接数过高: {db_stats['active_connections']}")
        
        # 运行任务告警
        if running_tasks_info.get("warning", False):
            warnings.append(f"运行中任务数过多: {running_tasks_info['count']}")
        
        result = {
            "code": 0,
            "msg": "success",
            "data": {
                "resources": all_stats,
                "warnings": warnings,
                "is_healthy": len(warnings) == 0
            }
        }
        
        # 如果有告警，记录日志
        if warnings:
            logger.warning(f"[系统健康检查] 告警: {warnings}")
        
    except Exception as e:
        logger.error(f"系统健康检查失败: {e}")
        result = {
            "code": 1,
            "msg": f"检查失败: {str(e)}",
            "data": None
        }
    
    return SystemHealthOutput(result=result)
