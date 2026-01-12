from langchain_core.runnables import RunnableConfig
from langgraph.runtime import Runtime
from coze_coding_utils.runtime_ctx.context import Context
from langchain_core.messages import SystemMessage, HumanMessage, AIMessage
from coze_coding_dev_sdk import LLMClient
from jinja2 import Template
import json
from graphs.state import (
    RegisterLoginInput, RegisterLoginOutput,
    UploadInput, UploadOutput,
    SaveInput, SaveOutput,
    HistoryInput, HistoryOutput,
    FormatResponseInput, FormatResponseOutput,
    GlobalState,
    RouterInput,
    RouterOutput,
    ToolRouteInput,
    ToolRouteOutput,
    ReverseImageInput,
    ReverseImageOutput,
    TranslateDoubaoInput,
    TranslateDoubaoOutput
)
import os
import requests
from urllib.parse import urlparse
import io
import base64
import re

from storage.database.db import get_session


def router_node(state: RouterInput, config: RunnableConfig, runtime: Runtime[Context]) -> RouterOutput:
    """
    title: 路由节点
    desc: 用于条件分支的虚拟节点，传递 call_type
    """
    return RouterOutput(call_type=state.call_type)
from storage.database.user_manager import UserManager, UserCreate, UserLogin
from storage.database.history_manager import HistoryManager, HistoryCreate
from storage.s3.s3_storage import S3SyncStorage


# 初始化对象存储客户端
storage = S3SyncStorage(
    endpoint_url=os.getenv("COZE_BUCKET_ENDPOINT_URL"),
    access_key=os.getenv("COZE_ACCESS_KEY", ""),
    secret_key=os.getenv("COZE_SECRET_KEY", ""),
    bucket_name=os.getenv("COZE_BUCKET_NAME"),
    region=os.getenv("COZE_BUCKET_REGION", "cn-beijing"),
)


def register_login_node(state: RegisterLoginInput, config: RunnableConfig, runtime: Runtime[Context]) -> RegisterLoginOutput:
    """
    title: 注册/登录
    desc: 处理用户注册和登录操作，包括注册新用户和密码比对认证
    integrations: 数据库
    """
    ctx = runtime.context

    db = get_session()
    try:
        mgr = UserManager()

        if state.call_type == "register":
            # 注册逻辑
            user_in = UserCreate(username=state.username, password=state.password)
            db_user = mgr.create_user(db, user_in)

            if db_user is None:
                # 用户名已存在
                return RegisterLoginOutput(result={"success": False, "message": "用户名已存在"})

            return RegisterLoginOutput(result={"success": True, "message": "注册成功", "user_id": db_user.id})

        elif state.call_type == "login":
            # 登录逻辑
            login_in = UserLogin(username=state.username, password=state.password)
            db_user = mgr.authenticate_user(db, login_in)

            if db_user is None:
                # 认证失败
                return RegisterLoginOutput(result={"success": False, "message": "用户名或密码错误"})

            return RegisterLoginOutput(result={"success": True, "message": "登录成功", "user_id": db_user.id})

        else:
            return RegisterLoginOutput(result={"success": False, "message": "无效的调用类型"})

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
    desc: 接收用户 ID 和 RunningHub 链接，将图片持久化转存到对象存储，并在 History 表记录
    integrations: 对象存储, 数据库
    """
    ctx = runtime.context

    if not state.user_id or not state.runninghub_link:
        return SaveOutput(result={"success": False, "message": "缺少必要参数：user_id 或 runninghub_link"})

    try:
        # 1. 将 RunningHub 链接中的图片转存到对象存储（持久化）
        file_key = storage.upload_from_url(url=state.runninghub_link)

        # 生成永久链接（不设置过期时间，或者设置很长的时间）
        # 这里使用 10 年有效期作为"永久"链接
        permanent_url = storage.generate_presigned_url(key=file_key, expire_time=315360000)

        # 2. 在 History 表中记录
        db = get_session()
        try:
            history_mgr = HistoryManager()

            # 这里可以添加任务参数，暂时为空
            history_in = HistoryCreate(
                user_id=state.user_id,
                permanent_link=permanent_url,
                task_params=None
            )

            db_history = history_mgr.create_history(db, history_in)

            return SaveOutput(result={
                "success": True,
                "message": "保存成功",
                "history_id": db_history.id,
                "permanent_link": permanent_url,
                "iso_timestamp": db_history.iso_timestamp
            })

        finally:
            db.close()

    except Exception as e:
        return SaveOutput(result={"success": False, "message": f"保存失败: {str(e)}"})


def history_node(state: HistoryInput, config: RunnableConfig, runtime: Runtime[Context]) -> HistoryOutput:
    """
    title: 历史查询
    desc: 根据用户 ID 查询该用户的所有历史归档记录
    integrations: 数据库
    """
    ctx = runtime.context

    if not state.user_id:
        return HistoryOutput(result={"success": False, "message": "缺少必要参数：user_id"})

    try:
        db = get_session()
        try:
            history_mgr = HistoryManager()
            histories = history_mgr.get_histories_by_user_id(db, state.user_id)

            # 转换为可序列化的字典列表
            history_list = []
            for h in histories:
                history_list.append({
                    "id": h.id,
                    "user_id": h.user_id,
                    "permanent_link": h.permanent_link,
                    "task_params": h.task_params,
                    "iso_timestamp": h.iso_timestamp,
                    "meta_data": h.meta_data,
                    "created_at": h.created_at.isoformat() if h.created_at is not None else None
                })

            return HistoryOutput(result={
                "success": True,
                "message": "查询成功",
                "histories": history_list
            })

        finally:
            db.close()

    except Exception as e:
        return HistoryOutput(result={"success": False, "message": f"查询失败: {str(e)}"})


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

        # 处理其他节点的 dict 结果
        if result.get("success"):
            code = 0
            msg = result.get("message", "操作成功")
            data = {k: v for k, v in result.items() if k not in ["success", "message"]}
        else:
            code = -1
            msg = result.get("message", "操作失败")
            data = None

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
    title: 反推图像
    desc: 使用视觉模型分析图像，反推图像内容
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

        return ReverseImageOutput(result={"success": True, "message": "反推成功", "result": response.content})

    except Exception as e:
        return ReverseImageOutput(result={"success": False, "message": f"反推失败: {str(e)}"})


def translate_doubao_node(state: TranslateDoubaoInput, config: RunnableConfig, runtime: Runtime[Context]) -> TranslateDoubaoOutput:
    """
    title: 翻译（推荐版）
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
