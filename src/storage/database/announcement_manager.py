"""更新公告管理接口"""
import time
import uuid
from typing import Any, List, Optional

from pydantic import BaseModel, Field
from sqlalchemy import case, or_
from sqlalchemy.orm import Session

from storage.database.shared.model import UpdateAnnouncements


class AnnouncementCreate(BaseModel):
    """创建更新公告的输入"""
    title: str = Field(..., description="公告标题")
    summary: Optional[str] = Field(default=None, description="公告摘要")
    items: List[Any] = Field(default_factory=list, description="公告条目数组")
    cta_text: Optional[str] = Field(default=None, description="行动按钮文案")
    cta_url: Optional[str] = Field(default=None, description="行动按钮链接")
    target_audience: str = Field(default="all", description="目标用户：all/logged_in/guest/admin")
    priority: str = Field(default="medium", description="优先级：low/medium/high/urgent")
    is_active: bool = Field(default=True, description="是否启用")
    start_time: Optional[int] = Field(default=None, description="生效时间戳（毫秒）")
    end_time: Optional[int] = Field(default=None, description="失效时间戳（毫秒）")
    version: Optional[str] = Field(default=None, description="公告版本")
    created_by: str = Field(..., description="创建者用户ID")


class AnnouncementUpdate(BaseModel):
    """更新更新公告的输入"""
    title: Optional[str] = Field(default=None, description="公告标题")
    summary: Optional[str] = Field(default=None, description="公告摘要")
    items: Optional[List[Any]] = Field(default=None, description="公告条目数组")
    cta_text: Optional[str] = Field(default=None, description="行动按钮文案")
    cta_url: Optional[str] = Field(default=None, description="行动按钮链接")
    target_audience: Optional[str] = Field(default=None, description="目标用户")
    priority: Optional[str] = Field(default=None, description="优先级")
    is_active: Optional[bool] = Field(default=None, description="是否启用")
    start_time: Optional[int] = Field(default=None, description="生效时间戳")
    end_time: Optional[int] = Field(default=None, description="失效时间戳")
    version: Optional[str] = Field(default=None, description="公告版本")


class AnnouncementManager:
    """更新公告管理类"""

    @staticmethod
    def _to_dict(announcement: UpdateAnnouncements) -> dict:
        return {
            "id": announcement.id,
            "title": announcement.title,
            "summary": announcement.summary,
            "items": announcement.items or [],
            "cta_text": announcement.cta_text,
            "cta_url": announcement.cta_url,
            "target_audience": announcement.target_audience,
            "priority": announcement.priority,
            "is_active": announcement.is_active,
            "start_time": announcement.start_time,
            "end_time": announcement.end_time,
            "version": announcement.version,
            "created_at": announcement.created_at,
            "updated_at": announcement.updated_at,
            "created_by": announcement.created_by,
        }

    @staticmethod
    def _priority_rank():
        return case(
            (UpdateAnnouncements.priority == "urgent", 4),
            (UpdateAnnouncements.priority == "high", 3),
            (UpdateAnnouncements.priority == "medium", 2),
            (UpdateAnnouncements.priority == "low", 1),
            else_=0,
        )

    @staticmethod
    def create_announcement(
        db: Session,
        announcement_data: AnnouncementCreate,
    ) -> tuple[bool, dict, Optional[str]]:
        try:
            now = int(time.time() * 1000)
            announcement = UpdateAnnouncements(
                id=f"announcement_{now}_{uuid.uuid4().hex[:8]}",
                title=announcement_data.title,
                summary=announcement_data.summary,
                items=announcement_data.items,
                cta_text=announcement_data.cta_text,
                cta_url=announcement_data.cta_url,
                target_audience=announcement_data.target_audience,
                priority=announcement_data.priority,
                is_active=announcement_data.is_active,
                start_time=announcement_data.start_time or now,
                end_time=announcement_data.end_time,
                version=announcement_data.version,
                created_at=now,
                updated_at=now,
                created_by=announcement_data.created_by,
            )

            db.add(announcement)
            db.commit()
            db.refresh(announcement)
            return True, AnnouncementManager._to_dict(announcement), None

        except Exception as e:
            db.rollback()
            return False, {}, f"创建更新公告失败: {str(e)}"

    @staticmethod
    def get_active_popup(
        db: Session,
        current_time: Optional[int] = None,
        target_audience: str = "all",
    ) -> tuple[bool, Optional[dict], Optional[str]]:
        try:
            if current_time is None:
                current_time = int(time.time() * 1000)

            announcement = db.query(UpdateAnnouncements).filter(
                UpdateAnnouncements.is_active.is_(True),
                UpdateAnnouncements.start_time <= current_time,
                or_(
                    UpdateAnnouncements.end_time >= current_time,
                    UpdateAnnouncements.end_time.is_(None),
                ),
                UpdateAnnouncements.target_audience.in_(["all", target_audience or "all"]),
            ).order_by(
                AnnouncementManager._priority_rank().desc(),
                UpdateAnnouncements.updated_at.desc(),
                UpdateAnnouncements.created_at.desc(),
            ).first()

            if announcement is None:
                return True, None, None

            return True, AnnouncementManager._to_dict(announcement), None

        except Exception as e:
            return False, None, f"查询当前更新公告失败: {str(e)}"

    @staticmethod
    def get_all_announcements(db: Session) -> tuple[bool, List[dict], Optional[str]]:
        try:
            announcements = db.query(UpdateAnnouncements).order_by(
                UpdateAnnouncements.updated_at.desc(),
                UpdateAnnouncements.created_at.desc(),
            ).all()

            return True, [AnnouncementManager._to_dict(item) for item in announcements], None

        except Exception as e:
            return False, [], f"查询全部更新公告失败: {str(e)}"

    @staticmethod
    def update_announcement(
        db: Session,
        announcement_id: str,
        announcement_updates: AnnouncementUpdate,
    ) -> tuple[bool, Optional[dict], Optional[str]]:
        try:
            announcement = db.query(UpdateAnnouncements).filter(
                UpdateAnnouncements.id == announcement_id,
            ).first()

            if announcement is None:
                return False, None, "更新公告不存在"

            updates = announcement_updates.model_dump(exclude_unset=True)
            for field, value in updates.items():
                setattr(announcement, field, value)

            announcement.updated_at = int(time.time() * 1000)

            db.commit()
            db.refresh(announcement)
            return True, AnnouncementManager._to_dict(announcement), None

        except Exception as e:
            db.rollback()
            return False, None, f"更新更新公告失败: {str(e)}"

    @staticmethod
    def disable_announcement(db: Session, announcement_id: str) -> tuple[bool, Optional[str]]:
        try:
            announcement = db.query(UpdateAnnouncements).filter(
                UpdateAnnouncements.id == announcement_id,
            ).first()

            if announcement is None:
                return False, "更新公告不存在"

            announcement.is_active = False
            announcement.updated_at = int(time.time() * 1000)
            db.commit()
            return True, None

        except Exception as e:
            db.rollback()
            return False, f"停用更新公告失败: {str(e)}"
