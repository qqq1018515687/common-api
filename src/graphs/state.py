from typing import Literal, Optional, List
from pydantic import BaseModel, Field
from utils.file.file import File


class GlobalState(BaseModel):
    """全局状态定义"""
    call_type: str = Field(..., description="调用类型：register/login/upload/save/history/tool")
    username: Optional[str] = Field(default=None, description="用户名（注册/登录使用）")
    password: Optional[str] = Field(default=None, description="密码（注册/登录使用）")
    file: Optional[File] = Field(default=None, description="上传的文件（upload/tool 使用）")
    user_id: Optional[int] = Field(default=None, description="用户 ID（save/history 使用）")
    runninghub_link: Optional[str] = Field(default=None, description="RunningHub 链接（save 使用）")
    tool_type: Optional[str] = Field(default=None, description="工具类型：reverse_image/translate_doubao/translate_flash")
    prompt: Optional[str] = Field(default=None, description="提示词/待翻译文本（tool 使用）")
    response_data: Optional[dict] = Field(default=None, description="统一响应数据")


class GraphInput(BaseModel):
    """工作流的输入"""
    call_type: str = Field(..., description="调用类型：register/login/upload/save/history/tool")
    username: Optional[str] = Field(default=None, description="用户名（注册/登录使用）")
    password: Optional[str] = Field(default=None, description="密码（注册/登录使用）")
    file: Optional[File] = Field(default=None, description="上传的文件（upload/tool 使用）")
    user_id: Optional[int] = Field(default=None, description="用户 ID（save/history 使用）")
    runninghub_link: Optional[str] = Field(default=None, description="RunningHub 链接（save 使用）")
    tool_type: Optional[str] = Field(default=None, description="工具类型：reverse_image/translate_doubao/translate_flash")
    prompt: Optional[str] = Field(default=None, description="提示词/待翻译文本（tool 使用）")


class GraphOutput(BaseModel):
    """工作流的输出"""
    response_data: dict = Field(..., description="统一响应数据：{code, msg, data}")


# 注册/登录节点
class RegisterLoginInput(BaseModel):
    """注册/登录节点的输入"""
    call_type: str = Field(..., description="调用类型：register 或 login")
    username: Optional[str] = Field(default=None, description="用户名")
    password: Optional[str] = Field(default=None, description="密码")


class RegisterLoginOutput(BaseModel):
    """注册/登录节点的输出"""
    result: dict = Field(default={}, description="操作结果")


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
    user_id: Optional[int] = Field(default=None, description="用户 ID")
    runninghub_link: Optional[str] = Field(default=None, description="RunningHub 链接")


class SaveOutput(BaseModel):
    """保存历史节点的输出"""
    result: dict = Field(default={}, description="保存结果")


# 历史查询节点
class HistoryInput(BaseModel):
    """历史查询节点的输入"""
    user_id: Optional[int] = Field(default=None, description="用户 ID")


class HistoryOutput(BaseModel):
    """历史查询节点的输出"""
    result: dict = Field(default={}, description="查询结果：历史记录列表")


# 统一返回节点
class FormatResponseInput(BaseModel):
    """统一返回节点的输入"""
    call_type: str = Field(..., description="调用类型")
    result: dict = Field(default={}, description="各节点的结果")


class FormatResponseOutput(BaseModel):
    """统一返回节点的输出"""
    response_data: dict = Field(..., description="统一响应数据：{code, msg, data}")


class RouterOutput(BaseModel):
    """路由节点的输出"""
    call_type: str = Field(..., description="调用类型")


class RouterInput(BaseModel):
    """路由节点的输入"""
    call_type: str = Field(..., description="调用类型")


# 工具路由节点
class ToolRouteInput(BaseModel):
    """工具路由节点的输入"""
    tool_type: str = Field(..., description="工具类型：reverse_image/translate_doubao/translate_flash")


class ToolRouteOutput(BaseModel):
    """工具路由节点的输出"""
    tool_type: str = Field(..., description="工具类型")


# 反推图像节点
class ReverseImageInput(BaseModel):
    """反推图像节点的输入"""
    file: Optional[File] = Field(default=None, description="图像文件")
    prompt: str = Field(..., description="反推指令")


class ReverseImageOutput(BaseModel):
    """反推图像节点的输出"""
    result: dict = Field(default={}, description="反推结果")


# 翻译节点（推荐版）
class TranslateDoubaoInput(BaseModel):
    """翻译节点（推荐版）的输入"""
    prompt: str = Field(..., description="待翻译文本")


class TranslateDoubaoOutput(BaseModel):
    """翻译节点（推荐版）的输出"""
    result: dict = Field(default={}, description="翻译结果")



