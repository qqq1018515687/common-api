from coze_coding_dev_sdk.database import Base

from sqlalchemy import BigInteger, Boolean, DateTime, Index, Integer, JSON, PrimaryKeyConstraint, String, Text, UniqueConstraint, text
from typing import Optional
import datetime

from sqlalchemy.orm import Mapped, mapped_column

class RateLimits(Base):
    __tablename__ = 'rate_limits'
    __table_args__ = (
        PrimaryKeyConstraint('record_id', name='rate_limits_pkey'),
        Index('ix_rate_limits_is_blocked', 'is_blocked'),
        Index('ix_rate_limits_last_request_at', 'last_request_at'),
        Index('ix_rate_limits_phone_ip_address', 'phone', 'ip_address')
    )

    record_id: Mapped[str] = mapped_column(String(64), primary_key=True, comment='记录唯一标识')
    phone: Mapped[str] = mapped_column(String(11), nullable=False, comment='手机号')
    ip_address: Mapped[str] = mapped_column(String(64), nullable=False, comment='IP 地址')
    request_count: Mapped[int] = mapped_column(Integer, nullable=False, server_default=text('1'), comment='请求次数')
    first_request_at: Mapped[datetime.datetime] = mapped_column(DateTime(True), nullable=False, server_default=text('now()'), comment='首次请求时间')
    last_request_at: Mapped[datetime.datetime] = mapped_column(DateTime(True), nullable=False, server_default=text('now()'), comment='最后请求时间')
    is_blocked: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default=text('false'), comment='是否封禁')
    created_at: Mapped[datetime.datetime] = mapped_column(DateTime(True), nullable=False, server_default=text('now()'), comment='创建时间')
    blocked_until: Mapped[Optional[datetime.datetime]] = mapped_column(DateTime(True), comment='封禁到期时间')


class Tasks(Base):
    __tablename__ = 'tasks'
    __table_args__ = (
        PrimaryKeyConstraint('id', name='tasks_pkey'),
        Index('idx_created_at', 'created_at'),
        Index('idx_platform_task', 'platform', 'platform_task_id'),
        Index('idx_team_id', 'team_id'),
        Index('idx_user_status_updated', 'user_id', 'status', 'updated_at'),
        {'comment': '用户任务历史记录表，用于存储和管理所有生成任务'}
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    user_id: Mapped[str] = mapped_column(String(36), nullable=False)
    platform: Mapped[str] = mapped_column(String(50), nullable=False)
    platform_task_id: Mapped[str] = mapped_column(String(100), nullable=False)
    type: Mapped[str] = mapped_column(String(10), nullable=False)
    status: Mapped[str] = mapped_column(String(10), nullable=False)
    created_at: Mapped[str] = mapped_column(String(20), nullable=False)
    updated_at: Mapped[str] = mapped_column(String(20), nullable=False)
    workflow_parameters: Mapped[Optional[dict]] = mapped_column(JSON)
    parameter_snapshot: Mapped[Optional[dict]] = mapped_column(JSON)
    result: Mapped[Optional[dict]] = mapped_column(JSON)
    error: Mapped[Optional[str]] = mapped_column(Text)
    deduction_result: Mapped[Optional[dict]] = mapped_column(JSON, comment="扣费结果记录")
    completed_at: Mapped[Optional[str]] = mapped_column(String(20))
    batch_id: Mapped[Optional[str]] = mapped_column(String(36))
    connection_mode: Mapped[Optional[str]] = mapped_column(String(10), server_default=text("'sse'::character varying"))
    team_id: Mapped[Optional[str]] = mapped_column(String(64))
    is_deleted: Mapped[Optional[bool]] = mapped_column(Boolean, server_default=text("false"), comment="是否已删除（软删除标记）")
    scene_tags: Mapped[Optional[list]] = mapped_column(JSON, nullable=True, comment='场景标签（数组）')
    product_tags: Mapped[Optional[list]] = mapped_column(JSON, nullable=True, comment='产品标签（数组）')


class Users(Base):
    __tablename__ = 'users'
    __table_args__ = (
        PrimaryKeyConstraint('id', name='users_pkey'),
        UniqueConstraint('phone', name='users_phone_key'),
        UniqueConstraint('user_id', name='users_user_id_key'),
        Index('ix_users_account_status', 'account_status'),
        Index('ix_users_created_at', 'created_at'),
        Index('ix_users_phone', 'phone'),
        Index('ix_users_role', 'role'),
        Index('ix_users_team_id', 'team_id'),
        Index('ix_users_tier', 'tier')
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, comment='用户 ID')
    username: Mapped[str] = mapped_column(String(255), nullable=False, comment='用户名')
    password_hash: Mapped[str] = mapped_column(String(255), nullable=False, comment='密码哈希')
    created_at: Mapped[datetime.datetime] = mapped_column(DateTime(True), nullable=False, server_default=text('now()'), comment='创建时间')
    user_id: Mapped[Optional[str]] = mapped_column(String(255))
    phone: Mapped[Optional[str]] = mapped_column(String(11))
    avatar: Mapped[Optional[str]] = mapped_column(String(256))
    team_id: Mapped[Optional[str]] = mapped_column(String(64))
    gold_credits: Mapped[Optional[int]] = mapped_column(Integer, server_default=text('0'))
    silver_credits: Mapped[Optional[int]] = mapped_column(Integer, server_default=text('999999999'))
    role: Mapped[Optional[str]] = mapped_column(String(20), server_default=text("'user'::character varying"))
    tier: Mapped[Optional[str]] = mapped_column(String(20), server_default=text("'standard'::character varying"))
    account_status: Mapped[Optional[str]] = mapped_column(String(20), server_default=text("'active'::character varying"))
    updated_at: Mapped[Optional[datetime.datetime]] = mapped_column(DateTime)


class SystemNotifications(Base):
    __tablename__ = 'system_notifications'
    __table_args__ = (
        PrimaryKeyConstraint('id', name='system_notifications_pkey'),
        Index('ix_system_notifications_is_active', 'is_active'),
        Index('ix_system_notifications_priority', 'priority'),
        Index('ix_system_notifications_type', 'type'),
        Index('ix_system_notifications_time_range', 'start_time', 'end_time'),
        {'comment': '系统通知表，用于显示网站实时状态条内容'}
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, comment='主键，UUID格式')
    type: Mapped[str] = mapped_column(String(20), nullable=False, comment='通知类型：info/warning/error/maintenance/update')
    title: Mapped[str] = mapped_column(String(200), nullable=False, comment='通知标题（短文本）')
    content: Mapped[str] = mapped_column(Text, nullable=False, comment='通知内容（支持HTML）')
    priority: Mapped[str] = mapped_column(String(10), nullable=False, server_default=text("'medium'"), comment='优先级：low/medium/high/urgent')
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default=text('true'), comment='是否激活')
    start_time: Mapped[int] = mapped_column(BigInteger, nullable=False, comment='生效时间戳（毫秒）')
    end_time: Mapped[Optional[int]] = mapped_column(BigInteger, comment='失效时间戳（毫秒，null表示永久）')
    dismissible: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default=text('true'), comment='是否允许用户关闭')
    link_url: Mapped[Optional[str]] = mapped_column(String(500), comment='点击跳转链接（可选）')
    target_audience: Mapped[str] = mapped_column(String(20), nullable=False, server_default=text("'all'"), comment='目标用户：all/logged_in/guest/admin')
    created_at: Mapped[int] = mapped_column(BigInteger, nullable=False, comment='创建时间（毫秒）')
    updated_at: Mapped[Optional[int]] = mapped_column(BigInteger, comment='更新时间（毫秒）')
    created_by: Mapped[str] = mapped_column(String(36), nullable=False, comment='创建者用户ID')

