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
# 头像保留7天，任务文件保留3天
python scripts/cleanup_files.py --avatar-days 7 --task-days 3
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
- **头像文件**：清理孤立头像（用户已删除但对象存储中仍存在），默认保留30天
- **任务文件**：清理已删除任务的相关文件，默认保留7天
- **安全模式**：先使用 `--dry-run` 参数模拟运行，确认无误后再实际执行

