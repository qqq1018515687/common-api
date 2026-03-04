"""系统通知管理接口"""
import time
from typing import Optional, List
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from storage.database.shared.model import SystemNotifications


class NotificationCreate(BaseModel):
    """创建通知的输入"""
    type: str = Field(..., description="通知类型：info/warning/error/maintenance/update")
    title: str = Field(..., description="通知标题")
    content: str = Field(..., description="通知内容")
    priority: str = Field(default="medium", description="优先级：low/medium/high/urgent")
    is_active: bool = Field(default=True, description="是否激活")
    start_time: int = Field(..., description="生效时间戳（毫秒）")
    end_time: Optional[int] = Field(default=None, description="失效时间戳（毫秒，null表示永久）")
    dismissible: bool = Field(default=True, description="是否允许用户关闭")
    link_url: Optional[str] = Field(default=None, description="点击跳转链接（可选）")
    target_audience: str = Field(default="all", description="目标用户：all/logged_in/guest/admin")
    created_by: str = Field(..., description="创建者用户ID")


class NotificationUpdate(BaseModel):
    """更新通知的输入"""
    type: Optional[str] = Field(default=None, description="通知类型")
    title: Optional[str] = Field(default=None, description="通知标题")
    content: Optional[str] = Field(default=None, description="通知内容")
    priority: Optional[str] = Field(default=None, description="优先级")
    is_active: Optional[bool] = Field(default=None, description="是否激活")
    start_time: Optional[int] = Field(default=None, description="生效时间戳")
    end_time: Optional[int] = Field(default=None, description="失效时间戳")
    dismissible: Optional[bool] = Field(default=None, description="是否允许用户关闭")
    link_url: Optional[str] = Field(default=None, description="点击跳转链接")
    target_audience: Optional[str] = Field(default=None, description="目标用户")


class NotificationManager:
    """通知管理类"""

    @staticmethod
    def create_notification(db: Session, notification_data: NotificationCreate) -> tuple[bool, dict, Optional[str]]:
        """
        创建新通知

        Args:
            db: 数据库会话
            notification_data: 通知数据

        Returns:
            (是否成功, 通知数据, 错误信息)
        """
        try:
            now = int(time.time() * 1000)

            # 创建通知对象
            notification = SystemNotifications(
                id=notification_data.type + "_" + str(now),
                type=notification_data.type,
                title=notification_data.title,
                content=notification_data.content,
                priority=notification_data.priority,
                is_active=notification_data.is_active,
                start_time=notification_data.start_time,
                end_time=notification_data.end_time,
                dismissible=notification_data.dismissible,
                link_url=notification_data.link_url,
                target_audience=notification_data.target_audience,
                created_at=now,
                updated_at=now,
                created_by=notification_data.created_by
            )

            db.add(notification)
            db.commit()
            db.refresh(notification)

            # 转换为字典
            notification_dict = {
                "id": notification.id,
                "type": notification.type,
                "title": notification.title,
                "content": notification.content,
                "priority": notification.priority,
                "is_active": notification.is_active,
                "start_time": notification.start_time,
                "end_time": notification.end_time,
                "dismissible": notification.dismissible,
                "link_url": notification.link_url,
                "target_audience": notification.target_audience,
                "created_at": notification.created_at,
                "updated_at": notification.updated_at,
                "created_by": notification.created_by
            }

            return True, notification_dict, None

        except Exception as e:
            db.rollback()
            return False, {}, f"创建通知失败: {str(e)}"

    @staticmethod
    def get_notification(db: Session, notification_id: str) -> tuple[bool, Optional[dict], Optional[str]]:
        """
        获取单个通知

        Args:
            db: 数据库会话
            notification_id: 通知ID

        Returns:
            (是否成功, 通知数据, 错误信息)
        """
        try:
            notification = db.query(SystemNotifications).filter(
                SystemNotifications.id == notification_id
            ).first()

            if not notification:
                return False, None, "通知不存在"

            notification_dict = {
                "id": notification.id,
                "type": notification.type,
                "title": notification.title,
                "content": notification.content,
                "priority": notification.priority,
                "is_active": notification.is_active,
                "start_time": notification.start_time,
                "end_time": notification.end_time,
                "dismissible": notification.dismissible,
                "link_url": notification.link_url,
                "target_audience": notification.target_audience,
                "created_at": notification.created_at,
                "updated_at": notification.updated_at,
                "created_by": notification.created_by
            }

            return True, notification_dict, None

        except Exception as e:
            return False, None, f"查询通知失败: {str(e)}"

    @staticmethod
    def update_notification(db: Session, notification_id: str, notification_updates: NotificationUpdate) -> tuple[bool, Optional[dict], Optional[str]]:
        """
        更新通知

        Args:
            db: 数据库会话
            notification_id: 通知ID
            notification_updates: 更新数据

        Returns:
            (是否成功, 更新后的通知数据, 错误信息)
        """
        try:
            notification = db.query(SystemNotifications).filter(
                SystemNotifications.id == notification_id
            ).first()

            if not notification:
                return False, None, "通知不存在"

            # 更新字段
            if notification_updates.type is not None:
                notification.type = notification_updates.type
            if notification_updates.title is not None:
                notification.title = notification_updates.title
            if notification_updates.content is not None:
                notification.content = notification_updates.content
            if notification_updates.priority is not None:
                notification.priority = notification_updates.priority
            if notification_updates.is_active is not None:
                notification.is_active = notification_updates.is_active
            if notification_updates.start_time is not None:
                notification.start_time = notification_updates.start_time
            if notification_updates.end_time is not None:
                notification.end_time = notification_updates.end_time
            if notification_updates.dismissible is not None:
                notification.dismissible = notification_updates.dismissible
            if notification_updates.link_url is not None:
                notification.link_url = notification_updates.link_url
            if notification_updates.target_audience is not None:
                notification.target_audience = notification_updates.target_audience

            notification.updated_at = int(time.time() * 1000)

            db.commit()
            db.refresh(notification)

            notification_dict = {
                "id": notification.id,
                "type": notification.type,
                "title": notification.title,
                "content": notification.content,
                "priority": notification.priority,
                "is_active": notification.is_active,
                "start_time": notification.start_time,
                "end_time": notification.end_time,
                "dismissible": notification.dismissible,
                "link_url": notification.link_url,
                "target_audience": notification.target_audience,
                "created_at": notification.created_at,
                "updated_at": notification.updated_at,
                "created_by": notification.created_by
            }

            return True, notification_dict, None

        except Exception as e:
            db.rollback()
            return False, None, f"更新通知失败: {str(e)}"

    @staticmethod
    def delete_notification(db: Session, notification_id: str) -> tuple[bool, Optional[str]]:
        """
        删除通知（软删除，设置 is_active=False）

        Args:
            db: 数据库会话
            notification_id: 通知ID

        Returns:
            (是否成功, 错误信息)
        """
        try:
            notification = db.query(SystemNotifications).filter(
                SystemNotifications.id == notification_id
            ).first()

            if not notification:
                return False, "通知不存在"

            # 软删除：设置为不激活
            notification.is_active = False
            notification.updated_at = int(time.time() * 1000)

            db.commit()

            return True, None

        except Exception as e:
            db.rollback()
            return False, f"删除通知失败: {str(e)}"

    @staticmethod
    def get_active_notifications(db: Session, current_time: Optional[int] = None) -> tuple[bool, List[dict], Optional[str]]:
        """
        获取当前有效的通知

        Args:
            db: 数据库会话
            current_time: 当前时间戳（毫秒），如果不提供则使用当前时间

        Returns:
            (是否成功, 通知列表, 错误信息)
        """
        try:
            if current_time is None:
                current_time = int(time.time() * 1000)

            # 查询条件：is_active=true 且 start_time <= now <= end_time (end_time 为 null 表示永久)
            notifications = db.query(SystemNotifications).filter(
                SystemNotifications.is_active == True,
                SystemNotifications.start_time <= current_time,
                (SystemNotifications.end_time >= current_time) | (SystemNotifications.end_time.is_(None))
            ).order_by(SystemNotifications.priority.desc(), SystemNotifications.created_at.desc()).all()

            notification_list = []
            for notification in notifications:
                notification_dict = {
                    "id": notification.id,
                    "type": notification.type,
                    "title": notification.title,
                    "content": notification.content,
                    "priority": notification.priority,
                    "is_active": notification.is_active,
                    "start_time": notification.start_time,
                    "end_time": notification.end_time,
                    "dismissible": notification.dismissible,
                    "link_url": notification.link_url,
                    "target_audience": notification.target_audience,
                    "created_at": notification.created_at,
                    "updated_at": notification.updated_at,
                    "created_by": notification.created_by
                }
                notification_list.append(notification_dict)

            return True, notification_list, None

        except Exception as e:
            return False, [], f"查询有效通知失败: {str(e)}"

    @staticmethod
    def get_all_notifications(db: Session) -> tuple[bool, List[dict], Optional[str]]:
        """
        获取所有通知（管理后台用）

        Args:
            db: 数据库会话

        Returns:
            (是否成功, 通知列表, 错误信息)
        """
        try:
            notifications = db.query(SystemNotifications).order_by(
                SystemNotifications.created_at.desc()
            ).all()

            notification_list = []
            for notification in notifications:
                notification_dict = {
                    "id": notification.id,
                    "type": notification.type,
                    "title": notification.title,
                    "content": notification.content,
                    "priority": notification.priority,
                    "is_active": notification.is_active,
                    "start_time": notification.start_time,
                    "end_time": notification.end_time,
                    "dismissible": notification.dismissible,
                    "link_url": notification.link_url,
                    "target_audience": notification.target_audience,
                    "created_at": notification.created_at,
                    "updated_at": notification.updated_at,
                    "created_by": notification.created_by
                }
                notification_list.append(notification_dict)

            return True, notification_list, None

        except Exception as e:
            return False, [], f"查询所有通知失败: {str(e)}"
