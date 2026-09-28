#!/usr/bin/env bash
set -euo pipefail

project_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
python_bin="${CHANNEL_MONITOR_PYTHON:-$project_root/.venv/bin/python}"
flock_bin="$(command -v flock || true)"

if [[ ! -x "$python_bin" || -z "$flock_bin" ]]; then
  echo "需要可用的 Python 虚拟环境和 flock，才能安装模型波动监控定时任务" >&2
  exit 1
fi
if [[ "$project_root" == *' '* ]]; then
  echo "项目路径不能包含空格，请在服务器固定部署目录运行" >&2
  exit 1
fi

mkdir -p "$project_root/logs"
marker='# huixing-channel-monitor'
entry="*/3 * * * * cd $project_root && $flock_bin -n /tmp/huixing-channel-monitor.lock $python_bin $project_root/scripts/monitor_channel_tasks.py >> $project_root/logs/channel-monitor.log 2>&1 $marker"
existing="$(crontab -l 2>/dev/null || true)"
{
  printf '%s\n' "$existing" | grep -vF "$marker" || true
  printf '%s\n' "$entry"
} | crontab -

echo "模型波动监控已安装：每 3 分钟检查一次，日志在 $project_root/logs/channel-monitor.log"
