from typing import Literal, Optional, List
from pydantic import BaseModel, Field
from utils.file.file import File


class InputData(BaseModel):
    """输入数据对象，包含所有业务字段"""
    action: Optional[str] = Field(default=None, description="操作类型：init/check/create_team/get_team/add_member/list_members/recharge/deduct/refund/get_records/get_stats（团队余额等使用）")
    username: Optional[str] = Field(default=None, description="用户名")
    password: Optional[str] = Field(default=None, description="密码")
    file: Optional[File] = Field(default=None, description="上传的文件（upload/tool 使用）")
    file_list: Optional[List[File]] = Field(default=None, description="文件列表（提示词增强使用）")
    user_id: Optional[str] = Field(default=None, description="用户 ID（save/history/update_user/delete_user 使用）")
    runninghub_link: Optional[str] = Field(default=None, description="RunningHub 链接（save 使用）")
    tool_type: Optional[str] = Field(default=None, description="工具类型：reverse_image/translate_doubao/translate_flash/prompt_enhance")
    prompt: Optional[str] = Field(default=None, description="提示词/待翻译文本（tool 使用）")
    operation_type: Optional[str] = Field(default=None, description="操作类型：check_rate_limit/register/login/update_user/delete_user/list_users/create_task/update_task/delete_task/list_tasks/get_active/get_all/create/update/delete")

    # 用户管理相关字段
    phone: Optional[str] = Field(default=None, description="手机号")
    ip: Optional[str] = Field(default=None, description="IP地址")
    password_hash: Optional[str] = Field(default=None, description="密码哈希")
    avatar: Optional[str] = Field(default=None, description="头像URL")
    team_id: Optional[str] = Field(default=None, description="团队ID")
    gold_credits: Optional[int] = Field(default=None, description="金豆余额")
    silver_credits: Optional[int] = Field(default=None, description="银豆余额")
    role: Optional[str] = Field(default=None, description="用户角色")
    tier: Optional[str] = Field(default=None, description="用户等级")
    account_status: Optional[str] = Field(default=None, description="账号状态")
    updates: Optional[dict] = Field(default=None, description="更新字段")
    operator_role: Optional[str] = Field(default=None, description="操作者角色")
    operator_user_id: Optional[str] = Field(default=None, description="操作者用户ID")
    limit: Optional[int] = Field(default=None, description="每页数量")
    filter: Optional[dict] = Field(default=None, description="筛选条件")

    # 任务时间范围查询字段
    start_time: Optional[int] = Field(default=None, description="查询开始时间戳（毫秒，13位整数）")
    end_time: Optional[int] = Field(default=None, description="查询结束时间戳（毫秒，13位整数）")

    # 任务管理相关字段
    task_id: Optional[str] = Field(default=None, description="任务ID（update_task/delete_task 使用）")
    task_data: Optional[dict] = Field(default=None, description="任务数据（create_task 使用）")
    task_updates: Optional[dict] = Field(default=None, description="任务更新数据（update_task 使用）")

    # 系统通知相关字段
    notification_id: Optional[str] = Field(default=None, description="通知ID（update_notification/delete_notification 使用）")
    notification_data: Optional[dict] = Field(default=None, description="通知数据（create_notification/update_notification 使用）")
    current_time: Optional[int] = Field(default=None, description="当前时间戳（用于筛选有效通知）")

    # 团队余额相关字段
    amount: Optional[int] = Field(default=None, description="金额（充值/扣费/退款使用）")
    description: Optional[str] = Field(default=None, description="操作描述")
    days: Optional[int] = Field(default=None, description="查询天数")
    name: Optional[str] = Field(default=None, description="团队名称（创建团队使用）")
    target_user_id: Optional[str] = Field(default=None, description="目标用户ID")
    target_username: Optional[str] = Field(default=None, description="目标用户名")
    target_role: Optional[str] = Field(default=None, description="目标角色")
    original_record_id: Optional[str] = Field(default=None, description="原消费记录ID（退款用）")
    reason: Optional[str] = Field(default=None, description="退款原因")


class GlobalState(BaseModel):
    """全局状态定义"""
    call_type: str = Field(..., description="调用类型：account_management/upload/save/tool/user_task_management/notification_management/system_init")
    input: Optional[InputData] = Field(default=None, description="业务数据对象")
    username: Optional[str] = Field(default=None, description="用户名")
    password: Optional[str] = Field(default=None, description="密码")
    file: Optional[File] = Field(default=None, description="上传的文件（upload/tool 使用）")
    file_list: Optional[List[File]] = Field(default=None, description="文件列表（提示词增强使用）")
    user_id: Optional[str] = Field(default=None, description="用户 ID（save/update_user/delete_user/create_task/list_tasks 使用）")
    runninghub_link: Optional[str] = Field(default=None, description="RunningHub 链接（save 使用）")
    tool_type: Optional[str] = Field(default=None, description="工具类型：reverse_image/translate_doubao/translate_flash/prompt_enhance")
    operation_type: Optional[str] = Field(default=None, description="操作类型：check_rate_limit/register/login/update_user/delete_user/list_users/create_task/update_task/delete_task/list_tasks")
    action: Optional[str] = Field(default=None, description="操作类型：init/check（系统初始化使用）")
    prompt: Optional[str] = Field(default=None, description="提示词/待翻译文本（tool 使用）")
    result: dict = Field(default={}, description="各节点的结果")
    response_data: Optional[dict] = Field(default=None, description="统一响应数据")

    # 用户管理相关字段
    phone: Optional[str] = Field(default=None, description="手机号")
    ip: Optional[str] = Field(default=None, description="IP地址")
    password_hash: Optional[str] = Field(default=None, description="密码哈希")
    avatar: Optional[str] = Field(default=None, description="头像URL")
    team_id: Optional[str] = Field(default=None, description="团队ID")
    gold_credits: Optional[int] = Field(default=None, description="金豆余额")
    silver_credits: Optional[int] = Field(default=None, description="银豆余额")
    role: Optional[str] = Field(default=None, description="用户角色")
    tier: Optional[str] = Field(default=None, description="用户等级")
    account_status: Optional[str] = Field(default=None, description="账号状态")
    updates: Optional[dict] = Field(default=None, description="更新字段")
    operator_role: Optional[str] = Field(default=None, description="操作者角色")
    operator_user_id: Optional[str] = Field(default=None, description="操作者用户ID")
    limit: Optional[int] = Field(default=None, description="每页数量")
    filter: Optional[dict] = Field(default=None, description="筛选条件")

    # 任务时间范围查询字段
    start_time: Optional[int] = Field(default=None, description="查询开始时间戳（毫秒，13位整数）")
    end_time: Optional[int] = Field(default=None, description="查询结束时间戳（毫秒，13位整数）")

    # 任务管理相关字段
    task_id: Optional[str] = Field(default=None, description="任务ID（update_task/delete_task 使用）")
    task_data: Optional[dict] = Field(default=None, description="任务数据（create_task 使用）")
    task_updates: Optional[dict] = Field(default=None, description="任务更新数据（update_task 使用）")

    # 系统通知相关字段
    notification_id: Optional[str] = Field(default=None, description="通知ID（update_notification/delete_notification 使用）")
    notification_data: Optional[dict] = Field(default=None, description="通知数据（create_notification/update_notification 使用）")
    current_time: Optional[int] = Field(default=None, description="当前时间戳（用于筛选有效通知）")

    # 团队余额相关字段（用于团队余额操作）
    amount: Optional[int] = Field(default=None, description="金额（充值/扣费/退款使用）")
    description: Optional[str] = Field(default=None, description="操作描述")
    days: Optional[int] = Field(default=None, description="查询天数")
    name: Optional[str] = Field(default=None, description="团队名称（创建团队使用）")
    target_user_id: Optional[str] = Field(default=None, description="目标用户ID")
    target_username: Optional[str] = Field(default=None, description="目标用户名")
    target_role: Optional[str] = Field(default=None, description="目标角色")
    original_record_id: Optional[str] = Field(default=None, description="原消费记录ID（退款用）")
    reason: Optional[str] = Field(default=None, description="退款原因")


class GraphInput(BaseModel):
    """工作流的输入"""
    call_type: str = Field(..., description="调用类型：account_management/upload/save/history/tool/task_management/notification_management/team_balance")
    tool_type: Optional[str] = Field(default=None, description="工具类型：reverse_image/translate_doubao/translate_flash/prompt_enhance")
    action: Optional[str] = Field(default=None, description="操作类型：init/check/create_team/get_team/add_member/list_members/recharge/deduct/get_records/get_stats（团队余额使用）")
    input: Optional[InputData] = Field(default=None, description="业务数据对象")


class GraphOutput(BaseModel):
    """工作流的输出"""
    response_data: dict = Field(..., description="统一响应数据：{code, msg, data}")


# ============ 用户管理节点 ============

# 限流检查节点
class CheckRateLimitInput(BaseModel):
    """限流检查节点的输入"""
    phone: str = Field(..., description="手机号")
    ip: str = Field(..., description="IP地址")


class CheckRateLimitOutput(BaseModel):
    """限流检查节点的输出"""
    result: dict = Field(default={}, description="检查结果")
    allowed: bool = Field(default=False, description="是否允许")
    reason: Optional[str] = Field(default=None, description="拒绝原因")
    user_exists: bool = Field(default=False, description="用户是否已存在")


# 创建用户节点
class CreateUserInput(BaseModel):
    """创建用户节点的输入"""
    phone: str = Field(..., description="手机号")
    password_hash: str = Field(..., description="密码哈希")
    username: str = Field(..., description="用户名")
    avatar: str = Field(..., description="头像URL")
    team_id: Optional[str] = Field(default=None, description="团队ID")
    gold_credits: int = Field(default=0, description="金豆余额")
    silver_credits: int = Field(default=10000, description="银豆余额")
    role: str = Field(default="user", description="用户角色")
    tier: str = Field(default="standard", description="用户等级")
    account_status: str = Field(default="active", description="账号状态")


class CreateUserOutput(BaseModel):
    """创建用户节点的输出"""
    result: dict = Field(default={}, description="创建结果")
    success: bool = Field(default=True, description="是否成功")
    user: Optional[dict] = Field(default=None, description="用户数据")
    error: Optional[str] = Field(default=None, description="错误信息")


# 更新限流记录节点
class UpdateRateLimitInput(BaseModel):
    """更新限流记录节点的输入"""
    phone: str = Field(..., description="手机号")
    ip: str = Field(..., description="IP地址")


class UpdateRateLimitOutput(BaseModel):
    """更新限流记录节点的输出"""
    result: dict = Field(default={}, description="更新结果")
    success: bool = Field(..., description="是否成功")
    blocked: bool = Field(default=False, description="是否被封禁")


# 注册组合节点
class RegisterWithLimitInput(BaseModel):
    """注册组合节点的输入"""
    phone: Optional[str] = Field(default=None, description="手机号")
    ip: Optional[str] = Field(default=None, description="IP地址")
    password_hash: Optional[str] = Field(default=None, description="密码哈希")
    username: Optional[str] = Field(default=None, description="用户名")
    avatar: Optional[str] = Field(default=None, description="头像URL")


class RegisterWithLimitOutput(BaseModel):
    """注册组合节点的输出"""
    result: dict = Field(default={}, description="注册结果")
    success: bool = Field(default=True, description="是否成功")
    user: Optional[dict] = Field(default=None, description="用户数据")
    error: Optional[str] = Field(default=None, description="错误信息")


# 查询用户节点（登录）
class GetUserInput(BaseModel):
    """查询用户节点的输入"""
    phone: str = Field(..., description="手机号")
    password: str = Field(..., description="密码")


class GetUserOutput(BaseModel):
    """查询用户节点的输出"""
    result: dict = Field(default={}, description="查询结果")
    success: bool = Field(default=True, description="是否成功")
    user: Optional[dict] = Field(default=None, description="用户数据")
    error: Optional[str] = Field(default=None, description="错误信息")


# ============ 图像标签生成节点 ============

class ImageTaggingInput(BaseModel):
    """图像标签生成节点的输入"""
    image_url: str = Field(..., description="图像URL")
    task_id: str = Field(..., description="任务ID")


class ImageTaggingOutput(BaseModel):
    """图像标签生成节点的输出"""
    scene_tags: list = Field(default=[], description="场景标签")
    product_tags: list = Field(default=[], description="产品标签")
    success: bool = Field(default=True, description="是否成功")
    error: Optional[str] = Field(default=None, description="错误信息")
    task_id: Optional[str] = Field(default=None, description="任务ID")


# ============ 保存图像标签节点 ============

class SaveImageTagsInput(BaseModel):
    """保存图像标签节点的输入"""
    task_id: str = Field(..., description="任务ID")
    scene_tags: list = Field(default=[], description="场景标签")
    product_tags: list = Field(default=[], description="产品标签")


class SaveImageTagsOutput(BaseModel):
    """保存图像标签节点的输出"""
    success: bool = Field(default=True, description="是否成功")
    scene_tags: list = Field(default=[], description="场景标签")
    product_tags: list = Field(default=[], description="产品标签")
    error: Optional[str] = Field(default=None, description="错误信息")


# ============ 检查是否需要生成标签节点 ============

class CheckNeedTagsInput(BaseModel):
    """检查是否需要生成标签节点的输入"""
    task_id: str = Field(..., description="任务ID")
    status: str = Field(..., description="任务状态")
    task_result: Optional[dict] = Field(default=None, description="任务结果")


class CheckNeedTagsOutput(BaseModel):
    """检查是否需要生成标签节点的输出"""
    task_id: str = Field(..., description="任务ID")
    status: str = Field(..., description="任务状态")
    task_result: Optional[dict] = Field(default=None, description="任务结果")
    need_tags: bool = Field(default=False, description="是否需要生成标签")
    image_url: Optional[str] = Field(default=None, description="图像URL（需要生成标签时）")


# 查询单个用户节点（通过 user_id）
class GetUserByIdInput(BaseModel):
    """查询单个用户节点的输入"""
    user_id: str = Field(..., description="用户ID")


class GetUserByIdOutput(BaseModel):
    """查询单个用户节点的输出"""
    result: dict = Field(default={}, description="查询结果")
    success: bool = Field(default=True, description="是否成功")
    user: Optional[dict] = Field(default=None, description="用户数据")
    error: Optional[str] = Field(default=None, description="错误信息")


# 更新用户节点
class UpdateUserInput(BaseModel):
    """更新用户节点的输入"""
    user_id: str = Field(..., description="用户ID（要被更新的用户）")
    operator_user_id: Optional[str] = Field(default=None, description="操作者用户ID")
    operator_role: Optional[str] = Field(default=None, description="操作者角色（admin 或 user）")
    phone: Optional[str] = Field(default=None, description="手机号")
    username: Optional[str] = Field(default=None, description="用户名")
    avatar: Optional[str] = Field(default=None, description="头像URL")
    team_id: Optional[str] = Field(default=None, description="团队ID")
    gold_credits: Optional[int] = Field(default=None, description="金豆余额")
    silver_credits: Optional[int] = Field(default=None, description="银豆余额")
    role: Optional[str] = Field(default=None, description="用户角色")
    tier: Optional[str] = Field(default=None, description="用户等级")
    account_status: Optional[str] = Field(default=None, description="账号状态")
    updates: Optional[dict] = Field(default=None, description="更新字段（已废弃，使用上面的具体字段）")


class UpdateUserOutput(BaseModel):
    """更新用户节点的输出"""
    result: dict = Field(default={}, description="更新结果")
    success: bool = Field(default=True, description="是否成功")
    user: Optional[dict] = Field(default=None, description="用户数据")
    error: Optional[str] = Field(default=None, description="错误信息")


# 删除用户节点
class DeleteUserInput(BaseModel):
    """删除用户节点的输入"""
    user_id: str = Field(..., description="用户ID")
    operator_role: str = Field(..., description="操作者角色")


class DeleteUserOutput(BaseModel):
    """删除用户节点的输出"""
    result: dict = Field(default={}, description="删除结果")
    success: bool = Field(default=True, description="是否成功")
    error: Optional[str] = Field(default=None, description="错误信息")


# 用户列表节点
class ListUsersInput(BaseModel):
    """用户列表节点的输入"""
    page: Optional[int] = Field(default=1, description="页码")
    limit: Optional[int] = Field(default=20, description="每页数量")
    filter: Optional[dict] = Field(default=None, description="筛选条件")
    operator_role: str = Field(..., description="操作者角色")


class ListUsersOutput(BaseModel):
    """用户列表节点的输出"""
    result: dict = Field(default={}, description="列表结果")
    success: bool = Field(default=True, description="是否成功")
    users: Optional[List[dict]] = Field(default=None, description="用户列表")
    total: Optional[int] = Field(default=None, description="总数")
    page: Optional[int] = Field(default=None, description="当前页")
    limit: Optional[int] = Field(default=None, description="每页数量")
    error: Optional[str] = Field(default=None, description="错误信息")


# 文件上传节点
class UploadInput(BaseModel):
    """文件上传节点的输入"""
    file: Optional[File] = Field(default=None, description="上传的文件")


class UploadOutput(BaseModel):
    """文件上传节点的输出"""
    result: dict = Field(default={}, description="上传结果：包含公开 URL")


# 保存历史节点
class SaveInput(BaseModel):
    """保存历史节点的输入"""
    user_id: Optional[str] = Field(default=None, description="用户 ID")
    runninghub_link: Optional[str] = Field(default=None, description="RunningHub 链接")


class SaveOutput(BaseModel):
    """保存历史节点的输出"""
    result: dict = Field(default={}, description="保存结果")


# 历史查询节点
# 任务管理相关节点输入输出类

class CreateTaskInput(BaseModel):
    """创建任务节点的输入（仅限注册用户）"""
    user_id: str = Field(..., description="用户ID（必须是已注册的活跃用户）")
    task_data: dict = Field(..., description="任务数据")


class CreateTaskOutput(BaseModel):
    """创建任务节点的输出"""
    result: dict = Field(..., description="创建结果")


class UpdateTaskInput(BaseModel):
    """更新任务节点的输入（仅限注册用户）"""
    user_id: str = Field(..., description="用户ID（必须是已注册的活跃用户）")
    task_id: str = Field(..., description="任务ID")
    task_updates: dict = Field(..., description="更新数据")


class UpdateTaskOutput(BaseModel):
    """更新任务节点的输出"""
    result: dict = Field(..., description="更新结果")
    task_id: Optional[str] = Field(default=None, description="任务ID")
    status: Optional[str] = Field(default=None, description="任务状态")
    task_result: Optional[dict] = Field(default=None, description="任务结果")


class DeleteTaskInput(BaseModel):
    """删除任务节点的输入（仅限注册用户）"""
    user_id: str = Field(..., description="用户ID（必须是已注册的活跃用户）")
    task_id: str = Field(..., description="任务ID")


class DeleteTaskOutput(BaseModel):
    """删除任务节点的输出（软删除）"""
    result: dict = Field(..., description="删除结果")


class ListTasksInput(BaseModel):
    """查询任务列表节点的输入（支持灵活查询）"""
    user_id: Optional[str] = Field(default=None, description="用户ID（可选，至少提供 user_id 或 team_id 之一）")
    team_id: Optional[str] = Field(default=None, description="团队ID筛选（可选，至少提供 user_id 或 team_id 之一）")
    status: Optional[str] = Field(default=None, description="任务状态筛选")
    start_time: Optional[int] = Field(default=None, description="查询开始时间戳（毫秒，13位整数）")
    end_time: Optional[int] = Field(default=None, description="查询结束时间戳（毫秒，13位整数）")
    limit: Optional[int] = Field(default=100, description="最大返回数量（默认100，最大不超过500）")


class ListTasksOutput(BaseModel):
    """查询任务列表节点的输出（自动过滤已删除的任务）"""
    result: dict = Field(..., description="查询结果")


class TaskRouteInput(BaseModel):
    """任务路由节点的输入"""
    operation_type: str = Field(..., description="操作类型：create_task/update_task/delete_task/list_tasks")
    # 任务管理相关字段
    user_id: Optional[str] = Field(default=None, description="用户ID")
    task_id: Optional[str] = Field(default=None, description="任务ID")
    task_data: Optional[dict] = Field(default=None, description="任务数据")
    task_updates: Optional[dict] = Field(default=None, description="任务更新数据")
    # 时间范围查询字段
    start_time: Optional[int] = Field(default=None, description="查询开始时间戳（毫秒）")
    end_time: Optional[int] = Field(default=None, description="查询结束时间戳（毫秒）")
    # 其他筛选字段
    team_id: Optional[str] = Field(default=None, description="团队ID")
    status: Optional[str] = Field(default=None, description="任务状态")
    limit: Optional[int] = Field(default=None, description="最大返回数量")


class TaskRouteOutput(BaseModel):
    """任务路由节点的输出"""
    operation_type: str = Field(..., description="操作类型")
    # 任务管理相关字段
    user_id: Optional[str] = Field(default=None, description="用户ID")
    task_id: Optional[str] = Field(default=None, description="任务ID")
    task_data: Optional[dict] = Field(default=None, description="任务数据")
    task_updates: Optional[dict] = Field(default=None, description="任务更新数据")
    # 时间范围查询字段
    start_time: Optional[int] = Field(default=None, description="查询开始时间戳（毫秒）")
    end_time: Optional[int] = Field(default=None, description="查询结束时间戳（毫秒）")
    # 其他筛选字段
    team_id: Optional[str] = Field(default=None, description="团队ID")
    status: Optional[str] = Field(default=None, description="任务状态")
    limit: Optional[int] = Field(default=None, description="最大返回数量")


# 统一返回节点
class FormatResponseInput(BaseModel):
    """统一返回节点的输入"""
    call_type: str = Field(..., description="调用类型")
    result: dict = Field(default={}, description="各节点的结果")
    response_data: Optional[dict] = Field(default=None, description="直接返回的响应数据（团队余额等节点使用）")


class FormatResponseOutput(BaseModel):
    """统一返回节点的输出"""
    response_data: dict = Field(..., description="统一响应数据：{code, msg, data}")


class RouterOutput(BaseModel):
    """路由节点的输出"""
    call_type: str = Field(..., description="调用类型")
    action: Optional[str] = Field(default=None, description="操作类型（团队余额等使用）")


class RouterInput(BaseModel):
    """路由节点的输入"""
    call_type: str = Field(..., description="调用类型")
    action: Optional[str] = Field(default=None, description="操作类型（团队余额等使用）")


class OperationRouteInput(BaseModel):
    """操作路由节点的输入"""
    operation_type: str = Field(..., description="操作类型：check_rate_limit/register/login/update_user/delete_user/list_users")


class OperationRouteOutput(BaseModel):
    """操作路由节点的输出"""
    operation_type: str = Field(..., description="操作类型")


# 数据解包节点
class UnpackInputDataInput(BaseModel):
    """数据解包节点的输入"""
    call_type: str = Field(..., description="调用类型")
    action: Optional[str] = Field(default=None, description="操作类型（团队余额等使用）")
    tool_type: Optional[str] = Field(default=None, description="工具类型")
    input: Optional[InputData] = Field(default=None, description="业务数据对象")


class UnpackInputDataOutput(BaseModel):
    """数据解包节点的输出"""
    call_type: str = Field(..., description="调用类型")
    action: Optional[str] = Field(default=None, description="操作类型（团队余额等使用）")
    username: Optional[str] = Field(default=None, description="用户名")
    password: Optional[str] = Field(default=None, description="密码")
    file: Optional[File] = Field(default=None, description="上传的文件")
    file_list: Optional[List[File]] = Field(default=None, description="文件列表")
    user_id: Optional[str] = Field(default=None, description="用户ID")
    runninghub_link: Optional[str] = Field(default=None, description="RunningHub链接")
    tool_type: Optional[str] = Field(default=None, description="工具类型")
    operation_type: Optional[str] = Field(default=None, description="操作类型")
    prompt: Optional[str] = Field(default=None, description="提示词")
    # 用户管理相关字段
    phone: Optional[str] = Field(default=None, description="手机号")
    ip: Optional[str] = Field(default=None, description="IP地址")
    password_hash: Optional[str] = Field(default=None, description="密码哈希")
    avatar: Optional[str] = Field(default=None, description="头像URL")
    team_id: Optional[str] = Field(default=None, description="团队ID")
    gold_credits: Optional[int] = Field(default=None, description="金豆余额")
    silver_credits: Optional[int] = Field(default=None, description="银豆余额")
    role: Optional[str] = Field(default=None, description="用户角色")
    tier: Optional[str] = Field(default=None, description="用户等级")
    account_status: Optional[str] = Field(default=None, description="账号状态")
    updates: Optional[dict] = Field(default=None, description="更新字段")
    operator_role: Optional[str] = Field(default=None, description="操作者角色")
    operator_user_id: Optional[str] = Field(default=None, description="操作者用户ID")
    page: Optional[int] = Field(default=None, description="页码")
    limit: Optional[int] = Field(default=None, description="每页数量")
    filter: Optional[dict] = Field(default=None, description="筛选条件")
    # 任务时间范围查询字段
    start_time: Optional[int] = Field(default=None, description="查询开始时间戳（毫秒）")
    end_time: Optional[int] = Field(default=None, description="查询结束时间戳（毫秒）")
    # 任务管理相关字段
    task_id: Optional[str] = Field(default=None, description="任务ID")
    task_data: Optional[dict] = Field(default=None, description="任务数据")
    task_updates: Optional[dict] = Field(default=None, description="任务更新数据")
    # 系统通知相关字段
    notification_id: Optional[str] = Field(default=None, description="通知ID")
    notification_data: Optional[dict] = Field(default=None, description="通知数据")
    current_time: Optional[int] = Field(default=None, description="当前时间戳")
    # 团队余额相关字段
    amount: Optional[int] = Field(default=None, description="金额（充值/扣费/退款使用）")
    description: Optional[str] = Field(default=None, description="操作描述")
    days: Optional[int] = Field(default=None, description="查询天数")
    name: Optional[str] = Field(default=None, description="团队名称（创建团队使用）")
    target_user_id: Optional[str] = Field(default=None, description="目标用户ID")
    target_username: Optional[str] = Field(default=None, description="目标用户名")
    target_role: Optional[str] = Field(default=None, description="目标角色")
    original_record_id: Optional[str] = Field(default=None, description="原消费记录ID（退款用）")
    reason: Optional[str] = Field(default=None, description="退款原因")


# 工具路由节点
class ToolRouteInput(BaseModel):
    """工具路由节点的输入"""
    tool_type: str = Field(..., description="工具类型：reverse_image/translate_doubao/translate_flash")


class ToolRouteOutput(BaseModel):
    """工具路由节点的输出"""
    tool_type: str = Field(..., description="工具类型")


# 提示词生成节点
class ReverseImageInput(BaseModel):
    """提示词生成节点的输入"""
    file: Optional[File] = Field(default=None, description="图像文件")


class ReverseImageOutput(BaseModel):
    """提示词生成节点的输出"""
    result: dict = Field(default={}, description="提示词生成结果")


# 翻译节点
class TranslateDoubaoInput(BaseModel):
    """翻译节点的输入"""
    prompt: str = Field(..., description="待翻译文本")


class TranslateDoubaoOutput(BaseModel):
    """翻译节点的输出"""
    result: dict = Field(default={}, description="翻译结果")


# 提示词增强节点
class PromptEnhanceInput(BaseModel):
    """提示词增强节点的输入"""
    prompt: str = Field(..., description="用户提示词")
    file_list: List[File] = Field(..., description="图片文件列表，1-4个")


class PromptEnhanceOutput(BaseModel):
    """提示词增强节点的输出"""
    result: dict = Field(default={}, description="增强结果")


# ============ 系统通知节点 ============

class SystemNotificationInput(BaseModel):
    """系统通知处理节点的输入"""
    operation_type: str = Field(..., description="操作类型：get_active/get_all/create/update/delete")
    notification_id: Optional[str] = Field(default=None, description="通知ID（update/delete 使用）")
    notification_data: Optional[dict] = Field(default=None, description="通知数据（create/update 使用）")
    current_time: Optional[int] = Field(default=None, description="当前时间戳（用于筛选有效通知）")


class SystemNotificationOutput(BaseModel):
    """系统通知处理节点的输出"""
    result: dict = Field(..., description="操作结果")


