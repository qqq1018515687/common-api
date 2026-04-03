"""系统健康状态检查节点"""
import logging
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
    desc: 检查系统资源使用情况（内存、线程、CPU等）
    integrations: 
    """
    ctx = runtime.context
    
    try:
        from utils.resource_monitor import get_resource_stats, check_resource_warning
        
        # 获取资源统计
        stats = get_resource_stats()
        warning_result = check_resource_warning()
        
        result = {
            "code": 0,
            "msg": "success",
            "data": {
                "resources": stats,
                "warnings": warning_result["warnings"],
                "is_healthy": warning_result["is_healthy"]
            }
        }
        
        # 如果有告警，记录日志
        if warning_result["warnings"]:
            logger.warning(f"[系统健康检查] 告警: {warning_result['warnings']}")
        
    except Exception as e:
        logger.error(f"系统健康检查失败: {e}")
        result = {
            "code": 1,
            "msg": f"检查失败: {str(e)}",
            "data": None
        }
    
    return SystemHealthOutput(result=result)
