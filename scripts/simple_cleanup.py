#!/usr/bin/env python3
"""
简化清理工具 - 不检查文件大小，直接删除
"""
import os
import sys
import re
import logging
from pathlib import Path

# 添加项目根目录到 Python 路径
project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if project_root not in sys.path:
    sys.path.insert(0, project_root)

from src.storage.s3.s3_storage import S3SyncStorage

# 配置日志
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


class SimpleOldDataCleaner:
    """简化的旧数据清理器 - 不检查文件大小"""

    # 旧数据前缀
    OLD_DATA_PREFIX = "coze_storage_7592868590546845742/"

    def __init__(self, storage: S3SyncStorage):
        self.storage = storage

    def is_old_data_file(self, file_key: str) -> bool:
        """判断是否是旧数据文件"""
        return file_key.startswith(self.OLD_DATA_PREFIX) and file_key != self.OLD_DATA_PREFIX

    def is_avatar_file(self, file_key: str) -> bool:
        """判断是否是头像文件"""
        # 提取文件名（去掉路径）
        filename = file_key.split("/")[-1]
        # 检查是否包含 avatar
        return "avatar" in filename.lower()

    def identify_old_files(self) -> dict:
        """识别旧文件并分类"""
        result = {
            'avatar_files': [],
            'other_files': [],
            'total_count': 0
        }

        logger.info(f"正在扫描旧数据文件...")

        try:
            # 列出所有文件
            list_result = self.storage.list_files()

            for file_key in list_result['keys']:
                # 只处理旧数据文件
                if not self.is_old_data_file(file_key):
                    continue

                result['total_count'] += 1

                if self.is_avatar_file(file_key):
                    result['avatar_files'].append(file_key)
                    logger.info(f"  [头像] {file_key}")
                else:
                    result['other_files'].append(file_key)
                    logger.info(f"  [其他] {file_key}")

        except Exception as e:
            logger.error(f"扫描文件失败: {e}")
            raise e

        return result

    def cleanup(self, dry_run: bool = True) -> dict:
        """清理旧数据"""
        result = {
            'avatar_kept': 0,
            'others_deleted': 0,
            'failed': 0,
            'deleted_files': [],
            'failed_files': []
        }

        logger.info("=" * 60)
        logger.info(f"清理旧数据（{'试运行模式' if dry_run else '实际执行'}）")
        logger.info("=" * 60)

        # 识别旧文件
        files_info = self.identify_old_files()

        avatar_files = files_info['avatar_files']
        other_files = files_info['other_files']

        logger.info(f"\n扫描结果:")
        logger.info(f"  总文件数: {files_info['total_count']}")
        logger.info(f"  头像文件（保留）: {len(avatar_files)}")
        logger.info(f"  其他文件（删除）: {len(other_files)}")

        # 保留头像
        for file_key in avatar_files:
            logger.info(f"✅ 保留头像: {file_key}")
            result['avatar_kept'] += 1

        # 删除其他文件
        if other_files:
            logger.info(f"\n将要删除的文件 ({len(other_files)} 个):")
            for file_key in other_files:
                try:
                    if dry_run:
                        logger.info(f"  [试运行] 将删除: {file_key}")
                        result['others_deleted'] += 1
                    else:
                        # 直接删除，不检查文件大小
                        self.storage.delete_file(file_key=file_key)
                        logger.info(f"  ✅ 已删除: {file_key}")
                        result['others_deleted'] += 1

                except Exception as e:
                    result['failed'] += 1
                    result['failed_files'].append(file_key)
                    logger.error(f"  ❌ 删除失败: {file_key}, error: {e}")

        return result


def main():
    """主函数"""
    import argparse

    parser = argparse.ArgumentParser(
        description='简化清理工具 - 不检查文件大小，直接删除旧数据',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
示例:
  # 1. 扫描旧数据
  python scripts/simple_cleanup.py --analyze

  # 2. 试运行（不实际删除）
  python scripts/simple_cleanup.py --cleanup

  # 3. 确认后执行
  python scripts/simple_cleanup.py --cleanup --force
        """
    )

    parser.add_argument('--analyze', action='store_true', help='扫描旧数据')
    parser.add_argument('--cleanup', action='store_true', help='清理旧数据')
    parser.add_argument('--force', action='store_true', help='实际执行（需配合 --cleanup）')

    args = parser.parse_args()

    # 初始化存储
    storage = S3SyncStorage(
        endpoint_url=os.getenv("COZE_BUCKET_ENDPOINT_URL"),
        access_key=os.getenv("COZE_ACCESS_KEY", ""),
        secret_key=os.getenv("COZE_SECRET_KEY", ""),
        bucket_name=os.getenv("COZE_BUCKET_NAME"),
        region=os.getenv("COZE_BUCKET_REGION", "cn-beijing")
    )

    cleaner = SimpleOldDataCleaner(storage)

    if args.analyze:
        # 扫描模式
        logger.info("=" * 60)
        logger.info("扫描旧数据")
        logger.info("=" * 60)

        files_info = cleaner.identify_old_files()

        logger.info(f"\n统计结果:")
        logger.info(f"  总文件数: {files_info['total_count']}")
        logger.info(f"  头像文件: {len(files_info['avatar_files'])}")
        logger.info(f"  其他文件: {len(files_info['other_files'])}")

        logger.info(f"\n说明:")
        logger.info(f"  - 头像文件将被保留")
        logger.info(f"  - 其他文件将被删除")

    elif args.cleanup:
        # 清理模式
        dry_run = not args.force

        result = cleaner.cleanup(dry_run=dry_run)

        logger.info(f"\n" + "=" * 60)
        logger.info("清理结果")
        logger.info("=" * 60)
        logger.info(f"  头像文件（保留）: {result['avatar_kept']}")
        logger.info(f"  其他文件（删除）: {result['others_deleted']}")
        logger.info(f"  删除失败: {result['failed']}")

        if dry_run:
            logger.info(f"\n💡 提示: 这是试运行模式，没有实际删除文件")
            logger.info(f"   要实际执行，请使用: python scripts/simple_cleanup.py --cleanup --force")
        else:
            logger.info(f"\n✅ 清理完成!")

    else:
        parser.print_help()


if __name__ == "__main__":
    main()
