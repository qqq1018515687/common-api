# 修复 langchain_core 中缺失的类
# 必须在任何 langchain 相关导入之前执行
import logging
import langchain_core.exceptions
import langchain_core.language_models

logger = logging.getLogger(__name__)

# 修复 ContextOverflowError
if not hasattr(langchain_core.exceptions, 'ContextOverflowError'):
    class ContextOverflowError(langchain_core.exceptions.LangChainException):  # type: ignore[attr-defined]
        """ContextOverflowError - 用于兼容性"""
        pass
    langchain_core.exceptions.ContextOverflowError = ContextOverflowError  # type: ignore[attr-defined]

# 修复 ModelProfileRegistry
if not hasattr(langchain_core.language_models, 'ModelProfileRegistry'):
    class ModelProfileRegistry:  # type: ignore[no-redef]
        """ModelProfileRegistry - 用于兼容性"""
        @staticmethod
        def get_default_model_profile(model_name):
            return None
    langchain_core.language_models.ModelProfileRegistry = ModelProfileRegistry  # type: ignore[attr-defined]

from langchain_core.runnables import RunnableConfig
from langgraph.runtime import Runtime
from coze_coding_utils.runtime_ctx.context import Context
from langchain_core.messages import SystemMessage, HumanMessage, AIMessage
from coze_coding_dev_sdk import LLMClient
from jinja2 import Template
import json
import time
from typing import Any, Dict, Optional, List
from datetime import datetime

from graphs.state import (
    UploadInput, UploadOutput, DeleteUploadInput, DeleteUploadOutput,
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
    SendRegisterCodeInput, SendRegisterCodeOutput,
    SendPasswordResetCodeInput, SendPasswordResetCodeOutput,
    RegisterWithLimitInput, RegisterWithLimitOutput,
    RegisterWithCodeInput, RegisterWithCodeOutput,
    ResetPasswordWithCodeInput, ResetPasswordWithCodeOutput,
    GetUserInput, GetUserOutput,
    GetUserByIdInput, GetUserByIdOutput,
    UpdateUserInput, UpdateUserOutput,
    DeleteUserInput, DeleteUserOutput,
    ListUsersInput, ListUsersOutput,
    CreateTaskInput, CreateTaskOutput,
    UpdateTaskInput, UpdateTaskOutput,
    GetTaskInput, GetTaskOutput,
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
import secrets

from storage.database.db import get_session
from storage.database.amounts import gold_amount_to_number
from storage.storage_manager import get_storage_manager, StorageCategory
from utils.aliyun_sms import send_sms_verify_code
import datetime as _dt


def _to_epoch_ms(dt_val: _dt.datetime) -> int:
    """将 datetime 安全转为 13 位毫秒时间戳（修复 +8h 时区偏移）。

    PostgreSQL 时区为 Asia/Shanghai，但 created_at 列是 timestamp without time zone，
    存储的是 +08 本地时间但没有时区标记。
    修复：将 naive datetime 视为 Asia/Shanghai 本地时间，再转 UTC 算 epoch。
    """
    if dt_val.tzinfo is None:
        tz_shanghai = _dt.timezone(_dt.timedelta(hours=8))
        dt_val = dt_val.replace(tzinfo=tz_shanghai)
    return int(dt_val.timestamp() * 1000)

# 延迟导入以避免潜在的模块加载问题
def _get_user_manager():
    from storage.database.user_manager import UserManager, UserCreate, UserUpdate, RateLimitManager
    return UserManager, UserCreate, UserUpdate, RateLimitManager


def _get_register_code_manager():
    from storage.database.user_manager import RegisterCodeManager
    return RegisterCodeManager


def _get_password_reset_code_manager():
    from storage.database.user_manager import PasswordResetCodeManager
    return PasswordResetCodeManager


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
    elif operation_type == "send_register_code":
        return "发送注册验证码"
    elif operation_type == "send_password_reset_code":
        return "发送密码重置验证码"
    elif operation_type == "register":
        return "验证码注册"
    elif operation_type == "register_with_code":
        return "验证码注册"
    elif operation_type == "reset_password_with_code":
        return "验证码重置密码"
    elif operation_type == "login":
        return "用户登录"
    elif operation_type == "get_user_by_id":
        return "查询单个用户"
    elif operation_type == "get_user":
        return "查询单个用户"
    elif operation_type == "update_user":
        return "更新用户"
    elif operation_type == "delete_user":
        return "删除用户"
    elif operation_type == "list_users":
        return "用户列表"
    elif operation_type in [
        "list_objects",
        "get_object_metadata",
        "regenerate_url",
        "delete_object",
        "cleanup_expired",
    ]:
        return "对象储存管理"
    else:
        return "未知操作"


def parse_file_type(file_type: Optional[str]) -> str:
    """
    解析 file_type，支持枚举值和 MIME 类型

    Args:
        file_type: 文件类型，可以是枚举值或 MIME 类型

    Returns:
        解析后的文件类型枚举值（如果无法解析则返回 'document'）
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
            # 不支持的 MIME 类型：归类为 document（安全兜底）
            logger.warning(f"不支持的文件类型前缀: {mime_prefix}（完整类型: {file_type}），归类为 'document'")
            return 'document'
    else:
        # 无效的格式：归类为 document（安全兜底）
        logger.warning(f"无效的文件类型格式: {file_type}，归类为 'document'")
        return 'document'


def unpack_input_data_node(state: UnpackInputDataInput, config: RunnableConfig, runtime: Runtime[Context]) -> UnpackInputDataOutput:
    """
    title: 数据解包
    desc: 将 input 对象中的业务字段解包到全局状态中，支持 MIME 类型的 file_type 和密码自动哈希
    """
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

    # 处理密码哈希转换（如果是注册操作且提供了明文密码）
    password_hash = None
    if input_data:
        password_hash = input_data.password_hash
        if not password_hash and input_data.password and input_data.operation_type == "register":
            # 注册操作：如果提供了 password 但没有 password_hash，则自动转换
            from storage.database.user_manager import hash_password
            password_hash = hash_password(input_data.password)

    return UnpackInputDataOutput(
        call_type=state.call_type,
        tool_type=state.tool_type,
        operation_type=input_data.operation_type if input_data else None,
        username=input_data.username if input_data else None,
        password=input_data.password if input_data else None,
        confirm_password=input_data.confirm_password if input_data else None,
        code=input_data.code if input_data else None,
        file=processed_file,
        file_list=processed_file_list,
        file_key=input_data.file_key if input_data else None,
        category=input_data.category if input_data else None,
        prefix=input_data.prefix if input_data else None,
        folder_name=input_data.folder_name if input_data else None,
        file_name=input_data.file_name if input_data else None,
        content_type=input_data.content_type if input_data else None,
        size=input_data.size if input_data else None,
        file_content_base64=input_data.file_content_base64 if input_data else None,
        convert_to_pdf=input_data.convert_to_pdf if input_data else False,
        asset_mode=input_data.asset_mode if input_data else False,
        expires_in=input_data.expires_in if input_data else None,
        avoid_overwrite=input_data.avoid_overwrite if input_data else True,
        continuation_token=input_data.continuation_token if input_data else None,
        dry_run=input_data.dry_run if input_data else None,
        include_avatars=input_data.include_avatars if input_data else None,
        source=input_data.source if input_data else None,
        user_id=input_data.user_id if input_data else None,
        runninghub_link=input_data.runninghub_link if input_data else None,
        prompt=input_data.prompt if input_data else None,
        assets=input_data.assets if input_data else None,
        current_target=input_data.current_target if input_data else None,
        agent_preferences=input_data.agent_preferences if input_data else None,
        capability_hash=input_data.capability_hash if input_data else None,
        capability_manifest_url=input_data.capability_manifest_url if input_data else None,
        capability_manifest=input_data.capability_manifest if input_data else None,
        agent_run_id=input_data.agent_run_id if input_data else None,
        agent_step_id=input_data.agent_step_id if input_data else None,
        agent_plan_type=input_data.agent_plan_type if input_data else None,
        agent_plan=input_data.agent_plan if input_data else None,
        agent_steps=input_data.agent_steps if input_data else None,
        agent_run_updates=input_data.agent_run_updates if input_data else None,
        agent_step_updates=input_data.agent_step_updates if input_data else None,
        # 用户管理相关字段
        phone=input_data.phone if input_data else None,
        ip=input_data.ip if input_data else None,
        password_hash=password_hash,
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
        # 任务时间范围查询字段
        start_time=input_data.start_time if input_data else None,
        end_time=input_data.end_time if input_data else None,
        before_time=input_data.before_time if input_data else None,
        status=input_data.status if input_data else None,
        # 任务管理相关字段
        task_id=input_data.task_id if input_data else None,
        platform=input_data.platform if input_data else None,
        platform_task_id=input_data.platform_task_id if input_data else None,
        task_data=input_data.task_data if input_data else None,
        task_updates=input_data.task_updates if input_data else None,
        # 系统通知相关字段
        notification_id=input_data.notification_id if input_data else None,
        notification_data=input_data.notification_data if input_data else None,
        current_time=input_data.current_time if input_data else None,
        # 更新公告相关字段
        announcement_id=input_data.announcement_id if input_data else None,
        announcement_data=input_data.announcement_data if input_data else None,
        target_audience=input_data.target_audience if input_data else None,
        # 团队余额相关字段
        amount=input_data.amount if input_data else None,
        description=input_data.description if input_data else None,
        days=input_data.days if input_data else None,
        name=input_data.name if input_data else None,
        target_user_id=input_data.target_user_id if input_data else None,
        target_username=input_data.target_username if input_data else None,
        target_role=input_data.target_role if input_data else None,
        original_record_id=input_data.original_record_id if input_data else None,
        reason=input_data.reason if input_data else None,
        filter_user_id=input_data.filter_user_id if input_data else None,
        # RunningHub 错误分析相关字段
        error_response=input_data.error_response if input_data else None,
        # Billing 资金扣费相关字段
        credit_type=input_data.credit_type if input_data else None,
        idempotency_key=input_data.idempotency_key if input_data else None,
        service_secret=input_data.service_secret if input_data else None,
        final_amount=input_data.final_amount if input_data else None,
        billing_metadata=input_data.billing_metadata if input_data else None,
        metadata=input_data.metadata if input_data else None,
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

        # 4. 判断是否超过限制（增加容错机制）
        # 检查封禁阈值（真正超限才封禁）
        if limits["blocked_phone_10min"]:
            # 触发封禁：设置封禁状态
            record = rate_mgr.get_or_create(db, state.phone, state.ip)
            rate_mgr.block(db, record, block_duration_hours=10/60)  # 10分钟
            return CheckRateLimitOutput(
                result={"allowed": False, "reason": "该手机号发送验证码过于频繁，请10分钟后再试"},
                allowed=False,
                reason="该手机号发送验证码过于频繁，请10分钟后再试",
                user_exists=False
            )

        if limits["blocked_phone_1hour"]:
            # 触发封禁：设置封禁状态
            record = rate_mgr.get_or_create(db, state.phone, state.ip)
            rate_mgr.block(db, record, block_duration_hours=1)  # 1小时
            return CheckRateLimitOutput(
                result={"allowed": False, "reason": "该手机号今日发送次数已达上限，请1小时后再试"},
                allowed=False,
                reason="该手机号今日发送次数已达上限，请1小时后再试",
                user_exists=False
            )

        # IP限制已移除，仅保留手机号限流

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
            tier=state.tier or "commercial_registered",
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
            "gold_credits": gold_amount_to_number(db_user.gold_credits),
            "silver_credits": db_user.silver_credits,
            "role": db_user.role,
            "tier": db_user.tier,
            "account_status": db_user.account_status,
            "created_at": _to_epoch_ms(db_user.created_at),
            "updated_at": _to_epoch_ms(db_user.updated_at) if db_user.updated_at else None
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

        # IP 限流已移除，仅保留手机号维度限流

        return UpdateRateLimitOutput(
            result={"success": True, "blocked": False, "message": "更新成功"},
            success=True,
            blocked=False
        )

    finally:
        db.close()


def _mask_phone(phone: Optional[str]) -> str:
    if not phone or len(phone) < 7:
        return "***"
    return f"{phone[:3]}****{phone[-4:]}"


def _failure_result(message: str) -> dict:
    return {"success": False, "error": message}


PASSWORD_RESET_SEND_SUCCESS_MESSAGE = "验证码已发送"


def send_register_code_node(state: SendRegisterCodeInput, config: RunnableConfig, runtime: Runtime[Context]) -> SendRegisterCodeOutput:
    """
    title: 发送注册验证码
    desc: 检查手机号、限流、发送短信并持久化验证码哈希
    integrations: 数据库
    """
    phone = (state.phone or "").strip()
    ip = (state.ip or "unknown").strip() or "unknown"
    masked_phone = _mask_phone(phone)

    if not re.fullmatch(r"1[3-9]\d{9}", phone):
        return SendRegisterCodeOutput(
            result=_failure_result("手机号格式不正确"),
            success=False,
            error="手机号格式不正确",
        )

    logger.info("[注册验证码] 开始发送: phone=%s, ip=%s", masked_phone, ip)

    check_result = check_rate_limit_node(
        CheckRateLimitInput(phone=phone, ip=ip),
        config,
        runtime,
    )
    if not check_result.allowed:
        reason = check_result.reason or "发送过于频繁,请稍后再试"
        logger.info("[注册验证码] 限流或重复手机号拦截: phone=%s, reason=%s", masked_phone, reason)
        return SendRegisterCodeOutput(
            result=_failure_result(reason),
            success=False,
            error=reason,
        )

    code = str(secrets.randbelow(900000) + 100000)
    RegisterCodeManager = _get_register_code_manager()
    code_mgr = RegisterCodeManager()
    record_id = None

    db = get_session()
    try:
        record = code_mgr.save_code(db, phone, code, ip)
        record_id = record.id
    except RuntimeError as exc:
        logger.error("[注册验证码] 验证码服务配置错误: phone=%s, error=%s", masked_phone, exc)
        return SendRegisterCodeOutput(
            result=_failure_result("验证码服务未配置"),
            success=False,
            error="验证码服务未配置",
        )
    except Exception as exc:
        logger.exception("[注册验证码] 验证码保存失败: phone=%s, error=%s", masked_phone, exc)
        return SendRegisterCodeOutput(
            result=_failure_result("验证码保存失败,请稍后重试"),
            success=False,
            error="验证码保存失败,请稍后重试",
        )
    finally:
        db.close()

    send_result = send_sms_verify_code(phone, code)
    if not send_result.success:
        if record_id:
            cleanup_db = get_session()
            try:
                code_mgr.delete_code(cleanup_db, record_id)
            except Exception as exc:
                logger.warning("[注册验证码] 短信失败后的验证码清理失败: phone=%s, error=%s", masked_phone, exc)
            finally:
                cleanup_db.close()
        logger.info("[注册验证码] 短信发送失败: phone=%s, reason=%s", masked_phone, send_result.message)
        return SendRegisterCodeOutput(
            result=_failure_result(send_result.message or "发送失败,请稍后重试"),
            success=False,
            error=send_result.message or "发送失败,请稍后重试",
        )

    cleanup_db = get_session()
    try:
        code_mgr.mark_other_unused_codes_used(cleanup_db, phone, record_id)
    except Exception as exc:
        logger.warning("[注册验证码] 旧验证码废弃失败: phone=%s, error=%s", masked_phone, exc)
    finally:
        cleanup_db.close()

    try:
        update_result = update_rate_limit_node(
            UpdateRateLimitInput(phone=phone, ip=ip),
            config,
            runtime,
        )
        blocked = update_result.blocked
    except Exception as exc:
        logger.warning("[注册验证码] 限流记录更新失败: phone=%s, error=%s", masked_phone, exc)
        blocked = False
    logger.info(
        "[注册验证码] 发送成功: phone=%s, blocked=%s",
        masked_phone,
        blocked,
    )

    return SendRegisterCodeOutput(
        result={
            "success": True,
            "message": "验证码已发送",
            "countdown": 60,
            "expires_in": RegisterCodeManager.code_ttl_seconds,
        },
        success=True,
    )


def _check_password_reset_code_rate_limit(phone: str, ip: str) -> tuple[bool, str]:
    UserManager, UserCreate, UserUpdate, RateLimitManager = _get_user_manager()

    db = get_session()
    try:
        rate_mgr = RateLimitManager()

        blocked_info = rate_mgr.check_blocked_status(db, phone, ip)
        if blocked_info:
            return False, "账号已被封禁，请稍后再试"

        limits = rate_mgr.check_limits(db, phone, ip)
        if limits["blocked_phone_10min"]:
            record = rate_mgr.get_or_create(db, phone, ip)
            rate_mgr.block(db, record, block_duration_hours=10 / 60)
            return False, "该手机号发送验证码过于频繁，请10分钟后再试"

        if limits["blocked_phone_1hour"]:
            record = rate_mgr.get_or_create(db, phone, ip)
            rate_mgr.block(db, record, block_duration_hours=1)
            return False, "该手机号今日发送次数已达上限，请1小时后再试"

        return True, ""
    finally:
        db.close()


def _record_password_reset_code_attempt(
    phone: str,
    ip: str,
    config: RunnableConfig,
    runtime: Runtime[Context],
) -> bool:
    try:
        update_result = update_rate_limit_node(
            UpdateRateLimitInput(phone=phone, ip=ip),
            config,
            runtime,
        )
        return update_result.blocked
    except Exception as exc:
        logger.warning("[密码重置验证码] 限流记录更新失败: phone=%s, error=%s", _mask_phone(phone), exc)
        return False


def _password_reset_code_sent_output(expires_in: int = 300) -> SendPasswordResetCodeOutput:
    return SendPasswordResetCodeOutput(
        result={
            "success": True,
            "message": PASSWORD_RESET_SEND_SUCCESS_MESSAGE,
            "countdown": 60,
            "expires_in": expires_in,
        },
        success=True,
    )


def send_password_reset_code_node(
    state: SendPasswordResetCodeInput,
    config: RunnableConfig,
    runtime: Runtime[Context],
) -> SendPasswordResetCodeOutput:
    """
    title: 发送密码重置验证码
    desc: 检查手机号、用户状态、限流、发送短信并持久化验证码哈希
    integrations: 数据库
    """
    phone = (state.phone or "").strip()
    ip = (state.ip or "unknown").strip() or "unknown"
    masked_phone = _mask_phone(phone)

    if not re.fullmatch(r"1[3-9]\d{9}", phone):
        return SendPasswordResetCodeOutput(
            result=_failure_result("手机号格式不正确"),
            success=False,
            error="手机号格式不正确",
        )

    allowed, reason = _check_password_reset_code_rate_limit(phone, ip)
    if not allowed:
        logger.info("[密码重置验证码] 限流拦截: phone=%s, reason=%s", masked_phone, reason)
        return SendPasswordResetCodeOutput(
            result=_failure_result(reason),
            success=False,
            error=reason,
        )

    UserManager, UserCreate, UserUpdate, RateLimitManager = _get_user_manager()
    db = get_session()
    try:
        user_mgr = UserManager()
        db_user = user_mgr.get_user_by_phone(db, phone)
        if not db_user or db_user.account_status != "active":
            logger.info("[密码重置验证码] 账号不存在或不可用: phone=%s", masked_phone)
            _record_password_reset_code_attempt(phone, ip, config, runtime)
            PasswordResetCodeManager = _get_password_reset_code_manager()
            return _password_reset_code_sent_output(PasswordResetCodeManager.code_ttl_seconds)
    finally:
        db.close()

    logger.info("[密码重置验证码] 开始发送: phone=%s, ip=%s", masked_phone, ip)

    code = str(secrets.randbelow(900000) + 100000)
    PasswordResetCodeManager = _get_password_reset_code_manager()
    code_mgr = PasswordResetCodeManager()
    record_id = None

    db = get_session()
    try:
        record = code_mgr.save_code(db, phone, code, ip)
        record_id = record.id
    except RuntimeError as exc:
        logger.error("[密码重置验证码] 验证码服务配置错误: phone=%s, error=%s", masked_phone, exc)
        _record_password_reset_code_attempt(phone, ip, config, runtime)
        return _password_reset_code_sent_output(PasswordResetCodeManager.code_ttl_seconds)
    except Exception as exc:
        logger.exception("[密码重置验证码] 验证码保存失败: phone=%s, error=%s", masked_phone, exc)
        _record_password_reset_code_attempt(phone, ip, config, runtime)
        return _password_reset_code_sent_output(PasswordResetCodeManager.code_ttl_seconds)
    finally:
        db.close()

    send_result = send_sms_verify_code(phone, code)
    if not send_result.success:
        if record_id:
            cleanup_db = get_session()
            try:
                code_mgr.delete_code(cleanup_db, record_id)
            except Exception as exc:
                logger.warning("[密码重置验证码] 短信失败后的验证码清理失败: phone=%s, error=%s", masked_phone, exc)
            finally:
                cleanup_db.close()
        logger.info("[密码重置验证码] 短信发送失败: phone=%s, reason=%s", masked_phone, send_result.message)
        _record_password_reset_code_attempt(phone, ip, config, runtime)
        return _password_reset_code_sent_output(PasswordResetCodeManager.code_ttl_seconds)

    cleanup_db = get_session()
    try:
        code_mgr.mark_other_unused_codes_used(cleanup_db, phone, record_id)
    except Exception as exc:
        logger.warning("[密码重置验证码] 旧验证码废弃失败: phone=%s, error=%s", masked_phone, exc)
    finally:
        cleanup_db.close()

    blocked = _record_password_reset_code_attempt(phone, ip, config, runtime)

    logger.info("[密码重置验证码] 发送成功: phone=%s, blocked=%s", masked_phone, blocked)
    return _password_reset_code_sent_output(PasswordResetCodeManager.code_ttl_seconds)


def register_with_limit_node(state: RegisterWithLimitInput, config: RunnableConfig, runtime: Runtime[Context]) -> RegisterWithLimitOutput:
    """
    title: 用户注册
    desc: 完整的注册流程：检查限流 -> 创建用户 -> 更新限流记录
    integrations: 数据库
    """
    ctx = runtime.context

    # 验证必填字段
    if not state.phone or not state.ip or not state.password_hash or not state.username:
        return RegisterWithLimitOutput(
            result={"success": False, "error": "缺少必要参数：phone、ip、password_hash、username"},
            success=False,
            error="缺少必要参数：phone、ip、password_hash、username"
        )

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
            avatar=state.avatar or "https://example.com/default-avatar.png"
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


def register_with_code_node(state: RegisterWithCodeInput, config: RunnableConfig, runtime: Runtime[Context]) -> RegisterWithCodeOutput:
    """
    title: 验证码注册
    desc: 在事务中校验并消费验证码、哈希密码、创建用户
    integrations: 数据库
    """
    phone = (state.phone or "").strip()
    ip = (state.ip or "unknown").strip() or "unknown"
    username = (state.username or "").strip()
    password = state.password or ""
    code = (state.code or "").strip()
    masked_phone = _mask_phone(phone)

    if not re.fullmatch(r"1[3-9]\d{9}", phone):
        return RegisterWithCodeOutput(
            result=_failure_result("手机号格式不正确"),
            success=False,
            error="手机号格式不正确",
        )
    if len(username) < 2 or len(username) > 20:
        return RegisterWithCodeOutput(
            result=_failure_result("用户名长度为2-20字符"),
            success=False,
            error="用户名长度为2-20字符",
        )
    if len(password) < 7:
        return RegisterWithCodeOutput(
            result=_failure_result("密码至少需要7个字符"),
            success=False,
            error="密码至少需要7个字符",
        )
    if not re.fullmatch(r"\d{6}", code):
        return RegisterWithCodeOutput(
            result=_failure_result("验证码格式不正确"),
            success=False,
            error="验证码格式不正确",
        )

    logger.info("[验证码注册] 开始处理: phone=%s, username=%s, ip=%s", masked_phone, username, ip)

    RegisterCodeManager = _get_register_code_manager()
    code_mgr = RegisterCodeManager()
    db = get_session()
    try:
        success, message, user = code_mgr.register_user_with_code(
            db=db,
            phone=phone,
            username=username,
            password=password,
            code=code,
            ip_address=ip,
            avatar=state.avatar,
        )
    except Exception as exc:
        logger.exception("[验证码注册] 处理异常: phone=%s, error=%s", masked_phone, exc)
        return RegisterWithCodeOutput(
            result=_failure_result("注册失败,请稍后重试"),
            success=False,
            error="注册失败,请稍后重试",
        )
    finally:
        db.close()

    if not success:
        logger.info("[验证码注册] 注册失败: phone=%s, reason=%s", masked_phone, message)
        return RegisterWithCodeOutput(
            result=_failure_result(message),
            success=False,
            error=message,
        )

    logger.info("[验证码注册] 注册成功: phone=%s, user_id=%s", masked_phone, user.get("user_id") if user else None)
    return RegisterWithCodeOutput(
        result={
            "success": True,
            "message": "注册成功",
            "user": user,
        },
        success=True,
        user=user,
    )


def reset_password_with_code_node(
    state: ResetPasswordWithCodeInput,
    config: RunnableConfig,
    runtime: Runtime[Context],
) -> ResetPasswordWithCodeOutput:
    """
    title: 验证码重置密码
    desc: 在事务中校验并消费验证码、更新用户密码哈希
    integrations: 数据库
    """
    phone = (state.phone or "").strip()
    password = state.password or ""
    confirm_password = state.confirm_password or ""
    code = (state.code or "").strip()
    masked_phone = _mask_phone(phone)

    if not re.fullmatch(r"1[3-9]\d{9}", phone):
        return ResetPasswordWithCodeOutput(
            result=_failure_result("手机号格式不正确"),
            success=False,
            error="手机号格式不正确",
        )
    if len(password) < 7:
        return ResetPasswordWithCodeOutput(
            result=_failure_result("密码至少需要7个字符"),
            success=False,
            error="密码至少需要7个字符",
        )
    if password != confirm_password:
        return ResetPasswordWithCodeOutput(
            result=_failure_result("两次输入的密码不一致"),
            success=False,
            error="两次输入的密码不一致",
        )
    if not re.fullmatch(r"\d{6}", code):
        return ResetPasswordWithCodeOutput(
            result=_failure_result("验证码格式不正确"),
            success=False,
            error="验证码格式不正确",
        )

    logger.info("[验证码重置密码] 开始处理: phone=%s", masked_phone)
    PasswordResetCodeManager = _get_password_reset_code_manager()
    code_mgr = PasswordResetCodeManager()
    db = get_session()
    try:
        success, message = code_mgr.reset_password_with_code(
            db=db,
            phone=phone,
            password=password,
            code=code,
        )
    except Exception as exc:
        logger.exception("[验证码重置密码] 处理异常: phone=%s, error=%s", masked_phone, exc)
        return ResetPasswordWithCodeOutput(
            result=_failure_result("密码重置失败,请稍后重试"),
            success=False,
            error="密码重置失败,请稍后重试",
        )
    finally:
        db.close()

    if not success:
        logger.info("[验证码重置密码] 重置失败: phone=%s, reason=%s", masked_phone, message)
        return ResetPasswordWithCodeOutput(
            result=_failure_result(message),
            success=False,
            error=message,
        )

    logger.info("[验证码重置密码] 重置成功: phone=%s", masked_phone)
    return ResetPasswordWithCodeOutput(
        result={
            "success": True,
            "message": "密码已重置，请使用新密码登录",
        },
        success=True,
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
            "gold_credits": gold_amount_to_number(db_user.gold_credits),
            "silver_credits": db_user.silver_credits,
            "role": db_user.role,
            "tier": db_user.tier,
            "account_status": db_user.account_status,
            "created_at": _to_epoch_ms(db_user.created_at),
            "updated_at": _to_epoch_ms(db_user.updated_at) if db_user.updated_at else None
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
            "gold_credits": gold_amount_to_number(db_user.gold_credits),
            "silver_credits": db_user.silver_credits,
            "role": db_user.role,
            "tier": db_user.tier,
            "account_status": db_user.account_status,
            "created_at": _to_epoch_ms(db_user.created_at),
            "updated_at": _to_epoch_ms(db_user.updated_at) if db_user.updated_at else None
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
    base64_data = None
    mime_type = "image/png"  # 默认 MIME 类型
    
    # 检查是否为 Data URL 格式：data:image/png;base64,xxx
    if state.avatar and state.avatar.startswith('data:image'):
        try:
            match = re.match(r"data:([^;]+);base64,(.+)", state.avatar)
            if match:
                mime_type = match.group(1)  # 例如：image/png
                base64_data = match.group(2)
        except Exception:
            pass
    # 检查是否为纯 Base64 字符串（通过尝试解码来验证）
    elif state.avatar:
        try:
            # 尝试解码，如果成功则是 Base64
            file_content = base64.b64decode(state.avatar)
            # 验证解码后的内容是否为有效的图片数据
            # PNG 文件以 89 50 4E 47 开头
            # JPEG 文件以 FF D8 FF 开头
            if len(file_content) >= 8:
                header = file_content[:8]
                # 检查是否为 PNG 或 JPEG
                if header[:4] == b'\x89PNG' or header[:3] == b'\xff\xd8\xff':
                    base64_data = state.avatar
                    # 根据文件头确定 MIME 类型
                    if header[:4] == b'\x89PNG':
                        mime_type = "image/png"
                    elif header[:3] == b'\xff\xd8\xff':
                        mime_type = "image/jpeg"
        except Exception:
            # 解码失败，保持原样
            pass
    
    # 如果检测到 Base64 数据，则上传到对象存储
    if base64_data:
        try:
            file_content = base64.b64decode(base64_data)
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
            
            # 使用存储管理器上传（自动分类为 avatar）
            from storage.storage_manager import get_storage_manager, StorageCategory
            storage_mgr = get_storage_manager()
            
            upload_result = storage_mgr.upload_with_category(
                file_content=file_content,
                file_name=filename,
                category=StorageCategory.AVATAR,  # 头像归类为 avatar（永久）
                content_type=mime_type,
                acl='public-read'
            )
            
            # 使用生成的 URL（永久有效）
            processed_avatar = upload_result['url']
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
        if "team_id" in state.model_fields_set:
            # 显式传 null 才清除团队；空字符串视为不更新，保留原值
            if state.team_id is None:
                updates['team_id'] = None
            elif state.team_id != '':
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
            "gold_credits": gold_amount_to_number(db_user.gold_credits),
            "silver_credits": db_user.silver_credits,
            "role": db_user.role,
            "tier": db_user.tier,
            "account_status": db_user.account_status,
            "created_at": _to_epoch_ms(db_user.created_at),
            "updated_at": _to_epoch_ms(db_user.updated_at) if db_user.updated_at else None
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
                "gold_credits": gold_amount_to_number(user.gold_credits),
                "silver_credits": user.silver_credits,
                "role": user.role,
                "tier": user.tier,
                "account_status": user.account_status,
                "created_at": _to_epoch_ms(user.created_at),
                "updated_at": _to_epoch_ms(user.updated_at) if user.updated_at else None
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


def _normalize_upload_category(category: Optional[str]) -> str:
    if category == StorageCategory.TEMP:
        return StorageCategory.TEMP
    if category == StorageCategory.AVATAR:
        return StorageCategory.AVATAR
    return StorageCategory.UPLOAD


def _normalize_upload_metadata(metadata: Optional[dict]) -> Dict[str, Any]:
    if not isinstance(metadata, dict):
        return {}
    return {
        str(key): value
        for key, value in metadata.items()
        if value is not None and isinstance(key, str)
    }


def upload_node(state: UploadInput, config: RunnableConfig, runtime: Runtime[Context]) -> UploadOutput:
    """
    title: 文件上传
    desc: 将上传的文件存入对象存储，自动分类管理并生成访问 URL。支持远程 URL、本地路径和 Base64 格式
    integrations: 对象存储
    """
    ctx = runtime.context

    if not state.file:
        return UploadOutput(result={"success": False, "message": "未提供文件"})

    try:
        # 从 URL 读取文件内容
        file_url = state.file.url

        # 判断数据类型并获取文件内容
        if file_url.startswith(("http://", "https://")):
            # 远程 URL：使用 upload_from_url
            file_key = storage.upload_from_url(url=file_url)
            # 生成 URL
            public_url = storage.generate_presigned_url(key=file_key, expire_time=2592000)
            return UploadOutput(result={
                "success": True,
                "message": "文件上传成功",
                "public_url": public_url,
                "file_key": file_key
            })

        elif file_url.startswith(("data:image", "data:audio", "data:video")) or (file_url.startswith("data:application") and ";base64," in file_url):
            # Base64 格式（Data URL 格式）
            match = re.match(r"data:([^;]+);base64,(.+)", file_url)
            if not match:
                return UploadOutput(result={"success": False, "message": "无效的 Base64 格式"})

            mime_type = match.group(1)
            base64_data = match.group(2)

            # 解码 Base64
            try:
                file_content = base64.b64decode(base64_data)
            except Exception as e:
                return UploadOutput(result={"success": False, "message": f"Base64 解码失败: {str(e)}"})

            # 根据类型确定文件名
            if "png" in mime_type:
                filename = "upload.png"
            elif "jpeg" in mime_type or "jpg" in mime_type:
                filename = "upload.jpg"
            elif "gif" in mime_type:
                filename = "upload.gif"
            elif "webp" in mime_type:
                filename = "upload.webp"
            elif "bmp" in mime_type:
                filename = "upload.bmp"
            elif "svg" in mime_type:
                filename = "upload.svg"
            # 音频格式
            elif "mpeg" in mime_type or "mp3" in mime_type:
                filename = "upload.mp3"
            elif "wav" in mime_type:
                filename = "upload.wav"
            elif "ogg" in mime_type:
                filename = "upload.ogg"
            elif "flac" in mime_type:
                filename = "upload.flac"
            elif "aac" in mime_type:
                filename = "upload.aac"
            elif "m4a" in mime_type:
                filename = "upload.m4a"
            elif "wma" in mime_type:
                filename = "upload.wma"
            elif "aiff" in mime_type:
                filename = "upload.aiff"
            # 视频格式
            elif "mp4" in mime_type:
                filename = "upload.mp4"
            elif "webm" in mime_type:
                filename = "upload.webm"
            elif "avi" in mime_type:
                filename = "upload.avi"
            elif "mov" in mime_type or "quicktime" in mime_type:
                filename = "upload.mov"
            elif "mkv" in mime_type or "x-matroska" in mime_type:
                filename = "upload.mkv"
            elif "wmv" in mime_type or "ms-wmv" in mime_type:
                filename = "upload.wmv"
            elif "flv" in mime_type or "x-flv" in mime_type:
                filename = "upload.flv"
            # 文档格式
            elif "pdf" in mime_type:
                filename = "upload.pdf"
            else:
                filename = f"upload.{mime_type.split('/')[-1] if '/' in mime_type else 'bin'}"

            # 使用存储管理器上传（自动分类）
            storage_mgr = get_storage_manager()
            category = _normalize_upload_category(state.category)

            upload_result = storage_mgr.upload_with_category(
                file_content=file_content,
                file_name=filename,
                category=category,
                content_type=mime_type,
                acl=None,
                metadata=_normalize_upload_metadata(state.metadata)
            )

            return UploadOutput(result={
                "success": True,
                "message": "文件上传成功",
                "public_url": upload_result['url'],
                "file_key": upload_result['file_key'],
                "category": upload_result['category'],
                "expires_at": upload_result.get('expires_at')
            })

        else:
            # 本地路径：读取文件内容后上传
            clean_path = file_url.replace("file://", "")
            with open(clean_path, "rb") as f:
                file_content = f.read()
                filename = os.path.basename(clean_path)
                
                # 使用存储管理器上传
                storage_mgr = get_storage_manager()
                category = _normalize_upload_category(state.category)

                upload_result = storage_mgr.upload_with_category(
                    file_content=file_content,
                    file_name=filename,
                    category=category,
                    content_type="application/octet-stream",
                    acl=None,
                    metadata=_normalize_upload_metadata(state.metadata)
                )

                return UploadOutput(result={
                    "success": True,
                    "message": "文件上传成功",
                    "public_url": upload_result['url'],
                    "file_key": upload_result['file_key'],
                    "category": upload_result['category'],
                    "expires_at": upload_result.get('expires_at')
                })

    except Exception as e:
        return UploadOutput(result={"success": False, "message": f"文件上传失败: {str(e)}"})


def delete_upload_node(state: DeleteUploadInput, config: RunnableConfig, runtime: Runtime[Context]) -> DeleteUploadOutput:
    """
    title: 删除上传文件
    desc: 仅允许删除文生图模式生成的临时白底参考图
    integrations: 对象存储
    """
    file_key = (state.file_key or "").strip()
    category = (state.category or "").strip()
    source = (state.source or "").strip()

    if not file_key:
        return DeleteUploadOutput(result={"success": False, "message": "缺少 file_key"})

    if not file_key.startswith("temp/") or category != StorageCategory.TEMP or source != "text_to_image_white_reference":
        return DeleteUploadOutput(result={"success": False, "message": "只允许删除临时白底参考图"})

    try:
        storage_mgr = get_storage_manager()
        metadata = storage_mgr.get_file_metadata(file_key)
        if not metadata:
            exists = storage_mgr.storage.file_exists(file_key=file_key)
            if not exists:
                return DeleteUploadOutput(result={
                    "success": True,
                    "message": "文件不存在或已删除",
                    "file_key": file_key,
                    "deleted": False,
                })
            return DeleteUploadOutput(result={"success": False, "message": "文件元数据缺失，拒绝删除"})

        if metadata.get("category") != StorageCategory.TEMP or metadata.get("source") != "text_to_image_white_reference":
            return DeleteUploadOutput(result={"success": False, "message": "文件来源校验失败，拒绝删除"})

        deleted = storage_mgr.storage.delete_file(file_key=file_key)
        return DeleteUploadOutput(result={
            "success": bool(deleted),
            "message": "临时白底参考图已删除" if deleted else "删除失败",
            "file_key": file_key,
            "deleted": bool(deleted),
        })
    except Exception as e:
        return DeleteUploadOutput(result={"success": False, "message": f"删除失败: {str(e)}"})


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
    desc: 用于任务管理的二级路由，传递 operation_type 和相关字段
    """
    return TaskRouteOutput(
        operation_type=state.operation_type,
        user_id=state.user_id,
        task_id=state.task_id,
        platform=state.platform,
        platform_task_id=state.platform_task_id,
        task_data=state.task_data,
        task_updates=state.task_updates,
        start_time=state.start_time,
        end_time=state.end_time,
        before_time=state.before_time,
        team_id=state.team_id,
        status=state.status,
        limit=state.limit
    )


def route_by_task_operation_type(state: TaskRouteInput) -> str:
    """
    title: 任务管理二级路由
    desc: 根据操作类型分发到不同的节点
    """
    operation_type = state.operation_type

    if operation_type == "create_task":
        return "创建任务"
    elif operation_type == "get_task":
        return "查询单个任务"
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
                connection_mode=state.task_data.get("connection_mode", "sse"),
                deduction_result=state.task_data.get("deduction_result")
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

            # 构建更新参数，只传入存在的字段，避免 None 值覆盖
            update_kwargs = {}
            for field in [
                "status",
                "platform_task_id",
                "result",
                "error",
                "completed_at",
                "started_at",  # 【新增】允许更新 started_at
                "user_friendly_message",
                "workflow_parameters",
                "parameter_snapshot",
                "connection_mode",
                "deleted_image_urls",
            ]:
                if field in state.task_updates:
                    update_kwargs[field] = state.task_updates.get(field)
            # deduction_result 单独处理，只有明确存在时才更新
            if "deduction_result" in state.task_updates:
                update_kwargs["deduction_result"] = state.task_updates.get("deduction_result")

            task_in = TaskUpdate(**update_kwargs)

            db_task = task_mgr.update_task(db, state.task_id, task_in)

            if not db_task:
                return UpdateTaskOutput(result={"success": False, "message": "任务不存在"})

            return UpdateTaskOutput(
                result={
                    "success": True,
                    "message": "任务更新成功",
                    "task_id": db_task.id,
                    "status": db_task.status
                },
                task_id=db_task.id,
                status=db_task.status,
                task_result=db_task.result
            )

        finally:
            db.close()

    except Exception as e:
        return UpdateTaskOutput(result={"success": False, "message": f"更新失败: {str(e)}"})


def get_task_node(state: GetTaskInput, config: RunnableConfig, runtime: Runtime[Context]) -> GetTaskOutput:
    """
    title: 查询单个任务
    desc: 根据任务ID或平台任务ID精确查询任务（仅限注册用户；管理员可查任意任务，普通用户只能查自己的任务）
    integrations: 数据库
    """
    ctx = runtime.context

    query_id = state.query_id or None

    if not state.user_id:
        return GetTaskOutput(result={"success": False, "message": "缺少必要参数：user_id"})

    if not state.task_id and not state.platform_task_id and not query_id:
        return GetTaskOutput(result={"success": False, "message": "缺少必要参数：task_id 或 platform_task_id 或 query_id"})

    try:
        from storage.database.task_manager import TaskManager
        from storage.database.shared.model import Users

        db = get_session()
        try:
            task_mgr = TaskManager()
            has_permission, error_msg = task_mgr.verify_user_permission(db, state.user_id)
            if not has_permission:
                return GetTaskOutput(result={"success": False, "message": error_msg})

            # 支持三种查询模式：
            #   1. task_id（前端主键）
            #   2. platform + platform_task_id（平台任务ID）
            #   3. query_id（自动匹配 id 或 platform_task_id）
            if state.task_id:
                db_task = task_mgr.get_task_by_id(db, state.task_id)
            elif state.platform_task_id and state.platform:
                db_task = task_mgr.get_task_by_platform_task_id(db, state.platform, state.platform_task_id)
            elif query_id:
                db_task = task_mgr.get_task_by_id(db, query_id)
                if not db_task or db_task.is_deleted:
                    db_task = task_mgr.get_task_by_platform_task_id_flexible(db, query_id)
            else:
                return GetTaskOutput(result={"success": False, "message": "使用 platform_task_id 查询时必须同时提供 platform"})

            if not db_task or db_task.is_deleted:
                return GetTaskOutput(result={"success": False, "message": "任务不存在"})

            user = db.query(Users).filter(Users.user_id == state.user_id).first()
            if not user:
                return GetTaskOutput(result={"success": False, "message": "用户不存在"})
            if user.role != 'admin' and db_task.user_id != state.user_id:
                return GetTaskOutput(result={"success": False, "message": "无权访问此任务"})

            task = {
                "id": db_task.id,
                "user_id": db_task.user_id,
                "team_id": db_task.team_id,
                "platform": db_task.platform,
                "platform_task_id": db_task.platform_task_id,
                "type": db_task.type,
                "status": db_task.status,
                "workflow_parameters": db_task.workflow_parameters,
                "parameter_snapshot": db_task.parameter_snapshot,
                "result": db_task.result,
                "error": db_task.error,
                "deduction_result": db_task.deduction_result,
                "user_friendly_message": db_task.user_friendly_message,
                "created_at": db_task.created_at,
                "updated_at": db_task.updated_at,
                "completed_at": db_task.completed_at,
                "batch_id": db_task.batch_id,
                "connection_mode": db_task.connection_mode,
                "is_deleted": db_task.is_deleted
            }
            return GetTaskOutput(result={"success": True, "message": "查询成功", "task": task})

        finally:
            db.close()

    except Exception as e:
        return GetTaskOutput(result={"success": False, "message": f"查询失败: {str(e)}"})


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
    desc: 根据用户ID、团队ID查询任务列表，支持状态筛选、时间范围和游标分页（仅限注册用户）。
          查询规则：
          - 只提供 user_id：查询该用户的所有任务
          - 同时提供 user_id 和 team_id：查询该团队的所有任务（包含团队所有成员的任务）
          - 必须至少提供 user_id 或 team_id 其中之一
          - 查询团队任务时需要同时提供 user_id 用于权限验证
          - days 参数指定查询最近N天的数据，默认30天
          - limit 参数指定返回数量，默认50，最大1000
          - before_time 参数用于游标分页，查询早于该时间戳的记录
          - 返回 has_more 表示是否还有更多数据，next_before_time 用于翻页
    integrations: 数据库
    """
    ctx = runtime.context

    # 至少需要 user_id 或 team_id 其中之一
    if not state.user_id and not state.team_id:
        return ListTasksOutput(result={"success": False, "message": "缺少必要参数：user_id 和 team_id 至少需要提供一个"})

    # 如果提供了 team_id，必须提供用户 ID 进行权限验证
    if state.team_id and not state.user_id:
        return ListTasksOutput(result={"success": False, "message": "查询团队任务需要同时提供 user_id 用于权限验证"})

    # 验证用户权限（仅当提供了 user_id 时）
    if state.user_id:
        try:
            from storage.database.task_manager import TaskManager
            db = get_session()
            try:
                task_mgr = TaskManager()
                has_permission, error_msg = task_mgr.verify_user_permission(db, state.user_id)
                if not has_permission:
                    return ListTasksOutput(result={"success": False, "message": error_msg})
            finally:
                db.close()
        except Exception as e:
            return ListTasksOutput(result={"success": False, "message": f"权限验证失败: {str(e)}"})

    try:
        from storage.database.task_manager import TaskManager

        db = get_session()
        try:
            task_mgr = TaskManager()

            # 根据 days 计算时间范围
            days = state.days or 30
            current_time = int(time.time() * 1000)
            start_time = current_time - (days * 24 * 60 * 60 * 1000)  # N天前
            end_time = current_time

            # 返回数量限制
            limit = min(state.limit or 50, 1000)  # 最大1000

            # 游标分页参数
            before_time = state.before_time

            # 过-fetch 任务用于 Python 层过滤媒体结果
            # 由于 completed 任务可能被过滤掉，需要多查一些数据以保证分页准确
            overfetch_limit = min(limit * 3, 2000)

            # 查询任务列表
            raw_tasks = task_mgr.get_tasks_flexible(
                db,
                user_id=state.user_id,
                team_id=state.team_id,
                status=state.status,
                start_time=start_time,
                end_time=end_time,
                limit=overfetch_limit,
                before_time=before_time
            )

            # 转换为可序列化的字典列表，过滤无媒体结果的 completed 任务
            task_list = []
            for task, username in raw_tasks:
                task_dict = {
                    "id": task.id,
                    "user_id": task.user_id,
                    "username": username,
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
                    "user_friendly_message": task.user_friendly_message,
                    "created_at": task.created_at,
                    "updated_at": task.updated_at,
                    "completed_at": task.completed_at,
                    "started_at": task.started_at,  # 【新增】任务开始时间
                    "elapsed_time_seconds": task.elapsed_time_seconds if hasattr(task, 'elapsed_time_seconds') else 0,  # 【新增】后端统一计算的耗时(秒)
                    "batch_id": task.batch_id,
                    "connection_mode": task.connection_mode,
                    "is_deleted": task.is_deleted,
                    "deleted_image_urls": task.deleted_image_urls
                }
                # 过滤：completed 任务必须有媒体结果才展示
                if task.status == "completed":
                    result_data = task.result
                    has_media = False
                    if isinstance(result_data, dict):
                        # 检查 result 中是否有图片/视频/音频 URL
                        files = result_data.get("files")
                        if isinstance(files, list) and len(files) > 0:
                            # files 中至少有一个条目包含 url 或 file_url
                            for f in files:
                                if isinstance(f, dict) and (f.get("url") or f.get("file_url")):
                                    has_media = True
                                    break
                            if not has_media and len(files) > 0:
                                has_media = True
                        elif result_data.get("url") or result_data.get("image_url") or result_data.get("video_url") or result_data.get("audio_url"):
                            has_media = True
                        elif result_data.get("thumbnailUrl") or result_data.get("previewUrl") or result_data.get("thumbnail_url") or result_data.get("preview_url"):
                            has_media = True
                        # 检查 images 数组
                        images = result_data.get("images")
                        if isinstance(images, list) and len(images) > 0:
                            has_media = True
                    if not has_media:
                        continue
                task_list.append(task_dict)

            # 精确计算符合媒体过滤条件的总数
            total = task_mgr.count_tasks_flexible(
                db,
                user_id=state.user_id,
                team_id=state.team_id,
                status=state.status,
                start_time=start_time,
                end_time=end_time
            )

            # 如果是 completed 状态查询，用 SQL 精确统计有媒体结果的任务数
            if state.status == "completed":
                try:
                    media_total = task_mgr.count_tasks_with_media(
                        db,
                        user_id=state.user_id,
                        team_id=state.team_id,
                        start_time=start_time,
                        end_time=end_time,
                        before_time=before_time
                    )
                    total = media_total
                except Exception as e:
                    logging.getLogger(__name__).warning(f"count_tasks_with_media failed: {e}")

            # 分页：从过滤后的列表中截取当前页
            has_more = len(task_list) > limit
            if has_more:
                task_list = task_list[:limit]

            # 计算 next_before_time：当前页最后一条记录的 created_at
            next_before_time = None
            if task_list:
                try:
                    next_before_time = int(task_list[-1]["created_at"])
                except (ValueError, TypeError):
                    next_before_time = None

            return ListTasksOutput(result={
                "success": True,
                "message": "查询成功",
                "tasks": task_list,
                "total": total,
                "limit": limit,
                "days": days,
                "has_more": has_more,
                "next_before_time": next_before_time
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
        # 优先检查 response_data（团队余额等节点直接返回的数据）
        if state.response_data is not None:
            return FormatResponseOutput(response_data=state.response_data)

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

        # 构造消息（有图片时用多模态，无图片时用纯文本）
        if state.file_list:
            content = [{"type": "text", "text": user_prompt_content}]
            for file in state.file_list:
                content.append({
                    "type": "image_url",
                    "image_url": {"url": file.url}
                })
            human_msg = HumanMessage(content=content)
        else:
            human_msg = HumanMessage(content=user_prompt_content)

        messages = [
            SystemMessage(content=system_prompt_content),
            human_msg
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


# ============ 团队余额初始化节点 ============
