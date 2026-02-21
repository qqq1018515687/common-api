# 对象存储管理方案

## 概述

本方案提供了一个向后兼容的对象存储管理解决方案，支持文件分类、自动过期、清理等功能。

## 架构设计

### 文件分类

| 分类 | 目录前缀 | 保留时间 | 用途 | 访问控制 |
|-----|---------|---------|------|---------|
| `avatar` | `avatars/` | 10年 | 用户头像 | public-read |
| `upload` | `uploads/` | 7天 | 用户上传文件 | 私有 |
| `temp` | `temp/` | 1天 | 临时文件 | 私有 |

### 目录结构

```
bucket/
├── avatars/                   # 用户头像
│   ├── avatar_123_abc12345.png
│   └── avatar_456_def67890.jpg
├── uploads/                   # 用户上传
│   ├── upload_789_ghi01234.png
│   └── upload_012_jkl34567.pdf
└── temp/                      # 临时文件
    ├── temp_345_mno67890.bin
    └── temp_678_pqr90123.txt
```

## 核心特性

### 1. 自动分类存储

文件上传时根据用途自动分类：

```python
from storage.storage_manager import get_storage_manager, StorageCategory

storage_mgr = get_storage_manager()

# 上传头像（永久）
result = storage_mgr.upload_with_category(
    file_content=b"avatar_data",
    file_name="avatar.png",
    category=StorageCategory.AVATAR,
    content_type="image/png",
    acl='public-read'
)

# 上传用户上传文件（7天过期）
result = storage_mgr.upload_with_category(
    file_content=b"upload_data",
    file_name="upload.png",
    category=StorageCategory.UPLOAD,
    content_type="image/png"
)

# 上传临时文件（1天过期）
result = storage_mgr.upload_with_category(
    file_content=b"temp_data",
    file_name="temp.bin",
    category=StorageCategory.TEMP,
    content_type="application/octet-stream"
)
```

### 2. 元数据管理

每个文件都包含元数据：

```python
metadata = {
    'category': 'avatar',           # 分类
    'created_at': '1771218000',     # 创建时间（秒）
    'expires_in': '315360000',      # 过期时间（秒）
    'original_filename': 'avatar.png', # 原始文件名
    'is_permanent': 'True'         # 是否永久
}
```

### 3. 过期检查

```python
# 检查文件是否过期
is_expired = storage_mgr.is_expired(file_key="uploads/upload_789.png")

# 获取文件元数据
metadata = storage_mgr.get_file_metadata(file_key="uploads/upload_789.png")
```

### 4. 重新生成 URL

```python
# 为文件重新生成访问 URL
new_url = storage_mgr.regenerate_url(file_key="uploads/upload_789.png")
```

## 使用方式

### 方式一：通过节点自动使用（推荐）

现有的节点已自动使用存储管理器：

1. **文件上传节点** (`upload_node`)
   - 自动将用户上传文件归类为 `upload`
   - 返回 URL 和过期时间

2. **用户更新节点** (`update_user_node`)
   - 自动将头像归类为 `avatar`
   - 使用 `public-read` ACL

### 方式二：直接使用存储管理器

```python
from storage.storage_manager import get_storage_manager, StorageCategory

# 获取存储管理器实例
storage_mgr = get_storage_manager()

# 上传文件
result = storage_mgr.upload_with_category(
    file_content=b"file_content",
    file_name="example.png",
    category=StorageCategory.UPLOAD,
    content_type="image/png"
)

print(f"文件键: {result['file_key']}")
print(f"访问 URL: {result['url']}")
print(f"分类: {result['category']}")
print(f"过期时间: {result.get('expires_at')}")
print(f"是否永久: {result['is_permanent']}")
```

## 清理工具

### 试运行（推荐先执行）

```bash
python scripts/cleanup_storage.py --cleanup --dry-run
```

### 实际删除

```bash
python scripts/cleanup_storage.py --cleanup --force
```

### 列出文件

```bash
# 列出所有文件
python scripts/cleanup_storage.py --list

# 列出特定分类的文件
python scripts/cleanup_storage.py --list --category upload

# 详细模式
python scripts/cleanup_storage.py --list --verbose
```

### 输出示例

```
============================================================
清理统计
============================================================
扫描文件数: 150
过期文件数: 45
实际删除数: 45
失败文件数: 0
============================================================
清理完成
============================================================
```

## API 响应格式

### 上传响应

```json
{
  "success": true,
  "message": "文件上传成功",
  "public_url": "https://storage.example.com/uploads/upload_abc123.png?X-Amz-...",
  "file_key": "uploads/upload_abc123.png",
  "category": "upload",
  "expires_at": 1771304400
}
```

## 向后兼容性

### 旧数据兼容

- **旧文件**：没有分类前缀的文件仍然可以访问
- **旧 API**：现有接口保持不变
- **渐进迁移**：新上传的文件自动使用新方案，旧文件继续工作

### 数据库记录

Tasks 表中的 URL 记录不受影响：
- runninghub 生成的结果：继续记录 runninghub URL
- 对象存储的文件：记录新的签名 URL

## 定期维护建议

### 推荐清理策略

1. **每日试运行**：检查是否有大量过期文件
   ```bash
   python scripts/cleanup_storage.py --cleanup --dry-run
   ```

2. **每周实际清理**：删除过期文件
   ```bash
   python scripts/cleanup_storage.py --cleanup --force
   ```

3. **每月检查**：查看存储空间使用情况
   ```bash
   python scripts/cleanup_storage.py --list --verbose
   ```

### 定时任务配置（可选）

如果需要自动化清理，可以使用 crontab：

```bash
# 每天凌晨 2 点试运行
0 2 * * * cd /app && python scripts/cleanup_storage.py --cleanup --dry-run >> /var/log/storage_cleanup.log 2>&1

# 每周日凌晨 3 点实际清理
0 3 * * 0 cd /app && python scripts/cleanup_storage.py --cleanup --force >> /var/log/storage_cleanup.log 2>&1
```

## 常见问题

### Q1: URL 过期后文件会被删除吗？

**A**: 不会。URL 过期只是无法通过该签名访问，文件仍然存在。需要使用清理工具手动删除过期文件。

### Q2: 如何区分永久文件和临时文件？

**A**: 查看文件元数据中的 `is_permanent` 字段：
- `True`: 永久文件（avatar）
- `False`: 临时文件（upload/temp）

### Q3: 可以修改文件的过期时间吗？

**A**: 当前版本不支持直接修改过期时间。如需延长有效期，可以：
1. 重新上传文件
2. 使用 `regenerate_url` 生成新的访问 URL

### Q4: 清理工具会删除哪些文件？

**A**: 只删除满足以下条件的文件：
- 有 `created_at` 和 `expires_in` 元数据
- 当前时间超过创建时间 + 过期时间
- 不是永久文件（`is_permanent = False`）

### Q5: 如何恢复误删除的文件？

**A**: 对象存储通常不支持恢复已删除的文件。建议：
1. 清理前先试运行，检查将要删除的文件列表
2. 重要文件（如头像）使用 `avatar` 分类，不会自动删除
3. 定期备份重要数据

## 未来改进方向

1. **生命周期规则**：如果存储服务支持，配置自动过期策略
2. **批量操作**：支持批量上传和删除
3. **监控告警**：监控存储空间使用情况，超过阈值自动告警
4. **访问统计**：记录文件的访问频率，优化清理策略

## 技术支持

如有问题，请查看：
- 代码：`src/storage/storage_manager.py`
- 清理工具：`scripts/cleanup_storage.py`
- 示例代码：`src/graphs/node.py`
