from typing import Literal, Optional, List
from pydantic import BaseModel, Field, field_validator
from utils.file.file import File


def normalize_silver_credits_value(value):
    """兼容 Coze/DB 返回的银豆小数字符串，银豆只保留整数。"""
    if value is None or isinstance(value, int):
        return value
    if isinstance(value, float):
        return int(value)
    if isinstance(value, str):
        text = value.strip()
        if not text:
            return None
        return int(float(text))
    return value


class InputData(BaseModel):
    """输入数据对象，包含所有业务字段"""
    username: Optional[str] = Field(default=None, description="用户名")
    password: Optional[str] = Field(default=None, description="密码")
    confirm_password: Optional[str] = Field(default=None, description="确认密码")
    code: Optional[str] = Field(default=None, description="验证码")
    file: Optional[File] = Field(default=None, description="上传的文件（upload/tool 使用）")
    file_list: Optional[List[File]] = Field(default=None, description="文件列表（提示词增强使用）")
    file_key: Optional[str] = Field(default=None, description="对象存储文件键（delete_upload/storage_management 使用）")
    category: Optional[str] = Field(default=None, description="文件分类：avatar/upload/temp 或 storage 分类")
    prefix: Optional[str] = Field(default=None, description="对象存储前缀筛选（storage_management 使用）")
    continuation_token: Optional[str] = Field(default=None, description="对象存储分页 token（storage_management 使用）")
    dry_run: Optional[bool] = Field(default=None, description="对象储存清理试运行（storage_management 使用）")
    include_avatars: Optional[bool] = Field(default=None, description="对象储存清理是否包含头像（storage_management 使用）")
    folder_name: Optional[str] = Field(default=None, description="对象存储文件夹名称")
    file_name: Optional[str] = Field(default=None, description="对象存储上传文件名")
    content_type: Optional[str] = Field(default=None, description="对象存储上传文件 MIME 类型")
    size: Optional[int] = Field(default=None, description="对象存储上传文件大小")
    file_content_base64: Optional[str] = Field(default=None, description="对象存储上传文件 base64 内容")
    convert_to_pdf: bool = Field(default=False, description="对象存储上传时是否将 Office 文档转换为 PDF")
    asset_mode: bool = Field(default=False, description="对象存储是否按站点长期资源处理")
    expires_in: Optional[int] = Field(default=None, description="对象存储签名 URL 过期秒数")
    avoid_overwrite: bool = Field(default=True, description="对象存储上传是否避免覆盖")
    source: Optional[str] = Field(default=None, description="文件来源标记")
    user_id: Optional[str] = Field(default=None, description="用户 ID（save/history/update_user/delete_user 使用）")
    runninghub_link: Optional[str] = Field(default=None, description="RunningHub 链接（save 使用）")
    tool_type: Optional[str] = Field(default=None, description="工具类型：reverse_image/translate_doubao/translate_flash/prompt_enhance")
    prompt: Optional[str] = Field(default=None, description="提示词/待翻译文本（tool 使用）")
    operation_type: Optional[str] = Field(default=None, description="操作类型：账号管理(check_rate_limit/update_rate_limit/send_register_code/send_password_reset_code/register/register_with_code/reset_password_with_code/login/get_user/get_user_by_id/update_user/delete_user/list_users)、任务管理(create_task/get_task/update_task/delete_task/list_tasks)、通知管理(get_active/get_all/create/update/delete)、公告管理(get_active_popup/get_all/create/update/disable)、团队余额(init/check/create_team/get_team/add_member/list_members/recharge/deduct/refund/get_records/get_stats/get_member_stats)、资金扣费(get_balance/deduct/refund/settle/list_records)、RunningHub错误分析(runninghub_error_analysis)")
    assets: Optional[List[dict]] = Field(default=None, description="Agent 意图判断素材摘要列表")
    current_target: Optional[dict] = Field(default=None, description="Agent 意图判断当前已选目标")
    agent_preferences: Optional[dict] = Field(default=None, description="Agent 生成偏好与模型偏好")
    capability_hash: Optional[str] = Field(default=None, description="Agent 能力表哈希")
    capability_manifest_url: Optional[str] = Field(default=None, description="Agent 能力表获取地址")
    capability_manifest: Optional[dict] = Field(default=None, description="Agent 能力表快照")
    agent_run_id: Optional[str] = Field(default=None, description="Agent Run ID")
    agent_step_id: Optional[str] = Field(default=None, description="Agent Step ID")
    agent_plan_type: Optional[str] = Field(default=None, description="Agent 计划类型")
    agent_plan: Optional[dict] = Field(default=None, description="Agent 执行计划")
    agent_steps: Optional[List[dict]] = Field(default=None, description="Agent 执行步骤")
    agent_run_updates: Optional[dict] = Field(default=None, description="Agent Run 更新字段")
    agent_step_updates: Optional[dict] = Field(default=None, description="Agent Step 更新字段")

    # 用户管理相关字段
    phone: Optional[str] = Field(default=None, description="手机号")
    ip: Optional[str] = Field(default=None, description="IP地址")
    password_hash: Optional[str] = Field(default=None, description="密码哈希")
    avatar: Optional[str] = Field(default=None, description="头像URL")
    team_id: Optional[str] = Field(default=None, description="团队ID")
    gold_credits: Optional[float] = Field(default=None, description="金豆余额")
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
    start_time: Optional[int] = Field(default=None, description="查询开始时间戳（毫秒，13位整数）")
    end_time: Optional[int] = Field(default=None, description="查询结束时间戳（毫秒，13位整数）")
    before_time: Optional[int] = Field(default=None, description="游标分页：查询早于该时间戳的记录（毫秒，13位整数）")
    status: Optional[str] = Field(default=None, description="任务状态筛选（list_tasks 使用）")
    days: Optional[int] = Field(default=None, description="查询最近N天的数据（list_tasks 使用）")

    # 任务管理相关字段
    task_id: Optional[str] = Field(default=None, description="任务ID（get_task/update_task/delete_task 使用）")
    platform: Optional[str] = Field(default=None, description="平台标识，与 platform_task_id 配合使用")
    platform_task_id: Optional[str] = Field(default=None, description="平台任务ID，与 platform 配合使用")
    query_id: Optional[str] = Field(default=None, description="通用查询ID：自动匹配 id 或 platform_task_id")
    task_data: Optional[dict] = Field(default=None, description="任务数据（create_task 使用）")
    task_updates: Optional[dict] = Field(default=None, description="任务更新数据（update_task 使用）")

    # 系统通知相关字段
    notification_id: Optional[str] = Field(default=None, description="通知ID（update_notification/delete_notification 使用）")
    notification_data: Optional[dict] = Field(default=None, description="通知数据（create_notification/update_notification 使用）")
    current_time: Optional[int] = Field(default=None, description="当前时间戳（用于筛选有效通知）")

    # 更新公告相关字段
    announcement_id: Optional[str] = Field(default=None, description="公告ID（update/disable 使用）")
    announcement_data: Optional[dict] = Field(default=None, description="公告数据（create/update 使用）")
    target_audience: Optional[str] = Field(default=None, description="目标用户：all/logged_in/guest/admin")

    # 团队余额相关字段
    amount: Optional[float] = Field(default=None, description="金额（充值/扣费/退款使用）")
    description: Optional[str] = Field(default=None, description="操作描述")
    name: Optional[str] = Field(default=None, description="团队名称（创建团队使用）")
    target_user_id: Optional[str] = Field(default=None, description="目标用户ID")
    target_username: Optional[str] = Field(default=None, description="目标用户名")
    target_role: Optional[str] = Field(default=None, description="目标角色")
    original_record_id: Optional[str] = Field(default=None, description="原消费记录ID（退款用）")
    reason: Optional[str] = Field(default=None, description="退款原因")
    filter_user_id: Optional[str] = Field(default=None, description="筛选用户ID（消费记录查询使用）")

    # RunningHub 错误分析相关字段
    error_response: Optional[dict] = Field(default=None, description="RunningHub 错误响应数据（runninghub_error_analysis 使用）")

    # Billing 资金扣费相关字段
    credit_type: Optional[str] = Field(default=None, description="资金类型：personal_gold/personal_silver/team_gold")
    idempotency_key: Optional[str] = Field(default=None, description="幂等键（deduct/refund/settle 必传）")
    service_secret: Optional[str] = Field(default=None, description="服务密钥（billing 操作必传）")
    final_amount: Optional[float] = Field(default=None, description="结算金额（settle 使用）")
    billing_metadata: Optional[dict] = Field(default=None, description="billing 元数据（main 透传，含 title/workflow/model 等信息）")
    metadata: Optional[dict] = Field(default=None, description="通用元数据（含 billing_metadata 嵌套结构，main 透传）")

    @field_validator("silver_credits", mode="before")
    @classmethod
    def normalize_silver_credits(cls, value):
        return normalize_silver_credits_value(value)


class GlobalState(BaseModel):
    """全局状态定义"""
    call_type: str = Field(..., description="调用类型：account_management/upload/delete_upload/storage_management/save/tool/user_task_management/notification_management/announcement_management/team_balance/billing/agent_intent/agent_run")
    input: Optional[InputData] = Field(default=None, description="业务数据对象")
    username: Optional[str] = Field(default=None, description="用户名")
    password: Optional[str] = Field(default=None, description="密码")
    confirm_password: Optional[str] = Field(default=None, description="确认密码")
    code: Optional[str] = Field(default=None, description="验证码")
    file: Optional[File] = Field(default=None, description="上传的文件（upload/tool 使用）")
    file_list: Optional[List[File]] = Field(default=None, description="文件列表（提示词增强使用）")
    file_key: Optional[str] = Field(default=None, description="对象存储文件键（delete_upload/storage_management 使用）")
    category: Optional[str] = Field(default=None, description="文件分类：avatar/upload/temp 或 storage 分类")
    prefix: Optional[str] = Field(default=None, description="对象存储前缀筛选（storage_management 使用）")
    continuation_token: Optional[str] = Field(default=None, description="对象存储分页 token（storage_management 使用）")
    dry_run: Optional[bool] = Field(default=None, description="对象储存清理试运行（storage_management 使用）")
    include_avatars: Optional[bool] = Field(default=None, description="对象储存清理是否包含头像（storage_management 使用）")
    folder_name: Optional[str] = Field(default=None, description="对象存储文件夹名称")
    file_name: Optional[str] = Field(default=None, description="对象存储上传文件名")
    content_type: Optional[str] = Field(default=None, description="对象存储上传文件 MIME 类型")
    size: Optional[int] = Field(default=None, description="对象存储上传文件大小")
    file_content_base64: Optional[str] = Field(default=None, description="对象存储上传文件 base64 内容")
    convert_to_pdf: bool = Field(default=False, description="对象存储上传时是否将 Office 文档转换为 PDF")
    asset_mode: bool = Field(default=False, description="对象存储是否按站点长期资源处理")
    expires_in: Optional[int] = Field(default=None, description="对象存储签名 URL 过期秒数")
    avoid_overwrite: bool = Field(default=True, description="对象存储上传是否避免覆盖")
    source: Optional[str] = Field(default=None, description="文件来源标记")
    user_id: Optional[str] = Field(default=None, description="用户 ID（save/update_user/delete_user/create_task/list_tasks 使用）")
    runninghub_link: Optional[str] = Field(default=None, description="RunningHub 链接（save 使用）")
    tool_type: Optional[str] = Field(default=None, description="工具类型：reverse_image/translate_doubao/translate_flash/prompt_enhance")
    operation_type: Optional[str] = Field(default=None, description="操作类型")
    prompt: Optional[str] = Field(default=None, description="提示词/待翻译文本（tool 使用）")
    assets: Optional[List[dict]] = Field(default=None, description="Agent 意图判断素材摘要列表")
    current_target: Optional[dict] = Field(default=None, description="Agent 意图判断当前已选目标")
    agent_preferences: Optional[dict] = Field(default=None, description="Agent 生成偏好与模型偏好")
    capability_hash: Optional[str] = Field(default=None, description="Agent 能力表哈希")
    capability_manifest_url: Optional[str] = Field(default=None, description="Agent 能力表获取地址")
    capability_manifest: Optional[dict] = Field(default=None, description="Agent 能力表快照")
    agent_run_id: Optional[str] = Field(default=None, description="Agent Run ID")
    agent_step_id: Optional[str] = Field(default=None, description="Agent Step ID")
    agent_plan_type: Optional[str] = Field(default=None, description="Agent 计划类型")
    agent_plan: Optional[dict] = Field(default=None, description="Agent 执行计划")
    agent_steps: Optional[List[dict]] = Field(default=None, description="Agent 执行步骤")
    agent_run_updates: Optional[dict] = Field(default=None, description="Agent Run 更新字段")
    agent_step_updates: Optional[dict] = Field(default=None, description="Agent Step 更新字段")
    result: dict = Field(default={}, description="各节点的结果")
    response_data: Optional[dict] = Field(default=None, description="统一响应数据")

    # 用户管理相关字段
    phone: Optional[str] = Field(default=None, description="手机号")
    ip: Optional[str] = Field(default=None, description="IP地址")
    password_hash: Optional[str] = Field(default=None, description="密码哈希")
    avatar: Optional[str] = Field(default=None, description="头像URL")
    team_id: Optional[str] = Field(default=None, description="团队ID")
    gold_credits: Optional[float] = Field(default=None, description="金豆余额")
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
    start_time: Optional[int] = Field(default=None, description="查询开始时间戳（毫秒，13位整数）")
    end_time: Optional[int] = Field(default=None, description="查询结束时间戳（毫秒，13位整数）")
    before_time: Optional[int] = Field(default=None, description="游标分页：查询早于该时间戳的记录（毫秒）")
    status: Optional[str] = Field(default=None, description="任务状态筛选（running/completed/failed）")

    # 任务管理相关字段
    task_id: Optional[str] = Field(default=None, description="任务ID（get_task/update_task/delete_task 使用）")
    platform: Optional[str] = Field(default=None, description="平台标识，与 platform_task_id 配合使用")
    platform_task_id: Optional[str] = Field(default=None, description="平台任务ID，与 platform 配合使用")
    query_id: Optional[str] = Field(default=None, description="通用查询ID：自动匹配 id 或 platform_task_id")
    task_data: Optional[dict] = Field(default=None, description="任务数据（create_task 使用）")
    task_updates: Optional[dict] = Field(default=None, description="任务更新数据（update_task 使用）")

    # 系统通知相关字段
    notification_id: Optional[str] = Field(default=None, description="通知ID（update_notification/delete_notification 使用）")
    notification_data: Optional[dict] = Field(default=None, description="通知数据（create_notification/update_notification 使用）")
    current_time: Optional[int] = Field(default=None, description="当前时间戳（用于筛选有效通知）")

    # 更新公告相关字段
    announcement_id: Optional[str] = Field(default=None, description="公告ID（update/disable 使用）")
    announcement_data: Optional[dict] = Field(default=None, description="公告数据（create/update 使用）")
    target_audience: Optional[str] = Field(default=None, description="目标用户：all/logged_in/guest/admin")

    # 团队余额相关字段（用于团队余额操作）
    amount: Optional[float] = Field(default=None, description="金额（充值/扣费/退款使用）")
    description: Optional[str] = Field(default=None, description="操作描述")
    days: Optional[int] = Field(default=None, description="查询天数")
    name: Optional[str] = Field(default=None, description="团队名称（创建团队使用）")
    target_user_id: Optional[str] = Field(default=None, description="目标用户ID")
    target_username: Optional[str] = Field(default=None, description="目标用户名")
    target_role: Optional[str] = Field(default=None, description="目标角色")
    original_record_id: Optional[str] = Field(default=None, description="原消费记录ID（退款用）")
    reason: Optional[str] = Field(default=None, description="退款原因")
    filter_user_id: Optional[str] = Field(default=None, description="筛选用户ID（消费记录查询使用）")

    # RunningHub 错误分析相关字段
    error_response: Optional[dict] = Field(default=None, description="RunningHub 错误响应数据")

    # Billing 资金扣费相关字段
    credit_type: Optional[str] = Field(default=None, description="资金类型：personal_gold/personal_silver/team_gold")
    idempotency_key: Optional[str] = Field(default=None, description="幂等键（deduct/refund/settle 必传）")
    service_secret: Optional[str] = Field(default=None, description="服务密钥（billing 操作必传）")
    final_amount: Optional[float] = Field(default=None, description="结算金额（settle 使用）")
    billing_metadata: Optional[dict] = Field(default=None, description="billing 元数据（main 透传，含 title/workflow/model 等信息）")
    metadata: Optional[dict] = Field(default=None, description="通用元数据（含 billing_metadata 嵌套结构，main 透传）")

    @field_validator("silver_credits", mode="before")
    @classmethod
    def normalize_silver_credits(cls, value):
        return normalize_silver_credits_value(value)


class GraphInput(BaseModel):
    """工作流的输入"""
    call_type: str = Field(..., description="调用类型：account_management/upload/delete_upload/storage_management/save/history/tool/task_management/notification_management/announcement_management/team_balance/billing/agent_intent/agent_run")
    tool_type: Optional[str] = Field(default=None, description="工具类型：reverse_image/translate_doubao/translate_flash/prompt_enhance")
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
    gold_credits: float = Field(default=0, description="金豆余额")
    silver_credits: int = Field(default=2000, description="银豆余额")
    role: str = Field(default="user", description="用户角色")
    tier: str = Field(default="commercial_registered", description="用户等级")
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


class SendRegisterCodeInput(BaseModel):
    """发送注册验证码节点的输入"""
    phone: Optional[str] = Field(default=None, description="手机号")
    ip: Optional[str] = Field(default=None, description="IP地址")


class SendRegisterCodeOutput(BaseModel):
    """发送注册验证码节点的输出"""
    result: dict = Field(default={}, description="发送结果")
    success: bool = Field(default=True, description="是否成功")
    error: Optional[str] = Field(default=None, description="错误信息")


class SendPasswordResetCodeInput(BaseModel):
    """发送密码重置验证码节点的输入"""
    phone: Optional[str] = Field(default=None, description="手机号")
    ip: Optional[str] = Field(default=None, description="IP地址")


class SendPasswordResetCodeOutput(BaseModel):
    """发送密码重置验证码节点的输出"""
    result: dict = Field(default={}, description="发送结果")
    success: bool = Field(default=True, description="是否成功")
    error: Optional[str] = Field(default=None, description="错误信息")


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


class RegisterWithCodeInput(BaseModel):
    """验证码注册节点的输入"""
    phone: Optional[str] = Field(default=None, description="手机号")
    ip: Optional[str] = Field(default=None, description="IP地址")
    password: Optional[str] = Field(default=None, description="明文密码")
    code: Optional[str] = Field(default=None, description="验证码")
    username: Optional[str] = Field(default=None, description="用户名")
    avatar: Optional[str] = Field(default=None, description="头像URL")


class RegisterWithCodeOutput(BaseModel):
    """验证码注册节点的输出"""
    result: dict = Field(default={}, description="注册结果")
    success: bool = Field(default=True, description="是否成功")
    user: Optional[dict] = Field(default=None, description="用户数据")
    error: Optional[str] = Field(default=None, description="错误信息")


class ResetPasswordWithCodeInput(BaseModel):
    """验证码重置密码节点的输入"""
    phone: Optional[str] = Field(default=None, description="手机号")
    password: Optional[str] = Field(default=None, description="新密码")
    confirm_password: Optional[str] = Field(default=None, description="确认密码")
    code: Optional[str] = Field(default=None, description="验证码")


class ResetPasswordWithCodeOutput(BaseModel):
    """验证码重置密码节点的输出"""
    result: dict = Field(default={}, description="重置结果")
    success: bool = Field(default=True, description="是否成功")
    error: Optional[str] = Field(default=None, description="错误信息")


# 查询用户节点（登录）
class GetUserInput(BaseModel):
    """查询用户节点的输入"""
    phone: Optional[str] = Field(default=None, description="手机号")
    password: Optional[str] = Field(default=None, description="密码")


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
    gold_credits: Optional[float] = Field(default=None, description="金豆余额")
    silver_credits: Optional[int] = Field(default=None, description="银豆余额")
    role: Optional[str] = Field(default=None, description="用户角色")
    tier: Optional[str] = Field(default=None, description="用户等级")
    account_status: Optional[str] = Field(default=None, description="账号状态")
    updates: Optional[dict] = Field(default=None, description="更新字段（已废弃，使用上面的具体字段）")

    @field_validator("silver_credits", mode="before")
    @classmethod
    def normalize_silver_credits(cls, value):
        return normalize_silver_credits_value(value)


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
    category: Optional[str] = Field(default=None, description="文件分类：avatar/upload/temp")
    metadata: Optional[dict] = Field(default=None, description="文件元数据")


class UploadOutput(BaseModel):
    """文件上传节点的输出"""
    result: dict = Field(default={}, description="上传结果：包含公开 URL")


class DeleteUploadInput(BaseModel):
    """删除上传文件节点的输入"""
    file_key: Optional[str] = Field(default=None, description="对象存储文件键")
    category: Optional[str] = Field(default=None, description="文件分类")
    source: Optional[str] = Field(default=None, description="文件来源标记")


class DeleteUploadOutput(BaseModel):
    """删除上传文件节点的输出"""
    result: dict = Field(default={}, description="删除结果")


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


class GetTaskInput(BaseModel):
    """查询单个任务节点的输入（仅限注册用户）"""
    user_id: Optional[str] = Field(default=None, description="用户ID（必须是已注册的活跃用户）")
    task_id: Optional[str] = Field(default=None, description="任务ID（前端主键）")
    platform: Optional[str] = Field(default=None, description="平台标识，与 platform_task_id 配合使用")
    platform_task_id: Optional[str] = Field(default=None, description="平台任务ID（与 platform 配合使用）")
    query_id: Optional[str] = Field(default=None, description="通用查询ID：自动匹配 id 或 platform_task_id")


class GetTaskOutput(BaseModel):
    """查询单个任务节点的输出"""
    result: dict = Field(..., description="查询结果")


class DeleteTaskInput(BaseModel):
    """删除任务节点的输入（仅限注册用户）"""
    user_id: str = Field(..., description="用户ID（必须是已注册的活跃用户）")
    task_id: str = Field(..., description="任务ID")


class DeleteTaskOutput(BaseModel):
    """删除任务节点的输出（软删除）"""
    result: dict = Field(..., description="删除结果")


class ListTasksInput(BaseModel):
    """查询任务列表节点的输入"""
    user_id: Optional[str] = Field(default=None, description="用户ID（可选，至少提供 user_id 或 team_id 之一）")
    team_id: Optional[str] = Field(default=None, description="团队ID筛选（可选，至少提供 user_id 或 team_id 之一）")
    status: Optional[str] = Field(default=None, description="任务状态筛选")
    days: Optional[int] = Field(default=30, description="查询最近N天的数据（默认30天）")
    limit: Optional[int] = Field(default=50, description="返回数量限制（默认50，最大1000）")
    before_time: Optional[int] = Field(default=None, description="游标分页：查询早于该时间戳的记录（毫秒，13位整数）")


class ListTasksOutput(BaseModel):
    """查询任务列表节点的输出（自动过滤已删除的任务）"""
    result: dict = Field(..., description="查询结果")


class TaskRouteInput(BaseModel):
    """任务路由节点的输入"""
    operation_type: str = Field(..., description="操作类型：create_task/get_task/update_task/delete_task/list_tasks")
    # 任务管理相关字段
    user_id: Optional[str] = Field(default=None, description="用户ID")
    task_id: Optional[str] = Field(default=None, description="任务ID（前端主键）")
    platform: Optional[str] = Field(default=None, description="平台标识")
    platform_task_id: Optional[str] = Field(default=None, description="平台任务ID")
    query_id: Optional[str] = Field(default=None, description="通用查询ID")
    task_data: Optional[dict] = Field(default=None, description="任务数据")
    task_updates: Optional[dict] = Field(default=None, description="任务更新数据")
    # 时间范围查询字段
    start_time: Optional[int] = Field(default=None, description="查询开始时间戳（毫秒）")
    end_time: Optional[int] = Field(default=None, description="查询结束时间戳（毫秒）")
    before_time: Optional[int] = Field(default=None, description="游标分页：查询早于该时间戳的记录（毫秒）")
    # 其他筛选字段
    team_id: Optional[str] = Field(default=None, description="团队ID")
    status: Optional[str] = Field(default=None, description="任务状态")
    limit: Optional[int] = Field(default=None, description="最大返回数量")


class TaskRouteOutput(BaseModel):
    """任务路由节点的输出"""
    operation_type: str = Field(..., description="操作类型")
    # 任务管理相关字段
    user_id: Optional[str] = Field(default=None, description="用户ID")
    task_id: Optional[str] = Field(default=None, description="任务ID（前端主键）")
    platform: Optional[str] = Field(default=None, description="平台标识")
    platform_task_id: Optional[str] = Field(default=None, description="平台任务ID")
    query_id: Optional[str] = Field(default=None, description="通用查询ID")
    task_data: Optional[dict] = Field(default=None, description="任务数据")
    task_updates: Optional[dict] = Field(default=None, description="任务更新数据")
    # 时间范围查询字段
    start_time: Optional[int] = Field(default=None, description="查询开始时间戳（毫秒）")
    end_time: Optional[int] = Field(default=None, description="查询结束时间戳（毫秒）")
    before_time: Optional[int] = Field(default=None, description="游标分页：查询早于该时间戳的记录（毫秒）")
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


class RouterInput(BaseModel):
    """路由节点的输入"""
    call_type: str = Field(..., description="调用类型")


class OperationRouteInput(BaseModel):
    """操作路由节点的输入"""
    operation_type: Optional[str] = Field(default=None, description="操作类型")


class OperationRouteOutput(BaseModel):
    """操作路由节点的输出"""
    operation_type: Optional[str] = Field(default=None, description="操作类型")


# 数据解包节点
class UnpackInputDataInput(BaseModel):
    """数据解包节点的输入"""
    call_type: str = Field(..., description="调用类型")
    tool_type: Optional[str] = Field(default=None, description="工具类型")
    input: Optional[InputData] = Field(default=None, description="业务数据对象")


class UnpackInputDataOutput(BaseModel):
    """数据解包节点的输出"""
    call_type: str = Field(..., description="调用类型")
    username: Optional[str] = Field(default=None, description="用户名")
    password: Optional[str] = Field(default=None, description="密码")
    confirm_password: Optional[str] = Field(default=None, description="确认密码")
    code: Optional[str] = Field(default=None, description="验证码")
    file: Optional[File] = Field(default=None, description="上传的文件")
    file_list: Optional[List[File]] = Field(default=None, description="文件列表")
    file_key: Optional[str] = Field(default=None, description="对象存储文件键")
    category: Optional[str] = Field(default=None, description="文件分类")
    prefix: Optional[str] = Field(default=None, description="对象存储前缀筛选")
    continuation_token: Optional[str] = Field(default=None, description="对象存储分页 token")
    dry_run: Optional[bool] = Field(default=None, description="对象储存清理试运行")
    include_avatars: Optional[bool] = Field(default=None, description="对象储存清理是否包含头像")
    folder_name: Optional[str] = Field(default=None, description="对象存储文件夹名称")
    file_name: Optional[str] = Field(default=None, description="对象存储上传文件名")
    content_type: Optional[str] = Field(default=None, description="对象存储上传文件 MIME 类型")
    size: Optional[int] = Field(default=None, description="对象存储上传文件大小")
    file_content_base64: Optional[str] = Field(default=None, description="对象存储上传文件 base64 内容")
    convert_to_pdf: bool = Field(default=False, description="对象存储上传时是否将 Office 文档转换为 PDF")
    asset_mode: bool = Field(default=False, description="对象存储是否按站点长期资源处理")
    expires_in: Optional[int] = Field(default=None, description="对象存储签名 URL 过期秒数")
    avoid_overwrite: bool = Field(default=True, description="对象存储上传是否避免覆盖")
    source: Optional[str] = Field(default=None, description="文件来源标记")
    user_id: Optional[str] = Field(default=None, description="用户ID")
    runninghub_link: Optional[str] = Field(default=None, description="RunningHub链接")
    tool_type: Optional[str] = Field(default=None, description="工具类型")
    operation_type: Optional[str] = Field(default=None, description="操作类型")
    prompt: Optional[str] = Field(default=None, description="提示词")
    assets: Optional[List[dict]] = Field(default=None, description="Agent 意图判断素材摘要列表")
    current_target: Optional[dict] = Field(default=None, description="Agent 意图判断当前已选目标")
    agent_preferences: Optional[dict] = Field(default=None, description="Agent 生成偏好与模型偏好")
    capability_hash: Optional[str] = Field(default=None, description="Agent 能力表哈希")
    capability_manifest_url: Optional[str] = Field(default=None, description="Agent 能力表获取地址")
    capability_manifest: Optional[dict] = Field(default=None, description="Agent 能力表快照")
    agent_run_id: Optional[str] = Field(default=None, description="Agent Run ID")
    agent_step_id: Optional[str] = Field(default=None, description="Agent Step ID")
    agent_plan_type: Optional[str] = Field(default=None, description="Agent 计划类型")
    agent_plan: Optional[dict] = Field(default=None, description="Agent 执行计划")
    agent_steps: Optional[List[dict]] = Field(default=None, description="Agent 执行步骤")
    agent_run_updates: Optional[dict] = Field(default=None, description="Agent Run 更新字段")
    agent_step_updates: Optional[dict] = Field(default=None, description="Agent Step 更新字段")
    # 用户管理相关字段
    phone: Optional[str] = Field(default=None, description="手机号")
    ip: Optional[str] = Field(default=None, description="IP地址")
    password_hash: Optional[str] = Field(default=None, description="密码哈希")
    avatar: Optional[str] = Field(default=None, description="头像URL")
    team_id: Optional[str] = Field(default=None, description="团队ID")
    gold_credits: Optional[float] = Field(default=None, description="金豆余额")
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
    before_time: Optional[int] = Field(default=None, description="游标分页：查询早于该时间戳的记录（毫秒）")
    status: Optional[str] = Field(default=None, description="任务状态筛选")
    days: Optional[int] = Field(default=None, description="查询天数")
    # 任务管理相关字段
    task_id: Optional[str] = Field(default=None, description="任务ID（get_task/update_task/delete_task 使用）")
    platform: Optional[str] = Field(default=None, description="平台标识，与 platform_task_id 配合使用")
    platform_task_id: Optional[str] = Field(default=None, description="平台任务ID，与 platform 配合使用")
    query_id: Optional[str] = Field(default=None, description="通用查询ID：自动匹配 id 或 platform_task_id")
    task_data: Optional[dict] = Field(default=None, description="任务数据（create_task 使用）")
    task_updates: Optional[dict] = Field(default=None, description="任务更新数据（update_task 使用）")

    # 系统通知相关字段
    notification_id: Optional[str] = Field(default=None, description="通知ID")
    notification_data: Optional[dict] = Field(default=None, description="通知数据")
    current_time: Optional[int] = Field(default=None, description="当前时间戳")

    # 更新公告相关字段
    announcement_id: Optional[str] = Field(default=None, description="公告ID")
    announcement_data: Optional[dict] = Field(default=None, description="公告数据")
    target_audience: Optional[str] = Field(default=None, description="目标用户")

    # 团队余额相关字段
    amount: Optional[float] = Field(default=None, description="金额（充值/扣费/退款使用）")
    description: Optional[str] = Field(default=None, description="操作描述")
    name: Optional[str] = Field(default=None, description="团队名称（创建团队使用）")
    target_user_id: Optional[str] = Field(default=None, description="目标用户ID")
    target_username: Optional[str] = Field(default=None, description="目标用户名")
    target_role: Optional[str] = Field(default=None, description="目标角色")
    original_record_id: Optional[str] = Field(default=None, description="原消费记录ID（退款用）")
    reason: Optional[str] = Field(default=None, description="退款原因")
    filter_user_id: Optional[str] = Field(default=None, description="筛选用户ID（查询消费记录用）")

    # RunningHub 错误分析相关字段
    error_response: Optional[dict] = Field(default=None, description="RunningHub 错误响应数据")

    # Billing 资金扣费相关字段
    credit_type: Optional[str] = Field(default=None, description="资金类型：personal_gold/personal_silver/team_gold")
    idempotency_key: Optional[str] = Field(default=None, description="幂等键")
    service_secret: Optional[str] = Field(default=None, description="服务密钥")
    final_amount: Optional[float] = Field(default=None, description="结算金额（settle 使用）")
    billing_metadata: Optional[dict] = Field(default=None, description="billing 元数据（main 透传）")
    metadata: Optional[dict] = Field(default=None, description="通用元数据（含 billing_metadata 嵌套结构，main 透传）")

    @field_validator("silver_credits", mode="before")
    @classmethod
    def normalize_silver_credits(cls, value):
        return normalize_silver_credits_value(value)


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
    file_list: List[File] = Field(default=[], description="图片文件列表，0-4个，非必传")

    @field_validator("file_list", mode="before")
    @classmethod
    def normalize_file_list(cls, v: object) -> list:
        if v is None:
            return []
        return v  # type: ignore[return-value]


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


# ============ 更新公告节点 ============

class AnnouncementInput(BaseModel):
    """更新公告处理节点的输入"""
    operation_type: str = Field(..., description="操作类型：get_active_popup/get_all/create/update/disable")
    current_time: Optional[int] = Field(default=None, description="当前时间戳（用于筛选有效公告）")
    target_audience: Optional[str] = Field(default="all", description="目标用户：all/logged_in/guest/admin")
    announcement_id: Optional[str] = Field(default=None, description="公告ID（update/disable 使用）")
    announcement_data: Optional[dict] = Field(default=None, description="公告数据（create/update 使用）")
    operator_user_id: Optional[str] = Field(default=None, description="操作者用户ID")


class AnnouncementOutput(BaseModel):
    """更新公告处理节点的输出"""
    result: dict = Field(..., description="操作结果")


# ============ RunningHub 错误分析节点 ============

class RunningHubErrorAnalysisInput(BaseModel):
    """RunningHub 错误分析节点的输入"""
    error_response: dict = Field(..., description="RunningHub 任务失败响应数据")


class RunningHubErrorAnalysisOutput(BaseModel):
    """RunningHub 错误分析节点的输出"""
    result: dict = Field(default={}, description="错误分析结果：包含用户友好的错误说明")


# ============ Billing 资金扣费节点 ============

class BillingRouteInput(BaseModel):
    """Billing 路由节点的输入"""
    operation_type: Optional[str] = Field(default=None, description="操作类型：get_balance/deduct/refund/settle/list_records/get_records")
    user_id: Optional[str] = Field(default=None, description="用户ID")
    filter_user_id: Optional[str] = Field(default=None, description="筛选用户ID")
    team_id: Optional[str] = Field(default=None, description="团队ID")
    credit_type: Optional[str] = Field(default=None, description="资金类型：personal_gold/personal_silver/team_gold")
    amount: Optional[float] = Field(default=None, description="金额（deduct 使用）")
    days: Optional[int] = Field(default=None, description="查询最近N天")
    limit: Optional[int] = Field(default=None, description="返回数量上限")
    idempotency_key: Optional[str] = Field(default=None, description="幂等键（deduct/refund/settle 必传）")
    service_secret: Optional[str] = Field(default=None, description="服务密钥（billing 操作必传）")
    task_id: Optional[str] = Field(default=None, description="关联任务ID（deduct 可选）")
    description: Optional[str] = Field(default=None, description="操作描述")
    original_record_id: Optional[str] = Field(default=None, description="原扣费记录ID（refund/settle 使用）")
    final_amount: Optional[float] = Field(default=None, description="结算金额（settle 使用）")
    operator_role: Optional[str] = Field(default=None, description="操作者角色")
    operator_user_id: Optional[str] = Field(default=None, description="操作者用户ID")
    billing_metadata: Optional[dict] = Field(default=None, description="billing 元数据（含 title/workflow/model 等）")
    metadata: Optional[dict] = Field(default=None, description="通用元数据（含 billing_metadata 嵌套结构，main 透传）")


class BillingRouteOutput(BaseModel):
    """Billing 路由节点的输出"""
    operation_type: str = Field(..., description="操作类型")
    user_id: Optional[str] = Field(default=None, description="用户ID")
    filter_user_id: Optional[str] = Field(default=None, description="筛选用户ID")
    team_id: Optional[str] = Field(default=None, description="团队ID")
    credit_type: Optional[str] = Field(default=None, description="资金类型")
    amount: Optional[float] = Field(default=None, description="金额")
    days: Optional[int] = Field(default=None, description="查询最近N天")
    limit: Optional[int] = Field(default=None, description="返回数量上限")
    idempotency_key: Optional[str] = Field(default=None, description="幂等键")
    service_secret: Optional[str] = Field(default=None, description="服务密钥")
    task_id: Optional[str] = Field(default=None, description="关联任务ID")
    description: Optional[str] = Field(default=None, description="操作描述")
    original_record_id: Optional[str] = Field(default=None, description="原扣费记录ID")
    final_amount: Optional[float] = Field(default=None, description="结算金额")
    operator_role: Optional[str] = Field(default=None, description="操作者角色")
    operator_user_id: Optional[str] = Field(default=None, description="操作者用户ID")
    billing_metadata: Optional[dict] = Field(default=None, description="billing 元数据（含 title/workflow/model 等）")
    metadata: Optional[dict] = Field(default=None, description="通用元数据（含 billing_metadata 嵌套结构，main 透传）")


class GetBalanceInput(BaseModel):
    """查询余额节点的输入"""
    user_id: str = Field(..., description="用户ID")


class GetBalanceOutput(BaseModel):
    """查询余额节点的输出"""
    response_data: dict = Field(default={}, description="统一响应数据")


class BillingDeductInput(BaseModel):
    """扣费节点的输入"""
    user_id: Optional[str] = Field(default=None, description="用户ID")
    credit_type: Optional[str] = Field(default=None, description="资金类型：personal_gold/personal_silver/team_gold")
    amount: Optional[float] = Field(default=None, description="扣费金额")
    idempotency_key: Optional[str] = Field(default=None, description="幂等键")
    service_secret: Optional[str] = Field(default=None, description="服务密钥")
    task_id: Optional[str] = Field(default=None, description="关联任务ID")
    description: Optional[str] = Field(default=None, description="操作描述")
    billing_metadata: Optional[dict] = Field(default=None, description="billing 元数据（含 title/workflow/model 等）")
    metadata: Optional[dict] = Field(default=None, description="通用元数据（含 billing_metadata 嵌套结构，main 透传）")


class BillingDeductOutput(BaseModel):
    """扣费节点的输出"""
    response_data: dict = Field(default={}, description="统一响应数据")


class BillingRefundInput(BaseModel):
    """退款节点的输入"""
    user_id: Optional[str] = Field(default=None, description="用户ID")
    original_record_id: Optional[str] = Field(default=None, description="原扣费记录ID")
    idempotency_key: Optional[str] = Field(default=None, description="幂等键")
    service_secret: Optional[str] = Field(default=None, description="服务密钥")
    amount: Optional[float] = Field(default=None, description="退款金额（不传则全额退款）")
    description: Optional[str] = Field(default=None, description="退款描述")
    billing_metadata: Optional[dict] = Field(default=None, description="billing 元数据（含 title/workflow/model 等）")
    metadata: Optional[dict] = Field(default=None, description="通用元数据（含 billing_metadata 嵌套结构，main 透传）")


class BillingRefundOutput(BaseModel):
    """退款节点的输出"""
    response_data: dict = Field(default={}, description="统一响应数据")


class BillingSettleInput(BaseModel):
    """结算节点的输入"""
    user_id: Optional[str] = Field(default=None, description="用户ID")
    original_record_id: Optional[str] = Field(default=None, description="原扣费记录ID")
    final_amount: Optional[float] = Field(default=None, description="最终结算金额")
    idempotency_key: Optional[str] = Field(default=None, description="幂等键")
    service_secret: Optional[str] = Field(default=None, description="服务密钥")
    description: Optional[str] = Field(default=None, description="结算描述")
    billing_metadata: Optional[dict] = Field(default=None, description="billing 元数据（含 title/workflow/model 等）")
    metadata: Optional[dict] = Field(default=None, description="通用元数据（含 billing_metadata 嵌套结构，main 透传）")


class BillingSettleOutput(BaseModel):
    """结算节点的输出"""
    response_data: dict = Field(default={}, description="统一响应数据")
