## 项目概述
- **名称**: Coze Coding 工作流
- **功能**: 基于 LangGraph 的工作流项目，包含用户管理、文件上传、历史保存、任务管理、图像自动打标、标签池管理、团队余额管理等功能

### 任务管理功能说明
- **创建任务**：注册用户可创建任务，支持存储 workflow_parameters 和 parameter_snapshot
- **更新任务**：
  - 注册用户可更新任务状态、结果、错误信息、完成时间和扣费结果
  - 支持扣费结果记录（deduction_result），包含扣费模式、预扣金额、最终金额和结算时间
  - 已适配 RunningHub 响应结构
  - **图像自动打标**：已实现但暂时禁用，需要时在 `src/graphs/graph.py` 中启用
- **删除任务**：
  - 注册用户可软删除任务（is_deleted=true）
  - **管理员**（role='admin'）可删除任何任务
  - **普通用户**（role='user'）只能删除自己的任务
- **查询任务**：注册用户可查询自己的任务列表（自动过滤已删除任务），包含扣费结果信息、场景标签和产品标签
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
| call_type_router | node.py | condition | 根据调用类型路由 | 账号管理→operation_route, 文件上传→upload, 保存历史→save, 任务管理→task_route, 工具中心→tool_route, 通知管理→system_notification_handler, 团队余额→team_init | - |
| operation_route | node.py | condition | 根据操作类型路由 | 限流检查→check_rate_limit, 更新限流→update_rate_limit, 用户注册→register_with_limit, 用户登录→get_user, 查询单个用户→get_user_by_id, 更新用户→update_user, 删除用户→delete_user, 用户列表→list_users | - |
| tool_route | node.py | condition | 根据工具类型路由 | 反推图像→reverse_image, 翻译推荐→translate_doubao, 提示词增强→prompt_enhance | - |
| task_route | node.py | condition | 根据任务操作类型路由 | 创建任务→create_task, 更新任务→update_task, 删除任务→delete_task, 查询任务列表→list_tasks | - |
| team_init | nodes/team_init_node.py | task | 团队系统初始化（创建表/检查表） | init/check→team_init, 其他操作路由到对应节点 | - |
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
| list_tasks | node.py | task | 查询任务列表 | - | - |
| check_need_tags | nodes/check_need_tags_node.py | task | 检查是否需要生成标签 | 需要标签→image_tagging, 不需要→format_response | - |
| image_tagging | nodes/image_tagging_node.py | agent | 图像标签生成（场景标签+产品标签） | - | config/image_tagging_cfg.json |
| save_image_tags | nodes/save_image_tags_node.py | task | 保存图像标签到数据库 | - | - |
| system_notification_handler | nodes/system_notification_handler_node.py | task | 系统通知处理（增删改查） | - | - |
| reverse_image | node.py | agent | 反推图像提示词 | - | config/reverse_image_cfg.json |
| translate_doubao | node.py | agent | 豆包翻译 | - | config/translate_doubao_cfg.json |
| prompt_enhance | node.py | agent | 提示词增强 | - | config/prompt_enhance_cfg.json |
| format_response | node.py | task | 格式化响应 | - | - |

**类型说明**: task(task节点) / agent(大模型) / condition(条件分支)

## 子图清单
无子图

## 集成使用
- 节点 `check_rate_limit`, `update_rate_limit`, `register_with_limit`, `get_user`, `update_user`, `delete_user`, `list_users`, `save`, `upload`, `create_task`, `update_task`, `delete_task`, `list_tasks` 使用数据库集成
- 节点 `system_notification_handler` 使用数据库集成（系统通知表）
- 节点 `team_init`, `team_manage`, `team_recharge`, `team_deduct`, `team_refund`, `team_records` 使用数据库集成（团队余额表）
- 节点 `upload`, `save`, `update_user` 使用对象存储集成（使用 StorageManager 自动分类管理）
- 节点 `reverse_image`, `translate_doubao`, `prompt_enhance` 使用大语言模型集成
- 节点 `upload` 使用内容处理集成

### 团队余额调用方式
通过工作流调用，参数示例：
```json
{
  "call_type": "team_balance",
  "action": "create_team",
  "input": {
    "team_id": "mars",
    "name": "火星团队",
    "user_id": "1001",
    "username": "张三"
  }
}
```

支持的 action：
- `init` / `check` → team_init 节点（初始化/检查表）
- `create_team` / `get_team` / `add_member` / `list_members` → team_manage 节点
- `recharge` → team_recharge 节点
- `deduct` → team_deduct 节点
- `refund` → team_refund 节点
- `get_records` / `get_stats` / `get_member_stats` → team_records 节点

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
