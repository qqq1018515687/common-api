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

| 项目 | 当前状态 | 处理方式 |
|-----|---------|---------|
| **旧文件位置** | `avatar_abc123.png`（无分类前缀） | 继续正常工作，不影响访问 |
| **旧文件元数据** | ❌ 无元数据（无法判断创建时间、过期时间） | 清理工具会跳过 |
| **是否自动分类** | ❌ 不会 | 需要手动迁移 |
| **是否自动删除** | ❌ 不会 | 需要手动清理 |

**重要说明**：

1. **旧数据不会按照新的文件分类**
   - 旧数据：`avatar_abc123.png`（无分类前缀）
   - 新数据：`uploads/avatar_abc123.png`（有分类前缀）
   - 旧数据继续使用，不受新方案影响

2. **旧数据无法自动区分删除**
   - 旧数据没有元数据
   - 清理工具无法判断哪些旧数据应该删除
   - 清理工具会**跳过**所有无元数据的文件

### 旧数据迁移（可选）

如果需要将旧数据迁移到新方案，使用迁移工具：

```bash
# 1. 先分析旧数据
python scripts/migrate_old_data.py --analyze

# 2. 试运行迁移（不实际执行）
python scripts/migrate_old_data.py --migrate

# 3. 确认无误后，实际迁移
python scripts/migrate_old_data.py --migrate --force
```

### 旧数据清理（推荐）

如果不需要迁移，只想清理旧数据中的非头像文件，使用安全清理工具：

```bash
# 1. 分析旧数据
python scripts/clean_old_data.py --analyze

# 2. 试运行清理
python scripts/clean_old_data.py --cleanup

# 3. 确认后执行
python scripts/clean_old_data.py --cleanup --force
```

**清理规则**：
- ✅ 保留：文件名包含 `avatar` 的旧头像
- ❌ 删除：其他旧文件（上传、临时等）
- ✅ 不受影响：已有分类前缀的新文件

详细指南：`docs/CLEAN_OLD_DATA_GUIDE.md`

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

### Q1: 旧数据会按照新的文件分类吗？

**A**: 不会。旧数据是迁移前上传的文件，没有分类前缀（如 `avatar_abc123.png`）。新上传的文件才会使用分类前缀（如 `uploads/avatar_abc123.png`）。旧数据继续正常工作，不受新方案影响。

### Q2: 旧数据现在无法区分删除是吗？

**A**: 是的。旧数据没有元数据（created_at、expires_in、category），清理工具无法判断：
- 创建时间
- 过期时间
- 文件类型

因此，清理工具会**跳过所有无元数据的文件**，不会自动删除旧数据。

### Q3: 如何处理旧数据？

**A**: 有三种选择：

1. **保持不变**（推荐）：旧数据继续正常工作，不影响新功能
2. **手动迁移**：使用迁移工具将旧数据迁移到新方案
   ```bash
   # 分析旧数据
   python scripts/migrate_old_data.py --analyze
   
   # 试运行迁移
   python scripts/migrate_old_data.py --migrate
   
   # 实际迁移
   python scripts/migrate_old_data.py --migrate --force
   ```
3. **手动清理**：通过对象存储控制台手动删除不需要的旧文件

### Q4: 迁移旧数据有什么风险？

**A**:
- **数据丢失风险**：迁移过程中如果出错，可能导致数据丢失
- **访问中断**：迁移期间文件可能暂时无法访问
- **不可逆**：一旦迁移完成，无法回滚

**建议**：
- 先试运行，确认将要迁移的文件列表
- 在低峰期执行迁移
- 确保有数据备份

### Q5: 旧数据会影响新方案的效果吗？

**A**: 不会。旧数据和新数据完全独立：
- 旧数据：无分类前缀，无元数据，无法自动管理
- 新数据：有分类前缀，有元数据，可以自动清理

两者互不影响。

### Q6: 如何查看旧数据的数量？

**A**: 使用迁移工具的分析功能：
```bash
python scripts/migrate_old_data.py --analyze --verbose
```

输出示例：
```
总文件数: 150
头像 (avatar): 20
上传 (upload): 100
临时 (temp): 25
未知 (unknown): 5
```

### Q7: URL 过期后文件会被删除吗？

**A**: 不会。URL 过期只是无法通过该签名访问，文件仍然存在。需要使用清理工具手动删除过期文件。

### Q8: 如何区分永久文件和临时文件？

**A**: 查看文件元数据中的 `is_permanent` 字段：
- `True`: 永久文件（avatar）
- `False`: 临时文件（upload/temp）

对于旧数据，无法通过元数据区分，只能通过文件名前缀判断（如 `avatar_` 表示头像）。

### Q9: 可以修改文件的过期时间吗？

**A**: 当前版本不支持直接修改过期时间。如需延长有效期，可以：
1. 重新上传文件
2. 使用 `regenerate_url` 生成新的访问 URL

对于旧数据，无法修改过期时间，因为没有元数据记录。

### Q10: 清理工具会删除哪些文件？

**A**: 只删除满足以下条件的文件：
- 有 `created_at` 和 `expires_in` 元数据
- 当前时间超过创建时间 + 过期时间
- 不是永久文件（`is_permanent = False`）

**旧数据不会被删除**，因为没有元数据。

### Q11: 如何恢复误删除的文件？

**A**: 对象存储通常不支持恢复已删除的文件。建议：
1. 清理前先试运行，检查将要删除的文件列表
2. 重要文件（如头像）使用 `avatar` 分类，不会自动删除
3. 定期备份重要数据

### Q12: runninghub 生成的结果会被清理吗？

**A**: 不会。runninghub 生成的结果不存储在对象存储中，tasks 表只记录 URL，不受清理工具影响。

## 总结

这个方案：

✅ **解决了核心问题**：提供分类管理和过期清理功能
✅ **向后兼容**：不影响现有数据和接口
✅ **轻量级实现**：无需复杂配置，易于维护
✅ **灵活可控**：支持手动清理和自动化
✅ **成本优化**：自动清理临时文件，降低存储成本

适用于您当前的架构，推荐使用！
