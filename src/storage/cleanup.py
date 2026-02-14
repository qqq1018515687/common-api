"""
文件清理管理器
用于定期清理对象存储中的过期文件
"""
import logging
from datetime import datetime
from typing import Optional, List, Dict
from sqlalchemy.orm import Session

from storage.file_metadata_manager import FileMetadataManager
from storage.s3.s3_storage import S3SyncStorage
from storage.database.shared.model import Users, Tasks, FileMetadata

logger = logging.getLogger(__name__)


class FileCleanupManager:
    """文件清理管理器"""

    def __init__(self, storage: S3SyncStorage, db: Session):
        self.storage = storage
        self.db = db
        self.meta_manager = FileMetadataManager(db)

    def clean_temp_files(self, dry_run: bool = False) -> Dict:
        """
        清理过期的临时文件（24小时URL过期）

        Args:
            dry_run: 是否只模拟执行，不真正删除

        Returns:
            统计信息
        """
        logger.info("=" * 60)
        logger.info("开始清理临时文件...")
        logger.info("=" * 60)

        # 获取过期的临时文件
        expired_files = self.meta_manager.get_expired_files(hours=24)
        # 过滤出 temp_ 前缀的文件
        temp_files = [f for f in expired_files if f.file_prefix == 'temp']

        logger.info(f"找到 {len(temp_files)} 个过期的临时文件")

        deleted_count = 0
        skipped_count = 0

        for file_meta in temp_files:
            try:
                if not dry_run:
                    # 删除对象存储中的文件
                    self.storage.delete_file(file_key=file_meta.file_key)

                    # 标记为已删除
                    self.meta_manager.mark_as_deleted(file_meta.file_key)
                    deleted_count += 1
                    logger.info(f"✓ 已删除临时文件: {file_meta.file_key}")
                else:
                    deleted_count += 1
                    logger.info(f"[DRY RUN] 将删除临时文件: {file_meta.file_key}")
            except Exception as e:
                logger.error(f"✗ 删除文件失败 {file_meta.file_key}: {e}")
                skipped_count += 1

        result = {
            'total': len(temp_files),
            'deleted': deleted_count,
            'skipped': skipped_count
        }

        logger.info("=" * 60)
        logger.info(f"临时文件清理完成: 总数={result['total']}, 删除={result['deleted']}, 跳过={result['skipped']}")
        logger.info("=" * 60)

        return result

    def clean_orphaned_avatars(self, dry_run: bool = False) -> Dict:
        """
        清理孤立的头像文件（用户已删除或已更换头像）

        Args:
            dry_run: 是否只模拟执行，不真正删除

        Returns:
            统计信息
        """
        logger.info("=" * 60)
        logger.info("开始清理孤立头像文件...")
        logger.info("=" * 60)

        # 获取所有用户的头像URL
        users = self.db.query(Users.avatar).filter(Users.avatar.isnot(None)).all()
        active_avatar_urls = {u.avatar for u in users}

        # 获取所有头像文件元数据
        avatar_files = self.meta_manager.get_files_by_prefix('avatar')

        logger.info(f"当前活跃头像数: {len(active_avatar_urls)}")
        logger.info(f"数据库中头像文件数: {len(avatar_files)}")

        deleted_count = 0
        skipped_count = 0

        for file_meta in avatar_files:
            try:
                # 获取文件的公开URL
                file_url = self.storage.get_file_url(file_meta.file_key)

                # 检查是否还在使用中
                if file_url in active_avatar_urls:
                    logger.debug(f"跳过活跃头像: {file_meta.file_key}")
                    skipped_count += 1
                    continue

                # 删除孤立文件
                if not dry_run:
                    self.storage.delete_file(file_key=file_meta.file_key)
                    self.meta_manager.mark_as_deleted(file_meta.file_key)
                    deleted_count += 1
                    logger.info(f"✓ 已删除孤立头像: {file_meta.file_key}")
                else:
                    deleted_count += 1
                    logger.info(f"[DRY RUN] 将删除孤立头像: {file_meta.file_key}")
            except Exception as e:
                logger.error(f"✗ 处理头像文件失败 {file_meta.file_key}: {e}")
                skipped_count += 1

        result = {
            'total': len(avatar_files),
            'active': len(active_avatar_urls),
            'deleted': deleted_count,
            'skipped': skipped_count
        }

        logger.info("=" * 60)
        logger.info(f"孤立头像清理完成: 总数={result['total']}, 活跃={result['active']}, 删除={result['deleted']}, 跳过={result['skipped']}")
        logger.info("=" * 60)

        return result

    def clean_deleted_task_files(self, days: int = 7, dry_run: bool = False) -> Dict:
        """
        清理已删除任务的相关文件

        Args:
            days: 保留天数，超过这个天数的任务文件将被清理
            dry_run: 是否只模拟执行，不真正删除

        Returns:
            统计信息
        """
        logger.info("=" * 60)
        logger.info(f"开始清理 {days} 天前已删除任务的文件...")
        logger.info("=" * 60)

        # 计算过期时间戳（毫秒）
        current_time = int(datetime.now().timestamp() * 1000)
        expire_time = current_time - (days * 24 * 60 * 60 * 1000)

        # 查询已删除超过指定天数的任务
        deleted_tasks = self.db.query(Tasks).filter(
            Tasks.is_deleted == True,
            Tasks.updated_at < expire_time
        ).all()

        logger.info(f"找到 {len(deleted_tasks)} 个已删除超过 {days} 天的任务")

        deleted_count = 0
        skipped_count = 0

        for task in deleted_tasks:
            try:
                # 从任务结果中提取文件URL
                result = task.result or {}
                file_urls = self._extract_file_urls(result)

                if not file_urls:
                    logger.debug(f"任务 {task.id} 没有关联文件")
                    continue

                logger.info(f"处理任务 {task.id} 的 {len(file_urls)} 个文件")

                # 删除文件
                for file_url in file_urls:
                    if not file_url:
                        continue

                    try:
                        # 从URL中提取文件key
                        file_key = self._extract_key_from_url(file_url)
                        if not file_key:
                            logger.debug(f"无法从URL提取key: {file_url}")
                            skipped_count += 1
                            continue

                        # 查询文件元数据
                        file_meta = self.meta_manager.get_file_by_key(file_key)

                        if not file_meta:
                            logger.debug(f"文件元数据不存在: {file_key}")
                            skipped_count += 1
                            continue

                        # 删除文件
                        if not dry_run:
                            self.storage.delete_file(file_key=file_key)
                            self.meta_manager.mark_as_deleted(file_key)
                            deleted_count += 1
                            logger.info(f"✓ 已删除任务文件: {file_key}")
                        else:
                            deleted_count += 1
                            logger.info(f"[DRY RUN] 将删除任务文件: {file_key}")
                    except Exception as e:
                        logger.error(f"✗ 删除任务文件失败 {file_url}: {e}")
                        skipped_count += 1

            except Exception as e:
                logger.error(f"✗ 处理任务失败 {task.id}: {e}")
                skipped_count += 1

        result = {
            'total_tasks': len(deleted_tasks),
            'deleted': deleted_count,
            'skipped': skipped_count
        }

        logger.info("=" * 60)
        logger.info(f"已删除任务文件清理完成: 任务数={result['total_tasks']}, 删除={result['deleted']}, 跳过={result['skipped']}")
        logger.info("=" * 60)

        return result

    def clean_all(
        self,
        temp_hours: int = 24,
        task_days: int = 7,
        dry_run: bool = False
    ) -> Dict:
        """
        综合清理：清理所有过期文件

        Args:
            temp_hours: 临时文件保留小时数
            task_days: 任务文件保留天数
            dry_run: 是否只模拟执行

        Returns:
            综合统计信息
        """
        logger.info("=" * 60)
        logger.info("开始综合清理过期文件...")
        logger.info(f"模式: {'模拟运行（不删除）' if dry_run else '实际运行'}")
        logger.info(f"临时文件保留时间: {temp_hours} 小时")
        logger.info(f"任务文件保留时间: {task_days} 天")
        logger.info("=" * 60)

        # 清理临时文件
        temp_result = self.clean_temp_files(dry_run=dry_run)

        # 清理孤立头像
        avatar_result = self.clean_orphaned_avatars(dry_run=dry_run)

        # 清理已删除任务文件
        task_result = self.clean_deleted_task_files(days=task_days, dry_run=dry_run)

        # 获取存储统计
        stats = self.meta_manager.get_storage_stats()

        result = {
            'temp_cleanup': temp_result,
            'avatar_cleanup': avatar_result,
            'task_cleanup': task_result,
            'storage_stats': stats,
            'summary': {
                'total_deleted': temp_result.get('deleted', 0) + avatar_result.get('deleted', 0) + task_result.get('deleted', 0),
                'total_skipped': temp_result.get('skipped', 0) + avatar_result.get('skipped', 0) + task_result.get('skipped', 0)
            }
        }

        logger.info("=" * 60)
        logger.info("综合清理完成")
        logger.info(f"总计删除: {result['summary']['total_deleted']} 个文件")
        logger.info(f"总计跳过: {result['summary']['total_skipped']} 个文件")
        logger.info(f"存储统计: {stats}")
        logger.info("=" * 60)

        return result

    def _extract_file_urls(self, result: Dict) -> List[str]:
        """
        从任务结果中提取文件URL

        Args:
            result: 任务结果字典

        Returns:
            文件URL列表
        """
        file_urls = []

        if not isinstance(result, dict):
            return file_urls

        # 提取各种可能的文件URL
        url_keys = [
            'image_url', 'video_url', 'audio_url', 'file_url',
            'url', 'image', 'video', 'audio', 'file'
        ]

        for key in url_keys:
            if key in result and result[key]:
                url = result[key]
                if isinstance(url, str):
                    file_urls.append(url)

        return file_urls

    def _extract_key_from_url(self, url: str) -> Optional[str]:
        """
        从URL中提取文件key

        Args:
            url: 文件URL

        Returns:
            文件key，如果提取失败则返回None
        """
        try:
            # URL格式: {endpoint}/{bucket}/{key}
            parts = url.rstrip('/').split('/')
            if len(parts) >= 3:
                # 最后一个部分是文件key
                key = parts[-1]
                # 验证key是否包含已知前缀
                if key.startswith('temp_') or key.startswith('perm_') or key.startswith('avatar_') or key.startswith('task_'):
                    return key
        except Exception as e:
            logger.error(f"从URL提取key失败: {e}")

        return None


# 便捷函数
def cleanup_expired_files(
    storage: S3SyncStorage,
    db: Session,
    temp_hours: int = 24,
    task_days: int = 7,
    dry_run: bool = False
) -> Dict:
    """
    便捷函数：清理过期文件

    Args:
        storage: S3存储实例
        db: 数据库会话
        temp_hours: 临时文件保留小时数
        task_days: 任务文件保留天数
        dry_run: 是否只模拟执行

    Returns:
        统计信息
    """
    manager = FileCleanupManager(storage, db)
    return manager.clean_all(
        temp_hours=temp_hours,
        task_days=task_days,
        dry_run=dry_run
    )
