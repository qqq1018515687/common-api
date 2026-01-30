## 项目概述
- **名称**: Coze Coding 工作流
- **功能**: 基于 LangGraph 的工作流项目，包含用户管理、文件上传、历史保存等功能

### 节点清单
| 节点名 | 文件位置 | 类型 | 功能描述 | 分支逻辑 | 配置文件 |
|-------|---------|------|---------|---------|---------|
| unpack_input_data | node.py | task | 解包输入数据 | - | - |
| call_type_router | node.py | condition | 根据调用类型路由 | 账号管理→operation_route, 文件上传→upload, 保存历史→save, 工具中心→tool_route | - |
| operation_route | node.py | condition | 根据操作类型路由 | 限流检查→check_rate_limit, 更新限流→update_rate_limit, 用户注册→register_with_limit, 用户登录→get_user, 更新用户→update_user, 删除用户→delete_user, 用户列表→list_users | - |
| tool_route | node.py | condition | 根据工具类型路由 | 反推图像→reverse_image, 翻译推荐→translate_doubao, 提示词增强→prompt_enhance | - |
| check_rate_limit | node.py | task | 检查限流 | - | - |
| update_rate_limit | node.py | task | 更新限流 | - | - |
| register_with_limit | node.py | task | 用户注册（带限流检查） | - | - |
| get_user | node.py | task | 获取用户信息 | - | - |
| update_user | node.py | task | 更新用户信息 | - | - |
| delete_user | node.py | task | 删除用户 | - | - |
| list_users | node.py | task | 用户列表 | - | - |
| upload | node.py | task | 文件上传 | - | - |
| save | node.py | task | 保存历史记录 | - | - |
| reverse_image | node.py | agent | 反推图像提示词 | - | config/reverse_image_cfg.json |
| translate_doubao | node.py | agent | 豆包翻译 | - | config/translate_doubao_cfg.json |
| prompt_enhance | node.py | agent | 提示词增强 | - | config/prompt_enhance_cfg.json |
| format_response | node.py | task | 格式化响应 | - | - |

**类型说明**: task(task节点) / agent(大模型) / condition(条件分支)

## 子图清单
无子图

## 集成使用
- 节点 `check_rate_limit`, `update_rate_limit`, `register_with_limit`, `get_user`, `update_user`, `delete_user`, `list_users`, `save`, `upload` 使用数据库集成
- 节点 `upload`, `save` 使用对象存储集成
- 节点 `reverse_image`, `translate_doubao`, `prompt_enhance` 使用大语言模型集成
- 节点 `upload` 使用内容处理集成
