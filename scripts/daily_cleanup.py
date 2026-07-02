#!/usr/bin/env python3
"""
对象存储定时清理调度器
每天凌晨3点自动清理过期的 uploads/ 和 temp/ 目录文件
"""
import os
import sys
import time
import logging
from pathlib import Path
from datetime import datetime

# 添加项目路径到 Python 路径
project_root = str(Path(__file__).resolve().parent.parent)
sys.path.insert(0, project_root)

from src.storage.storage_manager import get_storage_manager

# 配置日志
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


def cleanup_expired_files():
    """清理过期文件"""
    try:
        storage_mgr = get_storage_manager()

        logger.info("=" * 60)
        logger.info(f"[DailyCleanup] 开始清理 - {datetime.now()}")
        logger.info("=" * 60)

        # 执行清理（实际删除）
        result = storage_mgr.cleanup_expired_files(dry_run=False)

        logger.info("=" * 60)
        logger.info("[DailyCleanup] 清理统计")
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

        logger.info(f"[DailyCleanup] 清理完成 - {datetime.now()}")

        return result

    except Exception as e:
        logger.error(f"[DailyCleanup] 清理失败: {e}", exc_info=True)
        return None


def main():
    """主函数 - 执行一次清理"""
    logger.info("[DailyCleanup] 手动触发清理任务")
    result = cleanup_expired_files()

    if result and result.get('deleted', 0) > 0:
        logger.info(f"[DailyCleanup] 成功清理 {result['deleted']} 个过期文件")
        return 0
    elif result:
        logger.info("[DailyCleanup] 无过期文件需要清理")
        return 0
    else:
        logger.error("[DailyCleanup] 清理任务执行失败")
        return 1


if __name__ == '__main__':
    sys.exit(main())
