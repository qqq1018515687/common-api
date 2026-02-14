"""
文件清理工具模块
用于定期清理对象存储中的过期文件
"""
import time
import logging
from typing import Optional, List
from sqlalchemy.orm import Session
from storage.database.shared.model import Tasks, Users
from storage.s3.s3_storage import S3SyncStorage

logger = logging.getLogger(__name__)


class FileCleanupManager:
    """文件清理管理器"""

    def __init__(self, storage: S3SyncStorage):
        self.storage = storage

    def clean_orphaned_avatars(self, db: Session, dry_run: bool = False) -> dict:
        """
        清理孤立的头像文件（用户已删除的头像）

        Args:
            db: 数据库会话
            dry_run: 是否只模拟执行，不真正删除

        Returns:
            统计信息：{'total': 总数, 'deleted': 删除数, 'skipped': 跳过数}
        """
        logger.info("开始清理孤立头像文件...")

        # 获取所有用户的头像URL
        users = db.query(Users.avatar).filter(Users.avatar.isnot(None)).all()
        active_avatar_urls = {user.avatar for user in users}

        # 获取对象存储中所有文件
        try:
            all_files = self.storage.list_files()
        except Exception as e:
            logger.error(f"列出文件失败: {e}")
            return {'total': 0, 'deleted': 0, 'skipped': 0, 'error': str(e)}

        deleted_count = 0
        skipped_count = 0

        for file_key in all_files.get('keys', []):
            # 检查是否是头像文件
            if not file_key.startswith('avatar_'):
                skipped_count += 1
                continue

            # 获取文件的公开URL
            try:
                file_url = self.storage.get_file_url(file_key)
            except Exception as e:
                logger.warning(f"获取文件URL失败 {file_key}: {e}")
                skipped_count += 1
                continue

            # 检查是否还在使用中
            if file_url in active_avatar_urls:
                skipped_count += 1
                continue

            # 删除孤立文件
            if not dry_run:
                try:
                    self.storage.delete_file(file_key=file_key)
                    deleted_count += 1
                    logger.info(f"已删除孤立头像: {file_key}")
                except Exception as e:
                    logger.error(f"删除文件失败 {file_key}: {e}")
                    skipped_count += 1
            else:
                deleted_count += 1
                logger.info(f"[DRY RUN] 将删除: {file_key}")

        result = {
            'total': len(all_files.get('keys', [])),
            'deleted': deleted_count,
            'skipped': skipped_count
        }

        logger.info(f"清理完成: {result}")
        return result

    def clean_old_task_files(
        self,
        db: Session,
        days: int = 7,
        dry_run: bool = False
    ) -> dict:
        """
        清理旧任务相关的文件

        Args:
            db: 数据库会话
            days: 保留天数，超过这个天数的任务文件将被清理
            dry_run: 是否只模拟执行，不真正删除

        Returns:
            统计信息
        """
        logger.info(f"开始清理 {days} 天前的任务文件...")

        # 计算过期时间戳
        expire_time = int((time.time() - days * 24 * 60 * 60) * 1000)

        # 查询已删除或过期的任务
        old_tasks = db.query(Tasks).filter(
            Tasks.is_deleted == True,
            Tasks.created_at < expire_time
        ).all()

        deleted_count = 0
        skipped_count = 0

        for task in old_tasks:
            # 从任务结果中提取文件URL
            result = task.result or {}
            file_urls = []

            # 提取各种可能的文件URL
            if isinstance(result, dict):
                # 图片文件
                if 'image_url' in result:
                    file_urls.append(result['image_url'])
                # 视频文件
                if 'video_url' in result:
                    file_urls.append(result['video_url'])
                # 音频文件
                if 'audio_url' in result:
                    file_urls.append(result['audio_url'])
                # 其他文件
                if 'file_url' in result:
                    file_urls.append(result['file_url'])

            # 删除文件
            for file_url in file_urls:
                if not file_url:
                    continue

                try:
                    # 从URL中提取文件key
                    file_key = self.storage._extract_key_from_url(file_url)
                    if not file_key:
                        skipped_count += 1
                        continue

                    if not dry_run:
                        self.storage.delete_file(file_key=file_key)
                        deleted_count += 1
                        logger.info(f"已删除任务文件: {file_key}")
                    else:
                        deleted_count += 1
                        logger.info(f"[DRY RUN] 将删除: {file_key}")

                except Exception as e:
                    logger.error(f"删除任务文件失败 {file_url}: {e}")
                    skipped_count += 1

        result = {
            'total_tasks': len(old_tasks),
            'deleted': deleted_count,
            'skipped': skipped_count
        }

        logger.info(f"清理完成: {result}")
        return result

    def clean_expired_files(
        self,
        db: Session,
        avatar_days: int = 30,
        task_days: int = 7,
        dry_run: bool = False
    ) -> dict:
        """
        综合清理：清理所有过期文件

        Args:
            db: 数据库会话
            avatar_days: 头像保留天数
            task_days: 任务文件保留天数
            dry_run: 是否只模拟执行

        Returns:
            综合统计信息
        """
        logger.info("=" * 60)
        logger.info("开始综合清理过期文件...")
        logger.info("=" * 60)

        # 清理孤立头像
        avatar_result = self.clean_orphaned_avatars(db, dry_run=dry_run)

        # 清理旧任务文件
        task_result = self.clean_old_task_files(db, days=task_days, dry_run=dry_run)

        result = {
            'avatar_cleanup': avatar_result,
            'task_cleanup': task_result,
            'summary': {
                'total_deleted': avatar_result.get('deleted', 0) + task_result.get('deleted', 0),
                'total_skipped': avatar_result.get('skipped', 0) + task_result.get('skipped', 0)
            }
        }

        logger.info("=" * 60)
        logger.info(f"综合清理完成: {result['summary']}")
        logger.info("=" * 60)

        return result


# 便捷函数
def cleanup_expired_files(
    storage: S3SyncStorage,
    db: Session,
    avatar_days: int = 30,
    task_days: int = 7,
    dry_run: bool = False
) -> dict:
    """
    便捷函数：清理过期文件

    Args:
        storage: S3存储实例
        db: 数据库会话
        avatar_days: 头像保留天数
        task_days: 任务文件保留天数
        dry_run: 是否只模拟执行

    Returns:
        统计信息
    """
    manager = FileCleanupManager(storage)
    return manager.clean_expired_files(
        db=db,
        avatar_days=avatar_days,
        task_days=task_days,
        dry_run=dry_run
    )
