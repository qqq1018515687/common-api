#!/bin/bash
# 每周清理脚本
# 在支持 crontab 的环境中，可以添加到 crontab:
# 0 3 * * 0 /workspace/projects/scripts/weekly_cleanup.sh

# 进入项目目录
cd /workspace/projects

# 记录日志
LOG_FILE="/var/log/cleanup.log"

echo "========================================" >> "$LOG_FILE"
echo "开始清理过期文件 - $(date)" >> "$LOG_FILE"
echo "========================================" >> "$LOG_FILE"

# 执行清理
python scripts/cleanup_storage.py --cleanup >> "$LOG_FILE" 2>&1

echo "========================================" >> "$LOG_FILE"
echo "清理完成 - $(date)" >> "$LOG_FILE"
echo "========================================" >> "$LOG_FILE"
echo "" >> "$LOG_FILE"
