from typing import Optional, List
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session
import hashlib
import uuid
import bcrypt
import random
from datetime import datetime, timedelta, timezone

from src.storage.database.shared.model import Users, RateLimits


class UserCreate(BaseModel):
    phone: str = Field(..., description="手机号")
    password_hash: str = Field(..., description="密码哈希")
    username: str = Field(..., description="用户名")
    avatar: str = Field(..., description="头像URL")
    team_id: Optional[str] = Field(default=None, description="团队ID")
    gold_credits: int = Field(default=0, description="金豆余额")
    silver_credits: int = Field(default=10000, description="银豆余额")
    role: str = Field(default="user", description="用户角色")
    tier: str = Field(default="standard", description="用户等级")
    account_status: str = Field(default="active", description="账号状态")


class UserUpdate(BaseModel):
    username: Optional[str] = Field(default=None, description="用户名")
    avatar: Optional[str] = Field(default=None, description="头像URL")
    team_id: Optional[str] = Field(default=None, description="团队ID")
    gold_credits: Optional[int] = Field(default=None, description="金豆余额")
    silver_credits: Optional[int] = Field(default=None, description="银豆余额")
    role: Optional[str] = Field(default=None, description="用户角色")
    tier: Optional[str] = Field(default=None, description="用户等级")
    account_status: Optional[str] = Field(default=None, description="账号状态")


def hash_password(password: str) -> str:
    """
    生成密码哈希
    
    Args:
        password: 明文密码
        
    Returns:
        密码哈希字符串
    """
    salt = bcrypt.gensalt()
    return bcrypt.hashpw(password.encode('utf-8'), salt).decode('utf-8')


def verify_password(password: str, password_hash: str) -> bool:
    """
    验证密码
    
    Args:
        password: 明文密码
        password_hash: 密码哈希
        
    Returns:
        密码是否匹配
    """
    return bcrypt.checkpw(password.encode('utf-8'), password_hash.encode('utf-8'))


class UserManager:
    """Manager class for User operations."""

    @staticmethod
    def _generate_user_id() -> str:
        """
        生成用户 ID（10位随机数字）
        
        Returns:
            10位随机数字字符串
        """
        return str(random.randint(1000000000, 9999999999))

    def create_user(self, db: Session, user_in: UserCreate) -> Optional[Users]:
        """创建用户"""
        # 检查手机号是否已存在
        existing_user = db.query(Users).filter(Users.phone == user_in.phone).first()
        if existing_user:
            return None

        # 创建新用户
        user_data = user_in.model_dump()
        user_data["user_id"] = self._generate_user_id()
        db_user = Users(**user_data)
        db.add(db_user)
        try:
            db.commit()
            db.refresh(db_user)
            return db_user
        except Exception:
            db.rollback()
            raise

    def get_user_by_phone(self, db: Session, phone: str) -> Optional[Users]:
        """根据手机号获取用户"""
        return db.query(Users).filter(Users.phone == phone).first()

    def get_user_by_id(self, db: Session, user_id: str) -> Optional[Users]:
        """根据用户 ID 获取用户"""
        return db.query(Users).filter(Users.user_id == user_id).first()

    def update_user(self, db: Session, user_id: str, user_in: UserUpdate) -> Optional[Users]:
        """更新用户"""
        db_user = self.get_user_by_id(db, user_id)
        if not db_user:
            return None

        update_data = user_in.model_dump(exclude_unset=True)
        for field, value in update_data.items():
            if hasattr(db_user, field):
                setattr(db_user, field, value)

        db.add(db_user)
        try:
            db.commit()
            db.refresh(db_user)
            return db_user
        except Exception:
            db.rollback()
            raise

    def delete_user(self, db: Session, user_id: str) -> bool:
        """删除用户（软删除）"""
        db_user = self.get_user_by_id(db, user_id)
        if not db_user:
            return False

        db_user.account_status = "deleted"
        db.add(db_user)
        try:
            db.commit()
            return True
        except Exception:
            db.rollback()
            raise

    def list_users(
        self,
        db: Session,
        page: int = 1,
        limit: int = 20,
        role: Optional[str] = None,
        tier: Optional[str] = None,
        account_status: Optional[str] = None
    ) -> tuple[List[Users], int]:
        """用户列表"""
        query = db.query(Users).filter(Users.account_status != "deleted")

        if role:
            query = query.filter(Users.role == role)
        if tier:
            query = query.filter(Users.tier == tier)
        if account_status:
            query = query.filter(Users.account_status == account_status)

        # 统计总数
        total = query.count()

        # 分页
        offset = (page - 1) * limit
        users = query.order_by(Users.created_at.desc()).offset(offset).limit(limit).all()

        return users, total


class RateLimitManager:
    """Manager class for RateLimit operations."""

    @staticmethod
    def _generate_record_id() -> str:
        """生成记录 ID"""
        return f"limit_{uuid.uuid4()}"

    def get_or_create(self, db: Session, phone: str, ip_address: str) -> RateLimits:
        """获取或创建限流记录"""
        record = db.query(RateLimits).filter(
            RateLimits.phone == phone,
            RateLimits.ip_address == ip_address
        ).first()

        if not record:
            record = RateLimits(
                record_id=self._generate_record_id(),
                phone=phone,
                ip_address=ip_address,
                request_count=1,
                first_request_at=datetime.now(timezone.utc),
                last_request_at=datetime.now(timezone.utc)
            )
            db.add(record)
            try:
                db.commit()
                db.refresh(record)
            except Exception:
                db.rollback()
                raise

        return record

    def update_count(self, db: Session, record: RateLimits) -> RateLimits:
        """更新请求次数"""
        record.request_count += 1
        record.last_request_at = datetime.now(timezone.utc)
        db.add(record)
        try:
            db.commit()
            db.refresh(record)
        except Exception:
            db.rollback()
            raise

        return record

    def block(self, db: Session, record: RateLimits, block_duration_hours: int = 1):
        """封禁"""
        record.is_blocked = True
        record.blocked_until = datetime.now(timezone.utc) + timedelta(hours=block_duration_hours)
        db.add(record)
        try:
            db.commit()
        except Exception:
            db.rollback()
            raise

    def check_limits(self, db: Session, phone: str, ip_address: str) -> dict:
        """检查限流"""
        now = datetime.now(timezone.utc)
        ten_minutes_ago = now - timedelta(minutes=10)
        one_hour_ago = now - timedelta(hours=1)

        # 查询手机号维度的请求
        phone_records = db.query(RateLimits).filter(
            RateLimits.phone == phone,
            RateLimits.last_request_at > ten_minutes_ago
        ).all()
        count_phone_10min = sum(r.request_count for r in phone_records)

        phone_records_1h = db.query(RateLimits).filter(
            RateLimits.phone == phone,
            RateLimits.last_request_at > one_hour_ago
        ).all()
        count_phone_1hour = sum(r.request_count for r in phone_records_1h)

        # 查询 IP 维度的请求
        ip_records = db.query(RateLimits).filter(
            RateLimits.ip_address == ip_address,
            RateLimits.last_request_at > ten_minutes_ago
        ).all()
        count_ip_10min = sum(r.request_count for r in ip_records)

        ip_records_1h = db.query(RateLimits).filter(
            RateLimits.ip_address == ip_address,
            RateLimits.last_request_at > one_hour_ago
        ).all()
        count_ip_1hour = sum(r.request_count for r in ip_records_1h)

        return {
            "phone_10min": count_phone_10min,
            "phone_1hour": count_phone_1hour,
            "ip_10min": count_ip_10min,
            "ip_1hour": count_ip_1hour,
            "blocked_phone_10min": count_phone_10min >= 3,
            "blocked_phone_1hour": count_phone_1hour >= 5,
            "blocked_ip_10min": count_ip_10min >= 10,
            "blocked_ip_1hour": count_ip_1hour >= 20,
        }

    def get_active_records(self, db: Session, phone: Optional[str] = None, ip_address: Optional[str] = None) -> List[RateLimits]:
        """获取活跃的限流记录"""
        query = db.query(RateLimits)

        if phone:
            query = query.filter(RateLimits.phone == phone)
        if ip_address:
            query = query.filter(RateLimits.ip_address == ip_address)

        return query.all()

    def check_blocked_status(self, db: Session, phone: str, ip_address: str) -> Optional[dict]:
        """检查封禁状态"""
        record = db.query(RateLimits).filter(
            RateLimits.phone == phone,
            RateLimits.ip_address == ip_address
        ).first()

        if not record or not record.is_blocked:
            return None

        now = datetime.now(timezone.utc)
        if record.blocked_until and record.blocked_until > now:
            return {"blocked": True, "blocked_until": record.blocked_until.timestamp()}
        else:
            # 封禁已过期，解除封禁
            record.is_blocked = False
            record.blocked_until = None
            db.add(record)
            try:
                db.commit()
            except Exception:
                db.rollback()
            return None
