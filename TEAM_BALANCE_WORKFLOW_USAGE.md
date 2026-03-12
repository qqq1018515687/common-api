# 团队余额功能 - 通过工作流初始化数据库表

## 如何通过工作流创建数据库表

### 第一步：初始化团队余额系统

调用工作流，传入以下参数：

```json
{
  "call_type": "system_init",
  "action": "init"
}
```

### 第二步：检查表是否创建成功

调用工作流，传入以下参数：

```json
{
  "call_type": "system_init",
  "action": "check"
}
```

## 详细说明

### 工作流调用方式

通过 `/run` 接口调用：

```bash
curl -X POST "https://你的部署地址/run" \
  -H "Content-Type: application/json" \
  -d '{
    "call_type": "system_init",
    "action": "init"
  }'
```

### 初始化成功响应

```json
{
  "result": {
    "success": true,
    "message": "团队余额系统初始化成功",
    "tables_created": ["teams", "team_members", "team_consumption_records"]
  }
}
```

### 检查表状态响应

```json
{
  "result": {
    "success": true,
    "all_exist": true,
    "tables": {
      "teams": true,
      "team_members": true,
      "team_consumption_records": true
    }
  }
}
```

## 完整使用流程

### 1. 初始化数据库表（只需要执行一次）

```bash
curl -X POST "https://你的部署地址/run" \
  -H "Content-Type: application/json" \
  -d '{
    "call_type": "system_init",
    "action": "init"
  }'
```

### 2. 验证表是否创建成功

```bash
curl -X POST "https://你的部署地址/run" \
  -H "Content-Type: application/json" \
  -d '{
    "call_type": "system_init",
    "action": "check"
  }'
```

### 3. 开始使用团队余额功能

表创建成功后，可以使用以下 API 接口（注意：这些是独立 API，不是工作流）：

#### 创建团队
```bash
curl -X POST "https://你的部署地址/api/teams" \
  -H "Content-Type: application/json" \
  -d '{"name": "研发团队"}'
```

#### 添加成员
```bash
curl -X POST "https://你的部署地址/api/teams/team_xxx/members" \
  -H "Content-Type: application/json" \
  -d '{"user_id": "user_001", "role": "member"}'
```

#### 团队充值
```bash
curl -X POST "https://你的部署地址/api/teams/team_xxx/recharge" \
  -H "Content-Type: application/json" \
  -d '{"amount": 10000}'
```

#### 查询团队余额
```bash
curl "https://你的部署地址/api/teams/team_xxx/balance"
```

## 注意事项

1. **初始化只需要执行一次**：数据库表创建后不需要重复初始化
2. **可以重复调用**：如果表已存在，会提示已创建，不会报错
3. **初始化和团队管理是分开的**：
   - 初始化表：通过工作流调用（`/run` 接口）
   - 团队管理：通过独立 API 调用（`/api/teams/*` 接口）
4. **只有表创建成功后，才能使用团队余额功能**

## 常见问题

### Q: 如何知道表是否创建成功？
A: 调用 `action: "check"` 接口，查看 `tables` 字段中的状态。

### Q: 可以重复初始化吗？
A: 可以，重复初始化不会报错，但不会重复创建表。

### Q: 初始化失败怎么办？
A: 检查数据库连接是否正常，确保有创建表的权限。

### Q: 为什么初始化和团队管理是分开的？
A:
- 初始化：一次性操作，通过工作流调用更方便
- 团队管理：高频操作，通过独立 API 更高效
