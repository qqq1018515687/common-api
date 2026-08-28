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
ALEMBIC_OK=0
for attempt in 1 2 3; do
  echo "[DB] Alembic attempt ${attempt}/3"
  if python -m alembic upgrade head; then
    ALEMBIC_OK=1
    break
  fi
  echo "[DB] Alembic attempt ${attempt} failed"
  sleep 2
done

if [ "$ALEMBIC_OK" -ne 1 ]; then
  echo "[DB] WARNING: Alembic migrations failed after retries, continue with runtime DDL fallback"
fi

# 确保 users 表字段长度正确（Alembic 迁移 repeat 问题，每次部署兜底修复）
echo "[DB] 确保 users 表字段长度正确..."
python << 'PYEOF'
from sqlalchemy import text
from storage.database.db import get_engine
e = get_engine()
with e.connect() as c:
    for col in ('role', 'tier', 'account_status'):
        c.execute(text(f'ALTER TABLE users ALTER COLUMN {col} TYPE varchar(32)'))
    c.commit()
    print('✅ users 字段长度已确保为 varchar(32)')
PYEOF

# 确保 tasks 运行时字段存在（避免 Alembic 已标记但线上漏列）
echo "[DB] 确保 tasks 运行时字段存在..."
python << 'PYEOF'
from sqlalchemy import text
from storage.database.db import get_engine

e = get_engine()
with e.connect() as c:
    c.execute(text("ALTER TABLE tasks ADD COLUMN IF NOT EXISTS started_at VARCHAR(20)"))
    c.execute(text("ALTER TABLE tasks ADD COLUMN IF NOT EXISTS elapsed_time_seconds INTEGER DEFAULT 0"))
    c.execute(text("ALTER TABLE tasks ADD COLUMN IF NOT EXISTS confirmation_state VARCHAR(20) DEFAULT 'none'"))
    c.execute(text("ALTER TABLE tasks ADD COLUMN IF NOT EXISTS deleted_image_urls JSON"))
    c.execute(text("ALTER TABLE tasks ADD COLUMN IF NOT EXISTS result_fallback JSON"))
    c.execute(text("ALTER TABLE tasks ADD COLUMN IF NOT EXISTS persistence_status VARCHAR(20)"))
    c.execute(text("ALTER TABLE tasks ADD COLUMN IF NOT EXISTS persistence_error TEXT"))
    c.execute(text("ALTER TABLE tasks ADD COLUMN IF NOT EXISTS channel VARCHAR(32)"))
    c.execute(text("ALTER TABLE tasks ADD COLUMN IF NOT EXISTS failed_at VARCHAR(20)"))
    c.execute(text("ALTER TABLE tasks ADD COLUMN IF NOT EXISTS cancelled_at VARCHAR(20)"))
    c.execute(text("ALTER TABLE tasks ADD COLUMN IF NOT EXISTS status_updated_at VARCHAR(20)"))
    c.execute(text("UPDATE tasks SET started_at = created_at WHERE started_at IS NULL"))
    c.execute(text("UPDATE tasks SET elapsed_time_seconds = 0 WHERE elapsed_time_seconds IS NULL"))
    c.execute(text("""
        UPDATE tasks
        SET confirmation_state = CASE
            WHEN status = 'running'
             AND (
                (parameter_snapshot->>'confirmationState') = 'pending'
                OR COALESCE(user_friendly_message, '') LIKE '%结果确认中%'
             ) THEN 'pending'
            WHEN status IN ('completed', 'failed', 'cancelled') THEN 'confirmed'
            ELSE 'none'
        END
        WHERE confirmation_state IS NULL
    """))
    c.commit()
    print('✅ tasks 运行时字段已兜底修复')
PYEOF

# 确保 system_notifications 运行时字段存在（避免 Alembic 已标记但线上漏列）
echo "[DB] 确保 system_notifications 运行时字段存在..."
python << 'PYEOF'
from sqlalchemy import text
from storage.database.db import get_engine

e = get_engine()
with e.connect() as c:
    c.execute(text("ALTER TABLE system_notifications ADD COLUMN IF NOT EXISTS biz_key VARCHAR(64)"))
    # biz_key 唯一索引若缺失则补齐（线上漏建时）
    exists = c.execute(text(
        "SELECT 1 FROM pg_indexes WHERE tablename = 'system_notifications' AND indexname = 'uq_system_notifications_biz_key'"
    )).fetchone()
    if not exists:
        c.execute(text(
            "CREATE UNIQUE INDEX IF NOT EXISTS uq_system_notifications_biz_key ON system_notifications (biz_key)"
        ))
    c.commit()
    print('✅ system_notifications 运行时字段已兜底修复')
PYEOF

# 使用 -m 参数运行模块，确保 Python 能正确解析导入
python -m src.main -m http -p $PORT
