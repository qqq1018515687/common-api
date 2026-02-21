#!/usr/bin/env python3
"""
存储管理器测试脚本
"""
import os
import sys

# 添加项目路径
sys.path.insert(0, '/app')

from src.storage.storage_manager import get_storage_manager, StorageCategory


def test_upload_and_cleanup():
    """测试上传和清理功能"""
    print("=" * 60)
    print("测试存储管理器")
    print("=" * 60)
    
    # 获取存储管理器
    storage_mgr = get_storage_manager()
    
    # 测试 1: 上传临时文件
    print("\n1. 上传临时文件（temp 分类，1天过期）")
    temp_content = b"This is a temporary file for testing."
    temp_result = storage_mgr.upload_with_category(
        file_content=temp_content,
        file_name="temp_test.txt",
        category=StorageCategory.TEMP,
        content_type="text/plain"
    )
    print(f"   文件键: {temp_result['file_key']}")
    print(f"   URL: {temp_result['url']}")
    print(f"   分类: {temp_result['category']}")
    print(f"   过期时间: {temp_result.get('expires_at')}")
    print(f"   是否永久: {temp_result['is_permanent']}")
    
    # 测试 2: 上传用户上传文件
    print("\n2. 上传用户上传文件（upload 分类，7天过期）")
    upload_content = b"This is a user uploaded file."
    upload_result = storage_mgr.upload_with_category(
        file_content=upload_content,
        file_name="upload_test.txt",
        category=StorageCategory.UPLOAD,
        content_type="text/plain"
    )
    print(f"   文件键: {upload_result['file_key']}")
    print(f"   URL: {upload_result['url']}")
    print(f"   分类: {upload_result['category']}")
    print(f"   过期时间: {upload_result.get('expires_at')}")
    print(f"   是否永久: {upload_result['is_permanent']}")
    
    # 测试 3: 上传头像
    print("\n3. 上传头像（avatar 分类，10年过期）")
    avatar_content = b"This is an avatar image (simulated)."
    avatar_result = storage_mgr.upload_with_category(
        file_content=avatar_content,
        file_name="avatar_test.png",
        category=StorageCategory.AVATAR,
        content_type="image/png",
        acl='public-read'
    )
    print(f"   文件键: {avatar_result['file_key']}")
    print(f"   URL: {avatar_result['url']}")
    print(f"   分类: {avatar_result['category']}")
    print(f"   过期时间: {avatar_result.get('expires_at')}")
    print(f"   是否永久: {avatar_result['is_permanent']}")
    
    # 测试 4: 获取文件元数据
    print("\n4. 获取文件元数据")
    metadata = storage_mgr.get_file_metadata(temp_result['file_key'])
    if metadata:
        print(f"   分类: {metadata.get('category')}")
        print(f"   创建时间: {metadata.get('created_at')}")
        print(f"   过期时间: {metadata.get('expires_in')} 秒")
        print(f"   原始文件名: {metadata.get('original_filename')}")
        print(f"   是否永久: {metadata.get('is_permanent')}")
    
    # 测试 5: 检查文件是否过期
    print("\n5. 检查文件是否过期")
    is_expired = storage_mgr.is_expired(temp_result['file_key'])
    print(f"   临时文件是否过期: {is_expired}")
    
    # 测试 6: 重新生成 URL
    print("\n6. 重新生成 URL")
    new_url = storage_mgr.regenerate_url(temp_result['file_key'])
    print(f"   新 URL: {new_url}")
    
    # 测试 7: 试运行清理
    print("\n7. 试运行清理（dry_run=True）")
    cleanup_result = storage_mgr.cleanup_expired_files(dry_run=True)
    print(f"   扫描文件数: {cleanup_result['scanned']}")
    print(f"   过期文件数: {cleanup_result['expired']}")
    print(f"   实际删除数: {cleanup_result['deleted']}")
    print(f"   失败文件数: {cleanup_result['failed']}")
    
    print("\n" + "=" * 60)
    print("测试完成")
    print("=" * 60)
    
    # 返回上传的文件键，方便后续清理测试
    return {
        'temp': temp_result['file_key'],
        'upload': upload_result['file_key'],
        'avatar': avatar_result['file_key']
    }


if __name__ == '__main__':
    try:
        test_upload_and_cleanup()
        print("\n✓ 所有测试通过")
        sys.exit(0)
    except Exception as e:
        print(f"\n✗ 测试失败: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
