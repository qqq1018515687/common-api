# 初始化目录
if [ "$COZE_PROJECT_ENV" = "DEV" ]; then
    if [ ! -d "${COZE_WORKSPACE_PATH}/assets" ]; then
        mkdir -p "${COZE_WORKSPACE_PATH}/assets"
    fi
fi

# 安装Python三方包依赖
# 优先使用 uv（如果存在 uv.lock）
if [ -f "${COZE_WORKSPACE_PATH}/uv.lock" ]; then
    uv sync --frozen
else
    pip install -r requirements.txt
fi

# 安装系统依赖
