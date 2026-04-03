"""资源监控工具"""
import os
import psutil
import threading
import logging
from typing import Dict, Any

logger = logging.getLogger(__name__)


def get_resource_stats() -> Dict[str, Any]:
    """获取当前资源使用情况"""
    try:
        process = psutil.Process(os.getpid())
        
        # 内存信息
        memory_info = process.memory_info()
        memory_mb = memory_info.rss / 1024 / 1024
        
        # 线程数
        thread_count = threading.active_count()
        
        # 文件描述符数量
        try:
            fd_count = process.num_fds()
        except Exception:
            fd_count = -1  # Windows 不支持
        
        # CPU 使用率
        cpu_percent = process.cpu_percent(interval=0.1)
        
        return {
            "memory_mb": round(memory_mb, 2),
            "thread_count": thread_count,
            "fd_count": fd_count,
            "cpu_percent": round(cpu_percent, 2),
        }
    except Exception as e:
        logger.error(f"获取资源统计失败: {e}")
        return {
            "memory_mb": -1,
            "thread_count": -1,
            "fd_count": -1,
            "cpu_percent": -1,
            "error": str(e)
        }


def log_resource_stats():
    """记录资源使用情况日志"""
    stats = get_resource_stats()
    logger.info(f"[资源监控] 内存: {stats['memory_mb']}MB, 线程: {stats['thread_count']}, FD: {stats['fd_count']}, CPU: {stats['cpu_percent']}%")
    return stats


def check_resource_warning() -> Dict[str, Any]:
    """检查资源是否超过阈值"""
    stats = get_resource_stats()
    warnings = []
    
    # 内存警告阈值：1GB
    if stats['memory_mb'] > 1024:
        warnings.append(f"内存使用过高: {stats['memory_mb']}MB")
    
    # 线程数警告阈值：100
    if stats['thread_count'] > 100:
        warnings.append(f"线程数过多: {stats['thread_count']}")
    
    return {
        "stats": stats,
        "warnings": warnings,
        "is_healthy": len(warnings) == 0
    }
