# 生产环境数据清理指南

## 问题说明

默认情况下，清理工具使用当前环境的配置（开发环境）。要清理生产环境的数据，需要提供生产环境的配置参数。

---

## 方案一：命令行参数（推荐）

### 1. 准备生产环境配置

从生产环境获取以下信息：
- **Endpoint URL**: 对象存储端点地址
- **Bucket Name**: 生产环境 Bucket 名称
- **Access Key**: 访问密钥（可选）
- **Secret Key**: 秘钥（可选）

### 2. 扫描生产环境数据

```bash
python scripts/simple_cleanup.py \
  --analyze \
  --endpoint-url "https://your-production-endpoint.com" \
  --bucket-name "production-bucket"
```

### 3. 试运行（不实际删除）

```bash
python scripts/simple_cleanup.py \
  --cleanup \
  --endpoint-url "https://your-production-endpoint.com" \
  --bucket-name "production-bucket"
```

### 4. 确认后执行删除

```bash
python scripts/simple_cleanup.py \
  --cleanup \
  --force \
  --endpoint-url "https://your-production-endpoint.com" \
  --bucket-name "production-bucket"
```

---

## 方案二：环境变量

### 1. 设置环境变量

```bash
export COZE_BUCKET_ENDPOINT_URL="https://your-production-endpoint.com"
export COZE_BUCKET_NAME="production-bucket"
export COZE_ACCESS_KEY="your-access-key"
export COZE_SECRET_KEY="your-secret-key"
```

### 2. 执行清理

```bash
# 扫描
python scripts/simple_cleanup.py --analyze

# 试运行
python scripts/simple_cleanup.py --cleanup

# 执行删除
python scripts/simple_cleanup.py --cleanup --force
```

---

## 方案三：创建配置文件（适合多次使用）

### 1. 创建清理脚本

创建 `scripts/cleanup_production.sh`:

```bash
#!/bin/bash

# 生产环境配置
export COZE_BUCKET_ENDPOINT_URL="https://your-production-endpoint.com"
export COZE_BUCKET_NAME="production-bucket"
export COZE_ACCESS_KEY="your-access-key"
export COZE_SECRET_KEY="your-secret-key"

# 执行清理
python scripts/simple_cleanup.py "$@"
```

### 2. 赋予执行权限

```bash
chmod +x scripts/cleanup_production.sh
```

### 3. 使用脚本

```bash
# 扫描
./scripts/cleanup_production.sh --analyze

# 试运行
./scripts/cleanup_production.sh --cleanup

# 执行删除
./scripts/cleanup_production.sh --cleanup --force
```

---

## 安全注意事项

### ⚠️ 重要提醒

1. **先扫描再删除**：执行 `--analyze` 查看实际数据
2. **先试运行**：执行 `--cleanup`（不带 `--force`）预览删除列表
3. **确认无误后再执行**：确认后添加 `--force` 才会真正删除
4. **无法恢复**：删除后无法恢复，请谨慎操作

### 🔒 安全建议

- 不要在脚本中硬编码密钥
- 使用环境变量或配置管理工具
- 定期轮换访问密钥
- 使用最小权限原则（只赋予删除权限）

---

## 常见问题

### Q: 如何确认连接的是生产环境？

A: 执行扫描时会显示配置信息：
```
============================================================
对象存储配置
============================================================
  Endpoint: https://your-production-endpoint.com
  Bucket: production-bucket
  Region: cn-beijing
============================================================
```

### Q: 可以同时清理多个环境吗？

A: 不建议。一次只清理一个环境，避免误删。

### Q: 如果删除失败怎么办？

A: 查看错误日志，可能是：
- 权限不足
- 文件不存在
- 网络问题

修复后重新执行即可。

### Q: 如何只删除特定类型的文件？

A: 修改 `is_avatar_file` 方法，添加更多识别规则。

---

## 示例：完整清理流程

```bash
# 1. 扫描生产环境数据
python scripts/simple_cleanup.py \
  --analyze \
  --endpoint-url "https://production.example.com" \
  --bucket-name "my-production-bucket"

# 2. 试运行（预览删除列表）
python scripts/simple_cleanup.py \
  --cleanup \
  --endpoint-url "https://production.example.com" \
  --bucket-name "my-production-bucket"

# 3. 确认无误后，执行删除
python scripts/simple_cleanup.py \
  --cleanup \
  --force \
  --endpoint-url "https://production.example.com" \
  --bucket-name "my-production-bucket"
```

---

## 获取生产环境配置

### Coze 平台

登录 Coze 平台 → 设置 → 集成配置 → 对象存储，查看：
- Endpoint URL
- Bucket Name
- Access Key
- Secret Key

### 其他平台

请参考对应平台的文档获取配置信息。
