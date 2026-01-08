from langchain_core.runnables import RunnableConfig
from langgraph.runtime import Runtime
from coze_coding_utils.runtime_ctx.context import Context
from graphs.state import (
    RegisterLoginInput, RegisterLoginOutput,
    UploadInput, UploadOutput,
    SaveInput, SaveOutput,
    HistoryInput, HistoryOutput,
    FormatResponseInput, FormatResponseOutput
)
import os
import requests
from urllib.parse import urlparse
import io

from storage.database.db import get_session
from storage.database.user_manager import UserManager, UserCreate, UserLogin
from storage.database.history_manager import HistoryManager, HistoryCreate
from storage.s3.s3_storage import S3SyncStorage


# 初始化对象存储客户端
storage = S3SyncStorage(
    endpoint_url=os.getenv("COZE_BUCKET_ENDPOINT_URL"),
    access_key="",
    secret_key="",
    bucket_name=os.getenv("COZE_BUCKET_NAME"),
    region="cn-beijing",
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
    desc: 将上传的文件存入对象存储，并生成 24 小时公开 URL 返回
    integrations: 对象存储
    """
    ctx = runtime.context

    if not state.file:
        return UploadOutput(result={"success": False, "message": "未提供文件"})

    try:
        # 从 URL 读取文件内容
        file_url = state.file.url

        # 判断是本地路径还是远程 URL
        if file_url.startswith(("http://", "https://")):
            # 远程 URL：使用 upload_from_url
            file_key = storage.upload_from_url(url=file_url)
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
                    "created_at": h.created_at.isoformat() if h.created_at else None
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

    result = state.result

    # 根据结果生成统一响应
    if result.get("success"):
        code = 0
        msg = result.get("message", "操作成功")
        data = {k: v for k, v in result.items() if k not in ["success", "message"]}
    else:
        code = -1
        msg = result.get("message", "操作失败")
        data = None

    return FormatResponseOutput(response_data={"code": code, "msg": msg, "data": data})
