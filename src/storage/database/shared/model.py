from coze_coding_dev_sdk.database import Base

from sqlalchemy import Boolean, DateTime, Index, Integer, PrimaryKeyConstraint, String, UniqueConstraint, text
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
