# 定时清理设置说明

## 当前状态

✅ 已创建每周清理脚本：`scripts/weekly_cleanup.sh`
✅ 脚本已测试，可以正常运行
✅ 清理日志保存到：`/var/log/cleanup.log`

## 手动运行清理

```bash
# 方式1：使用清理脚本（推荐）
bash scripts/weekly_cleanup.sh

# 方式2：直接运行 Python 脚本
python scripts/cleanup_storage.py --cleanup

# 查看日志
tail -20 /var/log/cleanup.log
```

---

## 设置自动定时任务

### 方式1：在支持 crontab 的环境中

添加到 crontab（每周日凌晨3点）：

```bash
# 编辑 crontab
crontab -e

# 添加以下行
0 3 * * 0 /workspace/projects/scripts/weekly_cleanup.sh
```

### 方式2：在支持 systemd 的环境中

创建 systemd timer（每周日凌晨3点）：

```bash
# 已创建服务文件
cat > /etc/systemd/system/storage-cleanup.service << 'EOF'
[Unit]
Description=Storage Cleanup Service
After=network.target

[Service]
Type=oneshot
User=root
WorkingDirectory=/workspace/projects
ExecStart=/usr/bin/bash /workspace/projects/scripts/weekly_cleanup.sh
StandardOutput=append:/var/log/cleanup.log
StandardError=append:/var/log/cleanup.log

[Install]
WantedBy=multi-user.target
EOF

# 创建定时器
cat > /etc/systemd/system/storage-cleanup.timer << 'EOF'
[Unit]
Description=Run Storage Cleanup Weekly (Every Sunday 3:00 AM)
Requires=storage-cleanup.service

[Timer]
OnCalendar=Sun *-*-* 03:00:00
Persistent=true

[Install]
WantedBy=timers.target
EOF

# 启动定时器
systemctl daemon-reload
systemctl enable storage-cleanup.timer
systemctl start storage-cleanup.timer

# 查看状态
systemctl status storage-cleanup.timer
```

### 方式3：使用外部定时服务

如果当前环境不支持 crontab 或 systemd，可以使用外部定时服务：

#### 1. GitHub Actions（代码仓库）

创建 `.github/workflows/cleanup.yml`：

```yaml
name: Weekly Storage Cleanup

on:
  schedule:
    - cron: '0 3 * * 0'  # 每周日凌晨3点
  workflow_dispatch:

jobs:
  cleanup:
    runs-on: ubuntu-latest
    steps:
      - name: Checkout
        uses: actions/checkout@v3

      - name: Setup Python
        uses: actions/setup-python@v4
        with:
          python-version: '3.9'

      - name: Run Cleanup
        env:
          COZE_BUCKET_ENDPOINT_URL: ${{ secrets.COZE_BUCKET_ENDPOINT_URL }}
          COZE_BUCKET_NAME: ${{ secrets.COZE_BUCKET_NAME }}
          COZE_ACCESS_KEY: ${{ secrets.COZE_ACCESS_KEY }}
          COZE_SECRET_KEY: ${{ secrets.COZE_SECRET_KEY }}
        run: |
          python scripts/cleanup_storage.py --cleanup
```

#### 2. Cron-Job.org（免费定时服务）

1. 访问 https://cron-job.org/
2. 注册账号
3. 创建 cron job
4. 设置 URL：指向你的 webhook 或 API
5. 设置时间：每周日凌晨3点

#### 3. 云平台定时任务

| 平台 | 定时任务服务 |
|------|-------------|
| 阿里云 | 函数计算（定时触发） |
| 腾讯云 | 云函数（定时触发） |
| AWS | Lambda + EventBridge |
| 腾讯云 | 云函数（定时触发） |

---

## 当前环境限制

当前环境是容器环境，不支持：
- ❌ crontab（命令不存在）
- ❌ systemd（服务未启动）

**建议**：在生产服务器上设置真正的定时任务。

---

## 验证清理脚本

```bash
# 测试运行（不实际删除）
python scripts/cleanup_storage.py --list

# 试运行（预览删除列表）
python scripts/cleanup_storage.py --cleanup

# 实际运行
bash scripts/weekly_cleanup.sh

# 查看日志
cat /var/log/cleanup.log
```

---

## 定时任务时间格式

### Cron 格式

```bash
# 每周日凌晨3点
0 3 * * 0

# 每天凌晨3点
0 3 * * *

# 每月1号凌晨3点
0 3 1 * *

# 每小时执行
0 * * * *
```

字段说明：
```
分 时 日 月 周
0  3  *  *  0
│  │  │  │  └── 0-7 (0和7都表示周日)
│  │  │  └───── 1-12
│  │  └──────── 1-31
│  └─────────── 0-23
└────────────── 0-59
```

### Systemd Timer 格式

```bash
# 每周日凌晨3点
OnCalendar=Sun *-*-* 03:00:00

# 每天凌晨3点
OnCalendar=*-*-* 03:00:00

# 每月1号凌晨3点
OnCalendar=*-*-01 03:00:00
```

---

## 常见问题

### Q: 定时任务没有执行？

A: 检查以下几点：
1. 检查 crontab 是否正确设置：`crontab -l`
2. 检查脚本是否有执行权限：`ls -l scripts/weekly_cleanup.sh`
3. 检查日志文件：`cat /var/log/cleanup.log`
4. 检查系统日志：`journalctl -u cron` 或 `journalctl -u storage-cleanup`

### Q: 如何修改清理频率？

A: 修改 cron 或 systemd timer 的时间格式即可。

### Q: 清理失败怎么办？

A: 查看日志：
```bash
cat /var/log/cleanup.log
# 或
tail -f /var/log/cleanup.log
```

### Q: 如何暂停定时任务？

A:
```bash
# crontab 方式
crontab -e  # 注释掉定时任务行

# systemd 方式
systemctl stop storage-cleanup.timer
systemctl disable storage-cleanup.timer
```

---

## 总结

| 方式 | 自动执行 | 当前环境 | 生产环境 |
|------|---------|---------|---------|
| 手动运行 | ❌ | ✅ | ✅ |
| crontab | ✅ | ❌ | ✅ |
| systemd timer | ✅ | ❌ | ✅ |
| GitHub Actions | ✅ | ✅ | ✅ |

**建议**：在生产服务器上使用 crontab 或 systemd timer 设置定时任务。
