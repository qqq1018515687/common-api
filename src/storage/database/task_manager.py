"""任务管理接口"""

import logging

import time
from typing import Optional, List, Dict, Any
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session
from sqlalchemy import text, cast, String
import json

from storage.database.shared.model import Tasks, Users
from config.third_party_platforms import THIRD_PARTY_PLATFORMS
import time

状态筛选别名映射: Dict[str, List[str]] = {
    "completed": ["completed", "success", "succeeded"],
    "failed": ["failed", "error"],
    "running": ["running", "pending", "submitted", "processing", "in_progress"],
    "cancelled": ["cancelled", "canceled"],
}

logger = logging.getLogger(__name__)


class TaskCreate(BaseModel):
    """创建任务的输入"""

    id: str = Field(..., description="任务ID（前端生成的UUID）")
    user_id: str = Field(..., description="用户ID")
    team_id: Optional[str] = Field(default=None, description="团队ID")
    platform: str = Field(..., description="平台标识")
    platform_task_id: Optional[str] = Field(default=None, description="平台任务ID")
    type: str = Field(..., description="任务类型：image/video/audio")
    workflow_parameters: Optional[dict] = Field(default=None, description="工作流参数")
    parameter_snapshot: Optional[dict] = Field(default=None, description="完整参数快照")
    batch_id: Optional[str] = Field(default=None, description="批次ID")
    connection_mode: Optional[str] = Field(default="sse", description="连接模式")
    deduction_result: Optional[dict] = Field(default=None, description="扣费结果记录")


class TaskUpdate(BaseModel):
    """更新任务的输入"""

    status: Optional[str] = Field(default=None, description="任务状态")
    platform_task_id: Optional[str] = Field(default=None, description="平台任务ID")
    result: Optional[dict] = Field(default=None, description="生成结果")
    error: Optional[str] = Field(default=None, description="错误信息")
    completed_at: Optional[int] = Field(default=None, description="完成时间")
    failed_at: Optional[int] = Field(default=None, description="失败时间")
    cancelled_at: Optional[int] = Field(default=None, description="取消时间")
    status_updated_at: Optional[int] = Field(default=None, description="状态更新时间")
    started_at: Optional[int] = Field(
        default=None, description="任务真正开始执行时间(毫秒)"
    )
    workflow_parameters: Optional[dict] = Field(default=None, description="工作流参数")
    parameter_snapshot: Optional[dict] = Field(default=None, description="完整参数快照")
    connection_mode: Optional[str] = Field(default=None, description="连接模式")
    deduction_result: Optional[dict] = Field(default=None, description="扣费结果记录")
    elapsed_time_seconds: Optional[int] = Field(default=None, description="任务耗时秒数")
    user_friendly_message: Optional[str] = Field(
        default=None, description="LLM 生成的用户友好错误提示"
    )
    deleted_image_urls: Optional[List[str]] = Field(
        default=None, description="已删除的图片URL列表（图像级软删除）"
    )
    result_fallback: Optional[dict] = Field(default=None, description="结果转存失败时保留的原始回退结果")
    persistence_status: Optional[str] = Field(default=None, description="结果持久化状态：saving/saved/failed")
    persistence_error: Optional[str] = Field(default=None, description="结果持久化失败原因")
    confirmation_state: Optional[str] = Field(default=None, description="结果确认状态：none/pending/confirmed")


class TaskManager:
    """任务管理类"""

    _task_schema_checked = False
    _task_schema_lock = False

    @staticmethod
    def _pending_platform_task_id(task_id: str) -> str:
        return f"pending:{task_id}"

    @staticmethod
    def _is_real_platform_task_id(platform_task_id: Any) -> bool:
        if not isinstance(platform_task_id, str):
            return False
        task_id = platform_task_id.strip()
        return bool(task_id) and not task_id.startswith("pending:")

    @staticmethod
    def _should_use_platform_task_id_as_started_anchor(platform_task_id: Any) -> bool:
        if not TaskManager._is_real_platform_task_id(platform_task_id):
            return False
        if not isinstance(platform_task_id, str):
            return False
        task_id = platform_task_id.strip()
        return not task_id.startswith("tudou_sync:")

    @staticmethod
    def _has_displayable_result(result: Any) -> bool:
        if not isinstance(result, dict):
            return False

        for key in ("files", "imageUrls", "outputs"):
            value = result.get(key)
            if isinstance(value, list) and len(value) > 0:
                return True

        return False

    @staticmethod
    def _is_confirmation_pending(task: Tasks) -> bool:
        if getattr(task, "confirmation_state", None) == "pending":
            return True
        snapshot = task.parameter_snapshot if isinstance(task.parameter_snapshot, dict) else {}
        return snapshot.get("confirmationState") == "pending"

    @staticmethod
    def _contains_non_persisted_image_result(result: Any) -> bool:
        if not isinstance(result, dict):
            return False

        marker = "[data-url-pending-persist]"

        def has_bad_value(value: Any) -> bool:
            if isinstance(value, str):
                return value.startswith("data:image/") or value == marker
            if isinstance(value, list):
                return any(has_bad_value(item) for item in value)
            if isinstance(value, dict):
                return any(has_bad_value(item) for item in value.values())
            return False

        metadata = result.get("metadata") if isinstance(result.get("metadata"), dict) else {}
        return has_bad_value(result) or metadata.get("pendingPersist") is True

    @staticmethod
    def _is_completed_with_result(task: Tasks) -> bool:
        return task.status == "completed" and TaskManager._has_displayable_result(task.result)

    @staticmethod
    def _normalize_time_dimension(value: Optional[str]) -> str:
        normalized = (value or "created_at").strip().lower()
        if normalized in {"created_at", "completed_at", "failed_at", "cancelled_at", "status_updated_at"}:
            return normalized
        return "created_at"

    @classmethod
    def _resolve_effective_time_dimension(
        cls,
        status: Optional[str],
        statuses: Optional[List[str]],
        time_dimension: Optional[str],
    ) -> str:
        """统一解析本次查询实际使用的任务时间列，保证查询/排序/游标三处口径完全一致。

        规则：
        - 显式传入 status 视为单逻辑状态（statuses 仅作别名展开），尊重显式 time_dimension，
          否则按状态默认时间列（completed→completed_at / failed→failed_at / cancelled→cancelled_at）。
        - 未传 status：
          - 无 statuses：全量查询，跨状态时间列无统一语义，一律使用 created_at。
          - 单 statuses：视作单状态，尊重显式 time_dimension 或状态默认。
          - 多 statuses：跨状态查询，一律使用 created_at。
        """
        if status:
            primary = status.strip().lower()
        else:
            status_list = [s for s in (statuses or []) if s and s.strip()]
            if not status_list:
                return "created_at"
            distinct = {s.strip().lower() for s in status_list}
            if len(distinct) > 1:
                return "created_at"
            primary = next(iter(distinct))
        normalized = cls._normalize_time_dimension(time_dimension)
        if time_dimension:
            return normalized
        return {
            "completed": "completed_at",
            "failed": "failed_at",
            "cancelled": "cancelled_at",
        }.get(primary, "created_at")

    @staticmethod
    def _get_time_column(time_dimension: str):
        return getattr(Tasks, time_dimension)

    @staticmethod
    def _expand_statuses(status: Optional[str], statuses: Optional[List[str]]) -> List[str]:
        merged: List[str] = []
        for item in ([status] if status else []) + (statuses or []):
            normalized = (item or "").strip().lower()
            if not normalized:
                continue
            merged.extend(状态筛选别名映射.get(normalized, [normalized]))
        seen = set()
        result: List[str] = []
        for item in merged:
            if item not in seen:
                seen.add(item)
                result.append(item)
        return result

    @classmethod
    def _ensure_task_schema(cls, db: Session) -> None:
        """Ensure optional task columns exist before ORM queries select them."""
        if cls._task_schema_checked:
            return

        if cls._task_schema_lock:
            return

        cls._task_schema_lock = True

        try:
            db.execute(
                text(
                    "ALTER TABLE tasks ADD COLUMN IF NOT EXISTS deleted_image_urls JSON"
                )
            )
            db.execute(
                text(
                    "ALTER TABLE tasks ADD COLUMN IF NOT EXISTS started_at VARCHAR(20)"
                )
            )
            db.execute(
                text(
                    "ALTER TABLE tasks ADD COLUMN IF NOT EXISTS confirmation_state VARCHAR(20) DEFAULT 'none'"
                )
            )
            db.execute(
                text(
                    "ALTER TABLE tasks ADD COLUMN IF NOT EXISTS elapsed_time_seconds INTEGER DEFAULT 0"
                )
            )
            db.execute(
                text(
                    "ALTER TABLE tasks ADD COLUMN IF NOT EXISTS result_fallback JSON"
                )
            )
            db.execute(
                text(
                    "ALTER TABLE tasks ADD COLUMN IF NOT EXISTS failed_at VARCHAR(20)"
                )
            )
            db.execute(
                text(
                    "ALTER TABLE tasks ADD COLUMN IF NOT EXISTS cancelled_at VARCHAR(20)"
                )
            )
            db.execute(
                text(
                    "ALTER TABLE tasks ADD COLUMN IF NOT EXISTS status_updated_at VARCHAR(20)"
                )
            )
            db.execute(
                text(
                    "ALTER TABLE tasks ADD COLUMN IF NOT EXISTS persistence_status VARCHAR(20)"
                )
            )
            db.execute(
                text(
                    "ALTER TABLE tasks ADD COLUMN IF NOT EXISTS persistence_error TEXT"
                )
            )
            db.commit()
            cls._task_schema_checked = True
        except Exception:
            db.rollback()
            raise
        finally:
            cls._task_schema_lock = False

    @classmethod
    def reset_task_schema_cache(cls) -> None:
        cls._task_schema_checked = False

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
        self._ensure_task_schema(db)
        existing_task = self.get_task_by_id(db, task_in.id)
        if existing_task:
            task_data = task_in.model_dump(exclude_unset=True)
            current_time = str(int(time.time() * 1000))
            for field in [
                "platform_task_id",
                "workflow_parameters",
                "parameter_snapshot",
                "connection_mode",
                "deduction_result",
                "result_fallback",
                "persistence_status",
                "persistence_error",
                "team_id",
                "batch_id",
            ]:
                value = task_data.get(field)
                if value not in (None, "", {}) and hasattr(existing_task, field):
                    current_value = getattr(existing_task, field)
                    if current_value in (None, "", {}) or (
                        field == "platform_task_id"
                        and isinstance(current_value, str)
                        and current_value.startswith("pending:")
                    ):
                        setattr(existing_task, field, value)
                        if (
                            field == "platform_task_id"
                            and self._should_use_platform_task_id_as_started_anchor(value)
                            and not existing_task.started_at
                        ):
                            existing_task.started_at = current_time

            existing_task.updated_at = current_time
            existing_task.status_updated_at = existing_task.status_updated_at or current_time
            db.add(existing_task)
            try:
                db.commit()
                db.refresh(existing_task)
                return existing_task
            except Exception:
                db.rollback()
                raise

        current_time = str(int(time.time() * 1000))
        task_data = task_in.model_dump()
        if not task_data.get("platform_task_id"):
            task_data["platform_task_id"] = self._pending_platform_task_id(task_in.id)
        task_data["status"] = "running"
        task_data["created_at"] = current_time
        task_data["updated_at"] = current_time
        task_data["status_updated_at"] = current_time
        task_data["started_at"] = current_time
        task_data["completed_at"] = None
        task_data["failed_at"] = None
        task_data["cancelled_at"] = None

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
        self._ensure_task_schema(db)
        try:
            return db.query(Tasks).filter(Tasks.id == task_id).first()
        except Exception as exc:
            if "column tasks.started_at does not exist" not in str(exc):
                raise
            db.rollback()
            self.reset_task_schema_cache()
            self._ensure_task_schema(db)
            return db.query(Tasks).filter(Tasks.id == task_id).first()

    def get_tasks_by_user_id(
        self,
        db: Session,
        user_id: str,
        status: Optional[str] = None,
        start_time: Optional[int] = None,
        end_time: Optional[int] = None,
        limit: int = 100,
        **filters,
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
        self._ensure_task_schema(db)
        # 限制最大返回数量
        limit = min(limit, 500)

        query = db.query(Tasks).filter(
            Tasks.user_id == user_id, Tasks.is_deleted == False
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
        statuses: Optional[List[str]] = None,
        start_time: Optional[int] = None,
        end_time: Optional[int] = None,
        limit: int = 50,
        before_time: Optional[int] = None,
        before_id: Optional[str] = None,
        admin_full_list: bool = False,
        include_deleted: bool = False,
        platform: Optional[str] = None,
        keyword: Optional[str] = None,
        username: Optional[str] = None,
        workflow_keyword: Optional[str] = None,
        model_keyword: Optional[str] = None,
        time_dimension: Optional[str] = None,
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
            before_id: 游标分页（可选），配合 before_time 使用，解决同一毫秒多条任务被漏的问题
            admin_full_list: 管理员全量模式，跳过 user_id/team_id 筛选查全表
            include_deleted: 是否包含已删除（软删除）的任务，管理员统计场景使用

        Returns:
            任务列表（按 created_at DESC 排序），每个元素是 (Task, username) 元组

        查询规则：
            - 如果只提供 user_id（没有 team_id）：查询该用户的所有任务
            - 如果提供 team_id（不管有没有 user_id）：查询该团队的所有任务
            - 如果既没有 user_id 也没有 team_id 且不是 admin_full_list：返回空列表
        """
        self._ensure_task_schema(db)
        # 限制最大返回数量
        limit = min(limit, 1000)

        # 基础查询：JOIN Users 表，获取 username
        query = (
            db.query(Tasks, Users.username)
            .outerjoin(Users, Tasks.user_id == Users.user_id)
        )
        if not include_deleted:
            query = query.filter(Tasks.is_deleted == False)

        if team_id:
            query = query.filter(Tasks.team_id == team_id)
        elif user_id:
            query = query.filter(Tasks.user_id == user_id)
        elif not admin_full_list:
            return []

        expanded_statuses = self._expand_statuses(status, statuses)
        resolved_time_dimension = self._resolve_effective_time_dimension(status, statuses, time_dimension)
        time_column = self._get_time_column(resolved_time_dimension)
        if resolved_time_dimension != "created_at":
            query = query.filter(time_column.is_not(None))

        if platform:
            query = query.filter(Tasks.platform == platform)

        if keyword:
            from sqlalchemy import or_

            keyword_text = keyword.strip()
            if keyword_text:
                like_value = f"%{keyword_text}%"
                query = query.filter(or_(
                    Tasks.id.ilike(like_value),
                    Tasks.user_id.ilike(like_value),
                    Tasks.platform_task_id.ilike(like_value),
                    Users.username.ilike(like_value),
                ))

        if username:
            query = query.filter(Users.username.ilike(f"%{username.strip()}%"))

        if workflow_keyword:
            workflow_like = f"%{workflow_keyword.strip()}%"
            query = query.filter(cast(Tasks.parameter_snapshot, String).ilike(workflow_like))

        if model_keyword:
            model_like = f"%{model_keyword.strip()}%"
            query = query.filter(or_(
                cast(Tasks.parameter_snapshot, String).ilike(model_like),
                cast(Tasks.workflow_parameters, String).ilike(model_like),
            ))

        if start_time is not None:
            query = query.filter(time_column >= str(start_time))
        if end_time is not None:
            query = query.filter(time_column <= str(end_time))

        from sqlalchemy import and_, or_
        if before_time is not None and before_id is not None:
            query = query.filter(or_(
                time_column < str(before_time),
                and_(time_column == str(before_time), Tasks.id < str(before_id))
            ))
        elif before_time is not None:
            query = query.filter(time_column < str(before_time))

        if expanded_statuses:
            query = query.filter(Tasks.status.in_(expanded_statuses))

        return query.order_by(time_column.desc(), Tasks.id.desc()).limit(limit).all()

    def get_admin_tasks_compact(
        self,
        db: Session,
        status: Optional[str] = None,
        statuses: Optional[List[str]] = None,
        start_time: Optional[int] = None,
        end_time: Optional[int] = None,
        limit: int = 50,
        before_time: Optional[int] = None,
        before_id: Optional[str] = None,
        include_deleted: bool = False,
        platform: Optional[str] = None,
        keyword: Optional[str] = None,
        username: Optional[str] = None,
        workflow_keyword: Optional[str] = None,
        model_keyword: Optional[str] = None,
        time_dimension: Optional[str] = None,
    ) -> List[Dict[str, Any]]:
        """管理后台任务轻量列表，只读取列表渲染需要的字段。"""
        self._ensure_task_schema(db)
        limit = min(max(limit, 1), 100)

        query = (
            db.query(
                Tasks.id,
                Tasks.user_id,
                Users.username,
                Tasks.team_id,
                Tasks.platform,
                Tasks.platform_task_id,
                Tasks.type,
                Tasks.status,
                Tasks.workflow_parameters,
                Tasks.parameter_snapshot,
                Tasks.result,
                Tasks.error,
                Tasks.confirmation_state,
                Tasks.user_friendly_message,
                Tasks.created_at,
                Tasks.started_at,
                Tasks.completed_at,
                Tasks.failed_at,
                Tasks.cancelled_at,
                Tasks.status_updated_at,
                Tasks.elapsed_time_seconds,
                Tasks.deduction_result,
                Tasks.connection_mode,
                Tasks.is_deleted,
            )
            .outerjoin(Users, Tasks.user_id == Users.user_id)
        )
        if not include_deleted:
            query = query.filter(Tasks.is_deleted == False)

        expanded_statuses = self._expand_statuses(status, statuses)
        resolved_time_dimension = self._resolve_effective_time_dimension(status, statuses, time_dimension)
        time_column = self._get_time_column(resolved_time_dimension)
        if resolved_time_dimension != "created_at":
            query = query.filter(time_column.is_not(None))

        if platform:
            query = query.filter(Tasks.platform == platform)

        if keyword:
            from sqlalchemy import or_

            keyword_text = keyword.strip()
            if keyword_text:
                like_value = f"%{keyword_text}%"
                query = query.filter(or_(
                    Tasks.id.ilike(like_value),
                    Tasks.user_id.ilike(like_value),
                    Tasks.platform_task_id.ilike(like_value),
                    Users.username.ilike(like_value),
                ))

        if username:
            query = query.filter(Users.username.ilike(f"%{username.strip()}%"))

        if workflow_keyword:
            workflow_like = f"%{workflow_keyword.strip()}%"
            query = query.filter(cast(Tasks.parameter_snapshot, String).ilike(workflow_like))

        if model_keyword:
            model_like = f"%{model_keyword.strip()}%"
            query = query.filter(or_(
                cast(Tasks.parameter_snapshot, String).ilike(model_like),
                cast(Tasks.workflow_parameters, String).ilike(model_like),
            ))

        if start_time is not None:
            query = query.filter(time_column >= str(start_time))
        if end_time is not None:
            query = query.filter(time_column <= str(end_time))

        from sqlalchemy import and_, or_
        if before_time is not None and before_id is not None:
            query = query.filter(or_(
                time_column < str(before_time),
                and_(time_column == str(before_time), Tasks.id < str(before_id))
            ))
        elif before_time is not None:
            query = query.filter(time_column < str(before_time))
        if expanded_statuses:
            query = query.filter(Tasks.status.in_(expanded_statuses))

        rows = query.order_by(time_column.desc(), Tasks.id.desc()).limit(limit + 1).all()
        tasks: List[Dict[str, Any]] = []

        for row in rows:
            parameter_snapshot = row.parameter_snapshot if isinstance(row.parameter_snapshot, dict) else {}
            workflow_parameters = row.workflow_parameters if isinstance(row.workflow_parameters, dict) else {}
            result = row.result if isinstance(row.result, dict) else None

            tasks.append({
                "id": row.id,
                "user_id": row.user_id,
                "username": row.username,
                "team_id": row.team_id,
                "platform": row.platform,
                "platform_task_id": row.platform_task_id,
                "type": row.type,
                "status": row.status,
                "workflow_parameters": self._compact_large_base64_fields(workflow_parameters),
                "parameter_snapshot": self._compact_large_base64_fields(parameter_snapshot),
                "confirmation_state": row.confirmation_state or "none",
                "result": self._compact_result(result),
                "error": row.error,
                "user_friendly_message": row.user_friendly_message,
                "created_at": row.created_at,
                "started_at": row.started_at,
                "completed_at": row.completed_at,
                "failed_at": row.failed_at,
                "cancelled_at": row.cancelled_at,
                "status_updated_at": row.status_updated_at,
                "elapsed_time_seconds": row.elapsed_time_seconds,
                "deduction_result": row.deduction_result,
                "connection_mode": row.connection_mode,
                "is_deleted": bool(row.is_deleted),
            })

        return tasks

    def _compact_large_base64_fields(self, value: Any) -> Any:
        """递归截断超长 base64 dataURL 字符串，其余字段保持完整。

        管理后台列表/总览接口需返回用户填写的完整暴露参数（prompt、上传图、比例等）
        供排查使用；仅对个别本地链路产生的超大 base64 图片串做截断，防止拖垮列表 payload。
        """
        if isinstance(value, dict):
            return {key: self._compact_large_base64_fields(item) for key, item in value.items()}
        if isinstance(value, list):
            return [self._compact_large_base64_fields(item) for item in value]
        if isinstance(value, str) and value.startswith("data:image/") and len(value) > 4000:
            return f"{value[:120]}...[base64 已截断，原 {len(value)} 字符]"
        return value

    def _compact_result(self, result: Optional[Dict[str, Any]]) -> Optional[Dict[str, Any]]:
        if not result:
            return None

        compact: Dict[str, Any] = {}
        files = result.get("files")
        if isinstance(files, list):
            compact_files = []
            for item in files:
                if isinstance(item, dict):
                    url = item.get("url") or item.get("file_url")
                    if url:
                        compact_files.append({"url": url, "file_url": item.get("file_url")})
            if compact_files:
                compact["files"] = compact_files

        image_urls = result.get("imageUrls")
        if isinstance(image_urls, list):
            compact["imageUrls"] = [url for url in image_urls if isinstance(url, str)]

        for key in ("videoUrl", "audioUrl", "image_url"):
            if isinstance(result.get(key), str):
                compact[key] = result.get(key)

        images = result.get("images")
        if isinstance(images, list):
            compact_images = []
            for image in images:
                if isinstance(image, dict) and image.get("url"):
                    compact_images.append({"url": image.get("url")})
            if compact_images:
                compact["images"] = compact_images

        return compact or None

    def get_task_by_platform_task_id(
        self, db: Session, platform: str, platform_task_id: str
    ) -> Optional[Tasks]:
        """根据平台和平台任务ID获取任务"""
        self._ensure_task_schema(db)
        if not platform_task_id:
            return None
        return (
            db.query(Tasks)
            .filter(
                Tasks.platform == platform, Tasks.platform_task_id == platform_task_id
            )
            .first()
        )

    def get_task_by_platform_task_id_flexible(
        self, db: Session, platform_task_id: str
    ) -> Optional[Tasks]:
        """仅根据平台任务ID获取任务（不限制平台，按 updated_at 降序返回最新一条）"""
        self._ensure_task_schema(db)
        if not platform_task_id:
            return None
        return (
            db.query(Tasks)
            .filter(Tasks.platform_task_id == platform_task_id)
            .order_by(Tasks.updated_at.desc())
            .first()
        )

    def list_pending_third_party_tasks(
        self,
        db: Session,
        *,
        limit: int = 100,
        older_than_ms: int = 0,
    ) -> List[Tasks]:
        """查询需要后端继续补偿的第三方运行中任务。"""
        self._ensure_task_schema(db)
        limit = min(max(limit, 1), 500)

        query = db.query(Tasks).filter(
            Tasks.is_deleted == False,
            Tasks.platform.in_(set(THIRD_PARTY_PLATFORMS)),
            Tasks.status == "running",
            Tasks.platform_task_id.isnot(None),
            Tasks.platform_task_id != "",
        )

        if older_than_ms > 0:
            cutoff = str(int(time.time() * 1000) - older_than_ms)
            query = query.filter(Tasks.updated_at <= cutoff)

        return query.order_by(Tasks.updated_at.asc()).limit(limit).all()

    def list_stale_running_tasks(
        self,
        db: Session,
        *,
        stale_for_ms: int = 0,
        limit: int = 50,
    ) -> List[Dict[str, Any]]:
        """列出长期未更新的运行中任务，供主流程后端兜底补偿收尾。

        Args:
            db: 数据库会话
            stale_for_ms: 超过该时长(毫秒)未更新的 running 任务；0 表示不限定时长
            limit: 返回上限（1~200）

        Returns:
            精简后的任务列表（含 id/user_id/platform/platform_task_id/快照/扣费记录），
            避免把 workflow_parameters 等大字段全量带出。
        """
        self._ensure_task_schema(db)
        limit = min(max(limit, 1), 200)

        query = db.query(Tasks).filter(
            Tasks.is_deleted == False,
            Tasks.status == "running",
        )
        if stale_for_ms > 0:
            cutoff = str(int(time.time() * 1000) - stale_for_ms)
            query = query.filter(Tasks.updated_at <= cutoff)

        rows = query.order_by(Tasks.updated_at.asc()).limit(limit).all()
        result: List[Dict[str, Any]] = []
        for task in rows:
            snapshot = task.parameter_snapshot if isinstance(task.parameter_snapshot, dict) else {}
            deduction = task.deduction_result if isinstance(task.deduction_result, dict) else None
            # 超大 result（如未转存的 base64 原图）不随补偿列表传出，避免超大响应；
            # 同时这类结果本就无法按“成功”收尾（common 守卫禁止带未转存图片的 completed）。
            results_payload = None
            if task.result is not None:
                try:
                    if len(json.dumps(task.result, ensure_ascii=False)) <= 100_000:
                        results_payload = task.result
                except (TypeError, ValueError):
                    results_payload = None
            result.append({
                "id": task.id,
                "user_id": task.user_id,
                "platform": task.platform,
                "platform_task_id": task.platform_task_id,
                "status": task.status,
                "updated_at": task.updated_at,
                "completed_at": task.completed_at,
                "confirmation_state": getattr(task, "confirmation_state", None),
                "parameter_snapshot": snapshot,
                "deduction_result": deduction,
                "result": results_payload,
            })
        return result

    def calculate_elapsed_time(self, task: Tasks) -> int:
        """
        【共享函数】统一计算任务耗时(秒)

        计算逻辑:
        1. 如果有 started_at 和 completed_at: elapsed = (completed_at - started_at) / 1000
        2. 如果没有 started_at,用 created_at 兜底: elapsed = (completed_at - created_at) / 1000
        3. 如果 completed_at 为空或任务未完成: 返回 0

        异常处理:
        - 负数或无效值返回 0
        - 超大值(>24小时=86400秒)截断到 86400

        Args:
            task: 任务对象

        Returns:
            耗时秒数(int),范围 0~86400
        """
        if not task.completed_at:
            return 0

        try:
            completed = int(task.completed_at)
            started = int(task.started_at) if task.started_at else int(task.created_at)

            elapsed_ms = completed - started
            elapsed_seconds = elapsed_ms // 1000

            # 异常值校验
            if elapsed_seconds < 0:
                return 0
            if elapsed_seconds > 86400:  # 超过24小时,截断
                elapsed_seconds = 86400

            return elapsed_seconds
        except (ValueError, TypeError):
            return 0

    def update_task(
        self, db: Session, task_id: str, task_in: TaskUpdate
    ) -> Optional[Tasks]:
        """更新任务"""
        db_task = self.get_task_by_id(db, task_id)
        if not db_task:
            return None

        update_data = task_in.model_dump(exclude_unset=True)

        # 【守卫】已取消/已删除任务是终态语义，禁止被状态回写覆盖为 failed/running，
        # 避免用户取消成功后 main 残留轮询 807（任务已不存在）把任务改成 failed。
        incoming_status = update_data.get("status")
        now_ms = str(int(time.time() * 1000))
        if db_task.status == "cancelled" or db_task.is_deleted:
            if incoming_status in ("failed", "running"):
                logger.info(
                    "[task-guard] 已取消/已删除任务拒绝被覆盖为 %s: task_id=%s",
                    incoming_status,
                    task_id,
                )
                update_data.pop("status", None)
                update_data.pop("error", None)
                update_data.pop("user_friendly_message", None)
                update_data.pop("completed_at", None)
                incoming_status = None

        if "elapsed_time_seconds" in update_data:
            elapsed_time_seconds = update_data.get("elapsed_time_seconds")
            if not isinstance(elapsed_time_seconds, int) or elapsed_time_seconds < 0:
                update_data.pop("elapsed_time_seconds", None)
            elif elapsed_time_seconds > 86400:
                update_data["elapsed_time_seconds"] = 86400

        if self._is_completed_with_result(db_task):
            incoming_status = update_data.get("status")
            if incoming_status in ("failed", "cancelled"):
                update_data.pop("status", None)
                update_data.pop("error", None)
                update_data.pop("user_friendly_message", None)
                update_data.pop("completed_at", None)

            if incoming_status == "completed":
                update_data.pop("completed_at", None)

        if self._is_confirmation_pending(db_task):
            incoming_status = update_data.get("status")
            incoming_result = update_data.get("result")
            # 明确失败（带非空 error 的原因）应允许收敛为 failed；
            # 只有“无错误原因的无结果失败”才视为仍需待确认，回退为 running + pending
            incoming_error = str(update_data.get("error") or "").strip()
            if (
                incoming_status == "failed"
                and not self._has_displayable_result(incoming_result)
                and not incoming_error
            ):
                update_data["status"] = "running"
                merged_snapshot = dict(db_task.parameter_snapshot or {})
                merged_snapshot["confirmationState"] = "pending"
                update_data["parameter_snapshot"] = merged_snapshot
                update_data["confirmation_state"] = "pending"
                update_data["completed_at"] = None

        if update_data.get("status") in ("completed", "failed", "cancelled") and "confirmation_state" not in update_data:
            update_data["confirmation_state"] = "confirmed"

        if (
            update_data.get("status") == "completed"
            and self._has_displayable_result(update_data.get("result"))
        ):
            if self._contains_non_persisted_image_result(update_data.get("result")):
                raise ValueError("completed 任务结果仍包含未转存图片，拒绝写库")
            update_data["error"] = None
            update_data["user_friendly_message"] = None
            if db_task.completed_at:
                update_data.pop("completed_at", None)

        if (
            self._should_use_platform_task_id_as_started_anchor(update_data.get("platform_task_id"))
            and not db_task.started_at
            and "started_at" not in update_data
        ):
            update_data["started_at"] = now_ms

        next_status = update_data.get("status")
        if next_status and next_status != db_task.status:
            update_data["status_updated_at"] = now_ms

        # 【终态时间一致性，无条件维护】无论状态是否变化，只要本轮落成的终态是
        # completed/failed/cancelled，都保证对应时间列已写入、其余终态时间列清空；
        # running/pending 则清空全部终态时间列。
        # 历史 bug：同一状态重复提交（如失败后再次回写 failed）漏写 failed_at/cancelled_at，
        # 导致管理后台"统计按 created_at 有数、按 failed_at 列表为空"。现改为按终态无条件维护，
        # 与 a5b6c7d8e9f0 数据回填迁移保持一致。
        if next_status == "completed":
            if db_task.completed_at:
                update_data.pop("completed_at", None)
            else:
                update_data.setdefault("completed_at", now_ms)
            update_data["failed_at"] = None
            update_data["cancelled_at"] = None
        elif next_status == "failed":
            update_data.setdefault("failed_at", now_ms)
            update_data["completed_at"] = None
            update_data["cancelled_at"] = None
        elif next_status == "cancelled":
            update_data.setdefault("cancelled_at", now_ms)
            update_data["completed_at"] = None
            update_data["failed_at"] = None
        elif next_status in ("pending", "running"):
            update_data["completed_at"] = None
            update_data["failed_at"] = None
            update_data["cancelled_at"] = None

        update_data["updated_at"] = now_ms

        for field, value in update_data.items():
            if hasattr(db_task, field):
                setattr(db_task, field, value)

        # 【新增】如果任务完成,自动计算耗时并写入 elapsed_time_seconds
        if "completed_at" in update_data and update_data["completed_at"] and "elapsed_time_seconds" not in update_data:
            elapsed_seconds = self.calculate_elapsed_time(db_task)
            db_task.elapsed_time_seconds = elapsed_seconds

        db.add(db_task)
        try:
            db.commit()
            db.refresh(db_task)
            return db_task
        except Exception:
            db.rollback()
            raise

    def force_fail_third_party_task(
        self,
        db: Session,
        task_id: str,
        *,
        error: str = "",
        user_friendly_message: str = "",
    ) -> Optional[Tasks]:
        """强制终态化第三方渠道卡住任务（绕过 confirmation_state=pending 守卫）。

        背景：main 轮询超时/瞬时错误时会把任务标为 running + confirmation_state=pending
        （“结果确认中”），而 common 的 update_task 对 pending 任务拒绝对无结果失败，
        导致任务永远无法收敛。本方法供补偿线程对超时任务直接置失败，不走 update_task。
        """
        db_task = self.get_task_by_id(db, task_id)
        if not db_task:
            return None

        # 【守卫】已取消/已删除任务是终态语义，补偿线程不得将其覆盖为 failed。
        # 必须返回 None：调用方以“返回值非空才继续退款/收尾”判定，返回 db_task 会误触发退款。
        if db_task.status == "cancelled" or db_task.is_deleted:
            logger.info(
                "[task-guard] 已取消/已删除任务跳过强制失败: task_id=%s",
                task_id,
            )
            return None

        db_task.status = "failed"
        db_task.confirmation_state = "confirmed"
        db_task.error = error or "任务处理超时，已强制结束"
        if user_friendly_message:
            db_task.user_friendly_message = user_friendly_message
        now_ms = str(int(time.time() * 1000))
        db_task.failed_at = db_task.failed_at or now_ms
        db_task.completed_at = None
        db_task.cancelled_at = None
        db_task.status_updated_at = now_ms
        db_task.updated_at = now_ms

        try:
            db.add(db_task)
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
        if user.role != "admin" and db_task.user_id != user_id:
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
        deleted_count = (
            db.query(Tasks)
            .filter(Tasks.user_id == user_id)
            .delete(synchronize_session=False)
        )
        db.commit()
        return deleted_count

    def count_tasks_by_user_id(
        self,
        db: Session,
        user_id: str,
        status: Optional[str] = None,
        start_time: Optional[int] = None,
        end_time: Optional[int] = None,
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
        self._ensure_task_schema(db)
        query = db.query(Tasks).filter(
            Tasks.user_id == user_id, Tasks.is_deleted == False
        )

        # 时间范围筛选（将时间戳转换为字符串比较）
        if start_time is not None:
            query = query.filter(Tasks.created_at >= str(start_time))
        if end_time is not None:
            query = query.filter(Tasks.created_at <= str(end_time))

        # 状态筛选
        if status:
            query = query.filter(Tasks.status == status)

        # 游标分页：统计早于该时间戳的记录
        if before_time is not None:
            query = query.filter(Tasks.created_at < str(before_time))

        return query.count()

    def count_tasks_with_media(
        self,
        db: Session,
        user_id: Optional[str] = None,
        team_id: Optional[str] = None,
        start_time: Optional[int] = None,
        end_time: Optional[int] = None,
        before_time: Optional[int] = None,
        include_deleted: bool = False,
        platform: Optional[str] = None,
        keyword: Optional[str] = None,
        username: Optional[str] = None,
        workflow_keyword: Optional[str] = None,
        model_keyword: Optional[str] = None,
        time_dimension: Optional[str] = None,
    ) -> int:
        """统计有可展示媒体结果的 completed 任务数量（与前端展示逻辑一致）"""
        self._ensure_task_schema(db)
        from sqlalchemy import func, text

        query = db.query(Tasks).outerjoin(Users, Tasks.user_id == Users.user_id).filter(Tasks.status == "completed")
        if not include_deleted:
            query = query.filter(Tasks.is_deleted == False)

        # 用户/团队筛选
        if team_id:
            query = query.filter(Tasks.team_id == team_id)
        elif user_id:
            query = query.filter(Tasks.user_id == user_id)
        else:
            return 0

        resolved_time_dimension = self._resolve_effective_time_dimension('completed', None, time_dimension)
        time_column = self._get_time_column(resolved_time_dimension)
        if resolved_time_dimension != 'created_at':
            query = query.filter(time_column.is_not(None))

        if platform:
            query = query.filter(Tasks.platform == platform)

        if keyword:
            from sqlalchemy import or_
            like_value = f"%{keyword.strip()}%"
            query = query.filter(or_(
                Tasks.id.ilike(like_value),
                Tasks.user_id.ilike(like_value),
                Tasks.platform_task_id.ilike(like_value),
                Users.username.ilike(like_value),
            ))

        if username:
            query = query.filter(Users.username.ilike(f"%{username.strip()}%"))

        if workflow_keyword:
            query = query.filter(cast(Tasks.parameter_snapshot, String).ilike(f"%{workflow_keyword.strip()}%"))

        if model_keyword:
            model_like = f"%{model_keyword.strip()}%"
            from sqlalchemy import or_
            query = query.filter(or_(
                cast(Tasks.parameter_snapshot, String).ilike(model_like),
                cast(Tasks.workflow_parameters, String).ilike(model_like),
            ))

        if start_time is not None:
            query = query.filter(time_column >= str(start_time))
        if end_time is not None:
            query = query.filter(time_column <= str(end_time))

        # 游标分页：统计早于该时间戳的记录
        if before_time is not None:
            query = query.filter(time_column < str(before_time))

        # 媒体结果过滤：result IS NOT NULL 且 result 包含可展示的媒体 URL
        # 使用 PostgreSQL JSON 查询，匹配以下任一条件：
        # 1. result->'files' 是非空数组
        # 2. result->'images' 是非空数组
        # 3. result 有 url/image_url/video_url/audio_url/thumbnailUrl/previewUrl/thumbnail_url/preview_url 键
        media_filter = text("""
            (result IS NOT NULL
             AND CAST(result AS text) != 'null'
             AND CAST(result AS text) != '{}'
             AND (
                 (result::jsonb->'files' IS NOT NULL AND jsonb_array_length(result::jsonb->'files') > 0)
                 OR (result::jsonb->'images' IS NOT NULL AND jsonb_array_length(result::jsonb->'images') > 0)
                 OR result::jsonb?'url' OR result::jsonb?'image_url' OR result::jsonb?'video_url' OR result::jsonb?'audio_url'
                 OR result::jsonb?'thumbnailUrl' OR result::jsonb?'previewUrl' OR result::jsonb?'thumbnail_url' OR result::jsonb?'preview_url'
             ))
        """)
        query = query.filter(media_filter)

        return query.count()

    def count_tasks_flexible(
        self,
        db: Session,
        user_id: Optional[str] = None,
        team_id: Optional[str] = None,
        status: Optional[str] = None,
        statuses: Optional[List[str]] = None,
        start_time: Optional[int] = None,
        end_time: Optional[int] = None,
        before_time: Optional[int] = None,
        admin_full_list: bool = False,
        include_deleted: bool = False,
        platform: Optional[str] = None,
        keyword: Optional[str] = None,
        username: Optional[str] = None,
        workflow_keyword: Optional[str] = None,
        model_keyword: Optional[str] = None,
        time_dimension: Optional[str] = None,
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
            admin_full_list: 管理员全量模式，跳过 user_id/team_id 筛选查全表
            include_deleted: 是否包含已删除（软删除）的任务，管理员统计场景使用

        Returns:
            任务数量

        查询规则：
            - 如果只提供 user_id（没有 team_id）：统计该用户的所有任务
            - 如果提供 team_id（不管有没有 user_id）：统计该团队的所有任务（包含团队所有成员的任务）
            - 如果既没有 user_id 也没有 team_id 且不是 admin_full_list：返回 0
        """
        self._ensure_task_schema(db)
        query = db.query(Tasks).outerjoin(Users, Tasks.user_id == Users.user_id)
        if not include_deleted:
            query = query.filter(Tasks.is_deleted == False)

        if team_id:
            query = query.filter(Tasks.team_id == team_id)
        elif user_id:
            query = query.filter(Tasks.user_id == user_id)
        elif not admin_full_list:
            return 0

        expanded_statuses = self._expand_statuses(status, statuses)
        resolved_time_dimension = self._resolve_effective_time_dimension(status, statuses, time_dimension)
        time_column = self._get_time_column(resolved_time_dimension)
        if resolved_time_dimension != "created_at":
            query = query.filter(time_column.is_not(None))

        if platform:
            query = query.filter(Tasks.platform == platform)

        if keyword:
            from sqlalchemy import or_

            keyword_text = keyword.strip()
            if keyword_text:
                like_value = f"%{keyword_text}%"
                query = query.filter(or_(
                    Tasks.id.ilike(like_value),
                    Tasks.user_id.ilike(like_value),
                    Tasks.platform_task_id.ilike(like_value),
                    Users.username.ilike(like_value),
                ))

        if username:
            query = query.filter(Users.username.ilike(f"%{username.strip()}%"))

        if workflow_keyword:
            query = query.filter(cast(Tasks.parameter_snapshot, String).ilike(f"%{workflow_keyword.strip()}%"))

        if model_keyword:
            model_like = f"%{model_keyword.strip()}%"
            query = query.filter(or_(
                cast(Tasks.parameter_snapshot, String).ilike(model_like),
                cast(Tasks.workflow_parameters, String).ilike(model_like),
            ))

        if start_time is not None:
            query = query.filter(time_column >= str(start_time))
        if end_time is not None:
            query = query.filter(time_column <= str(end_time))

        if before_time is not None:
            query = query.filter(time_column < str(before_time))

        if expanded_statuses:
            query = query.filter(Tasks.status.in_(expanded_statuses))

        return query.count()

    def count_tasks_stats(
        self,
        db: Session,
        start_time: Optional[int] = None,
        end_time: Optional[int] = None,
        admin_full_list: bool = False,
        include_deleted: bool = False,
        platform: Optional[str] = None,
        keyword: Optional[str] = None,
        username: Optional[str] = None,
        workflow_keyword: Optional[str] = None,
        model_keyword: Optional[str] = None,
        time_dimension: Optional[str] = None,
    ) -> dict:
        """按状态分组统计任务数量（支持 admin 全表模式）

        Args:
            db: 数据库会话
            start_time: 查询开始时间戳（毫秒，可选）
            end_time: 查询结束时间戳（毫秒，可选）
            admin_full_list: 管理员全量模式，跳过 user_id/team_id 筛选查全表
            include_deleted: 是否包含已删除（软删除）的任务，管理员统计场景使用

        Returns:
            { status: count, ... } 包含 total 汇总字段
        """
        self._ensure_task_schema(db)
        from sqlalchemy import func

        if not time_dimension:
            total = self.count_tasks_flexible(
                db,
                start_time=start_time,
                end_time=end_time,
                admin_full_list=admin_full_list,
                include_deleted=include_deleted,
                platform=platform,
                keyword=keyword,
                username=username,
                workflow_keyword=workflow_keyword,
                model_keyword=model_keyword,
                time_dimension='created_at',
            )
            completed = self.count_tasks_with_media(
                db,
                start_time=start_time,
                end_time=end_time,
                include_deleted=include_deleted,
                platform=platform,
                keyword=keyword,
                username=username,
                workflow_keyword=workflow_keyword,
                model_keyword=model_keyword,
                time_dimension='completed_at',
            )
            failed = self.count_tasks_flexible(
                db,
                status='failed',
                start_time=start_time,
                end_time=end_time,
                admin_full_list=admin_full_list,
                include_deleted=include_deleted,
                platform=platform,
                keyword=keyword,
                username=username,
                workflow_keyword=workflow_keyword,
                model_keyword=model_keyword,
                time_dimension='failed_at',
            )
            cancelled = self.count_tasks_flexible(
                db,
                status='cancelled',
                start_time=start_time,
                end_time=end_time,
                admin_full_list=admin_full_list,
                include_deleted=include_deleted,
                platform=platform,
                keyword=keyword,
                username=username,
                workflow_keyword=workflow_keyword,
                model_keyword=model_keyword,
                time_dimension='cancelled_at',
            )
            running = sum(
                self.count_tasks_flexible(
                    db,
                    status=status,
                    start_time=start_time,
                    end_time=end_time,
                    admin_full_list=admin_full_list,
                    include_deleted=include_deleted,
                    platform=platform,
                    keyword=keyword,
                    username=username,
                    workflow_keyword=workflow_keyword,
                    model_keyword=model_keyword,
                    time_dimension='created_at',
                )
                for status in ('running', 'pending', 'submitted', 'processing', 'in_progress')
            )
            return {
                'total': total,
                'completed': completed,
                'failed': failed,
                'cancelled': cancelled,
                'running': running,
            }

        query = db.query(Tasks.status, func.count(Tasks.id)).outerjoin(Users, Tasks.user_id == Users.user_id)
        if not include_deleted:
            query = query.filter(Tasks.is_deleted == False)

        resolved_time_dimension = self._normalize_time_dimension(time_dimension)
        time_column = self._get_time_column(resolved_time_dimension)
        if resolved_time_dimension != "created_at":
            query = query.filter(time_column.is_not(None))

        if platform:
            query = query.filter(Tasks.platform == platform)

        if keyword:
            from sqlalchemy import or_

            keyword_text = keyword.strip()
            if keyword_text:
                like_value = f"%{keyword_text}%"
                query = query.filter(or_(
                    Tasks.id.ilike(like_value),
                    Tasks.user_id.ilike(like_value),
                    Tasks.platform_task_id.ilike(like_value),
                    Users.username.ilike(like_value),
                ))

        if username:
            query = query.filter(Users.username.ilike(f"%{username.strip()}%"))

        if workflow_keyword:
            query = query.filter(cast(Tasks.parameter_snapshot, String).ilike(f"%{workflow_keyword.strip()}%"))

        if model_keyword:
            model_like = f"%{model_keyword.strip()}%"
            query = query.filter(or_(
                cast(Tasks.parameter_snapshot, String).ilike(model_like),
                cast(Tasks.workflow_parameters, String).ilike(model_like),
            ))

        if start_time is not None:
            query = query.filter(time_column >= str(start_time))
        if end_time is not None:
            query = query.filter(time_column <= str(end_time))

        query = query.group_by(Tasks.status)

        rows = query.all()
        stats = {status: count for status, count in rows}
        stats["total"] = sum(stats.values())
        return stats

    def list_local_comfyui_queue_snapshot(
        self,
        db: Session,
        task_id: Optional[str] = None,
    ) -> dict:
        """获取局域网 ComfyUI 任务的实时队列位置快照。

        Args:
            db: 数据库会话
            task_id: 可选，指定某个任务时仅返回该任务的排队信息

        Returns:
            按 created_at 升序排列的所有排队/执行中的 local_comfyui 任务，
            每个任务带 position（1 起）与 ahead（前方数量）。
            running 任务一并计入队列（天然兼容串行执行时仅 1 个 running，
            以及多实例/重启等瞬间可能出现多个 running 的边界）。
        """
        self._ensure_task_schema(db)

        query = (
            db.query(Tasks)
            .filter(
                Tasks.platform == "local_comfyui",
                Tasks.is_deleted == False,
                Tasks.status.in_(["queued", "running"]),
            )
            .order_by(Tasks.created_at.asc())
        )

        rows = query.all()
        entries = []
        for index, task in enumerate(rows):
            entry = {
                "job_id": task.id,
                "status": task.status,
                "position": index + 1,
                "ahead": index,
            }
            if task_id is not None and task.id == task_id:
                target = entry
            entries.append(entry)

        result = {"queue": entries, "running_count": 0, "queued_count": 0, "total": len(entries)}
        for entry in entries:
            if entry["status"] == "running":
                result["running_count"] += 1
            elif entry["status"] == "queued":
                result["queued_count"] += 1

        if task_id is not None:
            result["task"] = target if "target" in locals() else None

        return result
