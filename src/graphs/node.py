from langchain_core.runnables import RunnableConfig
from langgraph.runtime import Runtime
from coze_coding_utils.runtime_ctx.context import Context
from langchain_core.messages import SystemMessage, HumanMessage, AIMessage
from coze_coding_dev_sdk import LLMClient
from jinja2 import Template
import json
from typing import Optional, List
from datetime import datetime

from graphs.state import (
    UploadInput, UploadOutput,
    SaveInput, SaveOutput,
    FormatResponseInput, FormatResponseOutput,
    GlobalState,
    RouterInput,
    RouterOutput,
    OperationRouteInput,
    OperationRouteOutput,
    ToolRouteInput,
    ToolRouteOutput,
    ReverseImageInput,
    ReverseImageOutput,
    TranslateDoubaoInput,
    TranslateDoubaoOutput,
    PromptEnhanceInput,
    PromptEnhanceOutput,
    UnpackInputDataInput,
    UnpackInputDataOutput,
    CheckRateLimitInput, CheckRateLimitOutput,
    CreateUserInput, CreateUserOutput,
    UpdateRateLimitInput, UpdateRateLimitOutput,
    RegisterWithLimitInput, RegisterWithLimitOutput,
    GetUserInput, GetUserOutput,
    GetUserByIdInput, GetUserByIdOutput,
    UpdateUserInput, UpdateUserOutput,
    DeleteUserInput, DeleteUserOutput,
    ListUsersInput, ListUsersOutput,
    CreateTaskInput, CreateTaskOutput,
    UpdateTaskInput, UpdateTaskOutput,
    DeleteTaskInput, DeleteTaskOutput,
    ListTasksInput, ListTasksOutput,
    TaskRouteInput, TaskRouteOutput
)
import os
import requests
from urllib.parse import urlparse
import io
import base64
import re
import uuid

from storage.database.db import get_session

# 延迟导入以避免潜在的模块加载问题
def _get_user_manager():
    from storage.database.user_manager import UserManager, UserCreate, UserUpdate, RateLimitManager
    return UserManager, UserCreate, UserUpdate, RateLimitManager


def router_node(state: RouterInput, config: RunnableConfig, runtime: Runtime[Context]) -> RouterOutput:
    """
    title: 路由节点
    desc: 用于条件分支的虚拟节点，传递 call_type
    """
    return RouterOutput(call_type=state.call_type)


def operation_route_node(state: OperationRouteInput, config: RunnableConfig, runtime: Runtime[Context]) -> OperationRouteOutput:
    """
    title: 操作路由节点
    desc: 用于账号管理的二级路由，传递 operation_type
    """
    return OperationRouteOutput(operation_type=state.operation_type)


def route_by_operation_type(state: OperationRouteInput) -> str:
    """
    title: 账号管理二级路由
    desc: 根据操作类型分发到不同的节点
    """
    operation_type = state.operation_type

    if operation_type == "check_rate_limit":
        return "限流检查"
    elif operation_type == "update_rate_limit":
        return "更新限流"
    elif operation_type == "register":
        return "用户注册"
    elif operation_type == "login":
        return "用户登录"
    elif operation_type == "get_user_by_id":
        return "查询单个用户"
    elif operation_type == "update_user":
        return "更新用户"
    elif operation_type == "delete_user":
        return "删除用户"
    elif operation_type == "list_users":
        return "用户列表"
    else:
        return "未知操作"


def parse_file_type(file_type: Optional[str]) -> str:
    """
    解析 file_type，支持枚举值和 MIME 类型

    Args:
        file_type: 文件类型，可以是枚举值或 MIME 类型

    Returns:
        解析后的文件类型枚举值

    Raises:
        ValueError: 如果 file_type 格式无效或不支持
    """
    if not file_type:
        return "default"

    # 支持的枚举值
    enum_types = ['image', 'video', 'audio', 'document', 'default']

    # 如果是枚举值，直接返回
    if file_type in enum_types:
        return file_type

    # 如果是 MIME 类型，解析前缀
    if '/' in file_type:
        mime_prefix = file_type.split('/')[0].lower()
        if mime_prefix in enum_types or mime_prefix in ['application', 'text']:
            # application/* 和 text/* 归类为 document
            if mime_prefix in ['application', 'text']:
                return 'document'
            return mime_prefix
        else:
            raise ValueError(f"不支持的文件类型前缀: {mime_prefix}（完整类型: {file_type}）")
    else:
        raise ValueError(f"无效的文件类型格式: {file_type}")


def unpack_input_data_node(state: UnpackInputDataInput, config: RunnableConfig, runtime: Runtime[Context]) -> UnpackInputDataOutput:
    """
    title: 数据解包
    desc: 将 input 对象中的业务字段解包到全局状态中，支持 MIME 类型的 file_type
    """
    ctx = runtime.context

    # 从 input 对象中解包数据
    input_data = state.input if state.input else None

    # 处理 file_type 解析
    processed_file = None
    if input_data and input_data.file:
        # 解析 file_type
        parsed_type = parse_file_type(input_data.file.file_type)
        processed_file = input_data.file.model_copy(update={"file_type": parsed_type})

    # 处理 file_list 中的 file_type
    processed_file_list = None
    if input_data and input_data.file_list:
        processed_file_list = []
        for file_item in input_data.file_list:
            parsed_type = parse_file_type(file_item.file_type)
            processed_file = file_item.model_copy(update={"file_type": parsed_type})
            processed_file_list.append(processed_file)

    return UnpackInputDataOutput(
        call_type=state.call_type,
        tool_type=state.tool_type,
        operation_type=input_data.operation_type if input_data else None,
        username=input_data.username if input_data else None,
        password=input_data.password if input_data else None,
        file=processed_file,
        file_list=processed_file_list,
        user_id=input_data.user_id if input_data else None,
        runninghub_link=input_data.runninghub_link if input_data else None,
        prompt=input_data.prompt if input_data else None,
        # 用户管理相关字段
        phone=input_data.phone if input_data else None,
        ip=input_data.ip if input_data else None,
        password_hash=input_data.password_hash if input_data else None,
        avatar=input_data.avatar if input_data else None,
        team_id=input_data.team_id if input_data else None,
        gold_credits=input_data.gold_credits if input_data else None,
        silver_credits=input_data.silver_credits if input_data else None,
        role=input_data.role if input_data else None,
        tier=input_data.tier if input_data else None,
        account_status=input_data.account_status if input_data else None,
        updates=input_data.updates if input_data else None,
        operator_role=input_data.operator_role if input_data else None,
        operator_user_id=input_data.operator_user_id if input_data else None,
        page=input_data.page if input_data else None,
        limit=input_data.limit if input_data else None,
        filter=input_data.filter if input_data else None,
        # 任务管理相关字段
        task_id=input_data.task_id if input_data else None,
        task_data=input_data.task_data if input_data else None,
        task_updates=input_data.task_updates if input_data else None
    )

from storage.s3.s3_storage import S3SyncStorage


# 初始化对象存储客户端
storage = S3SyncStorage(
    endpoint_url=os.getenv("COZE_BUCKET_ENDPOINT_URL"),
    access_key=os.getenv("COZE_ACCESS_KEY", ""),
    secret_key=os.getenv("COZE_SECRET_KEY", ""),
    bucket_name=os.getenv("COZE_BUCKET_NAME"),
    region=os.getenv("COZE_BUCKET_REGION", "cn-beijing"),
)


# ============ 用户管理节点 ============

def check_rate_limit_node(state: CheckRateLimitInput, config: RunnableConfig, runtime: Runtime[Context]) -> CheckRateLimitOutput:
    """
    title: 限流检查
    desc: 检查手机号和IP地址的请求频率限制
    integrations: 数据库
    """
    UserManager, UserCreate, UserUpdate, RateLimitManager = _get_user_manager()
    ctx = runtime.context

    db = get_session()
    try:
        rate_mgr = RateLimitManager()
        user_mgr = UserManager()

        # 1. 检查封禁状态
        blocked_info = rate_mgr.check_blocked_status(db, state.phone, state.ip)
        if blocked_info:
            return CheckRateLimitOutput(
                result={"allowed": False, "reason": "账号已被封禁，请稍后再试"},
                allowed=False,
                reason="账号已被封禁，请稍后再试",
                user_exists=False
            )

        # 2. 检查手机号是否已注册
        existing_user = user_mgr.get_user_by_phone(db, state.phone)
        if existing_user:
            return CheckRateLimitOutput(
                result={"allowed": False, "reason": "该手机号已注册，请直接登录"},
                allowed=False,
                reason="该手机号已注册，请直接登录",
                user_exists=True
            )

        # 3. 计算时间窗口内的请求次数
        limits = rate_mgr.check_limits(db, state.phone, state.ip)

        # 4. 判断是否超过限制
        if limits["blocked_phone_10min"]:
            return CheckRateLimitOutput(
                result={"allowed": False, "reason": "该手机号发送验证码过于频繁，请10分钟后再试"},
                allowed=False,
                reason="该手机号发送验证码过于频繁，请10分钟后再试",
                user_exists=False
            )

        if limits["blocked_phone_1hour"]:
            return CheckRateLimitOutput(
                result={"allowed": False, "reason": "该手机号今日发送次数已达上限，请1小时后再试"},
                allowed=False,
                reason="该手机号今日发送次数已达上限，请1小时后再试",
                user_exists=False
            )

        if limits["blocked_ip_10min"]:
            return CheckRateLimitOutput(
                result={"allowed": False, "reason": "当前网络请求过于频繁，请稍后再试"},
                allowed=False,
                reason="当前网络请求过于频繁，请稍后再试",
                user_exists=False
            )

        if limits["blocked_ip_1hour"]:
            return CheckRateLimitOutput(
                result={"allowed": False, "reason": "当前网络请求已达上限，请1小时后再试"},
                allowed=False,
                reason="当前网络请求已达上限，请1小时后再试",
                user_exists=False
            )

        # 5. 所有检查通过
        return CheckRateLimitOutput(
            result={"allowed": True},
            allowed=True,
            user_exists=False
        )

    finally:
        db.close()


def create_user_node(state: CreateUserInput, config: RunnableConfig, runtime: Runtime[Context]) -> CreateUserOutput:
    """
    title: 创建用户
    desc: 创建新用户记录
    integrations: 数据库
    """
    UserManager, UserCreate, UserUpdate, RateLimitManager = _get_user_manager()
    ctx = runtime.context

    db = get_session()
    try:
        user_mgr = UserManager()

        user_in = UserCreate(
            phone=state.phone,
            password_hash=state.password_hash,
            username=state.username,
            avatar=state.avatar,
            team_id=state.team_id,
            gold_credits=state.gold_credits,
            silver_credits=state.silver_credits,
            role=state.role,
            tier=state.tier,
            account_status=state.account_status
        )

        db_user = user_mgr.create_user(db, user_in)

        if db_user is None:
            return CreateUserOutput(
                success=False,
                error="该手机号已被注册"
            )

        user_data = {
            "user_id": db_user.user_id,
            "phone": db_user.phone,
            "username": db_user.username,
            "avatar": db_user.avatar,
            "team_id": db_user.team_id,
            "gold_credits": db_user.gold_credits,
            "silver_credits": db_user.silver_credits,
            "role": db_user.role,
            "tier": db_user.tier,
            "account_status": db_user.account_status,
            "created_at": int(db_user.created_at.timestamp() * 1000),
            "updated_at": int(db_user.updated_at.timestamp() * 1000) if db_user.updated_at else None
        }

        return CreateUserOutput(
            result={"success": True, "user": user_data},
            success=True,
            user=user_data
        )

    finally:
        db.close()


def update_rate_limit_node(state: UpdateRateLimitInput, config: RunnableConfig, runtime: Runtime[Context]) -> UpdateRateLimitOutput:
    """
    title: 更新限流记录
    desc: 更新或创建限流记录，并检查是否需要封禁
    integrations: 数据库
    """
    UserManager, UserCreate, UserUpdate, RateLimitManager = _get_user_manager()
    ctx = runtime.context

    db = get_session()
    try:
        rate_mgr = RateLimitManager()

        # 1. 获取或创建记录
        record = rate_mgr.get_or_create(db, state.phone, state.ip)

        # 2. 更新请求次数
        record = rate_mgr.update_count(db, record)

        # 3. 检查是否需要封禁
        limits = rate_mgr.check_limits(db, state.phone, state.ip)

        if limits["blocked_phone_10min"] or limits["blocked_phone_1hour"]:
            rate_mgr.block(db, record, block_duration_hours=1)
            return UpdateRateLimitOutput(
                result={"success": True, "blocked": True, "message": "触发限流封禁"},
                success=True,
                blocked=True
            )

        if limits["blocked_ip_10min"] or limits["blocked_ip_1hour"]:
            rate_mgr.block(db, record, block_duration_hours=2)
            return UpdateRateLimitOutput(
                result={"success": True, "blocked": True, "message": "触发限流封禁"},
                success=True,
                blocked=True
            )

        return UpdateRateLimitOutput(
            result={"success": True, "blocked": False, "message": "更新成功"},
            success=True,
            blocked=False
        )

    finally:
        db.close()


def register_with_limit_node(state: RegisterWithLimitInput, config: RunnableConfig, runtime: Runtime[Context]) -> RegisterWithLimitOutput:
    """
    title: 用户注册
    desc: 完整的注册流程：检查限流 -> 创建用户 -> 更新限流记录
    integrations: 数据库
    """
    ctx = runtime.context

    # 1. 检查限流
    check_result = check_rate_limit_node(
        CheckRateLimitInput(phone=state.phone, ip=state.ip),
        config,
        runtime
    )

    if not check_result.allowed:
        return RegisterWithLimitOutput(
            result={"success": False, "error": check_result.reason},
            success=False,
            error=check_result.reason
        )

    # 2. 创建用户
    create_result = create_user_node(
        CreateUserInput(
            phone=state.phone,
            password_hash=state.password_hash,
            username=state.username,
            avatar=state.avatar
        ),
        config,
        runtime
    )

    if not create_result.success:
        return RegisterWithLimitOutput(
            result={"success": False, "error": create_result.error},
            success=False,
            error=create_result.error
        )

    # 3. 更新限流记录
    update_result = update_rate_limit_node(
        UpdateRateLimitInput(phone=state.phone, ip=state.ip),
        config,
        runtime
    )

    return RegisterWithLimitOutput(
        result={"success": True, "user": create_result.user},
        success=True,
        user=create_result.user
    )


def get_user_node(state: GetUserInput, config: RunnableConfig, runtime: Runtime[Context]) -> GetUserOutput:
    """
    title: 查询用户
    desc: 根据手机号和密码查询用户信息（用于登录）
    integrations: 数据库
    """
    UserManager, UserCreate, UserUpdate, RateLimitManager = _get_user_manager()
    from storage.database.user_manager import verify_password
    ctx = runtime.context

    db = get_session()
    try:
        user_mgr = UserManager()

        # 1. 查询用户
        db_user = user_mgr.get_user_by_phone(db, state.phone)

        if not db_user:
            return GetUserOutput(
                result={"success": False, "error": "用户不存在"},
                success=False,
                error="用户不存在"
            )

        # 2. 验证密码
        if not verify_password(state.password, db_user.password_hash):
            return GetUserOutput(
                result={"success": False, "error": "密码错误"},
                success=False,
                error="密码错误"
            )

        # 3. 返回用户信息
        user_data = {
            "user_id": db_user.user_id,
            "phone": db_user.phone,
            "username": db_user.username,
            "avatar": db_user.avatar,
            "team_id": db_user.team_id,
            "gold_credits": db_user.gold_credits,
            "silver_credits": db_user.silver_credits,
            "role": db_user.role,
            "tier": db_user.tier,
            "account_status": db_user.account_status,
            "created_at": int(db_user.created_at.timestamp() * 1000),
            "updated_at": int(db_user.updated_at.timestamp() * 1000) if db_user.updated_at else None
        }

        return GetUserOutput(
            result={"success": True, "user": user_data},
            success=True,
            user=user_data
        )

    finally:
        db.close()


def get_user_by_id_node(state: GetUserByIdInput, config: RunnableConfig, runtime: Runtime[Context]) -> GetUserByIdOutput:
    """
    title: 查询单个用户
    desc: 根据用户ID查询用户信息
    integrations: 数据库
    """
    UserManager, UserCreate, UserUpdate, RateLimitManager = _get_user_manager()
    ctx = runtime.context

    db = get_session()
    try:
        user_mgr = UserManager()

        # 查询用户
        db_user = user_mgr.get_user_by_id(db, state.user_id)

        if not db_user:
            return GetUserByIdOutput(
                result={"success": False, "error": "用户不存在"},
                success=False,
                error="用户不存在"
            )

        # 返回用户信息
        user_data = {
            "user_id": db_user.user_id,
            "phone": db_user.phone,
            "username": db_user.username,
            "avatar": db_user.avatar,
            "team_id": db_user.team_id,
            "gold_credits": db_user.gold_credits,
            "silver_credits": db_user.silver_credits,
            "role": db_user.role,
            "tier": db_user.tier,
            "account_status": db_user.account_status,
            "created_at": int(db_user.created_at.timestamp() * 1000),
            "updated_at": int(db_user.updated_at.timestamp() * 1000) if db_user.updated_at else None
        }

        return GetUserByIdOutput(
            result={"success": True, "user": user_data},
            success=True,
            user=user_data
        )

    finally:
        db.close()


def update_user_node(state: UpdateUserInput, config: RunnableConfig, runtime: Runtime[Context]) -> UpdateUserOutput:
    """
    title: 更新用户
    desc: 更新用户信息（管理员可更新任何用户，普通用户只能更新自己）。支持Base64头像自动转换为永久公开URL
    integrations: 数据库, 对象存储
    """
    UserManager, UserCreate, UserUpdate, RateLimitManager = _get_user_manager()
    ctx = runtime.context

    # 处理头像：如果为Base64则转换为永久URL
    processed_avatar = state.avatar
    if state.avatar and state.avatar.startswith('data:image'):
        try:
            # 解析 Data URL 格式：data:image/png;base64,xxx
            match = re.match(r"data:([^;]+);base64,(.+)", state.avatar)
            if match:
                mime_type = match.group(1)  # 例如：image/png
                base64_data = match.group(2)

                # 解码 Base64
                try:
                    file_content = base64.b64decode(base64_data)
                except Exception:
                    # 解码失败，保持原样
                    processed_avatar = state.avatar
                else:
                    # 根据类型确定文件名
                    if "png" in mime_type:
                        filename = "avatar.png"
                    elif "jpeg" in mime_type or "jpg" in mime_type:
                        filename = "avatar.jpg"
                    elif "gif" in mime_type:
                        filename = "avatar.gif"
                    elif "webp" in mime_type:
                        filename = "avatar.webp"
                    else:
                        filename = f"avatar.{mime_type.split('/')[-1] if '/' in mime_type else 'bin'}"

                    # 上传到对象存储，设置为公共可读
                    file_key = storage.upload_file(
                        file_content=file_content,
                        file_name=filename,
                        content_type=mime_type,
                        acl='public-read'
                    )

                    # 生成永久公开 URL（使用 Coze 公开域名）
                    public_domain = "https://coze-coding-project.tos.coze.site"
                    processed_avatar = f"{public_domain}/{storage.bucket_name}/{file_key}"
        except Exception:
            # 处理失败，保持原样
            processed_avatar = state.avatar

    db = get_session()
    try:
        user_mgr = UserManager()

        # 权限验证：管理员可以更新任何用户，普通用户只能更新自己
        if state.operator_role != 'admin' and state.operator_user_id != state.user_id:
            return UpdateUserOutput(
                result={"success": False, "error": "权限不足，仅管理员可更新其他用户"},
                success=False,
                error="权限不足，仅管理员可更新其他用户"
            )

        # 构造更新字典
        updates = {}
        if state.phone is not None:
            updates['phone'] = state.phone
        if state.username is not None:
            updates['username'] = state.username
        if state.avatar is not None:
            updates['avatar'] = processed_avatar  # 使用处理后的头像
        if state.team_id is not None:
            updates['team_id'] = state.team_id
        if state.gold_credits is not None:
            updates['gold_credits'] = state.gold_credits
        if state.silver_credits is not None:
            updates['silver_credits'] = state.silver_credits
        if state.role is not None:
            updates['role'] = state.role
        if state.tier is not None:
            updates['tier'] = state.tier
        if state.account_status is not None:
            updates['account_status'] = state.account_status

        # 如果没有提供任何更新字段，返回错误
        if not updates:
            return UpdateUserOutput(
                result={"success": False, "error": "未提供任何更新字段"},
                success=False,
                error="未提供任何更新字段"
            )

        user_in = UserUpdate(**updates)
        db_user = user_mgr.update_user(db, state.user_id, user_in)

        if not db_user:
            return UpdateUserOutput(
                result={"success": False, "error": "用户不存在"},
                success=False,
                error="用户不存在"
            )

        user_data = {
            "user_id": db_user.user_id,
            "phone": db_user.phone,
            "username": db_user.username,
            "avatar": db_user.avatar,
            "team_id": db_user.team_id,
            "gold_credits": db_user.gold_credits,
            "silver_credits": db_user.silver_credits,
            "role": db_user.role,
            "tier": db_user.tier,
            "account_status": db_user.account_status,
            "created_at": int(db_user.created_at.timestamp() * 1000),
            "updated_at": int(db_user.updated_at.timestamp() * 1000) if db_user.updated_at else None
        }

        return UpdateUserOutput(
            result={"success": True, "user": user_data},
            success=True,
            user=user_data
        )

    finally:
        db.close()


def delete_user_node(state: DeleteUserInput, config: RunnableConfig, runtime: Runtime[Context]) -> DeleteUserOutput:
    """
    title: 删除用户
    desc: 软删除用户（管理员功能）
    integrations: 数据库
    """
    UserManager, UserCreate, UserUpdate, RateLimitManager = _get_user_manager()
    ctx = runtime.context

    # 验证管理员权限
    if state.operator_role != 'admin':
        return DeleteUserOutput(success=False, error="权限不足，仅管理员可操作")

    db = get_session()
    try:
        user_mgr = UserManager()

        success = user_mgr.delete_user(db, state.user_id)

        if not success:
            return DeleteUserOutput(success=False, error="用户不存在")

        return DeleteUserOutput(
            result={"success": True, "deleted": True},
            success=True
        )

    finally:
        db.close()


def list_users_node(state: ListUsersInput, config: RunnableConfig, runtime: Runtime[Context]) -> ListUsersOutput:
    """
    title: 用户列表
    desc: 查询用户列表（管理员功能）
    integrations: 数据库
    """
    UserManager, UserCreate, UserUpdate, RateLimitManager = _get_user_manager()
    ctx = runtime.context

    # 验证管理员权限
    if state.operator_role != 'admin':
        return ListUsersOutput(success=False, error="权限不足，仅管理员可操作")

    db = get_session()
    try:
        user_mgr = UserManager()

        filter_dict = {}
        if state.filter:
            filter_dict = {
                "role": state.filter.get("role"),
                "tier": state.filter.get("tier"),
                "account_status": state.filter.get("account_status")
            }

        users, total = user_mgr.list_users(
            db,
            page=state.page,
            limit=state.limit,
            **filter_dict
        )

        users_data = []
        for user in users:
            users_data.append({
                "user_id": user.user_id,
                "phone": user.phone,
                "username": user.username,
                "avatar": user.avatar,
                "team_id": user.team_id,
                "gold_credits": user.gold_credits,
                "silver_credits": user.silver_credits,
                "role": user.role,
                "tier": user.tier,
                "account_status": user.account_status,
                "created_at": int(user.created_at.timestamp() * 1000),
                "updated_at": int(user.updated_at.timestamp() * 1000) if user.updated_at else None
            })

        return ListUsersOutput(
            result={"success": True, "users": users_data, "total": total, "page": state.page, "limit": state.limit},
            success=True,
            users=users_data,
            total=total,
            page=state.page,
            limit=state.limit
        )

    finally:
        db.close()


def upload_node(state: UploadInput, config: RunnableConfig, runtime: Runtime[Context]) -> UploadOutput:
    """
    title: 文件上传
    desc: 将上传的文件存入对象存储，并生成 24 小时公开 URL 返回。支持远程 URL、本地路径和 Base64 格式
    integrations: 对象存储
    """
    ctx = runtime.context

    if not state.file:
        return UploadOutput(result={"success": False, "message": "未提供文件"})

    try:
        # 从 URL 读取文件内容
        file_url = state.file.url

        # 判断数据类型
        if file_url.startswith(("http://", "https://")):
            # 远程 URL：使用 upload_from_url
            file_key = storage.upload_from_url(url=file_url)

        elif file_url.startswith("data:image") or (file_url.startswith("data:application") and ";base64," in file_url):
            # Base64 格式（Data URL 格式）
            # 解析 Data URL 格式：data:image/png;base64,xxx
            match = re.match(r"data:([^;]+);base64,(.+)", file_url)
            if not match:
                return UploadOutput(result={"success": False, "message": "无效的 Base64 格式"})

            mime_type = match.group(1)  # 例如：image/png
            base64_data = match.group(2)

            # 解码 Base64
            try:
                file_content = base64.b64decode(base64_data)
            except Exception as e:
                return UploadOutput(result={"success": False, "message": f"Base64 解码失败: {str(e)}"})

            # 根据类型确定文件名
            if "png" in mime_type:
                filename = "image.png"
            elif "jpeg" in mime_type or "jpg" in mime_type:
                filename = "image.jpg"
            elif "gif" in mime_type:
                filename = "image.gif"
            elif "webp" in mime_type:
                filename = "image.webp"
            else:
                filename = f"file.{mime_type.split('/')[-1] if '/' in mime_type else 'bin'}"

            # 上传到对象存储
            file_key = storage.upload_file(
                file_content=file_content,
                file_name=filename,
                content_type=mime_type
            )

        else:
            # 本地路径：读取文件内容后上传
            # 如果包含 file:// 前缀，去掉它
            clean_path = file_url.replace("file://", "")
            with open(clean_path, "rb") as f:
                file_content = f.read()
                # 从 URL 提取文件名
                filename = os.path.basename(clean_path)
                file_key = storage.upload_file(
                    file_content=file_content,
                    file_name=filename,
                    content_type="application/octet-stream"
                )

        # 生成 24 小时（86400 秒）公开 URL
        public_url = storage.generate_presigned_url(key=file_key, expire_time=86400)

        return UploadOutput(result={
            "success": True,
            "message": "文件上传成功",
            "public_url": public_url,
            "file_key": file_key
        })

    except Exception as e:
        return UploadOutput(result={"success": False, "message": f"文件上传失败: {str(e)}"})


def save_node(state: SaveInput, config: RunnableConfig, runtime: Runtime[Context]) -> SaveOutput:
    """
    title: 保存历史
    desc: 接收用户 ID 和 RunningHub 链接，将图片持久化转存到对象存储
    integrations: 对象存储
    """
    ctx = runtime.context

    if not state.user_id or not state.runninghub_link:
        return SaveOutput(result={"success": False, "message": "缺少必要参数：user_id 或 runninghub_link"})

    try:
        # 将 RunningHub 链接中的图片转存到对象存储（持久化）
        file_key = storage.upload_from_url(url=state.runninghub_link)

        # 生成永久链接（不设置过期时间，或者设置很长的时间）
        # 这里使用 10 年有效期作为"永久"链接
        permanent_url = storage.generate_presigned_url(key=file_key, expire_time=315360000)

        return SaveOutput(result={
            "success": True,
            "message": "保存成功",
            "permanent_link": permanent_url
        })

    except Exception as e:
        return SaveOutput(result={"success": False, "message": f"保存失败: {str(e)}"})


def task_route_node(state: TaskRouteInput, config: RunnableConfig, runtime: Runtime[Context]) -> TaskRouteOutput:
    """
    title: 任务路由
    desc: 用于任务管理的二级路由，传递 operation_type
    """
    return TaskRouteOutput(operation_type=state.operation_type)


def route_by_task_operation_type(state: TaskRouteInput) -> str:
    """
    title: 任务管理二级路由
    desc: 根据操作类型分发到不同的节点
    """
    operation_type = state.operation_type

    if operation_type == "create_task":
        return "创建任务"
    elif operation_type == "update_task":
        return "更新任务"
    elif operation_type == "delete_task":
        return "删除任务"
    elif operation_type == "list_tasks":
        return "查询任务列表"
    else:
        return "未知操作"


def create_task_node(state: CreateTaskInput, config: RunnableConfig, runtime: Runtime[Context]) -> CreateTaskOutput:
    """
    title: 创建任务
    desc: 创建新的任务记录（仅限注册用户）
    integrations: 数据库
    """
    ctx = runtime.context

    if not state.user_id or not state.task_data:
        return CreateTaskOutput(result={"success": False, "message": "缺少必要参数：user_id 或 task_data"})

    try:
        from storage.database.task_manager import TaskManager, TaskCreate

        db = get_session()
        try:
            task_mgr = TaskManager()

            # 验证用户权限
            has_permission, error_msg = task_mgr.verify_user_permission(db, state.user_id)
            if not has_permission:
                return CreateTaskOutput(result={"success": False, "message": error_msg})

            task_in = TaskCreate(
                id=state.task_data.get("id"),
                user_id=state.user_id,
                team_id=state.task_data.get("team_id"),
                platform=state.task_data.get("platform"),
                platform_task_id=state.task_data.get("platform_task_id"),
                type=state.task_data.get("type"),
                workflow_parameters=state.task_data.get("workflow_parameters"),
                parameter_snapshot=state.task_data.get("parameter_snapshot"),
                batch_id=state.task_data.get("batch_id"),
                connection_mode=state.task_data.get("connection_mode", "sse")
            )

            db_task = task_mgr.create_task(db, task_in)

            return CreateTaskOutput(result={
                "success": True,
                "message": "任务创建成功",
                "task_id": db_task.id,
                "status": db_task.status
            })

        finally:
            db.close()

    except Exception as e:
        return CreateTaskOutput(result={"success": False, "message": f"创建失败: {str(e)}"})


def update_task_node(state: UpdateTaskInput, config: RunnableConfig, runtime: Runtime[Context]) -> UpdateTaskOutput:
    """
    title: 更新任务
    desc: 更新任务状态、结果或错误信息（仅限注册用户）
    integrations: 数据库
    """
    ctx = runtime.context

    if not state.task_id:
        return UpdateTaskOutput(result={"success": False, "message": "缺少必要参数：task_id"})

    try:
        from storage.database.task_manager import TaskManager, TaskUpdate

        db = get_session()
        try:
            task_mgr = TaskManager()

            # 验证用户权限
            has_permission, error_msg = task_mgr.verify_user_permission(db, state.user_id or "")
            if not has_permission:
                return UpdateTaskOutput(result={"success": False, "message": error_msg})

            task_in = TaskUpdate(
                status=state.task_updates.get("status"),
                result=state.task_updates.get("result"),
                error=state.task_updates.get("error"),
                completed_at=state.task_updates.get("completed_at"),
                deduction_result=state.task_updates.get("deduction_result")
            )

            db_task = task_mgr.update_task(db, state.task_id, task_in)

            if not db_task:
                return UpdateTaskOutput(result={"success": False, "message": "任务不存在"})

            return UpdateTaskOutput(result={
                "success": True,
                "message": "任务更新成功",
                "task_id": db_task.id,
                "status": db_task.status
            })

        finally:
            db.close()

    except Exception as e:
        return UpdateTaskOutput(result={"success": False, "message": f"更新失败: {str(e)}"})


def delete_task_node(state: DeleteTaskInput, config: RunnableConfig, runtime: Runtime[Context]) -> DeleteTaskOutput:
    """
    title: 删除任务
    desc: 根据任务ID删除任务（软删除，仅限注册用户；管理员可删除任何任务，普通用户只能删除自己的任务）
    integrations: 数据库
    """
    ctx = runtime.context

    if not state.task_id or not state.user_id:
        return DeleteTaskOutput(result={"success": False, "message": "缺少必要参数：task_id 或 user_id"})

    try:
        from storage.database.task_manager import TaskManager

        db = get_session()
        try:
            task_mgr = TaskManager()
            success, message = task_mgr.delete_task(db, state.task_id, state.user_id)
            
            return DeleteTaskOutput(result={
                "success": success,
                "message": message
            })

        finally:
            db.close()

    except Exception as e:
        return DeleteTaskOutput(result={"success": False, "message": f"删除失败: {str(e)}"})


def list_tasks_node(state: ListTasksInput, config: RunnableConfig, runtime: Runtime[Context]) -> ListTasksOutput:
    """
    title: 查询任务列表
    desc: 根据用户ID查询任务列表，支持状态筛选和分页（仅限注册用户）
    integrations: 数据库
    """
    ctx = runtime.context

    if not state.user_id:
        return ListTasksOutput(result={"success": False, "message": "缺少必要参数：user_id"})

    try:
        from storage.database.task_manager import TaskManager

        db = get_session()
        try:
            task_mgr = TaskManager()

            # 验证用户权限
            has_permission, error_msg = task_mgr.verify_user_permission(db, state.user_id)
            if not has_permission:
                return ListTasksOutput(result={"success": False, "message": error_msg})

            page = state.page or 1
            limit = state.limit or 10
            skip = (page - 1) * limit

            # 构建筛选条件
            filters = {}
            if state.team_id:
                filters["team_id"] = state.team_id

            tasks = task_mgr.get_tasks_by_user_id(
                db,
                user_id=state.user_id,
                status=state.status,
                skip=skip,
                limit=limit,
                **filters
            )

            total = task_mgr.count_tasks_by_user_id(db, state.user_id, state.status)

            # 转换为可序列化的字典列表
            task_list = []
            for task in tasks:
                task_list.append({
                    "id": task.id,
                    "user_id": task.user_id,
                    "team_id": task.team_id,
                    "platform": task.platform,
                    "platform_task_id": task.platform_task_id,
                    "type": task.type,
                    "status": task.status,
                    "workflow_parameters": task.workflow_parameters,
                    "parameter_snapshot": task.parameter_snapshot,
                    "result": task.result,
                    "error": task.error,
                    "deduction_result": task.deduction_result,
                    "created_at": task.created_at,
                    "updated_at": task.updated_at,
                    "completed_at": task.completed_at,
                    "batch_id": task.batch_id,
                    "connection_mode": task.connection_mode,
                    "is_deleted": task.is_deleted
                })

            return ListTasksOutput(result={
                "success": True,
                "message": "查询成功",
                "tasks": task_list,
                "total": total,
                "page": page,
                "limit": limit
            })

        finally:
            db.close()

    except Exception as e:
        return ListTasksOutput(result={"success": False, "message": f"查询失败: {str(e)}"})


def format_response_node(state: FormatResponseInput, config: RunnableConfig, runtime: Runtime[Context]) -> FormatResponseOutput:
    """
    title: 统一返回
    desc: 将各节点的结果统一格式化为 {code, msg, data} 格式返回
    """
    ctx = runtime.context

    try:
        result = state.result if state.result is not None else {}

        # 处理空结果或 None
        if not isinstance(result, (dict, str)):
            return FormatResponseOutput(response_data={"code": -1, "msg": "无效的结果格式", "data": None})

        # 处理工具节点的字符串结果
        if isinstance(result, str):
            return FormatResponseOutput(response_data={"code": 0, "msg": "操作成功", "data": {"result": result}})

        # 处理空字典
        if not result:
            return FormatResponseOutput(response_data={"code": -1, "msg": "无结果返回", "data": None})

        # 处理不同类型的 dict 结果
        # 情况1: result 中有 success 字段（通用格式）
        if "success" in result:
            if result.get("success"):
                code = 0
                msg = result.get("message", "操作成功")
                data = {k: v for k, v in result.items() if k not in ["success", "message"]}
            else:
                code = -1
                msg = result.get("error", result.get("message", "操作失败"))
                data = None
        # 情况2: result 中有 allowed 字段（限流检查格式）
        elif "allowed" in result:
            if result.get("allowed"):
                code = 0
                msg = result.get("message", "检查通过")
                data = {k: v for k, v in result.items() if k not in ["allowed", "message"]}
            else:
                code = -1
                msg = result.get("reason", result.get("message", "检查未通过"))
                data = None
        # 情况3: 其他格式，假设成功
        else:
            code = 0
            msg = "操作成功"
            data = result

        return FormatResponseOutput(response_data={"code": code, "msg": msg, "data": data})

    except Exception as e:
        # 异常情况下返回友好的错误信息
        return FormatResponseOutput(response_data={"code": -1, "msg": f"结果格式化失败: {str(e)}", "data": None})


# ============ 工具节点 ============

def tool_route_node(state: ToolRouteInput, config: RunnableConfig, runtime: Runtime[Context]) -> ToolRouteOutput:
    """
    title: 工具路由
    desc: 根据 tool_type 将请求路由到不同的工具节点
    """
    ctx = runtime.context
    return ToolRouteOutput(tool_type=state.tool_type)


def reverse_image_node(state: ReverseImageInput, config: RunnableConfig, runtime: Runtime[Context]) -> ReverseImageOutput:
    """
    title: 提示词生成
    desc: 使用视觉模型分析图像，生成提示词
    integrations: 大语言模型
    """
    ctx = runtime.context

    if not state.file:
        return ReverseImageOutput(result={"success": False, "message": "未提供图像文件"})

    try:
        # 读取配置文件
        cfg_file = os.path.join(os.getenv("COZE_WORKSPACE_PATH"), config['metadata']['llm_cfg'])
        with open(cfg_file, 'r') as fd:
            _cfg = json.load(fd)

        llm_config = _cfg.get("config", {})
        sp = _cfg.get("sp", "")
        up = _cfg.get("up", "")

        # 使用 jinja2 模板渲染提示词
        sp_tpl = Template(sp)
        system_prompt_content = sp_tpl.render()

        up_tpl = Template(up)
        user_prompt_content = up_tpl.render()

        # 初始化 LLM 客户端
        client = LLMClient(ctx=ctx)

        # 构造多模态消息
        messages = [
            SystemMessage(content=system_prompt_content),
            HumanMessage(content=[
                {
                    "type": "text",
                    "text": user_prompt_content
                },
                {
                    "type": "image_url",
                    "image_url": {"url": state.file.url}
                }
            ])
        ]

        # 调用模型
        response = client.invoke(
            messages=messages,
            model=llm_config.get("model"),
            temperature=llm_config.get("temperature", 0.7),
            max_tokens=llm_config.get("max_tokens", 1000)
        )

        return ReverseImageOutput(result={"success": True, "message": "提示词生成成功", "result": response.content})

    except Exception as e:
        return ReverseImageOutput(result={"success": False, "message": f"提示词生成失败: {str(e)}"})


def translate_doubao_node(state: TranslateDoubaoInput, config: RunnableConfig, runtime: Runtime[Context]) -> TranslateDoubaoOutput:
    """
    title: 翻译
    desc: 使用豆包平衡模型进行中英互译
    integrations: 大语言模型
    """
    ctx = runtime.context

    try:
        # 读取配置文件
        cfg_file = os.path.join(os.getenv("COZE_WORKSPACE_PATH"), config['metadata']['llm_cfg'])
        with open(cfg_file, 'r') as fd:
            _cfg = json.load(fd)

        llm_config = _cfg.get("config", {})
        sp = _cfg.get("sp", "")
        up = _cfg.get("up", "")

        # 使用 jinja2 模板渲染提示词
        up_tpl = Template(up)
        user_prompt_content = up_tpl.render({"text": state.prompt})

        # 初始化 LLM 客户端
        client = LLMClient(ctx=ctx)

        # 构造消息
        messages = [
            SystemMessage(content=sp),
            HumanMessage(content=user_prompt_content)
        ]

        # 调用模型
        response = client.invoke(
            messages=messages,
            model=llm_config.get("model"),
            temperature=llm_config.get("temperature", 0.3),
            max_tokens=llm_config.get("max_tokens", 2000)
        )

        return TranslateDoubaoOutput(result={"success": True, "message": "翻译成功", "result": response.content})

    except Exception as e:
        return TranslateDoubaoOutput(result={"success": False, "message": f"翻译失败: {str(e)}"})


def prompt_enhance_node(state: PromptEnhanceInput, config: RunnableConfig, runtime: Runtime[Context]) -> PromptEnhanceOutput:
    """
    title: 提示词增强
    desc: 使用视觉模型理解图片，根据用户的提示词生成增强后的内容
    integrations: 大语言模型
    """
    ctx = runtime.context

    # 验证文件数量
    if not state.file_list or len(state.file_list) < 1:
        return PromptEnhanceOutput(result={"success": False, "message": "至少需要提供 1 个图片文件"})
    if len(state.file_list) > 4:
        return PromptEnhanceOutput(result={"success": False, "message": "最多支持 4 个图片文件"})

    try:
        # 读取配置文件
        cfg_file = os.path.join(os.getenv("COZE_WORKSPACE_PATH"), config['metadata']['llm_cfg'])
        with open(cfg_file, 'r') as fd:
            _cfg = json.load(fd)

        llm_config = _cfg.get("config", {})
        sp = _cfg.get("sp", "")
        up = _cfg.get("up", "")

        # 使用 jinja2 模板渲染提示词
        sp_tpl = Template(sp)
        system_prompt_content = sp_tpl.render({"prompt": state.prompt})

        up_tpl = Template(up)
        user_prompt_content = up_tpl.render({
            "file_list": [f.url for f in state.file_list],
            "prompt": state.prompt
        })

        # 初始化 LLM 客户端
        client = LLMClient(ctx=ctx)

        # 构造多模态消息（支持多图片）
        content = [{"type": "text", "text": user_prompt_content}]
        for file in state.file_list:
            content.append({
                "type": "image_url",
                "image_url": {"url": file.url}
            })

        messages = [
            SystemMessage(content=system_prompt_content),
            HumanMessage(content=content)
        ]

        # 调用模型
        response = client.invoke(
            messages=messages,
            model=llm_config.get("model"),
            temperature=llm_config.get("temperature", 0.7),
            max_tokens=llm_config.get("max_tokens", 2000)
        )

        return PromptEnhanceOutput(result={"success": True, "message": "增强成功", "result": response.content})

    except Exception as e:
        return PromptEnhanceOutput(result={"success": False, "message": f"增强失败: {str(e)}"})


