# 生产环境批量打标脚本使用指南

## 概述

`batch_retag_production.py` 是一个独立的脚本，用于在生产环境批量给已完成任务添加场景标签和产品标签。该脚本不依赖开发者环境，可以直接在生产服务器上运行。

## 功能特点

- ✅ 完全独立运行，不依赖现有项目代码
- ✅ 支持预览模式（dry-run），先查看再执行
- ✅ 支持限制处理数量，避免一次性处理过多数据
- ✅ 详细的日志输出，实时显示处理进度
- ✅ 支持AI模型调用（豆包多模态）或使用模拟数据
- ✅ 安全的数据库操作，失败自动回滚

## 依赖安装

在生产环境安装必要的依赖：

```bash
pip install psycopg2-binary requests
```

## 使用方法

### 1. 预览模式（推荐先执行）

先预览将处理多少任务，不实际执行：

```bash
python scripts/batch_retag_production.py \
  --db-url "postgresql://用户名:密码@主机:端口/数据库名" \
  --dry-run
```

输出示例：
```
📊 找到 150 个待打标任务

============================================================
🚀 开始批量打标
   总任务数: 150
   模式: 预览模式（不实际执行）
============================================================

[1/150] 处理任务 task_001
   图像URL: https://example.com/image1.jpg
   预览: 将生成标签（不实际执行）
...
```

### 2. 限制数量测试

先处理少量任务测试：

```bash
python scripts/batch_retag_production.py \
  --db-url "postgresql://用户名:密码@主机:端口/数据库名" \
  --limit 10 \
  --llm-api-key "你的API密钥"
```

### 3. 批量处理所有任务

确认无误后，处理所有待打标任务：

```bash
python scripts/batch_retag_production.py \
  --db-url "postgresql://用户名:密码@主机:端口/数据库名" \
  --llm-api-key "你的API密钥"
```

### 4. 环境变量方式

也可以通过环境变量传递：

```bash
export DB_URL="postgresql://用户名:密码@主机:端口/数据库名"
export LLM_API_KEY="你的API密钥"

python scripts/batch_retag_production.py --db-url "$DB_URL" --llm-api-key "$LLM_API_KEY"
```

## 参数说明

| 参数 | 必填 | 说明 |
|------|------|------|
| `--db-url` | 是 | 数据库连接URL，格式：`postgresql://user:pass@host:port/db` |
| `--limit` | 否 | 限制处理的任务数量（默认：不限制） |
| `--dry-run` | 否 | 预览模式，不实际执行（默认：否） |
| `--llm-api-key` | 否 | AI模型API密钥（不传则使用模拟数据） |

## 查询条件

脚本会查询满足以下条件的任务：

- 状态为 `completed`（已完成）
- `result` 字段不为空
- `result` 中包含 `url` 字段
- `scene_tags` 为空或数组长度为0
- `product_tags` 为空或数组长度为0

## 安全建议

### 1. 分步执行

```bash
# 第一步：预览
python scripts/batch_retag_production.py --db-url "$DB_URL" --dry-run

# 第二步：测试10条
python scripts/batch_retag_production.py --db-url "$DB_URL" --limit 10 --llm-api-key "$LLM_API_KEY"

# 第三步：测试100条
python scripts/batch_retag_production.py --db-url "$DB_URL" --limit 100 --llm-api-key "$LLM_API_KEY"

# 第四步：全量执行
python scripts/batch_retag_production.py --db-url "$DB_URL" --llm-api-key "$LLM_API_KEY"
```

### 2. 数据备份

执行前建议备份数据库：

```bash
pg_dump -U 用户名 -h 主机 -p 端口 数据库名 > backup_$(date +%Y%m%d).sql
```

### 3. 监控资源

大量任务处理时建议：

- 在业务低峰期执行
- 监控数据库连接数
- 监控AI API调用频率和费用

## 标签说明

### 场景标签池
- 座椅场景
- 睡眠场景
- 躺卧场景
- 驾驶场景
- 办公场景
- 客厅场景
- 装饰场景
- 户外场景

### 产品标签池
- 腰靠
- 腿枕
- 融蜡灯
- 脚垫
- 枕头
- 坐垫

## 输出结果

脚本会输出详细的处理日志和最终结果：

```
============================================================
✅ 批量打标完成
   总任务数: 150
   成功: 145
   失败: 5
============================================================

{
  "success": true,
  "total": 150,
  "success_count": 145,
  "failed_count": 5,
  "failed_tasks": [
    {
      "task_id": "task_003",
      "reason": "没有图像URL"
    },
    ...
  ],
  "dry_run": false
}
```

## 常见问题

### Q1: 提示缺少依赖

```bash
pip install psycopg2-binary requests
```

### Q2: 数据库连接失败

检查：
- 数据库URL格式是否正确
- 用户名和密码是否正确
- 网络是否通畅
- 数据库是否允许远程连接

### Q3: AI模型调用失败

- 检查 API 密钥是否正确
- 检查网络是否可以访问 AI 服务
- 检查 API 调用额度是否充足

如果不传 `--llm-api-key`，脚本会使用模拟数据：
```json
{
  "scene_tags": ["座椅场景"],
  "product_tags": ["坐垫"]
}
```

### Q4: 如何只更新特定日期的任务？

可以修改脚本中的 SQL 查询，添加时间过滤：

```sql
WHERE status = 'completed'
  AND created_at >= to_timestamp(开始时间戳 / 1000)
  AND created_at <= to_timestamp(结束时间戳 / 1000)
  ...
```

### Q5: 处理速度慢怎么办？

- 使用 `--limit` 参数分批处理
- 使用模拟数据（不传 `--llm-api-key`）快速测试
- 检查数据库和网络的性能

## 日志级别

脚本使用 `INFO` 级别日志，会输出：
- ✅ 成功操作
- ⚠️ 警告信息（如跳过的任务）
- ❌ 错误信息（如失败的更新）

如需更详细的调试信息，可以修改脚本中的日志级别：

```python
logging.basicConfig(
    level=logging.DEBUG,  # 改为 DEBUG
    ...
)
```

## 联系支持

如有问题，请联系技术团队。
