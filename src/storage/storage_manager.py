"""
存储管理器
提供分类存储、自动过期、向后兼容的文件管理功能
"""
import os
import time
import json
import logging
from typing import Optional, Dict, List, Any
from datetime import datetime, timedelta
from pathlib import Path

# 从 storage 导入
from storage.s3.s3_storage import S3SyncStorage

logger = logging.getLogger(__name__)


class StorageCategory:
    """文件分类定义"""
    AVATAR = 'avatar'      # 用户头像（永久）
    UPLOAD = 'upload'      # 用户上传（30天）
    TEMP = 'temp'          # 临时文件（1天）
    
    @classmethod
    def get_prefix(cls, category: str) -> str:
        """获取分类对应的目录前缀"""
        mapping = {
            cls.AVATAR: 'avatars',
            cls.UPLOAD: 'uploads',
            cls.TEMP: 'temp'
        }
        return mapping.get(category, 'misc')
    
    @classmethod
    def get_expiry_days(cls, category: str) -> int:
        """获取分类对应的保留天数"""
        mapping = {
            cls.AVATAR: 3650,    # 10年
            cls.UPLOAD: 30,      # 30天
            cls.TEMP: 1          # 1天
        }
        return mapping.get(category, 30)
    
    @classmethod
    def is_permanent(cls, category: str) -> bool:
        """判断是否为永久存储"""
        return category == cls.AVATAR


class StorageManager:
    """存储管理器"""
    
    def __init__(self, storage: S3SyncStorage):
        self.storage = storage
    
    def upload_with_category(
        self,
        file_content: bytes,
        file_name: str,
        category: str,
        content_type: str = "application/octet-stream",
        acl: Optional[str] = None,
        metadata: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        """
        上传文件并自动分类管理
        
        Args:
            file_content: 文件内容
            file_name: 原始文件名
            category: 文件分类（avatar/upload/temp）
            content_type: MIME 类型
            acl: 访问控制列表（public-read 或 None）
        
        Returns:
            {
                'file_key': str,           # 对象键
                'url': str,                # 访问 URL
                'category': str,           # 分类
                'expires_at': Optional[int], # 过期时间戳（毫秒）
                'is_permanent': bool       # 是否永久
            }
        """
        # 验证分类
        if category not in [StorageCategory.AVATAR, StorageCategory.UPLOAD, StorageCategory.TEMP]:
            raise ValueError(f"不支持的分类: {category}")
        
        # 生成带分类前缀的对象键
        prefix = StorageCategory.get_prefix(category)
        original_name = Path(file_name).name
        object_key = self.storage._generate_object_key(original_name=original_name)
        full_key = f"{prefix}/{object_key}"
        
        # 设置 ACL
        if acl is None:
            # 头像默认公开可读
            acl = 'public-read' if category == StorageCategory.AVATAR else None
        
        # 添加元数据
        object_metadata = {
            'category': category,
            'created_at': str(int(time.time())),  # 创建时间（秒）
            'expires_in': str(StorageCategory.get_expiry_days(category) * 86400),
            'original_filename': original_name,
            'is_permanent': str(StorageCategory.is_permanent(category))
        }
        if metadata:
            for key, value in metadata.items():
                if value is None:
                    continue
                clean_key = str(key).strip().lower().replace('_', '-')
                if not clean_key:
                    continue
                object_metadata[clean_key] = str(value)
        
        try:
            # 上传文件（需要修改 storage.upload_file 支持元数据）
            file_key = self._upload_with_metadata(
                file_content=file_content,
                file_name=full_key,
                content_type=content_type,
                acl=acl,
                metadata=object_metadata
            )
            
            # 计算 URL 过期时间
            expires_at = None
            if not StorageCategory.is_permanent(category):
                expiry_seconds = StorageCategory.get_expiry_days(category) * 86400
                expires_at = int(time.time() + expiry_seconds)
            
            # 生成签名 URL
            # 永久文件使用长期签名（10年），临时文件使用短期签名（24小时）
            url_expiry = 315360000 if StorageCategory.is_permanent(category) else 86400
            url = self.storage.generate_presigned_url(key=file_key, expire_time=url_expiry)
            
            return {
                'file_key': file_key,
                'url': url,
                'category': category,
                'expires_at': expires_at,
                'is_permanent': StorageCategory.is_permanent(category)
            }
            
        except Exception as e:
            logger.error(f"上传文件失败: {e}")
            raise
    
    def _upload_with_metadata(
        self,
        file_content: bytes,
        file_name: str,
        content_type: str,
        acl: Optional[str],
        metadata: Dict[str, str]
    ) -> str:
        """
        上传文件并添加元数据
        （需要调用底层的 put_object 方法）
        """
        try:
            client = self.storage._get_client()
            
            # 构造参数
            put_object_kwargs = {
                "Bucket": self.storage._resolve_bucket(None),
                "Key": file_name,
                "Body": file_content,
                "ContentType": content_type,
                "Metadata": metadata  # 添加元数据
            }
            
            if acl:
                put_object_kwargs["ACL"] = acl
            
            client.put_object(**put_object_kwargs)
            return file_name
            
        except Exception as e:
            logger.error(f"上传文件到对象存储失败: {e}")
            raise
    
    def get_file_metadata(self, file_key: str) -> Optional[Dict[str, Any]]:
        """
        获取文件元数据
        
        Args:
            file_key: 对象键
        
        Returns:
            元数据字典
        """
        try:
            client = self.storage._get_client()
            resp = client.head_object(
                Bucket=self.storage._resolve_bucket(None),
                Key=file_key
            )
            
            metadata = resp.get('Metadata', {})
            
            # 解析元数据
            return {
                'category': metadata.get('category'),
                'source': metadata.get('source'),
                'created_at': int(metadata.get('created_at', 0)),
                'expires_in': int(metadata.get('expires_in', 0)),
                'original_filename': metadata.get('original_filename'),
                'is_permanent': metadata.get('is_permanent') == 'True'
            }
            
        except Exception as e:
            logger.error(f"获取文件元数据失败: {e}")
            return None
    
    def is_expired(self, file_key: str) -> bool:
        """
        判断文件是否过期
        
        Args:
            file_key: 对象键
        
        Returns:
            是否过期
        """
        metadata = self.get_file_metadata(file_key)
        if not metadata:
            return False
        
        # 永久文件不过期
        if metadata.get('is_permanent', False):
            return False
        
        # 检查是否过期
        created_at = metadata.get('created_at', 0)
        expires_in = metadata.get('expires_in', 0)
        
        if created_at == 0 or expires_in == 0:
            return False
        
        return (created_at + expires_in) < time.time()
    
    def cleanup_expired_files(self, dry_run: bool = True) -> Dict[str, Any]:
        """
        清理过期文件
        
        Args:
            dry_run: 是否为试运行（不实际删除）
        
        Returns:
            清理结果统计
        """
        result = {
            'scanned': 0,
            'expired': 0,
            'deleted': 0,
            'failed': 0,
            'errors': []
        }
        
        # 遍历所有分类
        categories = [
            StorageCategory.AVATAR,
            StorageCategory.UPLOAD,
            StorageCategory.TEMP
        ]
        
        for category in categories:
            prefix = StorageCategory.get_prefix(category)
            logger.info(f"扫描分类: {category}/")
            
            try:
                # 列出该分类下的所有文件
                files = self.storage.list_files(prefix=prefix + '/', max_keys=1000)
                
                result['scanned'] += len(files.get('keys', []))
                
                for file_key in files.get('keys', []):
                    try:
                        # 检查是否过期
                        if self.is_expired(file_key):
                            result['expired'] += 1
                            
                            if not dry_run:
                                # 实际删除
                                self.storage.delete_file(file_key=file_key)
                                result['deleted'] += 1
                                logger.info(f"已删除过期文件: {file_key}")
                            else:
                                logger.info(f"[试运行] 发现过期文件: {file_key}")
                    
                    except Exception as e:
                        result['failed'] += 1
                        result['errors'].append({
                            'file_key': file_key,
                            'error': str(e)
                        })
                        logger.error(f"处理文件失败: {file_key}, error: {e}")
                
                # 处理分页
                while files.get('is_truncated'):
                    files = self.storage.list_files(
                        prefix=prefix + '/',
                        max_keys=1000,
                        continuation_token=files.get('next_continuation_token')
                    )
                    
                    result['scanned'] += len(files.get('keys', []))
                    
                    for file_key in files.get('keys', []):
                        try:
                            if self.is_expired(file_key):
                                result['expired'] += 1
                                
                                if not dry_run:
                                    self.storage.delete_file(file_key=file_key)
                                    result['deleted'] += 1
                                    logger.info(f"已删除过期文件: {file_key}")
                                else:
                                    logger.info(f"[试运行] 发现过期文件: {file_key}")
                        
                        except Exception as e:
                            result['failed'] += 1
                            result['errors'].append({
                                'file_key': file_key,
                                'error': str(e)
                            })
            
            except Exception as e:
                logger.error(f"扫描分类 {category} 失败: {e}")
                result['errors'].append({
                    'category': category,
                    'error': str(e)
                })
        
        logger.info(f"清理完成: {json.dumps(result, ensure_ascii=False, indent=2)}")
        return result
    
    def regenerate_url(self, file_key: str) -> Optional[str]:
        """
        重新生成文件的访问 URL
        
        Args:
            file_key: 对象键
        
        Returns:
            新的签名 URL
        """
        try:
            metadata = self.get_file_metadata(file_key)
            if not metadata:
                logger.warning(f"文件不存在或无元数据: {file_key}")
                return None
            
            # 检查是否过期
            if self.is_expired(file_key):
                logger.warning(f"文件已过期: {file_key}")
                return None
            
            # 生成新的签名 URL
            url_expiry = 315360000 if metadata.get('is_permanent', False) else 86400
            url = self.storage.generate_presigned_url(key=file_key, expire_time=url_expiry)
            
            return url
            
        except Exception as e:
            logger.error(f"重新生成 URL 失败: {e}")
            return None


# 全局存储管理器实例（初始化时创建）
_storage_manager: Optional[StorageManager] = None


def get_storage_manager() -> StorageManager:
    """获取全局存储管理器实例"""
    global _storage_manager
    if _storage_manager is None:
        storage = S3SyncStorage(
            endpoint_url=os.getenv("COZE_BUCKET_ENDPOINT_URL"),
            access_key=os.getenv("COZE_ACCESS_KEY", ""),
            secret_key=os.getenv("COZE_SECRET_KEY", ""),
            bucket_name=os.getenv("COZE_BUCKET_NAME"),
            region=os.getenv("COZE_BUCKET_REGION", "cn-beijing")
        )
        _storage_manager = StorageManager(storage)
    return _storage_manager
