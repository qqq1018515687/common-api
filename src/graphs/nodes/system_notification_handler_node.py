"""系统通知处理节点"""
import time
from typing import Optional
from langchain_core.runnables import RunnableConfig
from langgraph.runtime import Runtime
from coze_coding_utils.runtime_ctx.context import Context
from pydantic import BaseModel, Field

from storage.database.db import get_session
from storage.database.notification_manager import NotificationManager, NotificationCreate, NotificationUpdate


class NotificationHandlerInput(BaseModel):
    """通知处理节点的输入"""
    operation_type: str = Field(..., description="操作类型：get_active/get_all/create/update/delete")
    notification_id: Optional[str] = Field(default=None, description="通知ID（update/delete 使用）")
    notification_data: Optional[dict] = Field(default=None, description="通知数据（create/update 使用）")
    current_time: Optional[int] = Field(default=None, description="当前时间戳（用于筛选有效通知）")


class NotificationHandlerOutput(BaseModel):
    """通知处理节点的输出"""
    result: dict = Field(..., description="操作结果")


def system_notification_handler_node(
    state: NotificationHandlerInput,
    config: RunnableConfig,
    runtime: Runtime[Context]
) -> NotificationHandlerOutput:
    """
    title: 系统通知处理
    desc: 处理系统通知的增删改查操作
    integrations: 数据库
    """
    ctx = runtime.context

    operation_type = state.operation_type
    db = get_session()

    try:
        # 获取当前时间（用于筛选有效通知）
        current_time = state.current_time
        if current_time is None:
            current_time = int(time.time() * 1000)

        # 根据操作类型执行不同的逻辑
        if operation_type == "get_active":
            # 获取当前有效的通知
            success, notifications, error = NotificationManager.get_active_notifications(db, current_time)

            if success:
                result = {
                    "code": 0,
                    "msg": "查询成功",
                    "data": {
                        "notifications": notifications,
                        "total": len(notifications),
                        "current_time": current_time
                    }
                }
            else:
                result = {
                    "code": 1,
                    "msg": error or "查询失败",
                    "data": {
                        "notifications": [],
                        "total": 0
                    }
                }

        elif operation_type == "get_all":
            # 获取所有通知（管理后台用）
            success, notifications, error = NotificationManager.get_all_notifications(db)

            if success:
                result = {
                    "code": 0,
                    "msg": "查询成功",
                    "data": {
                        "notifications": notifications,
                        "total": len(notifications)
                    }
                }
            else:
                result = {
                    "code": 1,
                    "msg": error or "查询失败",
                    "data": {
                        "notifications": [],
                        "total": 0
                    }
                }

        elif operation_type == "create":
            # 创建通知
            if not state.notification_data:
                result = {
                    "code": 1,
                    "msg": "缺少通知数据",
                    "data": None
                }
            else:
                notification_data = NotificationCreate(**state.notification_data)
                success, notification, error = NotificationManager.create_notification(db, notification_data)

                if success:
                    result = {
                        "code": 0,
                        "msg": "创建成功",
                        "data": {
                            "id": notification["id"],
                            "notification": notification
                        }
                    }
                else:
                    result = {
                        "code": 1,
                        "msg": error or "创建失败",
                        "data": None
                    }

        elif operation_type == "update":
            # 更新通知
            if not state.notification_id:
                result = {
                    "code": 1,
                    "msg": "缺少通知ID",
                    "data": None
                }
            elif not state.notification_data:
                result = {
                    "code": 1,
                    "msg": "缺少更新数据",
                    "data": None
                }
            else:
                notification_updates = NotificationUpdate(**state.notification_data)
                success, notification, error = NotificationManager.update_notification(
                    db,
                    state.notification_id,
                    notification_updates
                )

                if success:
                    result = {
                        "code": 0,
                        "msg": "更新成功",
                        "data": {
                            "notification": notification
                        }
                    }
                else:
                    result = {
                        "code": 1,
                        "msg": error or "更新失败",
                        "data": None
                    }

        elif operation_type == "delete":
            # 删除通知（软删除）
            if not state.notification_id:
                result = {
                    "code": 1,
                    "msg": "缺少通知ID",
                    "data": None
                }
            else:
                success, error = NotificationManager.delete_notification(db, state.notification_id)

                if success:
                    result = {
                        "code": 0,
                        "msg": "删除成功",
                        "data": {
                            "id": state.notification_id
                        }
                    }
                else:
                    result = {
                        "code": 1,
                        "msg": error or "删除失败",
                        "data": None
                    }

        else:
            result = {
                "code": 1,
                "msg": f"不支持的操作类型: {operation_type}",
                "data": None
            }

        return NotificationHandlerOutput(result=result)

    finally:
        db.close()
