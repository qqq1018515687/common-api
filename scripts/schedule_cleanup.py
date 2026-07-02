#!/usr/bin/env python3
"""
定时清理过期文件的入口脚本
用于 Crontab 或 Coze 定时工作流调用
"""
import os
import sys
import logging
from datetime import datetime
from pathlib import Path

# 添加项目路径到 Python 路径
project_root = str(Path(__file__).resolve().parent.parent)
sys.path.insert(0, project_root)

from src.storage.storage_manager import get_storage_manager

# 配置日志
log_dir = Path(project_root) / 'logs'
log_dir.mkdir(exist_ok=True)

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler(log_dir / 'cleanup.log', encoding='utf-8'),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)


def cleanup_expired_files():
    """清理过期文件"""
    try:
        storage_mgr = get_storage_manager()

        logger.info("=" * 60)
        logger.info(f"[定时清理] 开始清理 - {datetime.now()}")
        logger.info("=" * 60)

        # 执行清理（实际删除）
        result = storage_mgr.cleanup_expired_files(dry_run=False)

        logger.info("=" * 60)
        logger.info("[定时清理] 清理统计")
        logger.info("=" * 60)
        logger.info(f"扫描文件数: {result['scanned']}")
        logger.info(f"过期文件数: {result['expired']}")
        logger.info(f"实际删除数: {result['deleted']}")
        logger.info(f"失败文件数: {result['failed']}")
        logger.info("=" * 60)

        # 计算节省空间（估算）
        if result['deleted'] > 0:
            avg_size_kb = 500  # 假设平均每张图片500KB
            saved_mb = (result['deleted'] * avg_size_kb) / 1024
            logger.info(f"预估节省空间: {saved_mb:.2f} MB")

        logger.info(f"[定时清理] 清理完成 - {datetime.now()}")

        return 0

    except Exception as e:
        logger.error(f"[定时清理] 清理失败: {e}", exc_info=True)
        return 1


if __name__ == '__main__':
    exit_code = cleanup_expired_files()
    sys.exit(exit_code)
