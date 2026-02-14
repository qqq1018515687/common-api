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

---

# 数据查询

## 用户列表查询
管理员可以查询用户列表，支持按时间范围筛选。

### 查询参数
```json
{
  "call_type": "account_management",
  "operation_type": "list_users",
  "input": {
    "operator_role": "admin",
    "time_range": "last_7_days",
    "start_date": null,
    "end_date": null,
    "filter": {
      "role": null,
      "tier": null,
      "account_status": null
    }
  }
}
```

### 时间范围选项
- `last_7_days` - 最近7天（默认）
- `last_15_days` - 最近15天
- `last_30_days` - 最近30天
- `all_time` - 全部时间

### 按团队ID查询
```json
{
  "input": {
    "operator_role": "admin",
    "team_id": "team_001",
    "time_range": "last_30_days"
  }
}
```

### 自定义时间范围
```json
{
  "input": {
    "operator_role": "admin",
    "time_range": null,
    "start_date": "2024-01-01",
    "end_date": "2024-01-31"
  }
}
```

### 返回结果
```json
{
  "code": 200,
  "msg": "success",
  "data": {
    "success": true,
    "users": [
      {
        "user_id": "1234567890",
        "phone": "138****8888",
        "username": "用户名",
        "avatar": "https://...",
        "team_id": "team_001",
        "gold_credits": 100,
        "silver_credits": 10000,
        "role": "user",
        "tier": "standard",
        "account_status": "active",
        "created_at": 1704067200000,
        "updated_at": 1704153600000
      }
    ],
    "time_range": "last_7_days",
    "start_date": "2024-01-24",
    "end_date": "2024-01-31"
  }
}
```

## 任务列表查询
注册用户可以查询自己的任务列表，支持按时间范围和状态筛选。

### 查询参数
```json
{
  "call_type": "user_task_management",
  "operation_type": "list_tasks",
  "input": {
    "user_id": "1234567890",
    "time_range": "last_7_days",
    "status": null,
    "team_id": null
  }
}
```

### 时间范围选项
- `last_7_days` - 最近7天（默认）
- `last_15_days` - 最近15天
- `last_30_days` - 最近30天
- `all_time` - 全部时间

### 状态筛选
- `pending` - 待处理
- `running` - 运行中
- `success` - 成功
- `failed` - 失败

### 自定义时间范围
```json
{
  "input": {
    "user_id": "1234567890",
    "time_range": null,
    "start_date": "2024-01-01",
    "end_date": "2024-01-31",
    "status": "success"
  }
}
```

### 返回结果
```json
{
  "code": 200,
  "msg": "success",
  "data": {
    "success": true,
    "message": "查询成功",
    "tasks": [
      {
        "id": "task_uuid",
        "user_id": "1234567890",
        "team_id": "team_001",
        "platform": "runninghub",
        "platform_task_id": "platform_task_001",
        "type": "image",
        "status": "success",
        "result": {...},
        "error": null,
        "created_at": 1704067200000,
        "updated_at": 1704153600000,
        "completed_at": 1704153605000
      }
    ],
    "time_range": "last_7_days",
    "start_date": "2024-01-24",
    "end_date": "2024-01-31"
  }
}
```

