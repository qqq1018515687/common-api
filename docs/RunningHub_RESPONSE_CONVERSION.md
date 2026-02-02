# RunningHub 响应转换指南

## 📋 概述

本文档说明如何将 RunningHub 的响应转换为我们系统的任务更新格式。

## 🔧 工具函数

### convert_runninghub_to_task_update()

将 RunningHub API 响应转换为任务更新格式。

**位置**: `src/utils/runninghub_converter.py`

**函数签名**:
```python
def convert_runninghub_to_task_update(runninghub_response: Dict[str, Any]) -> Dict[str, Any]
```

**参数**:
- `runninghub_response`: RunningHub API 响应（字典格式）

**返回值**:
- 任务更新格式字典：`{status, result|error, completed_at}`

### create_task_update_request()

创建完整的任务更新请求。

**函数签名**:
```python
def create_task_update_request(
    task_id: str,
    user_id: str,
    runninghub_response: Dict[str, Any]
) -> Dict[str, Any]
```

**参数**:
- `task_id`: 任务ID
- `user_id`: 用户ID
- `runninghub_response`: RunningHub API 响应

**返回值**:
- 完整的任务更新请求，可以直接调用任务管理API

---

## 📊 RunningHub 响应结构

### 成功响应

```json
{
    "code": 0,
    "msg": "success",
    "data": [
        {
            "fileUrl": "https://rh-images.xiaoyaoyou.com/de0db6f2564c8697b07df55a77f07be9/output/ComfyUI_00033_hpgko_1742822929.png",
            "fileType": "png",
            "taskCostTime": "83",
            "nodeId": "12",
            "thirdPartyConsumeMoney": null,
            "consumeMoney": null,
            "consumeCoins": "17"
        }
    ]
}
```

### 失败响应

```json
{
    "code": 805,
    "msg": "APIKEY_TASK_STATUS_ERROR",
    "data": {
        "failedReason": {
            "current_outputs": "{}",
            "exception_type": "TypeError",
            "node_name": "SONIC_PreData",
            "current_inputs": "{}",
            "traceback": "[...]",
            "node_id": "276",
            "exception_message": "SONIC_PreData.sampler_main() missing 2 required positional arguments: 'clip_vision' and 'vae'"
        }
    }
}
```

---

## 🔄 转换规则

### 成功响应转换 (code === 0)

**输入**: RunningHub 成功响应
**输出**: 任务更新格式（status = "completed"）

```json
{
  "status": "completed",
  "completed_at": 1770016663310,
  "result": {
    "message": "success",
    "files": [
      {
        "file_url": "https://rh-images.xiaoyaoyou.com/de0db6f2564c8697b07df55a77f07be9/output/ComfyUI_00033_hpgko_1742822929.png",
        "file_type": "png",
        "task_cost_time": "83",
        "node_id": "12",
        "consume_coins": "17",
        "third_party_consume_money": null,
        "consume_money": null
      }
    ],
    "raw_response": {...}
  }
}
```

#### 转换映射表

| RunningHub 字段 | 任务更新字段 | 说明 |
|----------------|-------------|------|
| `data[].fileUrl` | `files[].file_url` | 文件URL |
| `data[].fileType` | `files[].file_type` | 文件类型 |
| `data[].taskCostTime` | `files[].task_cost_time` | 任务耗时 |
| `data[].nodeId` | `files[].node_id` | 节点ID |
| `data[].consumeCoins` | `files[].consume_coins` | 消耗金币 |
| `data[].thirdPartyConsumeMoney` | `files[].third_party_consume_money` | 第三方消费金额 |
| `data[].consumeMoney` | `files[].consume_money` | 消费金额 |

---

### 失败响应转换 (code !== 0)

**输入**: RunningHub 失败响应
**输出**: 任务更新格式（status = "failed"）

```json
{
  "status": "failed",
  "completed_at": 1770016663311,
  "error": {
    "code": 805,
    "message": "APIKEY_TASK_STATUS_ERROR",
    "detail": {
      "exception_type": "TypeError",
      "node_name": "SONIC_PreData",
      "node_id": "276",
      "exception_message": "SONIC_PreData.sampler_main() missing 2 required positional arguments: 'clip_vision' and 'vae'",
      "traceback": "[...]",
      "current_inputs": "{}",
      "current_outputs": "{}"
    },
    "raw_response": {...}
  }
}
```

#### 转换映射表

| RunningHub 字段 | 任务更新字段 | 说明 |
|----------------|-------------|------|
| `code` | `error.code` | 错误码 |
| `msg` | `error.message` | 错误消息 |
| `data.failedReason.exception_type` | `error.detail.exception_type` | 异常类型 |
| `data.failedReason.node_name` | `error.detail.node_name` | 节点名称 |
| `data.failedReason.node_id` | `error.detail.node_id` | 节点ID |
| `data.failedReason.exception_message` | `error.detail.exception_message` | 异常消息 |
| `data.failedReason.traceback` | `error.detail.traceback` | 堆栈跟踪 |
| `data.failedReason.current_inputs` | `error.detail.current_inputs` | 当前输入 |
| `data.failedReason.current_outputs` | `error.detail.current_outputs` | 当前输出 |

---

## 📝 使用示例

### 示例 1：处理成功响应

```python
from utils.runninghub_converter import convert_runninghub_to_task_update, create_task_update_request
import requests
import json

# 1. 从 RunningHub 获取响应
runninghub_response = requests.get("https://api.runninghub.com/task/status/xxx").json()

# 2. 转换为任务更新格式
task_update = convert_runninghub_to_task_update(runninghub_response)
print(json.dumps(task_update, ensure_ascii=False, indent=2))

# 3. 创建完整的更新请求
update_request = create_task_update_request(
    task_id="task_uuid_001",
    user_id="user_test_001",
    runninghub_response=runninghub_response
)
print(json.dumps(update_request, ensure_ascii=False, indent=2))

# 4. 调用任务管理API更新任务
response = requests.post(
    "http://localhost:5000/run",
    json=update_request,
    headers={"Content-Type": "application/json"}
)
print(response.json())
```

### 示例 2：处理失败响应

```python
from utils.runninghub_converter import convert_runninghub_to_task_update
import json

# RunningHub 失败响应
runninghub_response = {
    "code": 805,
    "msg": "APIKEY_TASK_STATUS_ERROR",
    "data": {
        "failedReason": {
            "exception_type": "TypeError",
            "node_name": "SONIC_PreData",
            "exception_message": "SONIC_PreData.sampler_main() missing 2 required positional arguments: 'clip_vision' and 'vae'",
            "node_id": "276",
            "traceback": "[...]"
        }
    }
}

# 转换为任务更新格式
task_update = convert_runninghub_to_task_update(runninghub_response)

# 输出结果
print(json.dumps(task_update, ensure_ascii=False, indent=2))
```

**输出**:
```json
{
  "status": "failed",
  "completed_at": 1770016663311,
  "error": {
    "code": 805,
    "message": "APIKEY_TASK_STATUS_ERROR",
    "detail": {
      "exception_type": "TypeError",
      "node_name": "SONIC_PreData",
      "node_id": "276",
      "exception_message": "SONIC_PreData.sampler_main() missing 2 required positional arguments: 'clip_vision' and 'vae'",
      "traceback": "[...]",
      "current_inputs": null,
      "current_outputs": null
    },
    "raw_response": {...}
  }
}
```

---

## 🎯 完整的更新任务输入结构（适配 RunningHub）

### 场景：RunningHub 任务完成后更新

#### 输入结构（已转换）

```json
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
        "files": [
          {
            "file_url": "https://rh-images.xiaoyaoyou.com/de0db6f2564c8697b07df55a77f07be9/output/ComfyUI_00033_hpgko_1742822929.png",
            "file_type": "png",
            "task_cost_time": "83",
            "node_id": "12",
            "consume_coins": "17",
            "third_party_consume_money": null,
            "consume_money": null
          }
        ],
        "raw_response": {
          "code": 0,
          "msg": "success",
          "data": [...]
        }
      }
    }
  }
}
```

#### 输入字段说明

| 字段 | 类型 | 必填 | 说明 |
|------|------|------|------|
| **operation_type** | string | ✅ | 固定值："update_task" |
| **user_id** | string | ✅ | 用户ID（必须是已注册的活跃用户） |
| **task_id** | string | ✅ | 任务ID |
| **task_updates.status** | string | ✅ | 任务状态：completed/failed |
| **task_updates.completed_at** | int | ✅ | 完成时间（毫秒时间戳） |
| **task_updates.result** | object/null | ❌ | 生成结果（成功时） |
| **task_updates.result.message** | string | ❌ | 消息 |
| **task_updates.result.files** | array | ❌ | 文件列表 |
| **task_updates.result.files[].file_url** | string | ✅ | 文件URL |
| **task_updates.result.files[].file_type** | string | ✅ | 文件类型 |
| **task_updates.result.files[].task_cost_time** | string | ❌ | 任务耗时 |
| **task_updates.result.files[].node_id** | string | ❌ | 节点ID |
| **task_updates.result.files[].consume_coins** | string | ❌ | 消耗金币 |
| **task_updates.result.raw_response** | object | ❌ | 原始 RunningHub 响应 |

---

### 场景：RunningHub 任务失败后更新

#### 输入结构（已转换）

```json
{
  "call_type": "user_task_management",
  "input": {
    "operation_type": "update_task",
    "user_id": "user_test_001",
    "task_id": "task_uuid_12345678",
    "task_updates": {
      "status": "failed",
      "completed_at": 1770016663314,
      "error": {
        "code": 805,
        "message": "APIKEY_TASK_STATUS_ERROR",
        "detail": {
          "exception_type": "TypeError",
          "node_name": "SONIC_PreData",
          "node_id": "276",
          "exception_message": "SONIC_PreData.sampler_main() missing 2 required positional arguments: 'clip_vision' and 'vae'",
          "traceback": "[...]",
          "current_inputs": "{}",
          "current_outputs": "{}"
        },
        "raw_response": {
          "code": 805,
          "msg": "APIKEY_TASK_STATUS_ERROR",
          "data": {...}
        }
      }
    }
  }
}
```

#### 输入字段说明

| 字段 | 类型 | 必填 | 说明 |
|------|------|------|------|
| **operation_type** | string | ✅ | 固定值："update_task" |
| **user_id** | string | ✅ | 用户ID（必须是已注册的活跃用户） |
| **task_id** | string | ✅ | 任务ID |
| **task_updates.status** | string | ✅ | 任务状态：failed |
| **task_updates.completed_at** | int | ✅ | 完成时间（毫秒时间戳） |
| **task_updates.error** | string | ❌ | 错误信息（失败时，JSON字符串格式） |
| **task_updates.error.code** | int | ✅ | 错误码 |
| **task_updates.error.message** | string | ✅ | 错误消息 |
| **task_updates.error.detail** | object | ❌ | 错误详情 |
| **task_updates.error.detail.exception_type** | string | ❌ | 异常类型 |
| **task_updates.error.detail.node_name** | string | ❌ | 节点名称 |
| **task_updates.error.detail.node_id** | string | ❌ | 节点ID |
| **task_updates.error.detail.exception_message** | string | ❌ | 异常消息 |
| **task_updates.error.detail.traceback** | string | ❌ | 堆栈跟踪 |
| **task_updates.error.raw_response** | object | ❌ | 原始 RunningHub 响应 |

---

## ⚠️ 注意事项

1. **错误信息存储**
   - 失败时，error 字段存储为 JSON 字符串格式
   - 查询时需要反序列化：`json.loads(task.error)`

2. **原始响应保留**
   - 所有转换都会保留原始 RunningHub 响应
   - 便于调试和问题排查

3. **时间戳处理**
   - `completed_at` 自动生成当前时间（毫秒时间戳）
   - 如需使用 RunningHub 的时间，需手动设置

4. **文件列表处理**
   - 成功响应可能包含多个文件
   - 所有文件都会转换到 `files` 数组中

5. **字段命名转换**
   - RunningHub 使用驼峰命名：`fileUrl`
   - 转换后使用下划线命名：`file_url`

---

## 🔗 相关文档

- [任务路由完整文档](./TASK_ROUTE_GUIDE.md)
- [Tasks 数据表字段说明](./TASKS_TABLE_SCHEMA.md)
- [workflow_parameters vs parameter_snapshot](./PARAMETERS_DIFFERENCE.md)
