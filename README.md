# 项目结构说明

# 本地运行
## 运行流程
bash scripts/local_run.sh -m flow

## 运行节点
bash scripts/local_run.sh -m node -n node_name

# 启动HTTP服务
bash scripts/http_run.sh -m http -p 5000

# 文件清理
## 清理过期文件
对象存储会随着时间累积大量文件，需要定期清理。提供以下清理脚本：

### 模拟运行（不实际删除）
```bash
python scripts/cleanup_files.py --dry-run
```

### 实际运行
```bash
python scripts/cleanup_files.py
```

### 自定义保留天数
```bash
# 临时文件保留48小时，任务文件保留14天
python scripts/cleanup_files.py --temp-hours 48 --task-days 14
```

### 设置定时清理（推荐）
使用 cron 设置定时任务，每周自动清理：
```bash
# 编辑 crontab
crontab -e

# 添加以下行（每周日凌晨2点清理）
0 2 * * 0 cd /workspace/projects && python scripts/cleanup_files.py >> logs/cleanup.log 2>&1
```

### 清理策略
- **临时文件 (temp_)**：清理24小时前上传的临时文件
- **孤立头像 (avatar_)**：清理用户已删除或已更换的头像
- **已删除任务文件 (task_)**：清理已删除7天以上的任务关联文件
- **安全模式**：先使用 `--dry-run` 参数模拟运行，确认无误后再实际执行

### 文件命名规则
```
{prefix}_{uuid}.{extension}

- temp_    : 临时文件（24小时URL）
- perm_    : 永久文件（保存节点）
- avatar_  : 用户头像
- task_    : 任务文件（图片/视频/音频）
```

### 数据库表
- `file_metadata` - 文件元数据表，记录所有文件的详细信息

