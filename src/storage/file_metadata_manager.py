"""
文件元数据管理器
用于记录和管理对象存储中文件的元数据
"""
import logging
import time
from datetime import datetime, timedelta
from typing import Optional, List, Dict
from uuid import uuid4
from sqlalchemy.orm import Session

from storage.database.shared.model import FileMetadata

logger = logging.getLogger(__name__)


class FileMetadataManager:
    """文件元数据管理器"""

    def __init__(self, db: Session):
        self.db = db

    def record_file(
        self,
        *,
        file_key: str,
        file_prefix: str,
        file_type: str,
        file_size: Optional[int] = None,
        mime_type: Optional[str] = None,
        source_type: str,
        source_id: Optional[str] = None,
        retention_policy: Optional[str] = None,
        expire_hours: Optional[int] = None
    ) -> FileMetadata:
        """
        记录文件元数据

        Args:
            file_key: 文件在对象存储中的key
            file_prefix: 文件前缀（temp/perm/avatar/task）
            file_type: 文件类型（image/video/audio/document）
            file_size: 文件大小（字节）
            mime_type: MIME类型
            source_type: 来源类型（upload/save/avatar/task）
            source_id: 来源ID（user_id/task_id）
            retention_policy: 保留策略（24h/7d/30d/permanent）
            expire_hours: 过期时间（小时数），用于计算expire_time

        Returns:
            文件元数据对象
        """
        # 计算过期时间
        expire_time = None
        if expire_hours:
            expire_time = datetime.now() + timedelta(hours=expire_hours)

        # 创建文件元数据
        file_meta = FileMetadata(
            id=uuid4().hex,
            file_key=file_key,
            file_prefix=file_prefix,
            file_type=file_type,
            file_size=file_size,
            mime_type=mime_type,
            source_type=source_type,
            source_id=source_id,
            retention_policy=retention_policy,
            expire_time=expire_time,
            status='active'
        )

        self.db.add(file_meta)
        try:
            self.db.commit()
            self.db.refresh(file_meta)
            logger.info(f"记录文件元数据成功: {file_key}, 前缀: {file_prefix}, 来源: {source_type}")
            return file_meta
        except Exception as e:
            self.db.rollback()
            logger.error(f"记录文件元数据失败: {e}")
            raise e

    def get_file_by_key(self, file_key: str) -> Optional[FileMetadata]:
        """
        根据文件key获取文件元数据

        Args:
            file_key: 文件key

        Returns:
            文件元数据对象，如果不存在则返回None
        """
        return self.db.query(FileMetadata).filter(
            FileMetadata.file_key == file_key,
            FileMetadata.status == 'active'
        ).first()

    def mark_as_deleted(self, file_key: str) -> bool:
        """
        标记文件为已删除（软删除）

        Args:
            file_key: 文件key

        Returns:
            是否成功
        """
        file_meta = self.get_file_by_key(file_key)
        if not file_meta:
            logger.warning(f"文件不存在或已删除: {file_key}")
            return False

        file_meta.status = 'deleted'
        file_meta.updated_at = datetime.now()
        self.db.add(file_meta)

        try:
            self.db.commit()
            logger.info(f"标记文件为已删除: {file_key}")
            return True
        except Exception as e:
            self.db.rollback()
            logger.error(f"标记文件删除失败: {e}")
            return False

    def update_access_time(self, file_key: str) -> bool:
        """
        更新文件访问时间

        Args:
            file_key: 文件key

        Returns:
            是否成功
        """
        file_meta = self.get_file_by_key(file_key)
        if not file_meta:
            return False

        file_meta.access_time = datetime.now()
        file_meta.updated_at = datetime.now()
        self.db.add(file_meta)

        try:
            self.db.commit()
            return True
        except Exception as e:
            self.db.rollback()
            logger.error(f"更新访问时间失败: {e}")
            return False

    def get_files_by_source(self, source_type: str, source_id: str) -> List[FileMetadata]:
        """
        根据来源获取文件列表

        Args:
            source_type: 来源类型
            source_id: 来源ID

        Returns:
            文件元数据列表
        """
        return self.db.query(FileMetadata).filter(
            FileMetadata.source_type == source_type,
            FileMetadata.source_id == source_id,
            FileMetadata.status == 'active'
        ).all()

    def get_expired_files(self, hours: int = 24) -> List[FileMetadata]:
        """
        获取过期的文件

        Args:
            hours: 过期小时数

        Returns:
            过期文件列表
        """
        expire_time = datetime.now() - timedelta(hours=hours)

        return self.db.query(FileMetadata).filter(
            FileMetadata.status == 'active',
            FileMetadata.expire_time.isnot(None),
            FileMetadata.expire_time < expire_time
        ).all()

    def get_files_by_prefix(self, file_prefix: str) -> List[FileMetadata]:
        """
        根据文件前缀获取文件列表

        Args:
            file_prefix: 文件前缀

        Returns:
            文件元数据列表
        """
        return self.db.query(FileMetadata).filter(
            FileMetadata.file_prefix == file_prefix,
            FileMetadata.status == 'active'
        ).all()

    def get_storage_stats(self) -> Dict:
        """
        获取存储统计信息

        Returns:
            统计信息字典
        """
        stats = {}

        # 按前缀统计
        for prefix in ['temp', 'perm', 'avatar', 'task']:
            files = self.get_files_by_prefix(prefix)
            stats[f'{prefix}_count'] = len(files)
            stats[f'{prefix}_size'] = sum(f.file_size or 0 for f in files)

        # 总计
        stats['total_count'] = sum(stats[f'{prefix}_count'] for prefix in ['temp', 'perm', 'avatar', 'task'])
        stats['total_size'] = sum(stats[f'{prefix}_size'] for prefix in ['temp', 'perm', 'avatar', 'task'])

        # 按类型统计
        for file_type in ['image', 'video', 'audio', 'document']:
            files = self.db.query(FileMetadata).filter(
                FileMetadata.file_type == file_type,
                FileMetadata.status == 'active'
            ).all()
            stats[f'{file_type}_count'] = len(files)
            stats[f'{file_type}_size'] = sum(f.file_size or 0 for f in files)

        return stats
