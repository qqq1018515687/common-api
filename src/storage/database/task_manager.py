"""任务管理接口"""
import time
from typing import Optional, List
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from storage.database.shared.model import Tasks


class TaskCreate(BaseModel):
    """创建任务的输入"""
    id: str = Field(..., description="任务ID（前端生成的UUID）")
    user_id: str = Field(..., description="用户ID")
    team_id: Optional[str] = Field(default=None, description="团队ID")
    platform: str = Field(..., description="平台标识")
    platform_task_id: str = Field(..., description="平台任务ID")
    type: str = Field(..., description="任务类型：image/video/audio")
    workflow_parameters: Optional[dict] = Field(default=None, description="工作流参数")
    parameter_snapshot: Optional[dict] = Field(default=None, description="完整参数快照")
    batch_id: Optional[str] = Field(default=None, description="批次ID")
    connection_mode: Optional[str] = Field(default="sse", description="连接模式")


class TaskUpdate(BaseModel):
    """更新任务的输入"""
    status: Optional[str] = Field(default=None, description="任务状态")
    result: Optional[dict] = Field(default=None, description="生成结果")
    error: Optional[str] = Field(default=None, description="错误信息")
    completed_at: Optional[int] = Field(default=None, description="完成时间")


class TaskManager:
    """任务管理类"""

    def create_task(self, db: Session, task_in: TaskCreate) -> Tasks:
        """创建任务"""
        current_time = int(time.time() * 1000)
        task_data = task_in.model_dump()
        task_data['status'] = 'running'
        task_data['created_at'] = current_time
        task_data['updated_at'] = current_time

        db_task = Tasks(**task_data)
        db.add(db_task)
        try:
            db.commit()
            db.refresh(db_task)
            return db_task
        except Exception:
            db.rollback()
            raise

    def get_task_by_id(self, db: Session, task_id: str) -> Optional[Tasks]:
        """根据任务ID获取任务"""
        return db.query(Tasks).filter(Tasks.id == task_id).first()

    def get_tasks_by_user_id(
        self,
        db: Session,
        user_id: str,
        status: Optional[str] = None,
        skip: int = 0,
        limit: int = 100,
        **filters
    ) -> List[Tasks]:
        """根据用户ID获取任务列表"""
        query = db.query(Tasks).filter(Tasks.user_id == user_id)

        if status:
            query = query.filter(Tasks.status == status)

        for attr, value in filters.items():
            if hasattr(Tasks, attr):
                query = query.filter(getattr(Tasks, attr) == value)

        return query.order_by(Tasks.updated_at.desc()).offset(skip).limit(limit).all()

    def get_task_by_platform_task_id(
        self,
        db: Session,
        platform: str,
        platform_task_id: str
    ) -> Optional[Tasks]:
        """根据平台和平台任务ID获取任务"""
        return db.query(Tasks).filter(
            Tasks.platform == platform,
            Tasks.platform_task_id == platform_task_id
        ).first()

    def update_task(
        self,
        db: Session,
        task_id: str,
        task_in: TaskUpdate
    ) -> Optional[Tasks]:
        """更新任务"""
        db_task = self.get_task_by_id(db, task_id)
        if not db_task:
            return None

        update_data = task_in.model_dump(exclude_unset=True)
        update_data['updated_at'] = int(time.time() * 1000)

        for field, value in update_data.items():
            if hasattr(db_task, field):
                setattr(db_task, field, value)

        db.add(db_task)
        try:
            db.commit()
            db.refresh(db_task)
            return db_task
        except Exception:
            db.rollback()
            raise

    def delete_task(self, db: Session, task_id: str) -> bool:
        """删除任务"""
        db_task = self.get_task_by_id(db, task_id)
        if not db_task:
            return False

        db.delete(db_task)
        try:
            db.commit()
            return True
        except Exception:
            db.rollback()
            raise

    def delete_tasks_by_user_id(self, db: Session, user_id: str) -> int:
        """根据用户ID删除所有任务"""
        deleted_count = db.query(Tasks).filter(Tasks.user_id == user_id).delete(
            synchronize_session=False
        )
        db.commit()
        return deleted_count

    def count_tasks_by_user_id(
        self,
        db: Session,
        user_id: str,
        status: Optional[str] = None
    ) -> int:
        """统计用户任务数量"""
        query = db.query(Tasks).filter(Tasks.user_id == user_id)

        if status:
            query = query.filter(Tasks.status == status)

        return query.count()
