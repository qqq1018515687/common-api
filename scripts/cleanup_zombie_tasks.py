#!/usr/bin/env python3
"""
清理僵尸任务工具
用于清理状态为 'running' 但实际已经失败/超时的任务
"""
import os
import sys
import logging
from datetime import datetime, timedelta
from typing import Optional, Dict, List

# 添加项目根目录到 Python 路径
project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if project_root not in sys.path:
    sys.path.insert(0, project_root)

from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker, Session

# 配置日志
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


class ZombieTaskCleaner:
    """僵尸任务清理器"""

    def __init__(self, db_url: Optional[str] = None):
        """
        初始化清理器

        Args:
            db_url: 数据库连接URL，如果不提供则从环境变量读取
        """
        if db_url is None:
            # 从环境变量获取数据库URL
            db_url = os.getenv("DATABASE_URL")

        if not db_url:
            raise ValueError("DATABASE_URL 环境变量未设置")

        self.engine = create_engine(db_url)
        self.SessionLocal = sessionmaker(bind=self.engine)

    def get_zombie_tasks(self, timeout_minutes: int = 15) -> List[Dict]:
        """
        获取僵尸任务列表

        Args:
            timeout_minutes: 超时阈值（分钟），默认15分钟

        Returns:
            僵尸任务列表
        """
        session: Session = self.SessionLocal()
        try:
            # 计算超时时间戳（毫秒）
            timeout_timestamp = int((datetime.utcnow() - timedelta(minutes=timeout_minutes)).timestamp() * 1000)

            # 查询超过超时阈值的 running 任务
            query = text("""
                SELECT
                    id,
                    user_id,
                    platform,
                    platform_task_id,
                    type,
                    status,
                    created_at::bigint,
                    updated_at::bigint,
                    completed_at,
                    error,
                    (updated_at::bigint - created_at::bigint) / 1000 / 60 as duration_minutes,
                    (EXTRACT(EPOCH FROM (NOW() - to_timestamp(updated_at::bigint/1000))) / 60) as minutes_since_update
                FROM tasks
                WHERE status = 'running'
                  AND updated_at::bigint < :timeout_timestamp
                ORDER BY created_at ASC
            """)

            result = session.execute(query, {"timeout_timestamp": timeout_timestamp})
            tasks = [dict(row._mapping) for row in result]

            return tasks

        finally:
            session.close()

    def mark_tasks_as_failed(self, task_ids: List[str], error_message: str = "Task timeout - automatically marked as failed") -> int:
        """
        批量将任务标记为失败

        Args:
            task_ids: 任务ID列表
            error_message: 错误信息

        Returns:
            成功标记的任务数量
        """
        if not task_ids:
            return 0

        session: Session = self.SessionLocal()
        try:
            # 批量更新任务状态
            update_timestamp = int(datetime.utcnow().timestamp() * 1000)

            query = text("""
                UPDATE tasks
                SET
                    status = 'failed',
                    error = :error_message,
                    updated_at = :updated_at,
                    completed_at = :completed_at
                WHERE id = ANY(:task_ids)
                  AND status = 'running'
            """)

            result = session.execute(query, {
                "error_message": error_message,
                "updated_at": str(update_timestamp),
                "completed_at": str(update_timestamp),
                "task_ids": task_ids
            })

            session.commit()
            affected = result.rowcount

            logger.info(f"批量标记了 {affected} 个任务为失败状态")
            return affected

        except Exception as e:
            session.rollback()
            logger.error(f"批量标记失败: {e}")
            return 0
        finally:
            session.close()

    def cleanup_zombie_tasks(self, timeout_minutes: int = 15, dry_run: bool = True) -> Dict:
        """
        清理僵尸任务

        Args:
            timeout_minutes: 超时阈值（分钟）
            dry_run: 是否为试运行

        Returns:
            清理结果
        """
        logger.info("=" * 60)
        logger.info(f"清理僵尸任务 {'(试运行模式)' if dry_run else '(实际执行)'}")
        logger.info(f"超时阈值: {timeout_minutes} 分钟")
        logger.info("=" * 60)

        # 获取僵尸任务
        zombie_tasks = self.get_zombie_tasks(timeout_minutes)

        if not zombie_tasks:
            logger.info("没有发现僵尸任务")
            return {
                "total_zombies": 0,
                "cleaned": 0,
                "failed": 0,
                "skipped": 0
            }

        logger.info(f"\n发现 {len(zombie_tasks)} 个僵尸任务:")
        logger.info("-" * 60)

        # 按运行时长分组统计
        duration_groups = {
            ">1h": 0,
            "30min-1h": 0,
            "15-30min": 0,
            "5-15min": 0,
            "<5min": 0
        }

        for task in zombie_tasks:
            duration = task.get('duration_minutes', 0)

            if duration > 60:
                duration_groups[">1h"] += 1
            elif duration > 30:
                duration_groups["30min-1h"] += 1
            elif duration > 15:
                duration_groups["15-30min"] += 1
            elif duration > 5:
                duration_groups["5-15min"] += 1
            else:
                duration_groups["<5min"] += 1

        logger.info("运行时长分布:")
        for group, count in duration_groups.items():
            if count > 0:
                logger.info(f"  {group}: {count} 个")

        logger.info(f"\n僵尸任务列表 (最近10个):")
        for task in zombie_tasks[:10]:
            logger.info(
                f"  - ID: {task['id']}, "
                f"用户: {task['user_id']}, "
                f"平台: {task['platform']}, "
                f"运行时长: {task['duration_minutes']:.1f}分钟, "
                f"最后更新: {task['minutes_since_update']:.1f}分钟前"
            )

        if len(zombie_tasks) > 10:
            logger.info(f"  ... 还有 {len(zombie_tasks) - 10} 个任务")

        if dry_run:
            logger.info(f"\n[试运行] 将会标记 {len(zombie_tasks)} 个任务为失败状态")
            return {
                "total_zombies": len(zombie_tasks),
                "cleaned": 0,
                "failed": 0,
                "skipped": len(zombie_tasks)
            }

        # 实际执行清理
        logger.info(f"\n正在清理 {len(zombie_tasks)} 个僵尸任务...")

        task_ids = [task['id'] for task in zombie_tasks]
        cleaned = self.mark_tasks_as_failed(
            task_ids,
            error_message=f"Task timeout - exceeded {timeout_minutes} minutes, automatically marked as failed"
        )

        logger.info(f"成功清理了 {cleaned} 个僵尸任务")

        return {
            "total_zombies": len(zombie_tasks),
            "cleaned": cleaned,
            "failed": len(zombie_tasks) - cleaned,
            "skipped": 0
        }

    def get_running_tasks_stats(self) -> Dict:
        """
        获取运行中任务的统计信息

        Returns:
            统计信息
        """
        session: Session = self.SessionLocal()
        try:
            query = text("""
                SELECT
                    COUNT(*) as total_running,
                    COUNT(*) FILTER (WHERE (updated_at::bigint - created_at::bigint) / 1000 / 60 > 60) as over_1h,
                    COUNT(*) FILTER (WHERE (updated_at::bigint - created_at::bigint) / 1000 / 60 > 30) as over_30min,
                    COUNT(*) FILTER (WHERE (updated_at::bigint - created_at::bigint) / 1000 / 60 > 15) as over_15min,
                    COUNT(*) FILTER (WHERE (updated_at::bigint - created_at::bigint) / 1000 / 60 > 5) as over_5min,
                    COUNT(*) FILTER (WHERE (updated_at::bigint - created_at::bigint) / 1000 / 60 > 1) as over_1min,
                    COUNT(*) FILTER (WHERE (updated_at::bigint - created_at::bigint) / 1000 / 60 <= 1) as under_1min
                FROM tasks
                WHERE status = 'running'
            """)

            result = session.execute(query)
            stats = dict(result.fetchone()._mapping)

            return stats

        finally:
            session.close()


def main():
    """主函数"""
    import argparse

    parser = argparse.ArgumentParser(
        description='清理僵尸任务工具',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
示例:
  # 1. 查看僵尸任务统计
  python scripts/cleanup_zombie_tasks.py --stats

  # 2. 扫描僵尸任务（15分钟超时）
  python scripts/cleanup_zombie_tasks.py --scan --timeout 15

  # 3. 试运行清理（不实际修改）
  python scripts/cleanup_zombie_tasks.py --cleanup --timeout 15

  # 4. 实际清理僵尸任务
  python scripts/cleanup_zombie_tasks.py --cleanup --timeout 15 --force

  # 5. 使用自定义超时阈值（30分钟）
  python scripts/cleanup_zombie_tasks.py --cleanup --timeout 30 --force
        """
    )

    parser.add_argument('--stats', action='store_true', help='查看运行中任务统计')
    parser.add_argument('--scan', action='store_true', help='扫描僵尸任务列表')
    parser.add_argument('--cleanup', action='store_true', help='清理僵尸任务')
    parser.add_argument('--timeout', type=int, default=15, help='超时阈值（分钟），默认15分钟')
    parser.add_argument('--force', action='store_true', help='实际执行清理（需配合 --cleanup）')

    args = parser.parse_args()

    try:
        cleaner = ZombieTaskCleaner()

        if args.stats:
            # 显示统计信息
            logger.info("=" * 60)
            logger.info("运行中任务统计")
            logger.info("=" * 60)

            stats = cleaner.get_running_tasks_stats()

            logger.info(f"\n总运行中任务: {stats.get('total_running', 0)}")
            logger.info(f"  超过1小时: {stats.get('over_1h', 0)}")
            logger.info(f"  30-60分钟: {stats.get('over_30min', 0)}")
            logger.info(f"  15-30分钟: {stats.get('over_15min', 0)}")
            logger.info(f"  5-15分钟: {stats.get('over_5min', 0)}")
            logger.info(f"  1-5分钟: {stats.get('over_1min', 0)}")
            logger.info(f"  <1分钟: {stats.get('under_1min', 0)}")
            logger.info("=" * 60)

        elif args.scan:
            # 扫描僵尸任务
            zombie_tasks = cleaner.get_zombie_tasks(args.timeout)

            logger.info("=" * 60)
            logger.info(f"扫描僵尸任务 (超时阈值: {args.timeout}分钟)")
            logger.info("=" * 60)
            logger.info(f"\n发现 {len(zombie_tasks)} 个僵尸任务:\n")

            for task in zombie_tasks[:20]:
                logger.info(
                    f"ID: {task['id']}, "
                    f"用户: {task['user_id']}, "
                    f"平台: {task['platform']}, "
                    f"运行时长: {task['duration_minutes']:.1f}分钟, "
                    f"最后更新: {task['minutes_since_update']:.1f}分钟前"
                )

            if len(zombie_tasks) > 20:
                logger.info(f"\n... 还有 {len(zombie_tasks) - 20} 个任务")

            logger.info("=" * 60)

        elif args.cleanup:
            # 清理僵尸任务
            dry_run = not args.force

            if dry_run:
                logger.warning("[试运行模式] 不会实际修改数据库")
                logger.warning("添加 --force 参数来实际执行清理\n")

            result = cleaner.cleanup_zombie_tasks(args.timeout, dry_run=dry_run)

            logger.info("\n" + "=" * 60)
            logger.info("清理结果:")
            logger.info("=" * 60)
            logger.info(f"  发现僵尸任务: {result['total_zombies']}")
            logger.info(f"  已清理: {result['cleaned']}")
            logger.info(f"  失败: {result['failed']}")
            logger.info(f"  跳过: {result['skipped']}")
            logger.info("=" * 60)

        else:
            parser.print_help()

        return 0

    except Exception as e:
        logger.error(f"执行失败: {e}", exc_info=True)
        return 1


if __name__ == '__main__':
    sys.exit(main())
