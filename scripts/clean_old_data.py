#!/usr/bin/env python3
"""
安全清理旧数据工具
只保留头像，删除其他旧数据
"""
import os
import sys
import re
import logging
from pathlib import Path

sys.path.insert(0, '/app')

from src.storage.s3.s3_storage import S3SyncStorage

# 配置日志
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


class SafeOldDataCleaner:
    """安全的旧数据清理器"""
    
    def __init__(self, storage: S3SyncStorage):
        self.storage = storage
    
    def identify_avatar_files(self, file_key: str) -> bool:
        """
        识别是否为头像文件
        
        Args:
            file_key: 文件键
        
        Returns:
            是否为头像
        """
        # 排除已有分类前缀的文件（这些是新数据）
        if file_key.startswith(('avatars/', 'uploads/', 'temp/')):
            return False
        
        # 根据文件名前缀判断
        # 头像通常以 avatar_ 开头
        if file_key.startswith('avatar_'):
            return True
        
        # 用户头像也可能包含 user_id 相关的命名模式
        # 例如：user_123_avatar.png
        if 'avatar' in file_key.lower():
            return True
        
        # 默认不是头像
        return False
    
    def list_old_files(self) -> list:
        """列出所有旧数据文件（无分类前缀）"""
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
            
            # 过滤掉已有分类前缀的文件（只保留旧数据）
            old_files = [f for f in all_files if not self.has_category_prefix(f)]
            
            return old_files
        
        except Exception as e:
            logger.error(f"列出文件失败: {e}")
            return []
    
    def has_category_prefix(self, file_key: str) -> bool:
        """检查是否有分类前缀"""
        return file_key.startswith(('avatars/', 'uploads/', 'temp/'))
    
    def analyze_old_files(self) -> dict:
        """
        分析旧数据
        
        Returns:
            分析结果
        """
        old_files = self.list_old_files()
        
        analysis = {
            'total': len(old_files),
            'avatars': [],
            'others': [],
            'total_size': 0,
            'avatars_size': 0,
            'others_size': 0
        }
        
        for file_key in old_files:
            is_avatar = self.identify_avatar_files(file_key)
            
            try:
                # 获取文件大小
                client = self.storage._get_client()
                head_resp = client.head_object(
                    Bucket=self.storage._resolve_bucket(None),
                    Key=file_key
                )
                file_size = head_resp.get('ContentLength', 0)
                
                if is_avatar:
                    analysis['avatars'].append({
                        'file_key': file_key,
                        'size': file_size
                    })
                    analysis['avatars_size'] += file_size
                else:
                    analysis['others'].append({
                        'file_key': file_key,
                        'size': file_size
                    })
                    analysis['others_size'] += file_size
                
                analysis['total_size'] += file_size
            
            except Exception as e:
                logger.error(f"获取文件信息失败: {file_key}, error: {e}")
        
        return analysis
    
    def delete_non_avatar_files(self, dry_run: bool = True) -> dict:
        """
        删除非头像的旧文件
        
        Args:
            dry_run: 是否为试运行
        
        Returns:
            删除结果
        """
        old_files = self.list_old_files()
        
        result = {
            'total': len(old_files),
            'avatars_kept': 0,
            'others_deleted': 0,
            'deleted_files': [],
            'failed': 0,
            'failed_files': [],
            'total_size_freed': 0
        }
        
        for file_key in old_files:
            is_avatar = self.identify_avatar_files(file_key)
            
            if is_avatar:
                # 保留头像
                result['avatars_kept'] += 1
                logger.info(f"保留头像: {file_key}")
            else:
                # 删除其他文件
                try:
                    if not dry_run:
                        # 获取文件大小
                        client = self.storage._get_client()
                        head_resp = client.head_object(
                            Bucket=self.storage._resolve_bucket(None),
                            Key=file_key
                        )
                        file_size = head_resp.get('ContentLength', 0)
                        
                        # 删除文件
                        self.storage.delete_file(file_key=file_key)
                        result['total_size_freed'] += file_size
                        result['deleted_files'].append(file_key)
                        logger.info(f"已删除: {file_key} ({self.format_size(file_size)})")
                    else:
                        result['deleted_files'].append(file_key)
                        logger.info(f"[试运行] 将删除: {file_key}")
                    
                    result['others_deleted'] += 1
                
                except Exception as e:
                    result['failed'] += 1
                    result['failed_files'].append(file_key)
                    logger.error(f"删除失败: {file_key}, error: {e}")
        
        return result
    
    @staticmethod
    def format_size(size_bytes: int) -> str:
        """格式化文件大小"""
        for unit in ['B', 'KB', 'MB', 'GB']:
            if size_bytes < 1024:
                return f"{size_bytes:.2f} {unit}"
            size_bytes /= 1024
        return f"{size_bytes:.2f} TB"


def main():
    """主函数"""
    import argparse
    
    parser = argparse.ArgumentParser(
        description='安全清理旧数据工具 - 只保留头像，删除其他旧数据',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
示例:
  # 1. 先分析旧数据（推荐先执行）
  python scripts/clean_old_data.py --analyze
  
  # 2. 试运行（不实际删除）
  python scripts/clean_old_data.py --cleanup
  
  # 3. 确认无误后，实际删除
  python scripts/clean_old_data.py --cleanup --force
  
  # 4. 详细模式
  python scripts/clean_old_data.py --analyze --verbose
        """
    )
    
    parser.add_argument('--analyze', action='store_true', help='分析旧数据')
    parser.add_argument('--cleanup', action='store_true', help='清理旧数据（只保留头像）')
    parser.add_argument('--force', action='store_true', help='实际执行清理（需配合 --cleanup）')
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
    
    cleaner = SafeOldDataCleaner(storage)
    
    if args.analyze:
        # 分析旧数据
        logger.info("=" * 60)
        logger.info("分析旧数据")
        logger.info("=" * 60)
        
        analysis = cleaner.analyze_old_files()
        
        logger.info(f"\n总旧文件数: {analysis['total']}")
        logger.info(f"头像文件: {len(analysis['avatars'])} ({cleaner.format_size(analysis['avatars_size'])})")
        logger.info(f"其他文件: {len(analysis['others'])} ({cleaner.format_size(analysis['others_size'])})")
        logger.info(f"总大小: {cleaner.format_size(analysis['total_size'])}")
        
        if args.verbose and analysis['avatars']:
            logger.info("\n头像文件列表:")
            for avatar in analysis['avatars']:
                logger.info(f"  ✓ {avatar['file_key']} ({cleaner.format_size(avatar['size'])})")
        
        if args.verbose and analysis['others']:
            logger.info("\n其他文件列表（将被删除）:")
            for other in analysis['others']:
                logger.info(f"  ✗ {other['file_key']} ({cleaner.format_size(other['size'])})")
        
        logger.info("\n" + "=" * 60)
        logger.info("说明:")
        logger.info("  - 头像文件（以 avatar_ 开头）将被保留")
        logger.info("  - 其他旧文件将被删除")
        logger.info("  - 已有分类前缀的文件不受影响")
        logger.info("=" * 60)
    
    elif args.cleanup:
        # 清理旧数据
        dry_run = not args.force
        
        if dry_run:
            logger.info("=" * 60)
            logger.info("清理旧数据（试运行模式）")
            logger.info("  只保留头像，删除其他旧文件")
            logger.info("=" * 60)
        else:
            logger.info("=" * 60)
            logger.info("清理旧数据（实际执行）")
            logger.warning("⚠️  这将永久删除非头像的旧文件！")
            logger.info("=" * 60)
        
        # 先分析
        analysis = cleaner.analyze_old_files()
        logger.info(f"\n将要处理的文件:")
        logger.info(f"  头像文件（保留）: {len(analysis['avatars'])}")
        logger.info(f"  其他文件（删除）: {len(analysis['others'])} ({cleaner.format_size(analysis['others_size'])})")
        
        if not dry_run:
            logger.warning("\n⚠️  即将删除 {} 个文件，释放 {} 空间！".format(
                len(analysis['others']),
                cleaner.format_size(analysis['others_size'])
            ))
            confirm = input("\n确认继续清理？(yes/no): ")
            if confirm.lower() != 'yes':
                logger.info("已取消清理")
                return 0
        
        # 执行清理
        result = cleaner.delete_non_avatar_files(dry_run=dry_run)
        
        logger.info("\n" + "=" * 60)
        logger.info("清理结果:")
        logger.info("=" * 60)
        logger.info(f"  头像文件（保留）: {result['avatars_kept']}")
        logger.info(f"  其他文件（删除）: {result['others_deleted']}")
        logger.info(f"  失败: {result['failed']}")
        
        if not dry_run:
            logger.info(f"  释放空间: {cleaner.format_size(result['total_size_freed'])}")
        
        if result['failed_files']:
            logger.info("\n删除失败的文件:")
            for file_key in result['failed_files']:
                logger.error(f"  - {file_key}")
        
        logger.info("=" * 60)
    
    else:
        parser.print_help()
    
    return 0


if __name__ == '__main__':
    sys.exit(main())
