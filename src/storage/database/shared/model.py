from sqlalchemy import BigInteger, Boolean, Column, DateTime, ForeignKey, Index, Integer, String, Text, JSON, func
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship
from typing import Optional
import datetime


class Base(DeclarativeBase):
    pass


class User(Base):
    __tablename__ = "users"

    id = Column(Integer, primary_key=True, comment="用户 ID")
    username = Column(String(255), unique=True, nullable=False, comment="用户名")
    password_hash = Column(String(255), nullable=False, comment="密码哈希")
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False, comment="创建时间")

    # 关系
    histories = relationship("History", back_populates="user", cascade="all, delete-orphan")

    __table_args__ = (
        Index("ix_users_username", "username"),
    )


class History(Base):
    __tablename__ = "history"

    id = Column(Integer, primary_key=True, comment="记录 ID")
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False, comment="用户 ID")
    permanent_link = Column(Text, nullable=False, comment="永久链接")
    task_params = Column(JSON, nullable=True, comment="任务参数")
    iso_timestamp = Column(String(255), nullable=False, comment="ISO 时间戳")
    meta_data = Column(JSON, nullable=True, comment="预留元数据字段，用于向后兼容")
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False, comment="创建时间")

    # 关系
    user = relationship("User", back_populates="histories")

    __table_args__ = (
        Index("ix_history_user_id", "user_id"),
    )

