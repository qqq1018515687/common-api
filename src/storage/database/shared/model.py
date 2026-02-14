from coze_coding_dev_sdk.database import Base

from sqlalchemy import BigInteger, Boolean, DateTime, Index, Integer, JSON, PrimaryKeyConstraint, String, Text, UniqueConstraint, text
from typing import Optional
import datetime
import time

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
    created_at: Mapped[int] = mapped_column(BigInteger, nullable=False)
    updated_at: Mapped[int] = mapped_column(BigInteger, nullable=False)
    workflow_parameters: Mapped[Optional[dict]] = mapped_column(JSON)
    parameter_snapshot: Mapped[Optional[dict]] = mapped_column(JSON)
    result: Mapped[Optional[dict]] = mapped_column(JSON)
    error: Mapped[Optional[str]] = mapped_column(Text)
    deduction_result: Mapped[Optional[dict]] = mapped_column(JSON, comment="扣费结果记录")
    completed_at: Mapped[Optional[int]] = mapped_column(BigInteger)
    batch_id: Mapped[Optional[str]] = mapped_column(String(36))
    connection_mode: Mapped[Optional[str]] = mapped_column(String(10), server_default=text("'sse'::character varying"))
    team_id: Mapped[Optional[str]] = mapped_column(String(64))
    is_deleted: Mapped[Optional[bool]] = mapped_column(Boolean, server_default=text("false"), comment="是否已删除（软删除标记）")


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


class FileMetadata(Base):
    """文件元数据表，用于追踪和管理对象存储中的文件"""
    __tablename__ = 'file_metadata'
    __table_args__ = (
        PrimaryKeyConstraint('id', name='file_metadata_pkey'),
        Index('ix_file_metadata_file_key', 'file_key'),
        Index('ix_file_metadata_source_type', 'source_type'),
        Index('ix_file_metadata_source_id', 'source_id'),
        Index('ix_file_metadata_status', 'status'),
        Index('ix_file_metadata_expire_time', 'expire_time'),
        Index('ix_file_metadata_file_prefix', 'file_prefix'),
        {'comment': '文件元数据表，用于追踪和管理对象存储中的文件'}
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, comment='文件ID（UUID）')
    file_key: Mapped[str] = mapped_column(String(512), nullable=False, comment='文件在对象存储中的key')
    file_prefix: Mapped[str] = mapped_column(String(20), nullable=False, comment='文件前缀（temp/perm/avatar/task）')
    file_type: Mapped[str] = mapped_column(String(50), nullable=False, comment='文件类型（image/video/audio/document）')
    file_size: Mapped[Optional[int]] = mapped_column(BigInteger, comment='文件大小（字节）')
    mime_type: Mapped[Optional[str]] = mapped_column(String(100), comment='MIME类型')
    source_type: Mapped[str] = mapped_column(String(50), nullable=False, comment='来源类型（upload/save/avatar/task）')
    source_id: Mapped[Optional[str]] = mapped_column(String(36), comment='来源ID（user_id/task_id）')
    upload_time: Mapped[datetime.datetime] = mapped_column(DateTime(True), nullable=False, server_default=text('now()'), comment='上传时间')
    access_time: Mapped[Optional[datetime.datetime]] = mapped_column(DateTime(True), comment='最后访问时间')
    status: Mapped[str] = mapped_column(String(20), nullable=False, server_default=text("'active'::character varying"), comment='状态（active/deleted）')
    retention_policy: Mapped[Optional[str]] = mapped_column(String(50), comment='保留策略（24h/7d/30d/permanent）')
    expire_time: Mapped[Optional[datetime.datetime]] = mapped_column(DateTime(True), comment='过期时间')
    created_at: Mapped[datetime.datetime] = mapped_column(DateTime(True), nullable=False, server_default=text('now()'), comment='创建时间')
    updated_at: Mapped[datetime.datetime] = mapped_column(DateTime(True), nullable=False, server_default=text('now()'), comment='更新时间')

