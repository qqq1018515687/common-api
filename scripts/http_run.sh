#!/bin/bash

set -e
# 导出环境变量

export BILLING_SERVICE_SECRET="${BILLING_SERVICE_SECRET:-mars_billing_2024}"
export GITHUB_TOKEN="${GITHUB_TOKEN:-}"  # 填写你的 GitHub Personal Access Token，用于推送代码

WORK_DIR="${COZE_WORKSPACE_PATH:-.}"
PORT=8000

usage() {
  echo "用法: $0 -p <端口>"
}

while getopts "p:h" opt; do
  case "$opt" in
    p)
      PORT="$OPTARG"
      ;;
    h)
      usage
      exit 0
      ;;
    \?)
      echo "无效选项: -$OPTARG"
      usage
      exit 1
      ;;
  esac
done

# 设置 PYTHONPATH，确保 Python 可以找到所有模块
# 包含项目根目录和 src 目录
export PYTHONPATH="${WORK_DIR}:${WORK_DIR}/src:${PYTHONPATH}"

# 切换到工作目录
cd "${WORK_DIR}"

# Run database migrations before starting the HTTP service. Alembic skips
# already-applied revisions, so this is safe to run on every deployment.
echo "[DB] Running Alembic migrations..."
python -m alembic upgrade head

# 使用 -m 参数运行模块，确保 Python 能正确解析导入
python -m src.main -m http -p $PORT
