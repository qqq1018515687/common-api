## 项目概述
- **名称**: Coze Coding 工作流
- **功能**: 基于 LangGraph 的工作流项目，包含用户管理、文件上传、历史保存、任务管理等功能

### 任务管理功能说明
- **创建任务**：注册用户可创建任务，支持存储 workflow_parameters 和 parameter_snapshot
- **更新任务**：
  - 注册用户可更新任务状态、结果、错误信息、完成时间和扣费结果
  - 支持扣费结果记录（deduction_result），包含扣费模式、预扣金额、最终金额和结算时间
  - **deduction_result 保护机制**：更新时如果未传入或传入 null，不会覆盖已有的 deduction_result 值
  - 已适配 RunningHub 响应结构
- **删除任务**：
  - 注册用户可软删除任务（is_deleted=true）
  - **管理员**（role='admin'）可删除任何任务
  - **普通用户**（role='user'）只能删除自己的任务
- **查询任务**：注册用户可查询自己的任务列表（自动过滤已删除任务），包含扣费结果信息
- **权限控制**：所有任务操作仅限已注册的活跃用户（user_id 存在且 account_status=active）
- **RunningHub 集成**：提供工具函数将 RunningHub 响应转换为任务更新格式（详见 `docs/RunningHub_RESPONSE_CONVERSION.md`）

### 节点清单
| 节点名 | 文件位置 | 类型 | 功能描述 | 分支逻辑 | 配置文件 |
|-------|---------|------|---------|---------|---------|
| unpack_input_data | node.py | task | 解包输入数据 | - | - |
| call_type_router | node.py | condition | 根据调用类型路由 | 账号管理→operation_route, 文件上传→upload, 保存历史→save, 任务管理→task_route, 工具中心→tool_route | - |
| operation_route | node.py | condition | 根据操作类型路由 | 限流检查→check_rate_limit, 更新限流→update_rate_limit, 用户注册→register_with_limit, 用户登录→get_user, 更新用户→update_user, 删除用户→delete_user, 用户列表→list_users | - |
| tool_route | node.py | condition | 根据工具类型路由 | 反推图像→reverse_image, 翻译推荐→translate_doubao, 提示词增强→prompt_enhance | - |
| task_route | node.py | condition | 根据任务操作类型路由 | 创建任务→create_task, 更新任务→update_task, 删除任务→delete_task, 查询任务列表→list_tasks | - |
| check_rate_limit | node.py | task | 检查限流 | - | - |
| update_rate_limit | node.py | task | 更新限流 | - | - |
| register_with_limit | node.py | task | 用户注册（带限流检查） | - | - |
| get_user | node.py | task | 获取用户信息 | - | - |
| update_user | node.py | task | 更新用户信息 | - | - |
| delete_user | node.py | task | 删除用户 | - | - |
| list_users | node.py | task | 用户列表 | - | - |
| upload | node.py | task | 文件上传 | - | - |
| save | node.py | task | 保存历史记录 | - | - |
| create_task | node.py | task | 创建任务 | - | - |
| update_task | node.py | task | 更新任务 | - | - |
| delete_task | node.py | task | 删除任务 | - | - |
| list_tasks | node.py | task | 查询任务列表 | - | - |
| reverse_image | node.py | agent | 反推图像提示词 | - | config/reverse_image_cfg.json |
| translate_doubao | node.py | agent | 豆包翻译 | - | config/translate_doubao_cfg.json |
| prompt_enhance | node.py | agent | 提示词增强 | - | config/prompt_enhance_cfg.json |
| format_response | node.py | task | 格式化响应 | - | - |

**类型说明**: task(task节点) / agent(大模型) / condition(条件分支)

## 子图清单
无子图

## 集成使用
- 节点 `check_rate_limit`, `update_rate_limit`, `register_with_limit`, `get_user`, `update_user`, `delete_user`, `list_users`, `save`, `upload`, `create_task`, `update_task`, `delete_task`, `list_tasks` 使用数据库集成
- 节点 `upload`, `save` 使用对象存储集成
- 节点 `reverse_image`, `translate_doubao`, `prompt_enhance` 使用大语言模型集成
- 节点 `upload` 使用内容处理集成

## 文档索引
| 文档 | 路径 | 说明 |
|------|------|------|
| 数据库迁移指南 | `docs/ALEMBIC_GUIDE.md` | Alembic 迁移工具使用指南 |
| RunningHub 响应转换 | `docs/RunningHub_RESPONSE_CONVERSION.md` | RunningHub API 响应转换工具与示例 |
| 扣费结果字段说明 | `docs/DEDUCTION_RESULT_FIELD.md` | Tasks 表 deduction_result 字段结构和使用指南 |
