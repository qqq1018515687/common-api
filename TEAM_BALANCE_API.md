# 团队余额功能 - API 使用指南

## 功能概述

团队余额功能允许团队成员共享金豆余额，支持：
- 团队创建和成员管理
- 团队余额充值和扣费
- 完整的消费记录追踪
- 成员消费统计和分析

## 数据库表结构

### teams（团队表）
- `id`: 团队ID
- `name`: 团队名称
- `balance`: 团队金豆余额
- `total_consumed`: 团队总消费
- `member_count`: 成员数量
- `status`: 状态（active/disabled）

### team_members（团队成员表）
- `team_id`: 团队ID
- `user_id`: 用户ID
- `role`: 角色（admin/member）
- `total_consumed`: 该成员的总消费
- `joined_at`: 加入时间

### team_consumption_records（消费记录表）
- `team_id`: 团队ID
- `user_id`: 消费用户ID
- `amount`: 消费金额（正数消费，负数退款/充值）
- `balance_before`: 变动前余额
- `balance_after`: 变动后余额
- `operation_type`: 操作类型（consumption/refund/recharge）
- `related_id`: 关联ID（任务ID）
- `description`: 描述说明
- `created_at`: 创建时间

## API 接口

### 1. 团队管理

#### 创建团队
```bash
POST /api/teams
Content-Type: application/json

{
  "name": "研发团队",
  "description": "技术部门团队"
}
```

#### 查询团队列表
```bash
GET /api/teams?status=active
```

#### 查询团队信息
```bash
GET /api/teams/{team_id}
```

#### 添加成员
```bash
POST /api/teams/{team_id}/members
Content-Type: application/json

{
  "user_id": "user_xxx",
  "role": "member"
}
```

#### 移除成员
```bash
DELETE /api/teams/{team_id}/members/{user_id}
```

#### 查询团队成员列表
```bash
GET /api/teams/{team_id}/members
```

#### 查询用户所属团队
```bash
GET /api/teams/user/{user_id}/team
```

### 2. 余额管理

#### 查询团队余额
```bash
GET /api/teams/{team_id}/balance
```

响应：
```json
{
  "team_id": "team_xxx",
  "balance": 10000,
  "total_consumed": 5000,
  "recent_consumption": 200
}
```

#### 团队充值
```bash
POST /api/teams/{team_id}/recharge
Content-Type: application/json

{
  "amount": 1000,
  "payment_method": "alipay",
  "description": "充值1000金豆"
}
```

#### 扣减余额（消费）
```bash
POST /api/teams/{team_id}/deduct
Content-Type: application/json

{
  "user_id": "user_xxx",
  "amount": 10,
  "task_id": "task_xxx",
  "description": "生成图像"
}
```

#### 退款
```bash
POST /api/teams/{team_id}/refund
Content-Type: application/json

{
  "user_id": "user_xxx",
  "amount": 10,
  "task_id": "task_xxx",
  "description": "任务失败退款"
}
```

### 3. 消费记录

#### 查询消费记录
```bash
GET /api/teams/{team_id}/transactions?user_id=user_xxx&operation_type=consumption&page=1&page_size=20
```

#### 查询近N天消费记录
```bash
GET /api/teams/{team_id}/transactions/recent?days=30
```

响应：
```json
{
  "team_id": "team_xxx",
  "days": 30,
  "total_amount": 5000,
  "total_count": 150,
  "records": [...]
}
```

#### 查询成员消费统计
```bash
GET /api/teams/{team_id}/members/{user_id}/stats
```

响应：
```json
{
  "user_id": "user_xxx",
  "username": "张三",
  "role": "member",
  "total_consumed": 2000,
  "transaction_count": 50,
  "avg_consumption": 40.0,
  "recent_transactions": [...]
}
```

#### 查询团队统计
```bash
GET /api/teams/{team_id}/stats
```

响应：
```json
{
  "team_id": "team_xxx",
  "total_consumed": 5000,
  "total_transactions": 150,
  "member_count": 5,
  "top_consumers": [...]
}
```

## 使用流程

### 1. 创建团队并添加成员
```bash
# 创建团队
curl -X POST "http://localhost:8000/api/teams" \
  -H "Content-Type: application/json" \
  -d '{"name": "研发团队", "description": "技术部门"}'

# 添加成员
curl -X POST "http://localhost:8000/api/teams/team_xxx/members" \
  -H "Content-Type: application/json" \
  -d '{"user_id": "user_001", "role": "member"}'
```

### 2. 充值团队余额
```bash
curl -X POST "http://localhost:8000/api/teams/team_xxx/recharge" \
  -H "Content-Type: application/json" \
  -d '{"amount": 10000, "description": "初始充值"}'
```

### 3. 查询团队余额
```bash
curl "http://localhost:8000/api/teams/team_xxx/balance"
```

### 4. 消费扣费
```bash
curl -X POST "http://localhost:8000/api/teams/team_xxx/deduct" \
  -H "Content-Type: application/json" \
  -d '{"user_id": "user_001", "amount": 10, "description": "生成图像"}'
```

### 5. 查询消费记录
```bash
# 查询近30天消费
curl "http://localhost:8000/api/teams/team_xxx/transactions/recent?days=30"

# 查询成员统计
curl "http://localhost:8000/api/teams/team_xxx/members/user_001/stats"
```

## 权限说明

### 管理员（admin）
- 可以充值团队余额
- 可以添加/移除成员
- 可以查看所有成员的消费记录
- 可以查看团队统计

### 成员（member）
- 可以使用团队余额
- 可以查看团队余额
- 可以查看自己的消费记录
- 不能充值
- 不能查看其他成员的消费记录

## 注意事项

1. **一个用户只能属于一个团队**
   - 添加成员时会检查用户是否已在其他团队中
   - 如果用户已在其他团队，需要先移除

2. **余额不足处理**
   - 扣费前会检查余额是否充足
   - 余额不足会返回400错误

3. **数据一致性**
   - 所有余额操作都在事务中完成
   - 失败会自动回滚

4. **消费记录**
   - 所有消费、退款、充值都会记录
   - 支持按用户、类型、时间范围筛选

## 数据库迁移

执行数据库迁移：
```bash
alembic upgrade head
```

## 后续扩展

未来可以扩展的功能：
- 消费限额设置
- 余额预警通知
- 消费报表导出
- 多团队支持
