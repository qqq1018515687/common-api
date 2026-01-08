from typing import Optional
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session
import hashlib

from storage.database.shared.model import User


class UserCreate(BaseModel):
    username: str = Field(..., description="用户名")
    password: str = Field(..., description="密码")


class UserLogin(BaseModel):
    username: str = Field(..., description="用户名")
    password: str = Field(..., description="密码")


class UserManager:
    """Manager class for User operations."""

    @staticmethod
    def _hash_password(password: str) -> str:
        """密码哈希（SHA256）"""
        return hashlib.sha256(password.encode()).hexdigest()

    def create_user(self, db: Session, user_in: UserCreate) -> Optional[User]:
        """创建用户"""
        # 检查用户名是否已存在
        existing_user = db.query(User).filter(User.username == user_in.username).first()
        if existing_user:
            return None

        # 创建新用户
        user_data = user_in.model_dump()
        user_data["password_hash"] = self._hash_password(user_data.pop("password"))
        db_user = User(**user_data)
        db.add(db_user)
        try:
            db.commit()
            db.refresh(db_user)
            return db_user
        except Exception:
            db.rollback()
            raise

    def authenticate_user(self, db: Session, login_in: UserLogin) -> Optional[User]:
        """用户认证"""
        user = db.query(User).filter(User.username == login_in.username).first()
        if not user:
            return None

        password_hash = self._hash_password(login_in.password)
        if user.password_hash != password_hash:
            return None

        return user

    def get_user_by_username(self, db: Session, username: str) -> Optional[User]:
        """根据用户名获取用户"""
        return db.query(User).filter(User.username == username).first()

    def get_user_by_id(self, db: Session, user_id: int) -> Optional[User]:
        """根据用户 ID 获取用户"""
        return db.query(User).filter(User.id == user_id).first()
