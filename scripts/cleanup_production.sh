#!/bin/bash
# 生产环境清理脚本
# 使用方法: ./scripts/cleanup_production.sh [参数]
# 示例:
#   ./scripts/cleanup_production.sh --analyze
#   ./scripts/cleanup_production.sh --cleanup
#   ./scripts/cleanup_production.sh --cleanup --force

# 生产环境配置（请替换为实际配置）
export COZE_BUCKET_ENDPOINT_URL=""
export COZE_BUCKET_NAME=""
export COZE_ACCESS_KEY=""
export COZE_SECRET_KEY=""

# 检查配置
if [ -z "$COZE_BUCKET_ENDPOINT_URL" ] || [ -z "$COZE_BUCKET_NAME" ]; then
    echo "❌ 错误: 请先配置生产环境信息"
    echo "编辑本文件，设置以下环境变量："
    echo "  - COZE_BUCKET_ENDPOINT_URL"
    echo "  - COZE_BUCKET_NAME"
    echo "  - COZE_ACCESS_KEY (可选)"
    echo "  - COZE_SECRET_KEY (可选)"
    exit 1
fi

# 执行清理
python scripts/simple_cleanup.py "$@"
