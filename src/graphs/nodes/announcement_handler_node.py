"""更新公告处理节点"""
import time
from typing import Optional

from coze_coding_utils.runtime_ctx.context import Context
from langchain_core.runnables import RunnableConfig
from langgraph.runtime import Runtime
from pydantic import BaseModel, Field

from storage.database.announcement_manager import (
    AnnouncementCreate,
    AnnouncementManager,
    AnnouncementUpdate,
)
from storage.database.db import get_session


class AnnouncementHandlerInput(BaseModel):
    """更新公告处理节点的输入"""
    operation_type: str = Field(..., description="操作类型：get_active_popup/get_all/create/update/disable")
    current_time: Optional[int] = Field(default=None, description="当前时间戳（用于筛选有效公告）")
    target_audience: Optional[str] = Field(default="all", description="目标用户：all/logged_in/guest/admin")
    announcement_id: Optional[str] = Field(default=None, description="公告ID（update/disable 使用）")
    announcement_data: Optional[dict] = Field(default=None, description="公告数据（create/update 使用）")
    operator_user_id: Optional[str] = Field(default=None, description="操作者用户ID")


class AnnouncementHandlerOutput(BaseModel):
    """更新公告处理节点的输出"""
    result: dict = Field(..., description="操作结果")


def announcement_handler_node(
    state: AnnouncementHandlerInput,
    config: RunnableConfig,
    runtime: Runtime[Context],
) -> AnnouncementHandlerOutput:
    """
    title: 更新公告处理
    desc: 处理独立更新公告弹窗的增改查和停用操作
    integrations: 数据库
    """
    operation_type = state.operation_type
    db = get_session()

    try:
        current_time = state.current_time
        if current_time is None:
            current_time = int(time.time() * 1000)

        if operation_type == "get_active_popup":
            success, announcement, error = AnnouncementManager.get_active_popup(
                db,
                current_time=current_time,
                target_audience=state.target_audience or "all",
            )

            if success:
                result = {
                    "code": 0,
                    "msg": "查询成功",
                    "data": {
                        "announcement": announcement,
                        "active_popup": announcement,
                        "current_time": current_time,
                        "target_audience": state.target_audience or "all",
                    },
                }
            else:
                result = {
                    "code": 1,
                    "msg": error or "查询失败",
                    "data": {
                        "announcement": None,
                        "active_popup": None,
                    },
                }

        elif operation_type == "get_all":
            success, announcements, error = AnnouncementManager.get_all_announcements(db)

            if success:
                result = {
                    "code": 0,
                    "msg": "查询成功",
                    "data": {
                        "announcements": announcements,
                        "total": len(announcements),
                    },
                }
            else:
                result = {
                    "code": 1,
                    "msg": error or "查询失败",
                    "data": {
                        "announcements": [],
                        "total": 0,
                    },
                }

        elif operation_type == "create":
            if not state.announcement_data:
                result = {
                    "code": 1,
                    "msg": "缺少公告数据",
                    "data": None,
                }
            else:
                announcement_data = dict(state.announcement_data)
                if not announcement_data.get("created_by"):
                    announcement_data["created_by"] = state.operator_user_id or "system"

                create_data = AnnouncementCreate(**announcement_data)
                success, announcement, error = AnnouncementManager.create_announcement(db, create_data)

                if success:
                    result = {
                        "code": 0,
                        "msg": "创建成功",
                        "data": {
                            "id": announcement["id"],
                            "announcement": announcement,
                        },
                    }
                else:
                    result = {
                        "code": 1,
                        "msg": error or "创建失败",
                        "data": None,
                    }

        elif operation_type == "update":
            if not state.announcement_id:
                result = {
                    "code": 1,
                    "msg": "缺少公告ID",
                    "data": None,
                }
            elif not state.announcement_data:
                result = {
                    "code": 1,
                    "msg": "缺少更新数据",
                    "data": None,
                }
            else:
                update_data = AnnouncementUpdate(**state.announcement_data)
                success, announcement, error = AnnouncementManager.update_announcement(
                    db,
                    state.announcement_id,
                    update_data,
                )

                if success:
                    result = {
                        "code": 0,
                        "msg": "更新成功",
                        "data": {
                            "announcement": announcement,
                        },
                    }
                else:
                    result = {
                        "code": 1,
                        "msg": error or "更新失败",
                        "data": None,
                    }

        elif operation_type == "disable":
            if not state.announcement_id:
                result = {
                    "code": 1,
                    "msg": "缺少公告ID",
                    "data": None,
                }
            else:
                success, error = AnnouncementManager.disable_announcement(db, state.announcement_id)

                if success:
                    result = {
                        "code": 0,
                        "msg": "停用成功",
                        "data": {
                            "id": state.announcement_id,
                        },
                    }
                else:
                    result = {
                        "code": 1,
                        "msg": error or "停用失败",
                        "data": None,
                    }

        else:
            result = {
                "code": 1,
                "msg": f"不支持的操作类型: {operation_type}",
                "data": None,
            }

        return AnnouncementHandlerOutput(result=result)

    finally:
        db.close()
