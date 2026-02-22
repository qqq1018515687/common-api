#!/usr/bin/env python3
"""
对象存储清理工具
用于清理过期的文件
"""
import os
import sys
import argparse
import logging
from pathlib import Path

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


def cleanup_storage(dry_run: bool = False, verbose: bool = False):
    """
    清理过期的文件
    
    Args:
        dry_run: 是否为试运行（不实际删除）
        verbose: 是否显示详细信息
    """
    try:
        storage_mgr = get_storage_manager()
        
        if dry_run:
            logger.info("=" * 60)
            logger.info("开始清理（试运行模式，不会实际删除文件）")
            logger.info("=" * 60)
        else:
            logger.info("=" * 60)
            logger.info("开始清理（实际删除模式）")
            logger.info("=" * 60)
        
        # 执行清理
        result = storage_mgr.cleanup_expired_files(dry_run=dry_run)
        
        # 输出结果
        logger.info("\n" + "=" * 60)
        logger.info("清理统计")
        logger.info("=" * 60)
        logger.info(f"扫描文件数: {result['scanned']}")
        logger.info(f"过期文件数: {result['expired']}")
        logger.info(f"实际删除数: {result['deleted']}")
        logger.info(f"失败文件数: {result['failed']}")
        
        if result['errors'] and verbose:
            logger.info("\n" + "=" * 60)
            logger.info("错误详情")
            logger.info("=" * 60)
            for error in result['errors']:
                logger.error(f"{error}")
        
        logger.info("=" * 60)
        logger.info("清理完成")
        logger.info("=" * 60)
        
        return 0
        
    except Exception as e:
        logger.error(f"清理失败: {e}", exc_info=True)
        return 1


def list_files(category: str = None, verbose: bool = False):
    """
    列出存储中的文件
    
    Args:
        category: 文件分类（avatar/upload/temp）
        verbose: 是否显示详细信息
    """
    try:
        storage_mgr = get_storage_manager()
        
        from storage.storage_manager import StorageCategory
        
        # 确定前缀
        if category:
            if category not in ['avatar', 'upload', 'temp']:
                logger.error(f"不支持的分类: {category}")
                return 1
            prefix = StorageCategory.get_prefix(category) + '/'
        else:
            prefix = None
        
        logger.info(f"列出文件: {prefix or '全部'}")
        logger.info("=" * 60)
        
        # 列出文件
        files = storage_mgr.storage.list_files(prefix=prefix, max_keys=1000)
        
        total = len(files.get('keys', []))
        expired_count = 0
        
        for file_key in files.get('keys', []):
            try:
                is_expired = storage_mgr.is_expired(file_key)
                status = "[已过期]" if is_expired else "[正常]"
                
                if verbose:
                    metadata = storage_mgr.get_file_metadata(file_key)
                    logger.info(f"{status} {file_key}")
                    if metadata:
                        logger.info(f"  - 分类: {metadata.get('category')}")
                        logger.info(f"  - 创建时间: {metadata.get('created_at')}")
                        logger.info(f"  - 过期时间: {metadata.get('expires_in')}秒")
                        logger.info(f"  - 原始文件名: {metadata.get('original_filename')}")
                else:
                    logger.info(f"{status} {file_key}")
                
                if is_expired:
                    expired_count += 1
            
            except Exception as e:
                logger.error(f"检查文件失败: {file_key}, error: {e}")
        
        logger.info("=" * 60)
        logger.info(f"总计: {total} 个文件")
        logger.info(f"过期: {expired_count} 个文件")
        logger.info("=" * 60)
        
        return 0
        
    except Exception as e:
        logger.error(f"列出文件失败: {e}", exc_info=True)
        return 1


def main():
    """主函数"""
    parser = argparse.ArgumentParser(
        description='对象存储清理工具',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
示例:
  # 试运行（不实际删除）
  python scripts/cleanup_storage.py --dry-run
  
  # 实际删除过期文件
  python scripts/cleanup_storage.py --cleanup
  
  # 列出所有文件
  python scripts/cleanup_storage.py --list
  
  # 列出特定分类的文件
  python scripts/cleanup_storage.py --list --category upload
  
  # 详细模式
  python scripts/cleanup_storage.py --cleanup --verbose
        """
    )
    
    parser.add_argument(
        '--cleanup',
        action='store_true',
        help='清理过期文件（默认为试运行，添加 --force 实际删除）'
    )
    
    parser.add_argument(
        '--force',
        action='store_true',
        help='实际删除文件（需配合 --cleanup 使用）'
    )
    
    parser.add_argument(
        '--list',
        action='store_true',
        help='列出存储中的文件'
    )
    
    parser.add_argument(
        '--category',
        choices=['avatar', 'upload', 'temp'],
        help='指定文件分类（仅用于 --list）'
    )
    
    parser.add_argument(
        '--verbose', '-v',
        action='store_true',
        help='详细输出'
    )
    
    args = parser.parse_args()
    
    # 执行操作
    if args.cleanup:
        dry_run = not args.force
        return cleanup_storage(dry_run=dry_run, verbose=args.verbose)
    elif args.list:
        return list_files(category=args.category, verbose=args.verbose)
    else:
        # 默认行为：试运行
        parser.print_help()
        return 0


if __name__ == '__main__':
    sys.exit(main())
