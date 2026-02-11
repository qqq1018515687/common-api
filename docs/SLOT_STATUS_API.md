# 槽位状态查询接口说明

## 接口信息

**接口名称**: `slot_status`

**功能**: 通过两次获取账户信息请求，查询 RunningHub 服务器的生成槽位的占用情况

## 环境变量配置

在使用此接口前，需要在环境变量中配置两个 RunningHub API Key：

```bash
export RUNNINGHUB_API_KEY_1="your_first_api_key"
export RUNNINGHUB_API_KEY_2="your_second_api_key"
```

或在 `.env` 文件中添加：

```
RUNNINGHUB_API_KEY_1=your_first_api_key
RUNNINGHUB_API_KEY_2=your_second_api_key
```

## 请求格式

```json
{
  "call_type": "account_management",
  "input": {
    "operation_type": "slot_status"
  }
}
```

## 响应格式

### 成功响应

```json
{
  "response_data": {
    "code": 0,
    "msg": "操作成功",
    "data": {
      "available": true,
      "total": 6,
      "occupied": 3,
      "result": {
        "success": true,
        "errors": []
      }
    }
  }
}
```

### 失败响应

#### 未配置 API Key

```json
{
  "response_data": {
    "code": -1,
    "msg": "未配置 RunningHub API Key",
    "data": {
      "available": false,
      "total": 6,
      "occupied": 0,
      "result": {
        "success": false,
        "error": "未配置 RunningHub API Key"
      }
    }
  }
}
```

#### API 调用失败

```json
{
  "response_data": {
    "code": -1,
    "msg": "操作成功",
    "data": {
      "available": true,
      "total": 6,
      "occupied": 0,
      "result": {
        "success": false,
        "errors": [
          "API返回错误: 无效的API Key",
          "HTTP错误: 500"
        ]
      }
    }
  }
}
```

## 响应字段说明

| 字段 | 类型 | 说明 |
|------|------|------|
| `available` | boolean | 是否有空闲槽位（true 表示有至少 1 个空闲） |
| `total` | integer | 总槽位数，目前固定是 6 |
| `occupied` | integer | 当前已占用槽位数（根据两个 API Key 的 currentTaskCounts 之和） |
| `result.success` | boolean | 查询是否成功 |
| `result.errors` | array | 错误信息列表（如果有） |

## 实现逻辑

1. 从环境变量读取两个 RunningHub API Key
2. 分别调用 RunningHub API 查询账户状态
3. 获取每个账户的 `currentTaskCounts` 字段
4. 计算总占用数 = 两个账户的 `currentTaskCounts` 之和
5. 计算空闲槽位 = 6 - 总占用数
6. 返回结果

## RunningHub API 接口

**接口地址**: `https://www.runninghub.cn/uc/openapi/accountStatus`

**请求方法**: POST

**请求头**:
```
Host: www.runninghub.cn
Authorization: Bearer [Your API KEY]
Content-Type: application/json
```

**请求体**:
```json
{
  "apikey": "[Your API KEY]"
}
```

**响应示例**:
```json
{
  "code": 0,
  "msg": "success",
  "data": {
    "remainCoins": "99999",
    "currentTaskCounts": "2",
    "remainMoney": "999",
    "currency": "CNY",
    "apiType": "NORMAL"
  }
}
```

## 使用示例

### 示例 1: 有空闲槽位

**请求**:
```json
{
  "call_type": "account_management",
  "input": {
    "operation_type": "slot_status"
  }
}
```

**假设两个 API Key 的 `currentTaskCounts` 分别为 1 和 2**

**响应**:
```json
{
  "response_data": {
    "code": 0,
    "msg": "操作成功",
    "data": {
      "available": true,
      "total": 6,
      "occupied": 3,
      "result": {
        "success": true,
        "errors": []
      }
    }
  }
}
```

### 示例 2: 没有空闲槽位

**假设两个 API Key 的 `currentTaskCounts` 分别为 3 和 3**

**响应**:
```json
{
  "response_data": {
    "code": 0,
    "msg": "操作成功",
    "data": {
      "available": false,
      "total": 6,
      "occupied": 6,
      "result": {
        "success": true,
        "errors": []
      }
    }
  }
}
```

## 注意事项

1. 必须配置两个 RunningHub API Key，否则无法查询
2. 总槽位数固定为 6（两个 API Key，每个最多执行 3 个任务）
3. 如果 API 调用失败，`errors` 字段会包含详细的错误信息
4. 建议在调用生成接口前先检查槽位状态，避免任务排队
