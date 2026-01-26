from typing import List, Optional, Dict, Any
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session
from datetime import datetime

from storage.database.shared.model import History


class HistoryCreate(BaseModel):
    user_id: str = Field(..., description="用户 ID")
    permanent_link: str = Field(..., description="永久链接")
    task_params: Optional[Dict[str, Any]] = Field(default=None, description="任务参数")


class HistoryManager:
    """Manager class for History operations."""

    def create_history(self, db: Session, history_in: HistoryCreate) -> History:
        """创建历史记录"""
        history_data = history_in.model_dump()
        history_data["iso_timestamp"] = datetime.utcnow().isoformat()
        db_history = History(**history_data)
        db.add(db_history)
        try:
            db.commit()
            db.refresh(db_history)
            return db_history
        except Exception:
            db.rollback()
            raise

    def get_histories_by_user_id(self, db: Session, user_id: int) -> List[History]:
        """根据用户 ID 获取所有历史记录"""
        return db.query(History).filter(History.user_id == user_id).order_by(History.created_at.desc()).all()

    def get_history_by_id(self, db: Session, history_id: int) -> Optional[History]:
        """根据 ID 获取历史记录"""
        return db.query(History).filter(History.id == history_id).first()
