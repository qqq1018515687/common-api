"""任务管理接口"""
import time
from typing import Optional, List
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session
from sqlalchemy import text

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
    deduction_result: Optional[dict] = Field(default=None, description="扣费结果记录")


class TaskUpdate(BaseModel):
    """更新任务的输入"""
    status: Optional[str] = Field(default=None, description="任务状态")
    result: Optional[dict] = Field(default=None, description="生成结果")
    error: Optional[str] = Field(default=None, description="错误信息")
    completed_at: Optional[int] = Field(default=None, description="完成时间")
    deduction_result: Optional[dict] = Field(default=None, description="扣费结果记录")
    user_friendly_message: Optional[str] = Field(default=None, description="LLM 生成的用户友好错误提示")


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
        current_time = str(int(time.time() * 1000))
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
        start_time: Optional[int] = None,
        end_time: Optional[int] = None,
        limit: int = 100,
        **filters
    ) -> List[Tasks]:
        """根据用户ID获取任务列表（使用时间范围筛选，自动过滤已删除的任务）

        Args:
            db: 数据库会话
            user_id: 用户ID
            status: 任务状态筛选（可选）
            start_time: 查询开始时间戳（毫秒，可选）
            end_time: 查询结束时间戳（毫秒，可选）
            limit: 最大返回数量（默认100，最大500）
            **filters: 其他筛选条件（如 team_id）

        Returns:
            任务列表（按 created_at DESC 排序）
        """
        # 限制最大返回数量
        limit = min(limit, 500)

        query = db.query(Tasks).filter(
            Tasks.user_id == user_id,
            Tasks.is_deleted == False
        )

        # 时间范围筛选（将时间戳转换为字符串比较）
        if start_time is not None:
            query = query.filter(Tasks.created_at >= str(start_time))
        if end_time is not None:
            query = query.filter(Tasks.created_at <= str(end_time))

        # 游标分页：统计早于 before_time 的记录
        if before_time is not None:
            query = query.filter(Tasks.created_at < str(before_time))

        # 状态筛选
        if status:
            query = query.filter(Tasks.status == status)

        # 其他筛选条件
        for attr, value in filters.items():
            if hasattr(Tasks, attr):
                query = query.filter(getattr(Tasks, attr) == value)

        # 按 created_at 降序排列，限制返回数量
        return query.order_by(Tasks.created_at.desc()).limit(limit).all()

    def get_tasks_flexible(
        self,
        db: Session,
        user_id: Optional[str] = None,
        team_id: Optional[str] = None,
        status: Optional[str] = None,
        start_time: Optional[int] = None,
        end_time: Optional[int] = None,
        limit: int = 50,
        before_time: Optional[int] = None,
    ) -> List[tuple]:
        """灵活查询任务列表

        Args:
            db: 数据库会话
            user_id: 用户ID（可选）
            team_id: 团队ID（可选）
            status: 任务状态筛选（可选）
            start_time: 查询开始时间戳（毫秒，可选）
            end_time: 查询结束时间戳（毫秒，可选）
            limit: 返回数量限制（默认50，最大1000）
            before_time: 游标分页，查询早于该时间戳的记录（毫秒，可选）

        Returns:
            任务列表（按 created_at DESC 排序），每个元素是 (Task, username) 元组

        查询规则：
            - 如果只提供 user_id（没有 team_id）：查询该用户的所有任务
            - 如果提供 team_id（不管有没有 user_id）：查询该团队的所有任务
            - 如果既没有 user_id 也没有 team_id：返回空列表
        """
        # 限制最大返回数量
        limit = min(limit, 1000)

        # 基础查询：JOIN Users 表，获取 username
        query = db.query(Tasks, Users.username).outerjoin(
            Users, Tasks.user_id == Users.user_id
        ).filter(Tasks.is_deleted == False)

        # 查询逻辑：
        # - team_id 为 None（前端未传或传 null）：查询该用户的个人任务（team_id IS NULL）
        # - team_id 有值：查询该团队的所有任务
        # - 既没有 user_id 也没有 team_id：返回空列表
        if team_id:
            query = query.filter(Tasks.team_id == team_id)
        elif user_id:
            # 个人任务：team_id 为空或不存在
            query = query.filter(Tasks.user_id == user_id, Tasks.team_id.is_(None))
        else:
            return []

        # 时间范围筛选
        if start_time is not None:
            query = query.filter(Tasks.created_at >= str(start_time))
        if end_time is not None:
            query = query.filter(Tasks.created_at <= str(end_time))

        # 游标分页：查询早于 before_time 的记录
        if before_time is not None:
            query = query.filter(Tasks.created_at < str(before_time))

        # 状态筛选
        if status:
            query = query.filter(Tasks.status == status)

        # completed 任务：SQL 层过滤无媒体结果（确保分页正确）
        if status == 'completed':
            query = query.filter(
                Tasks.result.isnot(None),
                text("tasks.result::text NOT IN ('{}', '[]', 'null', '\"\"')"),
                text("""(
                    tasks.result->>'files' IS NOT NULL OR
                    tasks.result->>'url' IS NOT NULL OR
                    tasks.result->>'urls' IS NOT NULL OR
                    tasks.result->>'imageUrls' IS NOT NULL OR
                    tasks.result->>'image_urls' IS NOT NULL OR
                    tasks.result->>'output' IS NOT NULL OR
                    tasks.result->>'outputs' IS NOT NULL OR
                    tasks.result->>'previewUrl' IS NOT NULL OR
                    tasks.result->>'preview_url' IS NOT NULL OR
                    tasks.result->>'thumbnailUrl' IS NOT NULL OR
                    tasks.result->>'thumbnail_url' IS NOT NULL OR
                    tasks.result->>'previewUrls' IS NOT NULL OR
                    tasks.result->>'thumbnailUrls' IS NOT NULL
                )""")
            )

        # 按 created_at 降序排列，限制返回数量
        return query.order_by(Tasks.created_at.desc()).limit(limit).all()

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
        update_data['updated_at'] = str(int(time.time() * 1000))

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
        status: Optional[str] = None,
        start_time: Optional[int] = None,
        end_time: Optional[int] = None
    ) -> int:
        """统计用户任务数量（使用时间范围筛选，自动过滤已删除的任务）

        Args:
            db: 数据库会话
            user_id: 用户ID
            status: 任务状态筛选（可选）
            start_time: 查询开始时间戳（毫秒，可选）
            end_time: 查询结束时间戳（毫秒，可选）

        Returns:
            任务数量
        """
        query = db.query(Tasks).filter(
            Tasks.user_id == user_id,
            Tasks.is_deleted == False
        )

        # 时间范围筛选（将时间戳转换为字符串比较）
        if start_time is not None:
            query = query.filter(Tasks.created_at >= str(start_time))
        if end_time is not None:
            query = query.filter(Tasks.created_at <= str(end_time))

        # 状态筛选
        if status:
            query = query.filter(Tasks.status == status)

        return query.count()

    def count_tasks_flexible(
        self,
        db: Session,
        user_id: Optional[str] = None,
        team_id: Optional[str] = None,
        status: Optional[str] = None,
        start_time: Optional[int] = None,
        end_time: Optional[int] = None,
        before_time: Optional[int] = None
    ) -> int:
        """灵活统计任务数量（支持按用户ID、团队ID或两者统计）

        Args:
            db: 数据库会话
            user_id: 用户ID（可选）
            team_id: 团队ID（可选）
            status: 任务状态筛选（可选）
            start_time: 查询开始时间戳（毫秒，可选）
            end_time: 查询结束时间戳（毫秒，可选）
            before_time: 游标分页，统计早于该时间戳的记录（毫秒，可选）

        Returns:
            任务数量

        查询规则：
            - 如果只提供 user_id（没有 team_id）：统计该用户的所有任务
            - 如果提供 team_id（不管有没有 user_id）：统计该团队的所有任务（包含团队所有成员的任务）
            - 如果既没有 user_id 也没有 team_id：返回 0
        """
        # 基础查询条件：自动过滤已删除的任务
        query = db.query(Tasks).filter(Tasks.is_deleted == False)

        # 查询逻辑：
        # - 如果提供了 team_id，统计整个团队的任务（不加 user_id 筛选）
        # - 如果只提供 user_id（没有 team_id），统计该用户的任务
        # - 如果两者都提供，统计团队任务（包含团队所有成员的任务）

        if team_id:
            # 团队任务：只返回该团队的任务，不限制 user_id
            query = query.filter(Tasks.team_id == team_id)
        else:
            # 个人任务：只返回该用户的任务，且 team_id 为空
            if user_id:
                query = query.filter(Tasks.user_id == user_id, Tasks.team_id == None)
            else:
                return 0

        # 时间范围筛选
        if start_time is not None:
            query = query.filter(Tasks.created_at >= str(start_time))
        if end_time is not None:
            query = query.filter(Tasks.created_at <= str(end_time))

        # before_time 游标分页
        if before_time is not None:
            query = query.filter(Tasks.created_at < str(before_time))

        # 状态筛选
        if status:
            query = query.filter(Tasks.status == status)

        # completed 任务必须有可展示媒体结果（SQL 层过滤，与 get_tasks_flexible 保持一致）
        if status == "completed":
            query = query.filter(
                Tasks.result.isnot(None),
                text("tasks.result::text NOT IN ('{}', '[]', 'null', '\"\"')"),
                text("""(
                    tasks.result->>'files' IS NOT NULL OR
                    tasks.result->>'url' IS NOT NULL OR
                    tasks.result->>'urls' IS NOT NULL OR
                    tasks.result->>'imageUrls' IS NOT NULL OR
                    tasks.result->>'image_urls' IS NOT NULL OR
                    tasks.result->>'output' IS NOT NULL OR
                    tasks.result->>'outputs' IS NOT NULL OR
                    tasks.result->>'previewUrl' IS NOT NULL OR
                    tasks.result->>'preview_url' IS NOT NULL OR
                    tasks.result->>'thumbnailUrl' IS NOT NULL OR
                    tasks.result->>'thumbnail_url' IS NOT NULL OR
                    tasks.result->>'previewUrls' IS NOT NULL OR
                    tasks.result->>'thumbnailUrls' IS NOT NULL
                )""")
            )

        return query.count()
