#!/bin/bash
set -eo pipefail

# 不要自动生成 requirements.txt，保持手动维护的固定版本
# 避免把本地开发版本（如 Mako==1.3.2.dev0）写入

echo "[pack] Skipping requirements.txt generation, using fixed versions"

# 双模式打包：优先 uv，回退 pip（确保旧镜像回滚兼容）
# if command -v uv &>/dev/null && [ -f "pyproject.toml" ]; then
#   echo "[pack] uv mode: locking dependencies"
#   uv lock
#   # 同步生成 requirements.txt 以供旧镜像回滚使用
#   echo "[pack] generating requirements.txt for backward compatibility"
#   uv export --frozen --no-hashes --no-dev | grep -v "^#" | grep -v "^$" | grep -v "^    " | sed 's/ ;.*//' > requirements.txt
# else
#   echo "[pack] pip fallback mode: freezing dependencies"
#   pip freeze --exclude watchdog > requirements.txt
# fi
