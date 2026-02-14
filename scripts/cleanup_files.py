#!/usr/bin/env python3
"""
文件清理脚本
用于定期清理对象存储中的过期文件

使用方法:
    # 模拟运行（不实际删除）
    python scripts/cleanup_files.py --dry-run

    # 实际运行
    python scripts/cleanup_files.py

    # 自定义保留天数
    python scripts/cleanup_files.py --avatar-days 7 --task-days 3
"""
import argparse
import logging
import sys
import os

# 添加项目根目录到 Python 路径
project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, project_root)

from storage.s3.s3_storage import S3SyncStorage
from storage.database.db import get_db
from storage.cleanup import cleanup_expired_files

# 配置日志
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


def main():
    parser = argparse.ArgumentParser(description='清理对象存储中的过期文件')
    parser.add_argument(
        '--dry-run',
        action='store_true',
        help='模拟运行，不实际删除文件'
    )
    parser.add_argument(
        '--avatar-days',
        type=int,
        default=30,
        help='头像保留天数（默认：30天）'
    )
    parser.add_argument(
        '--task-days',
        type=int,
        default=7,
        help='任务文件保留天数（默认：7天）'
    )

    args = parser.parse_args()

    logger.info("=" * 60)
    logger.info("文件清理脚本启动")
    logger.info("=" * 60)
    logger.info(f"模式: {'模拟运行（不删除）' if args.dry_run else '实际运行'}")
    logger.info(f"头像保留天数: {args.avatar_days}")
    logger.info(f"任务文件保留天数: {args.task_days}")
    logger.info("=" * 60)

    try:
        # 初始化存储
        logger.info("初始化对象存储...")
        storage = S3SyncStorage(
            access_key=os.getenv("COZE_BUCKET_ACCESS_KEY", ""),
            secret_key=os.getenv("COZE_BUCKET_SECRET_KEY", ""),
            bucket_name=os.getenv("COZE_BUCKET_NAME", ""),
            region=os.getenv("COZE_BUCKET_REGION", "cn-beijing")
        )

        # 获取数据库会话
        logger.info("连接数据库...")
        db_gen = get_db()
        db = next(db_gen)

        try:
            # 执行清理
            result = cleanup_expired_files(
                storage=storage,
                db=db,
                avatar_days=args.avatar_days,
                task_days=args.task_days,
                dry_run=args.dry_run
            )

            # 输出结果
            logger.info("")
            logger.info("=" * 60)
            logger.info("清理结果汇总")
            logger.info("=" * 60)
            logger.info(f"头像清理: {result['avatar_cleanup']}")
            logger.info(f"任务清理: {result['task_cleanup']}")
            logger.info(f"总计删除: {result['summary']['total_deleted']} 个文件")
            logger.info(f"总计跳过: {result['summary']['total_skipped']} 个文件")
            logger.info("=" * 60)

            if args.dry_run:
                logger.info("⚠️  这是模拟运行，没有实际删除文件")
                logger.info("要实际删除文件，请去掉 --dry-run 参数")

            return 0

        finally:
            # 关闭数据库连接
            db.close()
            db_gen.close()

    except Exception as e:
        logger.error(f"清理失败: {e}", exc_info=True)
        return 1


if __name__ == '__main__':
    sys.exit(main())
