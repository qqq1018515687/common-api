from typing import Optional, List
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session
import hmac
import hashlib
import os
import uuid
import bcrypt
import random
from datetime import datetime, timedelta, timezone

from storage.database.shared.model import Users, RateLimits, RegisterVerificationCodes, PasswordResetVerificationCodes
from storage.database.amounts import gold_amount_to_number, normalize_gold_amount


class UserCreate(BaseModel):
    phone: str = Field(..., description="手机号")
    password_hash: str = Field(..., description="密码哈希")
    username: str = Field(..., description="用户名")
    avatar: str = Field(..., description="头像URL")
    team_id: Optional[str] = Field(default=None, description="团队ID")
    gold_credits: float = Field(default=0, description="金豆余额")
    silver_credits: int = Field(default=10000, description="银豆余额")
    role: str = Field(default="user", description="用户角色")
    tier: str = Field(default="commercial_registered", description="用户等级")
    account_status: str = Field(default="active", description="账号状态")


class UserUpdate(BaseModel):
    username: Optional[str] = Field(default=None, description="用户名")
    avatar: Optional[str] = Field(default=None, description="头像URL")
    team_id: Optional[str] = Field(default=None, description="团队ID")
    gold_credits: Optional[float] = Field(default=None, description="金豆余额")
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
        user_data["gold_credits"] = normalize_gold_amount(user_data.get("gold_credits", 0), allow_zero=True)
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
        if "gold_credits" in update_data:
            update_data["gold_credits"] = normalize_gold_amount(update_data["gold_credits"], allow_zero=True)
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


class RegisterCodeManager:
    """注册验证码管理，仅保存验证码哈希。"""

    code_ttl_seconds = 300
    max_attempts = 5

    @staticmethod
    def _generate_record_id() -> str:
        return f"reg_code_{uuid.uuid4()}"

    @staticmethod
    def _now() -> datetime:
        return datetime.now(timezone.utc)

    @staticmethod
    def _ensure_aware(value: datetime) -> datetime:
        if value.tzinfo is None:
            return value.replace(tzinfo=timezone.utc)
        return value

    @staticmethod
    def _ensure_register_codes_table(db: Session) -> None:
        bind = db.get_bind()
        RegisterVerificationCodes.__table__.create(bind=bind, checkfirst=True)
        for index in RegisterVerificationCodes.__table__.indexes:
            index.create(bind=bind, checkfirst=True)

    @staticmethod
    def _hash_secret() -> str:
        secret = (
            os.getenv("REGISTER_CODE_HASH_SECRET")
            or os.getenv("COZE_REGISTER_CODE_SECRET")
            or os.getenv("ALIYUN_ACCESS_KEY_SECRET")
            or os.getenv("ALIBABA_CLOUD_ACCESS_KEY_SECRET")
        )
        if not secret:
            raise RuntimeError("REGISTER_CODE_HASH_SECRET 未配置")
        return secret

    def hash_code(self, phone: str, code: str) -> str:
        payload = f"{phone}:{code}:{self._hash_secret()}".encode("utf-8")
        return hashlib.sha256(payload).hexdigest()

    def save_code(self, db: Session, phone: str, code: str, ip_address: str) -> RegisterVerificationCodes:
        """保存新的注册验证码哈希。短信发送成功后再废弃旧验证码。"""
        self._ensure_register_codes_table(db)
        now = self._now()
        record = RegisterVerificationCodes(
            id=self._generate_record_id(),
            phone=phone,
            code_hash=self.hash_code(phone, code),
            ip_address=ip_address,
            expires_at=now + timedelta(seconds=self.code_ttl_seconds),
            attempts=0,
            created_at=now,
            updated_at=now,
        )
        db.add(record)
        try:
            db.commit()
            db.refresh(record)
            return record
        except Exception:
            db.rollback()
            raise

    def mark_other_unused_codes_used(self, db: Session, phone: str, keep_record_id: str) -> None:
        """短信确认发送成功后，废弃同手机号其他未使用验证码。"""
        self._ensure_register_codes_table(db)
        now = self._now()
        db.query(RegisterVerificationCodes).filter(
            RegisterVerificationCodes.phone == phone,
            RegisterVerificationCodes.used_at.is_(None),
            RegisterVerificationCodes.id != keep_record_id,
        ).update(
            {
                "used_at": now,
                "updated_at": now,
            },
            synchronize_session=False,
        )
        try:
            db.commit()
        except Exception:
            db.rollback()
            raise

    def delete_code(self, db: Session, record_id: str) -> None:
        self._ensure_register_codes_table(db)
        record = db.query(RegisterVerificationCodes).filter(RegisterVerificationCodes.id == record_id).first()
        if not record:
            return
        db.delete(record)
        try:
            db.commit()
        except Exception:
            db.rollback()
            raise

    def _latest_unused_code(self, db: Session, phone: str) -> Optional[RegisterVerificationCodes]:
        return (
            db.query(RegisterVerificationCodes)
            .filter(
                RegisterVerificationCodes.phone == phone,
                RegisterVerificationCodes.used_at.is_(None),
            )
            .order_by(RegisterVerificationCodes.created_at.desc())
            .with_for_update()
            .first()
        )

    def register_user_with_code(
        self,
        db: Session,
        phone: str,
        username: str,
        password: str,
        code: str,
        ip_address: str,
        avatar: Optional[str] = None,
    ) -> tuple[bool, str, Optional[dict]]:
        """校验并消费验证码，同时创建用户。"""
        now = self._now()

        try:
            self._ensure_register_codes_table(db)
            existing_user = db.query(Users).filter(Users.phone == phone).first()
            if existing_user:
                return False, "该手机号已注册，请直接登录", None

            record = self._latest_unused_code(db, phone)
            if not record:
                return False, "验证码错误或已过期", None

            if self._ensure_aware(record.expires_at) <= now or record.attempts >= self.max_attempts:
                record.used_at = now
                record.updated_at = now
                db.add(record)
                db.commit()
                return False, "验证码错误或已过期", None

            expected_hash = self.hash_code(phone, code)
            if not hmac.compare_digest(record.code_hash, expected_hash):
                record.attempts += 1
                record.updated_at = now
                if record.attempts >= self.max_attempts:
                    record.used_at = now
                db.add(record)
                db.commit()
                return False, "验证码错误或已过期", None

            record.used_at = now
            record.updated_at = now

            db_user = Users(
                phone=phone,
                username=username,
                password_hash=hash_password(password),
                avatar=avatar or "",
                user_id=UserManager._generate_user_id(),
                gold_credits=normalize_gold_amount(0, allow_zero=True),
                silver_credits=10000,
                role="user",
                tier="commercial_registered",
                account_status="active",
            )
            db.add(record)
            db.add(db_user)
            db.commit()
            db.refresh(db_user)

            user_data = {
                "user_id": db_user.user_id,
                "phone": db_user.phone,
                "username": db_user.username,
                "avatar": db_user.avatar,
                "team_id": db_user.team_id,
                "gold_credits": gold_amount_to_number(db_user.gold_credits),
                "silver_credits": db_user.silver_credits,
                "role": db_user.role,
                "tier": db_user.tier,
                "account_status": db_user.account_status,
                "created_at": int(self._ensure_aware(db_user.created_at).timestamp() * 1000),
                "updated_at": int(self._ensure_aware(db_user.updated_at).timestamp() * 1000) if db_user.updated_at else None,
            }
            return True, "注册成功", user_data
        except Exception:
            db.rollback()
            raise


class PasswordResetCodeManager:
    """密码重置验证码管理，仅保存验证码哈希。"""

    code_ttl_seconds = 300
    max_attempts = 5

    @staticmethod
    def _generate_record_id() -> str:
        return f"pwd_reset_code_{uuid.uuid4()}"

    @staticmethod
    def _now() -> datetime:
        return datetime.now(timezone.utc)

    @staticmethod
    def _ensure_aware(value: datetime) -> datetime:
        if value.tzinfo is None:
            return value.replace(tzinfo=timezone.utc)
        return value

    @staticmethod
    def _ensure_password_reset_codes_table(db: Session) -> None:
        bind = db.get_bind()
        PasswordResetVerificationCodes.__table__.create(bind=bind, checkfirst=True)
        for index in PasswordResetVerificationCodes.__table__.indexes:
            index.create(bind=bind, checkfirst=True)

    @staticmethod
    def _hash_secret() -> str:
        secret = (
            os.getenv("PASSWORD_RESET_CODE_HASH_SECRET")
            or os.getenv("REGISTER_CODE_HASH_SECRET")
            or os.getenv("COZE_REGISTER_CODE_SECRET")
            or os.getenv("ALIYUN_ACCESS_KEY_SECRET")
            or os.getenv("ALIBABA_CLOUD_ACCESS_KEY_SECRET")
        )
        if not secret:
            raise RuntimeError("PASSWORD_RESET_CODE_HASH_SECRET 未配置")
        return secret

    def hash_code(self, phone: str, code: str) -> str:
        payload = f"password_reset:{phone}:{code}:{self._hash_secret()}".encode("utf-8")
        return hashlib.sha256(payload).hexdigest()

    def save_code(self, db: Session, phone: str, code: str, ip_address: str) -> PasswordResetVerificationCodes:
        """保存新的密码重置验证码哈希。短信发送成功后再废弃旧验证码。"""
        self._ensure_password_reset_codes_table(db)
        now = self._now()
        record = PasswordResetVerificationCodes(
            id=self._generate_record_id(),
            phone=phone,
            code_hash=self.hash_code(phone, code),
            ip_address=ip_address,
            expires_at=now + timedelta(seconds=self.code_ttl_seconds),
            attempts=0,
            created_at=now,
            updated_at=now,
        )
        db.add(record)
        try:
            db.commit()
            db.refresh(record)
            return record
        except Exception:
            db.rollback()
            raise

    def mark_other_unused_codes_used(self, db: Session, phone: str, keep_record_id: str) -> None:
        """短信确认发送成功后，废弃同手机号其他未使用密码重置验证码。"""
        self._ensure_password_reset_codes_table(db)
        now = self._now()
        db.query(PasswordResetVerificationCodes).filter(
            PasswordResetVerificationCodes.phone == phone,
            PasswordResetVerificationCodes.used_at.is_(None),
            PasswordResetVerificationCodes.id != keep_record_id,
        ).update(
            {
                "used_at": now,
                "updated_at": now,
            },
            synchronize_session=False,
        )
        try:
            db.commit()
        except Exception:
            db.rollback()
            raise

    def delete_code(self, db: Session, record_id: str) -> None:
        self._ensure_password_reset_codes_table(db)
        record = db.query(PasswordResetVerificationCodes).filter(PasswordResetVerificationCodes.id == record_id).first()
        if not record:
            return
        db.delete(record)
        try:
            db.commit()
        except Exception:
            db.rollback()
            raise

    def _latest_unused_code(self, db: Session, phone: str) -> Optional[PasswordResetVerificationCodes]:
        return (
            db.query(PasswordResetVerificationCodes)
            .filter(
                PasswordResetVerificationCodes.phone == phone,
                PasswordResetVerificationCodes.used_at.is_(None),
            )
            .order_by(PasswordResetVerificationCodes.created_at.desc())
            .with_for_update()
            .first()
        )

    def reset_password_with_code(
        self,
        db: Session,
        phone: str,
        password: str,
        code: str,
    ) -> tuple[bool, str]:
        """校验并消费密码重置验证码，同时更新用户密码。"""
        now = self._now()

        try:
            self._ensure_password_reset_codes_table(db)
            db_user = (
                db.query(Users)
                .filter(Users.phone == phone)
                .with_for_update()
                .first()
            )
            if not db_user or db_user.account_status != "active":
                return False, "验证码错误或已过期"

            record = self._latest_unused_code(db, phone)
            if not record:
                return False, "验证码错误或已过期"

            if self._ensure_aware(record.expires_at) <= now or record.attempts >= self.max_attempts:
                record.used_at = now
                record.updated_at = now
                db.add(record)
                db.commit()
                return False, "验证码错误或已过期"

            expected_hash = self.hash_code(phone, code)
            if not hmac.compare_digest(record.code_hash, expected_hash):
                record.attempts += 1
                record.updated_at = now
                if record.attempts >= self.max_attempts:
                    record.used_at = now
                db.add(record)
                db.commit()
                return False, "验证码错误或已过期"

            record.used_at = now
            record.updated_at = now
            db_user.password_hash = hash_password(password)
            db_user.updated_at = now
            db.add(record)
            db.add(db_user)
            db.commit()
            return True, "密码已重置"
        except Exception:
            db.rollback()
            raise


class RateLimitManager:
    """Manager class for RateLimit operations."""

    @staticmethod
    def _generate_record_id() -> str:
        """生成记录 ID"""
        return f"limit_{uuid.uuid4()}"

    def get_or_create(self, db: Session, phone: str, ip_address: str) -> RateLimits:
        """获取或创建限流记录（增加容错：同一手机号返回最早记录）"""
        # 优先查询完全匹配（phone + ip）
        record = db.query(RateLimits).filter(
            RateLimits.phone == phone,
            RateLimits.ip_address == ip_address
        ).first()

        if record:
            # 找到完全匹配的记录，直接返回
            return record

        # 没找到完全匹配，查询同一手机号的其他记录
        same_phone_record = db.query(RateLimits).filter(
            RateLimits.phone == phone,
            RateLimits.is_blocked == False  # 只查询未被封禁的记录
        ).order_by(RateLimits.first_request_at).first()

        if same_phone_record:
            # 找到同一手机号的记录（可能IP不同），返回这条记录
            # 这样可以避免IP变化导致的记录重复
            return same_phone_record

        # 没有任何记录，创建新记录
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
        """检查限流（仅限手机号维度，移除IP限制，增加容错机制）"""
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

        # 容错限流阈值（放宽限制）
        # 警告阈值：接近限制但不封禁
        # 封禁阈值：真正超限才封禁
        return {
            "phone_10min": count_phone_10min,
            "phone_1hour": count_phone_1hour,
            "warn_phone_10min": count_phone_10min >= 3,      # 警告：10分钟内3次
            "warn_phone_1hour": count_phone_1hour >= 5,      # 警告：1小时内5次
            "blocked_phone_10min": count_phone_10min >= 5,   # 封禁：10分钟内5次（从3次改为5次）
            "blocked_phone_1hour": count_phone_1hour >= 10,  # 封禁：1小时内10次（从5次改为10次）
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
        """检查封禁状态（仅根据手机号查询，移除IP限制）"""
        # 查询该手机号所有被封禁的记录
        now = datetime.now(timezone.utc)
        blocked_records = db.query(RateLimits).filter(
            RateLimits.phone == phone,
            RateLimits.is_blocked == True
        ).all()

        # 检查是否有未过期的封禁
        active_block = None
        for record in blocked_records:
            if record.blocked_until and record.blocked_until > now:
                # 找到未过期的封禁
                if not active_block or record.blocked_until > active_block.get("blocked_until", 0):
                    active_block = {"blocked": True, "blocked_until": record.blocked_until.timestamp()}
            else:
                # 封禁已过期，解除封禁
                record.is_blocked = False
                record.blocked_until = None
                db.add(record)

        # 提交所有解除封禁的操作
        if blocked_records:
            try:
                db.commit()
            except Exception:
                db.rollback()

        return active_block
