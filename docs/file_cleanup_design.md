# 文件清理方案设计

## 一、当前文件使用情况分析

### 1.1 文件来源分类

| 来源 | 节点 | 文件命名 | URL有效期 | 当前清理状态 |
|------|------|---------|----------|------------|
| **临时上传** | upload_node | `image.png`, `image.jpg` 等 | 24小时 (86400秒) | ❌ 不清理 |
| **持久保存** | save_node | 随机UUID命名 | 10年 (315360000秒) | ❌ 不清理 |
| **用户头像** | update_user_node | `avatar_xxxx.png` | 永久 | ❌ 不清理 |
| **任务文件** | 各生成节点 | 随机UUID命名 | 永久 | ❌ 不清理 |

### 1.2 文件存储位置

- **数据库记录**：
  - `Users.avatar` - 存储用户头像URL
  - `Tasks.result` - 存储任务生成的文件URL（image_url, video_url, audio_url等）
  - 没有专门的文件表

- **对象存储**：
  - 所有文件直接存储在S3兼容对象存储中
  - 没有文件元数据表
  - 无法通过数据库直接查询文件信息

### 1.3 存在的问题

1. **临时文件堆积**：24小时URL过期后，文件仍然存在
2. **孤立文件**：用户删除头像/任务后，文件没有被删除
3. **无法追踪**：无法区分哪些文件是临时文件，哪些是永久文件
4. **容量无限增长**：没有清理机制，存储容量会无限增长

## 二、清理方案设计

### 2.1 设计原则

1. **安全性**：不能误删除仍在使用的文件
2. **可追溯**：能够判断文件的来源和使用情况
3. **灵活性**：支持不同文件类型的保留策略
4. **可配置**：保留时间可以根据业务需求调整

### 2.2 方案对比

#### 方案A：修改文件命名规则 + 数据库追踪表 ⭐ 推荐

**优点**：
- 清晰的文件分类
- 精确的文件追踪
- 灵活的保留策略
- 安全性高

**缺点**：
- 需要修改现有代码
- 需要新增数据库表

**实现复杂度**：中等

#### 方案B：基于URL有效期 + 任务关联清理

**优点**：
- 不需要修改文件命名
- 实现相对简单

**缺点**：
- 无法区分临时文件和永久文件
- 可能误删除仍在使用的文件
- 安全性较低

**实现复杂度**：较低

#### 方案C：基于文件扩展名 + 文件大小清理

**优点**：
- 实现最简单

**缺点**：
- 不够精确
- 可能误删除重要文件
- 无法追踪文件来源

**实现复杂度**：最低

### 2.3 推荐方案：方案A（修改文件命名规则 + 数据库追踪表）

## 三、详细设计（方案A）

### 3.1 文件命名规则

为每个文件添加前缀，便于识别文件类型：

```
{prefix}_{uuid}.{extension}

前缀说明：
- temp_    : 临时文件（24小时URL）
- perm_    : 永久文件（保存节点）
- avatar_  : 用户头像
- task_    : 任务文件（图片/视频/音频）
```

**示例**：
```
temp_a1b2c3d4.png        # 临时上传的图片
perm_e5f6g7h8.jpg        # 持久保存的图片
avatar_user123.png       # 用户头像
task_video_abc123.mp4    # 任务生成的视频
```

### 3.2 数据库表设计

#### 3.2.1 文件元数据表 (file_metadata)

```sql
CREATE TABLE file_metadata (
    id VARCHAR(36) PRIMARY KEY,              -- 文件ID（UUID）
    file_key VARCHAR(512) NOT NULL,          -- 文件在对象存储中的key
    file_prefix VARCHAR(20) NOT NULL,        -- 文件前缀（temp/perm/avatar/task）
    file_type VARCHAR(50) NOT NULL,          -- 文件类型（image/video/audio/document）
    file_size BIGINT,                        -- 文件大小（字节）
    mime_type VARCHAR(100),                  -- MIME类型
    source_type VARCHAR(50) NOT NULL,        -- 来源类型（upload/save/avatar/task）
    source_id VARCHAR(36),                   -- 来源ID（user_id/task_id）
    upload_time TIMESTAMP NOT NULL,          -- 上传时间
    access_time TIMESTAMP,                   -- 最后访问时间
    status VARCHAR(20) DEFAULT 'active',     -- 状态（active/deleted）
    retention_policy VARCHAR(50),            -- 保留策略（24h/7d/30d/permanent）
    expire_time TIMESTAMP,                   -- 过期时间
    created_at TIMESTAMP DEFAULT NOW(),
    updated_at TIMESTAMP DEFAULT NOW(),

    INDEX idx_file_key (file_key),
    INDEX idx_source_type (source_type),
    INDEX idx_source_id (source_id),
    INDEX idx_status (status),
    INDEX idx_expire_time (expire_time)
);
```

### 3.3 保留策略

| 文件前缀 | 来源类型 | 保留策略 | 说明 |
|---------|---------|---------|------|
| `temp_` | upload | 24小时 | 临时上传文件，URL过期后可删除 |
| `perm_` | save | 永久 | 用户主动保存的文件 |
| `avatar_` | update_user | 永久 | 用户头像，删除用户时清理 |
| `task_` | task | 7天 | 任务文件，删除任务后保留7天 |

### 3.4 清理逻辑

#### 3.4.1 清理临时文件（每天执行）

```python
# 清理条件：
# 1. 文件前缀 = 'temp_'
# 2. 上传时间 > 24小时
# 3. 状态 = 'active'

def cleanup_temp_files():
    # 1. 查询过期的临时文件
    expired_files = db.query(FileMetadata).filter(
        FileMetadata.file_prefix == 'temp_',
        FileMetadata.upload_time < now() - 24h,
        FileMetadata.status == 'active'
    ).all()

    # 2. 删除对象存储中的文件
    for file_meta in expired_files:
        storage.delete_file(file_key=file_meta.file_key)

    # 3. 更新数据库状态
    for file_meta in expired_files:
        file_meta.status = 'deleted'
        file_meta.updated_at = now()
```

#### 3.4.2 清理孤立头像（每天执行）

```python
# 清理条件：
# 1. 文件前缀 = 'avatar_'
# 2. source_id 不在 Users 表中（用户已删除）
# 3. 或者 source_id 对应的 Users.avatar != 文件URL（用户已更换头像）

def cleanup_orphaned_avatars():
    # 1. 获取所有用户的头像URL
    user_avatars = db.query(Users.avatar).filter(
        Users.avatar.isnot(None)
    ).all()

    # 2. 查询所有头像文件
    avatar_files = db.query(FileMetadata).filter(
        FileMetadata.file_prefix == 'avatar_',
        FileMetadata.status == 'active'
    ).all()

    # 3. 找出孤立的头像文件
    orphaned_files = []
    active_avatar_urls = {u.avatar for u in user_avatars}

    for file_meta in avatar_files:
        file_url = storage.get_file_url(file_meta.file_key)
        if file_url not in active_avatar_urls:
            orphaned_files.append(file_meta)

    # 4. 删除孤立文件
    for file_meta in orphaned_files:
        storage.delete_file(file_key=file_meta.file_key)
        file_meta.status = 'deleted'
        file_meta.updated_at = now()
```

#### 3.4.3 清理已删除任务文件（每天执行）

```python
# 清理条件：
# 1. 文件前缀 = 'task_'
# 2. source_id 对应的任务已删除（is_deleted = True）
# 3. 删除时间 > 7天

def cleanup_deleted_task_files():
    # 1. 查询已删除超过7天的任务
    expired_tasks = db.query(Tasks).filter(
        Tasks.is_deleted == True,
        Tasks.updated_at < now() - 7d
    ).all()

    # 2. 删除关联的文件
    for task in expired_tasks:
        # 从 Tasks.result 中提取文件URL
        result = task.result or {}
        file_urls = extract_file_urls(result)

        # 查询文件元数据
        for file_url in file_urls:
            file_key = extract_key_from_url(file_url)
            file_meta = db.query(FileMetadata).filter(
                FileMetadata.file_key == file_key,
                FileMetadata.status == 'active'
            ).first()

            if file_meta:
                storage.delete_file(file_key=file_key)
                file_meta.status = 'deleted'
                file_meta.updated_at = now()
```

### 3.5 代码修改清单

#### 3.5.1 数据库层面

1. **新增表**：`file_metadata`
2. **修改表**：无

#### 3.5.2 代码层面

1. **storage/s3/s3_storage.py**
   - 修改 `upload_file()` 方法，支持自定义文件前缀
   - 修改 `upload_from_url()` 方法，支持自定义文件前缀
   - 新增 `_extract_prefix_from_key()` 方法，从文件key中提取前缀

2. **graphs/node.py**
   - 修改 `upload_node()`，使用 `temp_` 前缀，记录到 file_metadata 表
   - 修改 `save_node()`，使用 `perm_` 前缀，记录到 file_metadata 表
   - 修改 `update_user_node()`，使用 `avatar_` 前缀，记录到 file_metadata 表
   - 修改各任务节点，使用 `task_` 前缀，记录到 file_metadata 表
   - 修改 `delete_user_node()`，清理用户头像文件
   - 修改 `delete_task_node()`，清理任务文件（先标记，延迟删除）

3. **storage/cleanup.py**（新增）
   - `FileCleanupManager` 类
   - `cleanup_temp_files()` - 清理临时文件
   - `cleanup_orphaned_avatars()` - 清理孤立头像
   - `cleanup_deleted_task_files()` - 清理已删除任务文件
   - `cleanup_all()` - 综合清理

4. **scripts/cleanup_files.py**（新增）
   - 清理脚本入口
   - 支持 `--dry-run` 模式
   - 支持自定义清理策略

### 3.6 实施计划

#### 阶段1：准备阶段（不影响现有功能）

1. 创建 `file_metadata` 表
2. 实现文件元数据记录功能
3. 修改上传/保存节点，记录文件元数据
4. **测试**：确保不影响现有功能

#### 阶段2：数据迁移（可选）

1. 扫描现有对象存储中的文件
2. 尝试识别文件类型
3. 补充文件元数据记录
4. **注意**：现有文件无法精确分类，可能需要手动处理

#### 阶段3：清理功能上线

1. 部署清理脚本
2. 配置定时任务（cron）
3. 监控清理效果
4. 优化清理策略

### 3.7 监控指标

1. **存储容量**：总存储大小、文件总数
2. **清理效果**：每日清理文件数、释放的存储空间
3. **异常情况**：清理失败次数、孤立文件数量
4. **性能影响**：清理任务执行时间、数据库负载

### 3.8 风险评估

| 风险 | 影响 | 概率 | 应对措施 |
|------|------|------|---------|
| 误删除仍在使用的文件 | 高 | 低 | 清理前先验证文件是否在数据库中引用 |
| 清理任务影响系统性能 | 中 | 中 | 选择低峰时段执行，控制每次清理数量 |
| 数据迁移失败 | 中 | 中 | 提前备份数据，分批迁移 |
| 文件元数据不一致 | 中 | 高 | 定期校验对象存储与数据库的一致性 |

## 四、替代方案（方案B简化版）

如果觉得方案A太复杂，可以使用简化版：

### 4.1 不修改文件命名

- 保留现有文件命名规则
- 通过上传时间和文件大小判断

### 4.2 清理策略

```python
# 1. 清理24小时前上传的文件
def cleanup_old_files():
    # 获取对象存储中所有文件
    all_files = storage.list_files()

    # 遍历文件
    for file_key in all_files:
        # 获取文件上传时间（通过head_object获取LastModified）
        file_info = storage.head_object(file_key)
        upload_time = file_info['LastModified']

        # 判断是否超过24小时
        if upload_time < now() - 24h:
            # 检查文件是否仍在使用中
            if not is_file_in_use(file_key):
                # 删除文件
                storage.delete_file(file_key)

# 2. 检查文件是否在使用中
def is_file_in_use(file_key):
    file_url = storage.get_file_url(file_key)

    # 检查用户头像
    avatar_count = db.query(Users).filter(Users.avatar == file_url).count()
    if avatar_count > 0:
        return True

    # 检查任务结果
    # 需要解析 JSON 字段，较复杂

    return False
```

### 4.3 优缺点

**优点**：
- 不需要修改文件命名
- 实现相对简单

**缺点**：
- 无法精确区分临时文件和永久文件
- 可能误删除仍在使用的文件
- 清理效率低（需要遍历所有文件）
- 无法追踪文件来源

## 五、推荐决策

### 推荐：方案A（修改文件命名规则 + 数据库追踪表）

**理由**：
1. 安全性高：有完整的文件元数据，不会误删除
2. 可追溯：清楚知道每个文件的来源和用途
3. 灵活性：支持不同文件类型的保留策略
4. 可扩展：未来可以支持更多文件类型和清理规则

**实施建议**：
1. 先实施阶段1（准备阶段），确保不影响现有功能
2. 运行一段时间后，再实施阶段3（清理功能）
3. 阶段2（数据迁移）可以跳过，只处理新上传的文件
4. 定期监控清理效果，优化策略

**成本评估**：
- 开发时间：3-5天
- 测试时间：2-3天
- 部署风险：低（可以逐步上线）
- 维护成本：低（自动化脚本）
