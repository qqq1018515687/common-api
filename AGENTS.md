## 项目概述
- **名称**: Coze Coding 工作流
- **功能**: 基于 LangGraph 的工作流项目，包含用户管理、文件上传、历史保存、任务管理、图像自动打标、标签池管理、团队余额管理、RunningHub错误分析、资金扣费系统等功能
- **仓库地址**: https://github.com/qqq1018515687/common-api
- **推送认证**: 需要在 remote URL 中附带 GitHub Personal Access Token，或通过其他方式认证

### 关键业务标识
- **团队 team_id**: `Mars`（注意：Mars 是 team_id 字段，不是 name 字段，查询时用 `WHERE id = 'Mars'`）
- **团队充值 SQL 模板**：
```sql
-- 1. 团队余额 +{金额}
UPDATE teams SET balance = balance + {金额} WHERE id = 'Mars';

-- 2. 充值记录
INSERT INTO team_consumption_records (id, team_id, user_id, amount, balance_before, balance_after, operation_type, description, created_at, username, status)
SELECT
  gen_random_uuid()::text,
  'Mars',
  'system',
  {金额},
  t.balance - {金额},
  t.balance,
  'recharge',
  '团队充值{金额}',
  now(),
  'system',
  'completed'
FROM teams t WHERE t.id = 'Mars';
```
- **用户注册 SQL 模板**：
```sql
SELECT setval('users_id_seq', (SELECT MAX(id) FROM users));

INSERT INTO users (user_id, username, password_hash, phone, team_id, role, gold_credits, silver_credits, account_status)
VALUES ('{10位随机数字}', '{姓名}', '{bcrypt哈希}', '{手机号}', 'Mars', 'admin', 0, 9999, 'active');
```
- **密码哈希生成**：`python3 -c "import bcrypt; print(bcrypt.hashpw('{密码}'.encode('utf-8'), bcrypt.gensalt()).decode('utf-8'))"`
- **user_id 生成规则**：10位随机数字

### 任务管理功能说明
- **创建任务**：注册用户可创建任务，支持存储 workflow_parameters 和 parameter_snapshot
- **更新任务**：
  - 注册用户可更新任务状态、结果、错误信息、完成时间和扣费结果
  - 支持扣费结果记录（deduction_result），包含扣费模式、预扣金额、最终金额和结算时间
  - 已适配 RunningHub 响应结构
  - **图像自动打标**：已实现但暂时禁用，需要时在 `src/graphs/graph.py` 中启用
- **user_friendly_message 持久化**：
  - 任务表新增 `user_friendly_message` 字段（TEXT，nullable）
  - `update_task` 支持接收并保存该字段
  - `list_tasks` 查询时返回该字段
  - `runninghub_error_analysis` 节点输出该字段到 result 中
  - 页面刷新后从数据库加载历史任务时可恢复 LLM 友好提示
- **删除任务**：
  - 注册用户可软删除任务（is_deleted=true）
  - **管理员**（role='admin'）可删除任何任务
  - **普通用户**（role='user'）只能删除自己的任务
- **查询任务**：注册用户可查询自己的任务列表（自动过滤已删除任务），包含扣费结果信息、场景标签和产品标签
  - **游标分页**：支持基于时间戳的游标分页，通过 `before_time` 参数实现滚动加载
  - **分页参数**：
    - `limit`：每页数量，默认50，最大300
    - `before_time`：游标，查询早于该时间戳的记录
  - **返回字段**：
    - `has_more`：是否还有更多数据
    - `next_before_time`：下一次请求使用的游标（最后一条记录的 created_at）
- **权限控制**：所有任务操作仅限已注册的活跃用户（user_id 存在且 account_status=active）
- **RunningHub 集成**：提供工具函数将 RunningHub 响应转换为任务更新格式（详见 `docs/RunningHub_RESPONSE_CONVERSION.md`）
- **图像标签功能**：
  - **场景标签**：座椅场景、睡眠场景、躺卧场景、驾驶场景、办公场景、客厅场景、装饰场景、户外场景
  - **产品标签**：腰靠、腿枕、融蜡灯、脚垫、枕头、坐垫
  - **触发条件**：任务状态为 `completed` 且结果包含图像URL
  - **存储方式**：存储在 tasks 表的 `scene_tags` 和 `product_tags` 字段（JSON数组格式）
  - **标签池版本管理**：支持标签池的版本化管理，可追溯历史版本
  - **自动标签发现**：通过分析历史任务数据，自动发现高频新场景标签
  - **批量重打标**：更新标签池后，可批量重打标旧任务

### 标签池管理功能说明
- **版本管理**：
  - 标签池支持多版本管理，每个版本记录标签列表
  - 支持激活/回滚版本，可随时切换到历史版本
  - 所有变更记录在 `tag_change_history` 表中
- **标签分析**：
  - 自动分析标签使用频率，发现高频但未在标签池中的场景
  - 支持时间范围限制（默认30天，可自定义或分析所有数据）
  - 支持阈值控制（最小任务数、最小置信度）
  - 生成标签优化建议
- **自动更新**：
  - 一键应用标签更新，自动创建新版本
  - 批量重打标旧任务（可选）
  - 失败任务记录，支持重试
- **使用方式**：
  - **命令行**：`python scripts/analyze_tags_enhanced.py`
  - **无需前端**：开发者模式即可完成所有操作

### 团队余额管理功能说明
- **团队管理**：
  - 创建团队、添加/移除成员
  - 查询团队信息、成员列表
  - 支持角色管理（admin/member）
- **余额管理**：
  - 团队充值：管理员为团队充值金豆
  - 余额查询：查看团队余额、总消费
  - 扣减余额：任务执行时从团队余额扣费
- **退款功能**：
  - 任务失败时可将金额退还到团队账户
  - 支持全额/部分退款
  - 需关联原消费记录ID
  - 更新成员累计消费统计
- **消费记录**：
  - 记录每一笔消费（金额、时间、用户、说明）
  - 支持按时间段查询（7天、30天等）
  - 支持按用户ID筛选记录（不传则返回全部）
  - 成员消费统计（总消费、消费排行）
  - 团队消费统计
- **数据结构**：
  - `teams` 表：团队基本信息和余额
  - `team_members` 表：团队成员关系
  - `team_consumption_records` 表：消费记录明细
- **使用方式**：
  - **工作流节点**：通过 `call_type=team_balance` + `action` 调用不同节点
  - **节点列表**：team_init（初始化）、team_manage（团队管理）、team_recharge（充值）、team_deduct（扣费）、team_records（消费记录）

### 节点清单
| 节点名 | 文件位置 | 类型 | 功能描述 | 分支逻辑 | 配置文件 |
|-------|---------|------|---------|---------|---------|
| unpack_input_data | node.py | task | 解包输入数据 | - | - |
| call_type_router | node.py | condition | 根据调用类型路由 | 账号管理→operation_route, 文件上传→upload, 保存历史→save, 任务管理→task_route, 工具中心→tool_route, 通知管理→system_notification_handler, 团队余额→team_route, RunningHub错误分析→runninghub_error_analysis, 资金扣费→billing_route | - |
| operation_route | node.py | condition | 根据操作类型路由 | 限流检查→check_rate_limit, 更新限流→update_rate_limit, 用户注册→register_with_limit, 用户登录→get_user, 查询单个用户→get_user_by_id, 更新用户→update_user, 删除用户→delete_user, 用户列表→list_users | - |
| tool_route | node.py | condition | 根据工具类型路由 | 反推图像→reverse_image, 翻译推荐→translate_doubao, 提示词增强→prompt_enhance | - |
| task_route | node.py | condition | 根据任务操作类型路由 | 创建任务→create_task, 更新任务→update_task, 删除任务→delete_task, 查询任务列表→list_tasks | - |
| team_route | nodes/team_route_node.py | condition | 根据团队操作类型路由 | 初始化团队→team_init, 团队管理→team_manage, 团队充值→team_recharge, 团队扣费→team_deduct, 团队退款→team_refund, 消费记录→team_records | - |
| team_init | nodes/team_init_node.py | task | 团队系统初始化（创建表/检查表） | - | - |
| team_manage | nodes/team_manage_node.py | task | 团队管理（创建团队/查询/添加成员/成员列表） | - | - |
| team_recharge | nodes/team_recharge_node.py | task | 团队充值 | - | - |
| team_deduct | nodes/team_deduct_node.py | task | 团队扣费（任务消费） | - | - |
| team_refund | nodes/team_refund_node.py | task | 团队退款（任务失败时） | - | - |
| team_records | nodes/team_records_node.py | task | 团队消费记录查询（支持user_id筛选） | - | - |
| check_rate_limit | node.py | task | 检查限流 | - | - |
| update_rate_limit | node.py | task | 更新限流 | - | - |
| register_with_limit | node.py | task | 用户注册（带限流检查） | - | - |
| get_user | node.py | task | 获取用户信息（登录） | - | - |
| get_user_by_id | node.py | task | 根据用户ID查询单个用户 | - | - |
| update_user | node.py | task | 更新用户信息（支持Base64头像自动转换） | - | - |
| delete_user | node.py | task | 删除用户 | - | - |
| list_users | node.py | task | 用户列表 | - | - |
| upload | node.py | task | 文件上传 | - | - |
| save | node.py | task | 保存历史记录 | - | - |
| create_task | node.py | task | 创建任务 | - | - |
| update_task | node.py | task | 更新任务 | - | - |
| delete_task | node.py | task | 删除任务 | - | - |
| list_tasks | node.py | task | 查询任务列表（支持游标分页，过滤无媒体结果） | - | - |
| check_need_tags | nodes/check_need_tags_node.py | task | 检查是否需要生成标签 | 需要标签→image_tagging, 不需要→format_response | - |
| image_tagging | nodes/image_tagging_node.py | agent | 图像标签生成（场景标签+产品标签） | - | config/image_tagging_cfg.json |
| save_image_tags | nodes/save_image_tags_node.py | task | 保存图像标签到数据库 | - | - |
| system_notification_handler | nodes/system_notification_handler_node.py | task | 系统通知处理（增删改查） | - | - |
| reverse_image | node.py | agent | 反推图像提示词 | - | config/reverse_image_cfg.json |
| translate_doubao | node.py | agent | 豆包翻译 | - | config/translate_doubao_cfg.json |
| prompt_enhance | node.py | agent | 提示词增强 | - | config/prompt_enhance_cfg.json |
| format_response | node.py | task | 格式化响应 | - | - |
| runninghub_error_analysis | nodes/runninghub_error_analysis_node.py | agent | RunningHub错误分析（LLM分析失败响应生成友好说明） | - | config/runninghub_error_analysis_cfg.json |
| billing_route | nodes/billing_route_node.py | condition | 资金扣费二级路由 | 余额查询→get_balance, 扣费→billing_deduct, 退款→billing_refund, 结算→billing_settle | - |
| get_balance | nodes/get_balance_node.py | task | 查询用户余额（personal_gold/personal_silver/team_gold） | - | - |
| billing_deduct | nodes/billing_deduct_node.py | task | 原子扣费（行锁+幂等+余额校验） | - | - |
| billing_refund | nodes/billing_refund_node.py | task | 退款（幂等+原记录校验+不可重复退） | - | - |
| billing_settle | nodes/billing_settle_node.py | task | 结算（仅personal_silver退差额，gold预扣即最终） | - | - |

**类型说明**: task(task节点) / agent(大模型) / condition(条件分支)

## 子图清单
无子图

## 集成使用
- 节点 `check_rate_limit`, `update_rate_limit`, `register_with_limit`, `get_user`, `update_user`, `delete_user`, `list_users`, `save`, `upload`, `create_task`, `update_task`, `delete_task`, `list_tasks` 使用数据库集成
- 节点 `system_notification_handler` 使用数据库集成（系统通知表）
- 节点 `team_init`, `team_manage`, `team_recharge`, `team_deduct`, `team_refund`, `team_records` 使用数据库集成（团队余额表）
- 节点 `upload`, `save`, `update_user` 使用对象存储集成（使用 StorageManager 自动分类管理）
- 节点 `reverse_image`, `translate_doubao`, `prompt_enhance` 使用大语言模型集成
- 节点 `runninghub_error_analysis` 使用大语言模型集成
- 节点 `get_balance`, `billing_deduct`, `billing_refund`, `billing_settle` 使用数据库集成（billing_records 表 + users/teams 余额）
- 节点 `upload` 使用内容处理集成

### 团队余额调用方式
通过工作流调用，参数示例：
```json
{
  "call_type": "team_balance",
  "input": {
    "operation_type": "create_team",
    "team_id": "mars",
    "name": "火星团队",
    "user_id": "1001",
    "username": "张三"
  }
}
```

支持的 operation_type：
- `init` → team_init 节点（初始化表）
- `create_team` / `get_team` / `add_member` / `list_members` → team_manage 节点
- `recharge` → team_recharge 节点
- `deduct` → team_deduct 节点
- `refund` → team_refund 节点
- `get_records` / `get_stats` → team_records 节点

### 资金扣费系统调用方式
通过工作流调用，`call_type: billing`，支持 4 种 operation_type：

#### 1. 查询余额 `get_balance`
```json
{
  "call_type": "billing",
  "input": {
    "operation_type": "get_balance",
    "user_id": "8807043569"
  }
}
```

#### 2. 扣费 `deduct`
```json
{
  "call_type": "billing",
  "input": {
    "operation_type": "deduct",
    "user_id": "8807043569",
    "credit_type": "personal_silver",
    "amount": 100,
    "idempotency_key": "task_abc123_deduct",
    "service_secret": "mars_billing_2024",
    "description": "任务扣费",
    "task_id": "abc123"
  }
}
```
- `credit_type`：`personal_gold` / `personal_silver` / `team_gold`
- `amount`：正整数
- `idempotency_key`：幂等键（必填，唯一约束），重复请求返回原结果
- `service_secret`：服务密钥（必填），当前为 `mars_billing_2024`
- 余额校验：`personal_gold` ≥ 0，`personal_silver` ≥ -50，`team_gold` ≥ 0

#### 3. 退款 `refund`
```json
{
  "call_type": "billing",
  "input": {
    "operation_type": "refund",
    "user_id": "8807043569",
    "original_record_id": "原扣费记录ID",
    "idempotency_key": "task_abc123_refund",
    "service_secret": "mars_billing_2024",
    "description": "任务失败退款"
  }
}
```
- 必须关联原始 deduct 记录
- 不可重复退款（original_record_id + operation_type=refund 唯一校验）

#### 4. 结算 `settle`
```json
{
  "call_type": "billing",
  "input": {
    "operation_type": "settle",
    "user_id": "8807043569",
    "original_record_id": "原扣费记录ID",
    "final_amount": 60,
    "idempotency_key": "task_abc123_settle",
    "service_secret": "mars_billing_2024",
    "description": "预扣100结算60，退差额40"
  }
}
```
- `final_amount`：最终实际消费金额（须 < 原扣费金额）
- 仅 `personal_silver` 支持结算退差额；`gold`/`team_gold` 预扣即最终

#### 错误码
| 错误码 | 说明 |
|--------|------|
| INVALID_AMOUNT | 金额无效或不支持的 credit_type |
| MISSING_IDEMPOTENCY_KEY | 缺少幂等键 |
| UNAUTHORIZED | service_secret 无效 |
| USER_NOT_FOUND | 用户不存在 |
| TEAM_NOT_FOUND | 团队不存在（team_gold 操作时） |
| INSUFFICIENT_BALANCE | 余额不足 |
| ORIGINAL_RECORD_NOT_FOUND | 原始扣费记录不存在 |
| ALREADY_REFUNDED | 该记录已退款 |
| INTERNAL_ERROR | 内部错误 |

#### 数据库表 `billing_records`
| 字段 | 类型 | 说明 |
|------|------|------|
| id | VARCHAR(64) PK | 记录ID |
| idempotency_key | VARCHAR(128) UNIQUE | 幂等键 |
| user_id | VARCHAR(36) | 用户ID |
| team_id | VARCHAR(64) | 团队ID |
| operation_type | VARCHAR(20) | 操作类型 |
| credit_type | VARCHAR(20) | 积分类型 |
| amount | BIGINT | 金额 |
| balance_before | BIGINT | 操作前余额 |
| balance_after | BIGINT | 操作后余额 |
| related_id | VARCHAR(64) | 关联记录ID |
| task_id | VARCHAR(36) | 关联任务ID |
| description | VARCHAR(255) | 描述 |
| extra_data | JSON | 扩展数据 |
| status | VARCHAR(20) | 状态 |
| created_at | TIMESTAMPTZ | 创建时间 |

### RunningHub 错误分析调用方式
通过工作流调用，参数示例：
```json
{
  "call_type": "runninghub_error_analysis",
  "input": {
    "error_response": {
      "code": 805,
      "msg": "APIKEY_TASK_STATUS_ERROR",
      "data": {
        "failedReason": {
          "exception_type": "TypeError",
          "node_name": "SONIC_PreData",
          "exception_message": "missing 2 required positional arguments: 'clip_vision' and 'vae'"
        }
      }
    }
  }
}
```

### 系统通知功能说明
- **获取有效通知**：查询当前有效的通知列表（支持时间范围筛选）
- **获取所有通知**：查询所有通知（管理后台用）
- **创建通知**：创建新的系统通知
- **更新通知**：更新现有通知
- **删除通知**：软删除通知（设置 is_active=false）
- **通知类型**：info（信息）、warning（警告）、error（错误）、maintenance（维护）、update（更新）
- **优先级**：low（低）、medium（中）、high（高）、urgent（紧急）
- **目标受众**：all（所有用户）、logged_in（注册用户）、guest（访客）、admin（管理员）

### 注册限流规则说明
- **限流维度**：仅限手机号维度，**已移除IP地址限制**
- **手机号限流规则（容错机制）**：
  - 警告阈值：10分钟内 3次（不封禁，仅记录）
  - 封禁阈值：10分钟内 5次（封禁10分钟）
  - 警告阈值：1小时内 5次（不封禁，仅记录）
  - 封禁阈值：1小时内 10次（封禁1小时）
- **容错机制**：
  - 同一手机号在不同IP下会复用最早记录，避免因IP变化导致的重复计数
  - 达到警告阈值不会封禁，只有达到封禁阈值才封禁
  - 封禁时间：10分钟或1小时（根据超限情况）
- **限流机制**：
  - 使用滑动窗口计算请求次数
  - 超限后返回相应的错误提示
  - 封禁状态会自动过期

## 对象存储管理
- **存储管理器**: `src/storage/storage_manager.py` - 提供分类存储、自动过期、清理功能
- **文件分类**:
  - `avatars/` - 用户头像（永久存储，10年，public-read）
  - `uploads/` - 用户上传文件（7天过期）
  - `temp/` - 临时文件（1天过期）
- **清理工具**: 
  - `scripts/cleanup_storage.py` - 清理过期的新文件
  - `scripts/clean_old_data.py` - 安全清理旧数据（只保留头像，删除其他）
- **迁移工具**: `scripts/migrate_old_data.py` - 迁移旧数据到新方案
- **使用文档**: 
  - `docs/STORAGE_GUIDE.md` - 详细使用指南
  - `docs/STORAGE_SUMMARY.md` - 方案总结和常见问题
  - `docs/OLD_VS_NEW_DATA.md` - 旧数据 vs 新数据对比
  - `docs/CLEAN_OLD_DATA_GUIDE.md` - 安全清理旧数据指南

## 文档索引
| 文档 | 路径 | 说明 |
|------|------|------|
| 数据库迁移指南 | `docs/ALEMBIC_GUIDE.md` | Alembic 迁移工具使用指南 |
| RunningHub 响应转换 | `docs/RunningHub_RESPONSE_CONVERSION.md` | RunningHub API 响应转换工具与示例 |
| 扣费结果字段说明 | `docs/DEDUCTION_RESULT_FIELD.md` | Tasks 表 deduction_result 字段结构和使用指南 |
