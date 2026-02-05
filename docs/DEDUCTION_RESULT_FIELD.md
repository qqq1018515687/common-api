# Tasks 表 deduction_result 字段说明

## 📋 概述

`deduction_result` 字段用于记录任务的扣费结果信息，包含扣费模式、预扣金额、最终金额和结算时间。

---

## 📊 数据库字段定义

```sql
deduction_result JSON COMMENT '扣费结果记录'
```

**类型**: JSON (可选字段)

**位置**: Tasks 表

---

## 📝 数据结构

### 完整结构

```json
{
  "mode": "silver" | "gold",
  "preDeductedAmount": 50,
  "finalAmount": 20,
  "settledAt": 1234567890
}
```

### 字段说明

| 字段 | 类型 | 必填 | 说明 | 示例值 |
|------|------|------|------|--------|
| **mode** | string | ✅ | 扣费模式：`silver`（银币）或 `gold`（金币） | `"silver"`, `"gold"` |
| **preDeductedAmount** | number | ✅ | 预扣金额 | `50`, `100` |
| **finalAmount** | number | ✅ | 最终扣费金额 | `20`, `80` |
| **settledAt** | number | ✅ | 结算时间（毫秒时间戳） | `1234567890123` |

---

## 🎯 使用场景

### 场景 1：银币扣费

```json
{
  "mode": "silver",
  "preDeductedAmount": 100,
  "finalAmount": 80,
  "settledAt": 1770016663314
}
```

**说明**：
- 使用银币模式扣费
- 预先扣除 100 银币
- 实际消耗 80 银币（退回 20 银币）
- 结算时间：2026-11-27 15:44:23.314

---

### 场景 2：金币扣费

```json
{
  "mode": "gold",
  "preDeductedAmount": 10,
  "finalAmount": 10,
  "settledAt": 1770016663314
}
```

**说明**：
- 使用金币模式扣费
- 预先扣除 10 金币
- 实际消耗 10 金币（无退回）
- 结算时间：2026-11-27 15:44:23.314

---

### 场景 3：无扣费（可选字段为空）

```json
{
  "status": "completed",
  "result": {...},
  "deduction_result": null
}
```

**说明**：
- 任务完成但没有扣费
- `deduction_result` 为 `null` 或不传

---

## 🔧 更新任务时传入 deduction_result

### API 请求示例

#### HTTP 请求

```bash
POST /run
Content-Type: application/json

{
  "call_type": "user_task_management",
  "input": {
    "operation_type": "update_task",
    "user_id": "user_test_001",
    "task_id": "task_uuid_12345678",
    "task_updates": {
      "status": "completed",
      "completed_at": 1770016663314,
      "result": {
        "message": "success",
        "files": [...]
      },
      "deduction_result": {
        "mode": "silver",
        "preDeductedAmount": 50,
        "finalAmount": 20,
        "settledAt": 1770016663314
      }
    }
  }
}
```

#### Python 调用示例

```python
import requests
import json

url = "http://localhost:5000/run"
headers = {"Content-Type": "application/json"}

payload = {
    "call_type": "user_task_management",
    "input": {
        "operation_type": "update_task",
        "user_id": "user_test_001",
        "task_id": "task_uuid_12345678",
        "task_updates": {
            "status": "completed",
            "completed_at": 1770016663314,
            "result": {
                "message": "success",
                "files": [...]
            },
            "deduction_result": {
                "mode": "silver",
                "preDeductedAmount": 50,
                "finalAmount": 20,
                "settledAt": 1770016663314
            }
        }
    }
}

response = requests.post(url, headers=headers, json=payload)
print(response.json())
```

---

## 📤 查询任务时返回 deduction_result

### 查询任务列表响应示例

```json
{
  "response_data": {
    "code": 0,
    "msg": "操作成功",
    "data": {
      "success": true,
      "message": "查询成功",
      "tasks": [
        {
          "id": "task_uuid_12345678",
          "user_id": "user_test_001",
          "status": "completed",
          "result": {
            "message": "success",
            "files": [...]
          },
          "deduction_result": {
            "mode": "silver",
            "preDeductedAmount": 50,
            "finalAmount": 20,
            "settledAt": 1770016663314
          },
          "created_at": 1770016663300,
          "updated_at": 1770016663315,
          "completed_at": 1770016663314
        }
      ],
      "total": 1,
      "page": 1,
      "limit": 10
    }
  }
}
```

---

## ⚠️ 注意事项

### 1. 字段可选性

- `deduction_result` 是**可选字段**
- 如果任务不涉及扣费，可以不传或传 `null`

### 2. 数据类型约束

| 字段 | 类型 | 约束 |
|------|------|------|
| mode | string | 必须是 `"silver"` 或 `"gold"` |
| preDeductedAmount | number | 必须是非负整数 |
| finalAmount | number | 必须是非负整数，不能超过 preDeductedAmount |
| settledAt | number | 必须是有效的毫秒时间戳 |

### 3. 时间戳格式

- `settledAt` 使用**毫秒时间戳**（13位数字）
- 示例：`1770016663314`（对应 2026-11-27 15:44:23.314）

### 4. 金额计算逻辑

- `preDeductedAmount` ≥ `finalAmount`
- 退款金额 = `preDeductedAmount` - `finalAmount`

**示例**：
- 预扣 100，实际消耗 80 → 退款 20
- 预扣 100，实际消耗 100 → 退款 0

---

## 🔗 相关文档

- [RunningHub 响应转换指南](./RunningHub_RESPONSE_CONVERSION.md) - RunningHub 响应转换工具
- [更新任务输入输出说明](../AGENTS.md#任务管理功能说明) - 更新任务完整文档
- [数据库迁移指南](./ALEMBIC_GUIDE.md) - Alembic 迁移工具使用指南

---

## 📅 变更历史

| 版本 | 日期 | 变更内容 |
|------|------|---------|
| v1.0 | 2026-11-27 | 新增 `deduction_result` 字段到 Tasks 表 |
