# 对象存储管理方案 - 总结

## 方案概述

基于您的实际情况（runninghub 生成结果不使用对象存储，tasks 表只记录 URL），设计了一个**向后兼容、轻量级、易管理**的对象存储方案。

## 核心问题解答

### 1. 对象存储会知道 URL 过期时间吗？

**答**: 不会。

- 签名 URL 的过期时间只在 URL 参数中，对象存储本身不追踪
- 一个对象可以有多个不同有效期的签名 URL
- URL 过期后访问返回 403，但对象仍然存在

### 2. URL 过期能自动删除数据吗？

**答**: 不能直接实现，但可以通过**对象元数据 + 定期清理**实现类似效果。

## 实际架构

### 文件存储场景

| 场景 | 存储位置 | 管理方式 |
|-----|---------|---------|
| 用户头像 | 对象存储 | 永久存储（avatars/） |
| 用户上传 | 对象存储 | 7天后自动清理（uploads/） |
| 任务生成结果 | runninghub | URL 由 runninghub 管理 |
| 临时文件 | 对象存储 | 1天后自动清理（temp/） |

### 目录结构

```
bucket/
├── avatars/          # 用户头像（10年，永久）
├── uploads/          # 用户上传（7天）
├── temp/             # 临时文件（1天）
└── [旧文件]          # 向后兼容，仍可访问
```

## 核心特性

### 1. 自动分类管理

```python
from src.storage.storage_manager import get_storage_manager, StorageCategory

storage_mgr = get_storage_manager()

# 上传头像（永久）
avatar = storage_mgr.upload_with_category(
    file_content=b"avatar_data",
    file_name="avatar.png",
    category=StorageCategory.AVATAR,
    acl='public-read'
)

# 上传用户文件（7天）
upload = storage_mgr.upload_with_category(
    file_content=b"upload_data",
    file_name="upload.png",
    category=StorageCategory.UPLOAD
)

# 上传临时文件（1天）
temp = storage_mgr.upload_with_category(
    file_content=b"temp_data",
    file_name="temp.bin",
    category=StorageCategory.TEMP
)
```

### 2. 元数据标记

每个文件包含：
- `category`: 分类
- `created_at`: 创建时间
- `expires_in`: 过期时间（秒）
- `is_permanent`: 是否永久

### 3. 过期检查与清理

```python
# 检查文件是否过期
is_expired = storage_mgr.is_expired(file_key)

# 清理过期文件（试运行）
result = storage_mgr.cleanup_expired_files(dry_run=True)

# 实际删除
result = storage_mgr.cleanup_expired_files(dry_run=False)
```

## 向后兼容性

### 旧数据处理

| 项目 | 兼容方式 |
|-----|---------|
| 旧文件（无分类前缀） | 仍然可访问，不影响新功能 |
| 旧 API | 接口保持不变，内部升级 |
| 数据库 URL | runninghub URL 不受影响 |

### 渐进式迁移

- ✅ 新上传的文件自动使用新方案
- ✅ 旧文件继续正常工作
- ✅ 可选择性地迁移旧文件（如需要）

## 使用方式

### 方式一：自动使用（推荐）

现有节点已自动集成：

```python
# 文件上传节点 - 自动归类为 upload
def upload_node(state, config, runtime):
    # 自动使用 StorageCategory.UPLOAD
    # 返回 URL 和过期时间

# 用户更新节点 - 自动归类为 avatar
def update_user_node(state, config, runtime):
    # 自动使用 StorageCategory.AVATAR
    # 使用 public-read ACL
```

### 方式二：直接使用存储管理器

```python
from src.storage.storage_manager import get_storage_manager, StorageCategory

storage_mgr = get_storage_manager()

result = storage_mgr.upload_with_category(
    file_content=b"content",
    file_name="example.png",
    category=StorageCategory.UPLOAD,
    content_type="image/png"
)

print(f"URL: {result['url']}")
print(f"过期时间: {result['expires_at']}")
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
# 所有文件
python scripts/cleanup_storage.py --list

# 特定分类
python scripts/cleanup_storage.py --list --category upload

# 详细模式
python scripts/cleanup_storage.py --list --verbose
```

### 定时清理（可选）

```bash
# 每天试运行
0 2 * * * cd /app && python scripts/cleanup_storage.py --cleanup --dry-run

# 每周实际清理
0 3 * * 0 cd /app && python scripts/cleanup_storage.py --cleanup --force
```

## API 响应示例

### 上传响应

```json
{
  "success": true,
  "message": "文件上传成功",
  "public_url": "https://storage.example.com/uploads/upload_abc123.png?X-Amz-...",
  "file_key": "uploads/upload_abc123.png",
  "category": "upload",
  "expires_at": 1771304400,
  "is_permanent": false
}
```

## 优势

### 1. 轻量级实现

- 无需修改存储服务配置
- 无需复杂的定时任务
- 代码量小，易于维护

### 2. 向后兼容

- 旧数据不受影响
- API 保持不变
- 渐进式迁移

### 3. 灵活管理

- 按分类管理文件
- 自定义过期时间
- 便于批量操作

### 4. 成本控制

- 自动清理临时文件
- 减少无效文件占用
- 优化存储成本

## 测试

运行测试脚本：

```bash
python scripts/test_storage_manager.py
```

测试内容：
- 上传不同分类的文件
- 获取文件元数据
- 检查文件是否过期
- 重新生成 URL
- 试运行清理

## 文件清单

| 文件 | 说明 |
|-----|------|
| `src/storage/storage_manager.py` | 存储管理器核心实现 |
| `src/graphs/node.py` | 集成存储管理器的节点函数 |
| `scripts/cleanup_storage.py` | 清理工具 |
| `scripts/test_storage_manager.py` | 测试脚本 |
| `docs/STORAGE_GUIDE.md` | 详细使用文档 |

## 常见问题

### Q: 旧文件会被清理吗？

**A**: 不会。清理工具只处理有元数据的文件。旧文件无元数据，不会受影响。

### Q: 如何查看当前存储的文件？

**A**: 使用清理工具的列表功能：

```bash
python scripts/cleanup_storage.py --list --verbose
```

### Q: 清理工具会误删文件吗？

**A**: 不会。清理工具只删除满足以下条件的文件：
- 有 `created_at` 和 `expires_in` 元数据
- 当前时间超过创建时间 + 过期时间
- 不是永久文件（`is_permanent = False`）

建议清理前先试运行，检查将要删除的文件列表。

### Q: 如何永久保留某个文件？

**A**: 上传时使用 `StorageCategory.AVATAR` 分类：

```python
result = storage_mgr.upload_with_category(
    file_content=b"content",
    file_name="permanent.png",
    category=StorageCategory.AVATAR,  # 永久分类
    acl='public-read'
)
```

### Q: runninghub 生成的结果会被清理吗？

**A**: 不会。runninghub 生成的结果不存储在对象存储中，tasks 表只记录 URL，不受清理工具影响。

## 总结

这个方案：

✅ **解决了核心问题**：提供分类管理和过期清理功能
✅ **向后兼容**：不影响现有数据和接口
✅ **轻量级实现**：无需复杂配置，易于维护
✅ **灵活可控**：支持手动清理和自动化
✅ **成本优化**：自动清理临时文件，降低存储成本

适用于您当前的架构，推荐使用！
