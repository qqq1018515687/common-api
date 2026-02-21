#!/usr/bin/env python3
"""
旧数据迁移工具
将旧数据按照新方案重新分类
"""
import os
import sys
import re
import logging
from pathlib import Path
from typing import Dict, List, Tuple

sys.path.insert(0, '/app')

from src.storage.s3.s3_storage import S3SyncStorage

# 配置日志
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


class OldDataMigrator:
    """旧数据迁移器"""
    
    def __init__(self, storage: S3SyncStorage):
        self.storage = storage
    
    def identify_file_type(self, file_key: str) -> Tuple[str, int]:
        """
        识别文件类型和预期保留天数
        
        Args:
            file_key: 文件键
        
        Returns:
            (category, expiry_days)
        """
        # 根据文件名前缀识别类型
        if file_key.startswith('avatar_'):
            return ('avatar', 3650)  # 头像：永久
        elif file_key.startswith('upload_'):
            return ('upload', 7)     # 上传：7天
        elif file_key.startswith('temp_'):
            return ('temp', 1)       # 临时：1天
        elif file_key.startswith('image_'):
            return ('upload', 7)     # 图像：7天
        else:
            # 默认为上传类型
            return ('upload', 7)
    
    def list_all_files(self) -> List[str]:
        """列出所有文件（不包括已分类的）"""
        all_files = []
        
        try:
            # 列出所有文件
            result = self.storage.list_files(max_keys=1000)
            all_files.extend(result.get('keys', []))
            
            # 处理分页
            while result.get('is_truncated'):
                result = self.storage.list_files(
                    max_keys=1000,
                    continuation_token=result.get('next_continuation_token')
                )
                all_files.extend(result.get('keys', []))
            
            # 过滤掉已有分类前缀的文件
            old_files = [f for f in all_files if not self.has_category_prefix(f)]
            
            return old_files
        
        except Exception as e:
            logger.error(f"列出文件失败: {e}")
            return []
    
    def has_category_prefix(self, file_key: str) -> bool:
        """检查是否有分类前缀"""
        return file_key.startswith(('avatars/', 'uploads/', 'temp/'))
    
    def get_file_age_days(self, file_key: str) -> int:
        """
        获取文件创建时间（从文件名中提取时间戳）
        
        Args:
            file_key: 文件键
        
        Returns:
            文件存在天数，如果无法判断则返回 3650（永久）
        """
        try:
            # 从文件名中提取 UUID 时间戳部分
            # 例如：avatar_abc12345.png -> 12345 是时间戳的哈希
            match = re.search(r'_([a-f0-9]{8})\.', file_key)
            if match:
                # 这是一个简化的判断，实际上无法准确获取创建时间
                # 返回一个保守的估计值
                return 3650
            
            # 无法判断，假设是旧数据
            return 3650
        
        except Exception:
            return 3650
    
    def analyze_old_files(self) -> Dict:
        """
        分析旧数据
        
        Returns:
            分析结果统计
        """
        old_files = self.list_all_files()
        
        analysis = {
            'total': len(old_files),
            'by_category': {
                'avatar': 0,
                'upload': 0,
                'temp': 0,
                'unknown': 0
            },
            'files': []
        }
        
        for file_key in old_files:
            category, expiry_days = self.identify_file_type(file_key)
            age_days = self.get_file_age_days(file_key)
            
            analysis['by_category'][category] += 1
            
            analysis['files'].append({
                'file_key': file_key,
                'category': category,
                'expiry_days': expiry_days,
                'age_days': age_days,
                'should_keep': age_days < expiry_days
            })
        
        return analysis
    
    def migrate_file(self, file_key: str, dry_run: bool = True) -> bool:
        """
        迁移单个文件
        
        Args:
            file_key: 原始文件键
            dry_run: 是否为试运行
        
        Returns:
            是否成功
        """
        try:
            category, expiry_days = self.identify_file_type(file_key)
            category_prefix = {
                'avatar': 'avatars',
                'upload': 'uploads',
                'temp': 'temp'
            }.get(category, 'uploads')
            
            # 生成新的文件键
            new_key = f"{category_prefix}/{file_key}"
            
            if dry_run:
                logger.info(f"[试运行] 将迁移: {file_key} -> {new_key}")
                return True
            
            # 读取原文件
            file_content = self.storage.read_file(file_key=file_key)
            
            # 获取元数据（如果有）
            try:
                client = self.storage._get_client()
                head_resp = client.head_object(
                    Bucket=self.storage._resolve_bucket(None),
                    Key=file_key
                )
                content_type = head_resp.get('ContentType', 'application/octet-stream')
                acl = 'public-read' if category == 'avatar' else None
            except Exception:
                content_type = 'application/octet-stream'
                acl = 'public-read' if category == 'avatar' else None
            
            # 添加元数据
            import time
            metadata = {
                'category': category,
                'created_at': str(int(time.time())),  # 使用当前时间
                'expires_in': str(expiry_days * 86400),
                'original_filename': file_key,
                'is_permanent': str(category == 'avatar'),
                'migrated_from': file_key  # 记录原始位置
            }
            
            # 上传到新位置
            client = self.storage._get_client()
            put_object_kwargs = {
                "Bucket": self.storage._resolve_bucket(None),
                "Key": new_key,
                "Body": file_content,
                "ContentType": content_type,
                "Metadata": metadata
            }
            
            if acl:
                put_object_kwargs["ACL"] = acl
            
            client.put_object(**put_object_kwargs)
            
            # 删除原文件
            self.storage.delete_file(file_key=file_key)
            
            logger.info(f"已迁移: {file_key} -> {new_key}")
            return True
        
        except Exception as e:
            logger.error(f"迁移失败: {file_key}, error: {e}")
            return False
    
    def migrate_all(self, dry_run: bool = True) -> Dict:
        """
        迁移所有旧数据
        
        Args:
            dry_run: 是否为试运行
        
        Returns:
            迁移结果
        """
        old_files = self.list_all_files()
        
        result = {
            'total': len(old_files),
            'migrated': 0,
            'failed': 0,
            'failed_files': []
        }
        
        for file_key in old_files:
            success = self.migrate_file(file_key, dry_run=dry_run)
            if success:
                result['migrated'] += 1
            else:
                result['failed'] += 1
                result['failed_files'].append(file_key)
        
        return result


def main():
    """主函数"""
    import argparse
    
    parser = argparse.ArgumentParser(description='旧数据迁移工具')
    parser.add_argument('--analyze', action='store_true', help='分析旧数据')
    parser.add_argument('--migrate', action='store_true', help='迁移旧数据')
    parser.add_argument('--force', action='store_true', help='实际执行迁移（需配合 --migrate）')
    parser.add_argument('--verbose', '-v', action='store_true', help='详细输出')
    
    args = parser.parse_args()
    
    # 初始化存储
    storage = S3SyncStorage(
        endpoint_url=os.getenv("COZE_BUCKET_ENDPOINT_URL"),
        access_key=os.getenv("COZE_ACCESS_KEY", ""),
        secret_key=os.getenv("COZE_SECRET_KEY", ""),
        bucket_name=os.getenv("COZE_BUCKET_NAME"),
        region=os.getenv("COZE_BUCKET_REGION", "cn-beijing")
    )
    
    migrator = OldDataMigrator(storage)
    
    if args.analyze:
        # 分析旧数据
        logger.info("=" * 60)
        logger.info("分析旧数据")
        logger.info("=" * 60)
        
        analysis = migrator.analyze_old_files()
        
        logger.info(f"\n总文件数: {analysis['total']}")
        logger.info(f"头像 (avatar): {analysis['by_category']['avatar']}")
        logger.info(f"上传 (upload): {analysis['by_category']['upload']}")
        logger.info(f"临时 (temp): {analysis['by_category']['temp']}")
        logger.info(f"未知 (unknown): {analysis['by_category']['unknown']}")
        
        if args.verbose:
            logger.info("\n文件详情:")
            for file_info in analysis['files']:
                status = "[保留]" if file_info['should_keep'] else "[删除]"
                logger.info(f"  {status} {file_info['file_key']}")
                logger.info(f"    分类: {file_info['category']}")
                logger.info(f"    过期天数: {file_info['expiry_days']}")
        
        logger.info("\n" + "=" * 60)
    
    elif args.migrate:
        # 迁移旧数据
        dry_run = not args.force
        
        if dry_run:
            logger.info("=" * 60)
            logger.info("迁移旧数据（试运行模式）")
            logger.info("=" * 60)
        else:
            logger.info("=" * 60)
            logger.info("迁移旧数据（实际执行）")
            logger.warning("⚠️  这将实际移动文件，请确认！")
            logger.info("=" * 60)
        
        if not dry_run:
            confirm = input("确认继续迁移？(yes/no): ")
            if confirm.lower() != 'yes':
                logger.info("已取消迁移")
                return 0
        
        result = migrator.migrate_all(dry_run=dry_run)
        
        logger.info(f"\n迁移完成:")
        logger.info(f"  总文件数: {result['total']}")
        logger.info(f"  成功迁移: {result['migrated']}")
        logger.info(f"  失败: {result['failed']}")
        
        if result['failed_files']:
            logger.info(f"\n失败的文件:")
            for file_key in result['failed_files']:
                logger.error(f"  - {file_key}")
    
    else:
        parser.print_help()
    
    return 0


if __name__ == '__main__':
    sys.exit(main())
