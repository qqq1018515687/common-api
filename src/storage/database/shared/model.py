from coze_coding_dev_sdk.database import Base

from sqlalchemy import Boolean, DateTime, ForeignKeyConstraint, Index, Integer, JSON, PrimaryKeyConstraint, String, Text, UniqueConstraint, text
from typing import Optional
import datetime

from sqlalchemy.orm import Mapped, mapped_column, relationship

class Users(Base):
    __tablename__ = 'users'
    __table_args__ = (
        PrimaryKeyConstraint('id', name='users_pkey'),
        UniqueConstraint('user_id', name='users_user_id_key'),
        UniqueConstraint('username', name='users_username_key'),
        UniqueConstraint('phone', name='users_phone_key'),
        Index('ix_users_username', 'username'),
        Index('ix_users_phone', 'phone'),
        Index('ix_users_team_id', 'team_id'),
        Index('ix_users_role', 'role'),
        Index('ix_users_tier', 'tier'),
        Index('ix_users_account_status', 'account_status'),
        Index('ix_users_created_at', 'created_at')
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, comment='用户 ID')
    user_id: Mapped[Optional[str]] = mapped_column(String(64), unique=True, nullable=True, comment='用户唯一标识 (格式: user_xxx)')
    phone: Mapped[Optional[str]] = mapped_column(String(11), unique=True, nullable=True, comment='手机号')
    username: Mapped[str] = mapped_column(String(255), nullable=False, comment='用户名')
    password_hash: Mapped[str] = mapped_column(String(255), nullable=False, comment='密码哈希')
    avatar: Mapped[Optional[str]] = mapped_column(String(256), nullable=True, comment='头像 URL')
    team_id: Mapped[Optional[str]] = mapped_column(String(64), nullable=True, comment='团队 ID')
    gold_credits: Mapped[int] = mapped_column(Integer, nullable=False, server_default='0', comment='金豆余额')
    silver_credits: Mapped[int] = mapped_column(Integer, nullable=False, server_default='999999999', comment='银豆余额')
    role: Mapped[str] = mapped_column(String(20), nullable=False, server_default='user', comment='用户角色 (user/admin)')
    tier: Mapped[str] = mapped_column(String(20), nullable=False, server_default='standard', comment='用户等级 (standard/pro/enterprise)')
    account_status: Mapped[str] = mapped_column(String(20), nullable=False, server_default='active', comment='账号状态 (active/suspended/deleted)')
    created_at: Mapped[datetime.datetime] = mapped_column(DateTime(True), nullable=False, server_default=text('now()'), comment='创建时间')
    updated_at: Mapped[Optional[datetime.datetime]] = mapped_column(DateTime(True), nullable=True, onupdate=text('now()'), comment='更新时间')

    history: Mapped[list['History']] = relationship('History', back_populates='user')


class RateLimits(Base):
    __tablename__ = 'rate_limits'
    __table_args__ = (
        PrimaryKeyConstraint('record_id', name='rate_limits_pkey'),
        Index('ix_rate_limits_phone_ip_address', 'phone', 'ip_address'),
        Index('ix_rate_limits_last_request_at', 'last_request_at'),
        Index('ix_rate_limits_is_blocked', 'is_blocked')
    )

    record_id: Mapped[str] = mapped_column(String(64), primary_key=True, comment='记录唯一标识')
    phone: Mapped[str] = mapped_column(String(11), nullable=False, comment='手机号')
    ip_address: Mapped[str] = mapped_column(String(64), nullable=False, comment='IP 地址')
    request_count: Mapped[int] = mapped_column(Integer, nullable=False, server_default='1', comment='请求次数')
    first_request_at: Mapped[datetime.datetime] = mapped_column(DateTime(True), nullable=False, server_default=text('now()'), comment='首次请求时间')
    last_request_at: Mapped[datetime.datetime] = mapped_column(DateTime(True), nullable=False, server_default=text('now()'), comment='最后请求时间')
    is_blocked: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default=False, comment='是否封禁')
    blocked_until: Mapped[Optional[datetime.datetime]] = mapped_column(DateTime(True), nullable=True, comment='封禁到期时间')
    created_at: Mapped[datetime.datetime] = mapped_column(DateTime(True), nullable=False, server_default=text('now()'), comment='创建时间')


class History(Base):
    __tablename__ = 'history'
    __table_args__ = (
        ForeignKeyConstraint(['user_id'], ['users.id'], name='history_user_id_fkey'),
        PrimaryKeyConstraint('id', name='history_pkey'),
        Index('ix_history_user_id', 'user_id')
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, comment='记录 ID')
    user_id: Mapped[int] = mapped_column(Integer, nullable=False, comment='用户 ID')
    permanent_link: Mapped[str] = mapped_column(Text, nullable=False, comment='永久链接')
    iso_timestamp: Mapped[str] = mapped_column(String(255), nullable=False, comment='ISO 时间戳')
    created_at: Mapped[datetime.datetime] = mapped_column(DateTime(True), nullable=False, server_default=text('now()'), comment='创建时间')
    task_params: Mapped[Optional[dict]] = mapped_column(JSON, comment='任务参数')
    meta_data: Mapped[Optional[dict]] = mapped_column(JSON, comment='预留元数据字段，用于向后兼容')

    user: Mapped['Users'] = relationship('Users', back_populates='history')
