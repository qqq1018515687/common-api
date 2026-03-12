# 批量打标 API 使用文档

## 概述

通过API接口批量给已完成任务添加场景标签和产品标签，无需直接在服务器上运行脚本。

## API 端点

### 1. 预览待打标任务

**接口地址：** `GET /api/batch-retag/preview`

**功能：** 查询待打标的任务列表，不会实际执行打标

**请求参数：**

| 参数 | 类型 | 必填 | 说明 |
|------|------|------|------|
| limit | integer | 否 | 限制返回的任务数量 |

**请求示例：**

```bash
curl -X GET "https://your-domain.com/api/batch-retag/preview?limit=10"
```

**响应示例：**

```json
{
  "success": true,
  "message": "找到 10 个待打标任务",
  "total": 10,
  "tasks": [
    {
      "task_id": "task_001",
      "image_url": "https://example.com/image1.jpg",
      "created_at": "2024-01-15T10:30:00"
    },
    {
      "task_id": "task_002",
      "image_url": "https://example.com/image2.jpg",
      "created_at": "2024-01-15T11:00:00"
    }
  ]
}
```

---

### 2. 执行批量打标

**接口地址：** `POST /api/batch-retag/execute`

**功能：** 批量给任务生成标签

**请求头：**
```
Content-Type: application/json
```

**请求体（JSON）：**

| 参数 | 类型 | 必填 | 默认值 | 说明 |
|------|------|------|--------|------|
| limit | integer | 否 | null | 限制处理的任务数量，null表示不限制 |
| dry_run | boolean | 否 | false | 预览模式，只查询不实际更新 |
| use_mock_data | boolean | 否 | false | 使用模拟数据（不调用AI模型） |

**请求示例：**

```bash
# 预览模式（推荐先执行）
curl -X POST "https://your-domain.com/api/batch-retag/execute" \
  -H "Content-Type: application/json" \
  -d '{
    "dry_run": true,
    "limit": 10
  }'

# 使用模拟数据测试
curl -X POST "https://your-domain.com/api/batch-retag/execute" \
  -H "Content-Type: application/json" \
  -d '{
    "limit": 5,
    "use_mock_data": true
  }'

# 实际执行批量打标
curl -X POST "https://your-domain.com/api/batch-retag/execute" \
  -H "Content-Type: application/json" \
  -d '{
    "limit": 100
  }'
```

**响应示例：**

```json
{
  "success": true,
  "message": "批量打标完成，成功 98 个任务，耗时 45.32秒",
  "total": 100,
  "success_count": 98,
  "failed_count": 2,
  "failed_tasks": [
    {
      "task_id": "task_005",
      "reason": "没有图像URL"
    },
    {
      "task_id": "task_015",
      "reason": "数据库更新失败"
    }
  ],
  "dry_run": false,
  "processing_time": 45.32
}
```

---

## 使用流程

### 第一步：预览待打标任务

```bash
curl -X GET "https://your-domain.com/api/batch-retag/preview"
```

查看有多少待打标的任务，确认是否需要执行。

---

### 第二步：预览模式测试

```bash
curl -X POST "https://your-domain.com/api/batch-retag/execute" \
  -H "Content-Type: application/json" \
  -d '{
    "dry_run": true,
    "limit": 10
  }'
```

查看预览结果，确认将要处理的任务列表。

---

### 第三步：小批量测试（使用模拟数据）

```bash
curl -X POST "https://your-domain.com/api/batch-retag/execute" \
  -H "Content-Type: application/json" \
  -d '{
    "limit": 5,
    "use_mock_data": true
  }'
```

先用模拟数据测试5个任务，确认流程正常。

---

### 第四步：小批量实际测试

```bash
curl -X POST "https://your-domain.com/api/batch-retag/execute" \
  -H "Content-Type: application/json" \
  -d '{
    "limit": 10
  }'
```

使用AI模型实际打标10个任务，检查结果质量。

---

### 第五步：全量执行

```bash
curl -X POST "https://your-domain.com/api/batch-retag/execute" \
  -H "Content-Type: application/json" \
  -d '{}'
```

确认无误后，执行全量打标（不设置limit）。

---

## 查询条件

API 会自动查询满足以下条件的任务：

- ✅ 状态为 `completed`（已完成）
- ✅ `result` 字段不为空
- ✅ `result` 中包含 `url` 字段（图像URL）
- ✅ `scene_tags` 为空或数组长度为0
- ✅ `product_tags` 为空或数组长度为0

---

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

---

## 参数详解

### limit（限制数量）

```json
{
  "limit": 100
}
```

- 用于分批处理大量数据
- 避免一次性处理过多导致超时
- 建议首次测试使用小数值（5-10）

---

### dry_run（预览模式）

```json
{
  "dry_run": true
}
```

- 设置为 `true` 时，只查询不实际更新
- 用于预览将要处理的任务
- 不会调用AI模型，不会消耗API额度
- 推荐先使用预览模式确认数据

---

### use_mock_data（使用模拟数据）

```json
{
  "use_mock_data": true
}
```

- 设置为 `true` 时，使用预设的模拟标签：
  ```json
  {
    "scene_tags": ["座椅场景"],
    "product_tags": ["坐垫"]
  }
  ```
- 不会调用AI模型
- 不会消耗API额度
- 用于快速测试流程是否正常

---

## 错误处理

### 常见错误码

| 错误码 | 说明 | 解决方案 |
|--------|------|----------|
| 500 | 服务器内部错误 | 检查日志，重试 |
| 400 | 请求参数错误 | 检查请求体格式 |

### 失败任务

响应中的 `failed_tasks` 字段会列出所有失败的任务：

```json
{
  "failed_tasks": [
    {
      "task_id": "task_005",
      "reason": "没有图像URL"
    }
  ]
}
```

常见失败原因：
- 没有图像URL
- 数据库更新失败
- AI模型调用失败

---

## 安全建议

### 1. 分步执行

```bash
# 预览 → 预览模式 → 模拟数据测试 → 小批量 → 全量
```

### 2. 限制数量

首次执行建议设置 `limit` 参数：

```json
{
  "limit": 50
}
```

### 3. 预览模式

首次执行建议使用预览模式：

```json
{
  "dry_run": true
}
```

### 4. 监控执行

- 查看响应中的 `processing_time` 监控耗时
- 查看日志确认执行情况
- 检查失败的 `failed_tasks`

---

## Python 调用示例

```python
import requests
import json

BASE_URL = "https://your-domain.com/api/batch-retag"

# 1. 预览待打标任务
def preview_tasks(limit=None):
    params = {"limit": limit} if limit else {}
    response = requests.get(f"{BASE_URL}/preview", params=params)
    return response.json()

# 2. 执行批量打标
def execute_batch_retag(limit=None, dry_run=False, use_mock_data=False):
    payload = {
        "limit": limit,
        "dry_run": dry_run,
        "use_mock_data": use_mock_data
    }
    # 移除None值
    payload = {k: v for k, v in payload.items() if v is not None}
    
    response = requests.post(
        f"{BASE_URL}/execute",
        json=payload,
        headers={"Content-Type": "application/json"}
    )
    return response.json()

# 使用示例
if __name__ == "__main__":
    # 预览
    preview_result = preview_tasks(limit=10)
    print(f"待打标任务数: {preview_result['total']}")
    
    # 预览模式
    preview_run = execute_batch_retag(limit=5, dry_run=True)
    print(f"预览结果: {preview_run}")
    
    # 实际执行
    result = execute_batch_retag(limit=10)
    print(f"执行结果: 成功 {result['success_count']}, 失败 {result['failed_count']}")
```

---

## JavaScript/Node.js 调用示例

```javascript
const BASE_URL = "https://your-domain.com/api/batch-retag";

// 预览待打标任务
async function previewTasks(limit) {
  const params = limit ? `?limit=${limit}` : "";
  const response = await fetch(`${BASE_URL}/preview${params}`);
  return await response.json();
}

// 执行批量打标
async function executeBatchRetag(options = {}) {
  const { limit, dryRun, useMockData } = options;
  const payload = {};
  
  if (limit !== undefined) payload.limit = limit;
  if (dryRun !== undefined) payload.dry_run = dryRun;
  if (useMockData !== undefined) payload.use_mock_data = useMockData;
  
  const response = await fetch(`${BASE_URL}/execute`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload)
  });
  
  return await response.json();
}

// 使用示例
(async () => {
  // 预览
  const preview = await previewTasks(10);
  console.log(`待打标任务数: ${preview.total}`);
  
  // 预览模式
  const previewRun = await executeBatchRetag({
    limit: 5,
    dryRun: true
  });
  console.log("预览结果:", previewRun);
  
  // 实际执行
  const result = await executeBatchRetag({ limit: 10 });
  console.log(`执行结果: 成功 ${result.success_count}, 失败 ${result.failed_count}`);
})();
```

---

## 注意事项

1. **API 超时：** 大批量处理可能需要较长时间，建议分批执行（使用 `limit` 参数）

2. **AI 调用费用：** 实际打标会调用AI模型，产生费用。建议先用 `use_mock_data` 测试

3. **并发限制：** API 同一时间只能处理一个批量打标请求，请等待前一个请求完成后再发起

4. **数据库性能：** 大批量更新可能影响数据库性能，建议在业务低峰期执行

---

## 联系支持

如有问题，请联系技术团队。
