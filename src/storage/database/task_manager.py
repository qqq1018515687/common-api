"""任务管理接口"""
import time
from typing import Optional, List
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from storage.database.shared.model import Tasks, Users
import time


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
    deduction_result: Optional[dict] = Field(default=None, description="扣费结果记录")


class TaskManager:
    """任务管理类"""

    @staticmethod
    def verify_user_permission(db: Session, user_id: str) -> tuple[bool, Optional[str]]:
        """
        验证用户权限
        
        Args:
            db: 数据库会话
            user_id: 用户ID
        
        Returns:
            (是否有权限, 错误信息)
        """
        if not user_id:
            return False, "请先注册登录"
        
        # 查询用户
        user = db.query(Users).filter(Users.user_id == user_id).first()
        
        if not user:
            return False, "用户不存在，请先注册"
        
        if user.account_status != "active":
            return False, f"账号状态异常：{user.account_status}"
        
        return True, None

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
        """根据用户ID获取任务列表（自动过滤已删除的任务）"""
        query = db.query(Tasks).filter(Tasks.user_id == user_id, Tasks.is_deleted == False)

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

        # 保护 deduction_result 不被覆盖为 null
        if 'deduction_result' in update_data and update_data['deduction_result'] is None:
            del update_data['deduction_result']

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

    def delete_task(self, db: Session, task_id: str, user_id: str) -> tuple[bool, str]:
        """
        软删除任务（标记为已删除）
        
        Args:
            db: 数据库会话
            task_id: 任务ID
            user_id: 用户ID
        
        Returns:
            (是否成功, 消息)
        """
        # 验证用户权限
        has_permission, error_msg = self.verify_user_permission(db, user_id)
        if not has_permission:
            return False, error_msg
        
        # 查询任务
        db_task = self.get_task_by_id(db, task_id)
        if not db_task:
            return False, "任务不存在"
        
        # 查询用户信息（检查是否为管理员）
        user = db.query(Users).filter(Users.user_id == user_id).first()
        if not user:
            return False, "用户不存在"
        
        # 权限验证：管理员可以删除任何任务，普通用户只能删除自己的任务
        if user.role != 'admin' and db_task.user_id != user_id:
            return False, "无权删除此任务"
        
        # 软删除：设置 is_deleted 标记
        db_task.is_deleted = True
        db_task.updated_at = int(time.time() * 1000)

        db.add(db_task)
        try:
            db.commit()
            return True, "任务删除成功"
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
        """统计用户任务数量（自动过滤已删除的任务）"""
        query = db.query(Tasks).filter(Tasks.user_id == user_id, Tasks.is_deleted == False)

        if status:
            query = query.filter(Tasks.status == status)

        return query.count()
