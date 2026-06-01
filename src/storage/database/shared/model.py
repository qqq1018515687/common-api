from coze_coding_dev_sdk.database import Base

from decimal import Decimal
from sqlalchemy import BigInteger, Boolean, DateTime, Index, Integer, JSON, Numeric, PrimaryKeyConstraint, String, Text, UniqueConstraint, text
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


class RegisterVerificationCodes(Base):
    __tablename__ = 'register_verification_codes'
    __table_args__ = (
        PrimaryKeyConstraint('id', name='register_verification_codes_pkey'),
        Index('ix_register_codes_phone_created_at', 'phone', 'created_at'),
        Index('ix_register_codes_phone_used_expires', 'phone', 'used_at', 'expires_at'),
    )

    id: Mapped[str] = mapped_column(String(64), primary_key=True, comment='记录唯一标识')
    phone: Mapped[str] = mapped_column(String(11), nullable=False, comment='手机号')
    code_hash: Mapped[str] = mapped_column(String(64), nullable=False, comment='验证码哈希')
    ip_address: Mapped[Optional[str]] = mapped_column(String(64), comment='请求 IP')
    expires_at: Mapped[datetime.datetime] = mapped_column(DateTime(True), nullable=False, comment='过期时间')
    used_at: Mapped[Optional[datetime.datetime]] = mapped_column(DateTime(True), comment='使用时间')
    attempts: Mapped[int] = mapped_column(Integer, nullable=False, server_default=text('0'), comment='校验失败次数')
    created_at: Mapped[datetime.datetime] = mapped_column(DateTime(True), nullable=False, server_default=text('now()'), comment='创建时间')
    updated_at: Mapped[datetime.datetime] = mapped_column(DateTime(True), nullable=False, server_default=text('now()'), comment='更新时间')


class PasswordResetVerificationCodes(Base):
    __tablename__ = 'password_reset_verification_codes'
    __table_args__ = (
        PrimaryKeyConstraint('id', name='password_reset_verification_codes_pkey'),
        Index('ix_password_reset_codes_phone_created_at', 'phone', 'created_at'),
        Index('ix_password_reset_codes_phone_used_expires', 'phone', 'used_at', 'expires_at'),
    )

    id: Mapped[str] = mapped_column(String(64), primary_key=True, comment='记录唯一标识')
    phone: Mapped[str] = mapped_column(String(11), nullable=False, comment='手机号')
    code_hash: Mapped[str] = mapped_column(String(64), nullable=False, comment='验证码哈希')
    ip_address: Mapped[Optional[str]] = mapped_column(String(64), comment='请求 IP')
    expires_at: Mapped[datetime.datetime] = mapped_column(DateTime(True), nullable=False, comment='过期时间')
    used_at: Mapped[Optional[datetime.datetime]] = mapped_column(DateTime(True), comment='使用时间')
    attempts: Mapped[int] = mapped_column(Integer, nullable=False, server_default=text('0'), comment='校验失败次数')
    created_at: Mapped[datetime.datetime] = mapped_column(DateTime(True), nullable=False, server_default=text('now()'), comment='创建时间')
    updated_at: Mapped[datetime.datetime] = mapped_column(DateTime(True), nullable=False, server_default=text('now()'), comment='更新时间')


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
    platform_task_id: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
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
    user_friendly_message: Mapped[Optional[str]] = mapped_column(Text, comment="LLM 生成的用户友好错误提示")


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
    gold_credits: Mapped[Optional[Decimal]] = mapped_column(Numeric(12, 2), server_default=text('0.00'))
    silver_credits: Mapped[Optional[int]] = mapped_column(Integer, server_default=text('999999999'))
    role: Mapped[Optional[str]] = mapped_column(String(32), server_default=text("'user'::character varying"))
    tier: Mapped[Optional[str]] = mapped_column(String(32), server_default=text("'commercial_registered'::character varying"))
    account_status: Mapped[Optional[str]] = mapped_column(String(32), server_default=text("'active'::character varying"))
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


class UpdateAnnouncements(Base):
    __tablename__ = 'update_announcements'
    __table_args__ = (
        PrimaryKeyConstraint('id', name='update_announcements_pkey'),
        Index('ix_update_announcements_is_active', 'is_active'),
        Index('ix_update_announcements_target_audience', 'target_audience'),
        Index('ix_update_announcements_priority', 'priority'),
        Index('ix_update_announcements_time_range', 'start_time', 'end_time'),
        {'comment': '更新公告表，用于首页弹窗公告'}
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, comment='公告ID')
    title: Mapped[str] = mapped_column(String(200), nullable=False, comment='公告标题')
    summary: Mapped[Optional[str]] = mapped_column(Text, comment='公告摘要')
    items: Mapped[Optional[list]] = mapped_column(JSON, comment='公告条目数组')
    cta_text: Mapped[Optional[str]] = mapped_column(String(120), comment='行动按钮文案')
    cta_url: Mapped[Optional[str]] = mapped_column(String(500), comment='行动按钮链接')
    target_audience: Mapped[str] = mapped_column(String(20), nullable=False, server_default=text("'all'"), comment='目标用户：all/logged_in/guest/admin')
    priority: Mapped[str] = mapped_column(String(10), nullable=False, server_default=text("'medium'"), comment='优先级：low/medium/high/urgent')
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default=text('true'), comment='是否启用')
    start_time: Mapped[int] = mapped_column(BigInteger, nullable=False, comment='生效时间戳（毫秒）')
    end_time: Mapped[Optional[int]] = mapped_column(BigInteger, comment='失效时间戳（毫秒，null表示永久）')
    version: Mapped[Optional[str]] = mapped_column(String(64), comment='公告版本')
    created_at: Mapped[int] = mapped_column(BigInteger, nullable=False, comment='创建时间（毫秒）')
    updated_at: Mapped[int] = mapped_column(BigInteger, nullable=False, comment='更新时间（毫秒）')
    created_by: Mapped[str] = mapped_column(String(36), nullable=False, comment='创建者用户ID')


class TagPoolVersions(Base):
    __tablename__ = 'tag_pool_versions'
    __table_args__ = (
        PrimaryKeyConstraint('id', name='tag_pool_versions_pkey'),
        UniqueConstraint('pool_type', 'version', name='tag_pool_versions_type_version_key'),
        Index('ix_tag_pool_versions_type_version', 'pool_type', 'version'),
        Index('ix_tag_pool_versions_is_active', 'is_active'),
        {'comment': '标签池版本表，用于管理标签池的版本历史'}
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, comment='主键，UUID格式')
    pool_type: Mapped[str] = mapped_column(String(20), nullable=False, comment='标签池类型：scene/product')
    version: Mapped[int] = mapped_column(Integer, nullable=False, comment='版本号')
    tags: Mapped[Optional[list]] = mapped_column(JSON, nullable=True, comment='标签列表')
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default=text('false'), comment='是否激活')
    created_by: Mapped[Optional[str]] = mapped_column(String(36), comment='创建者用户ID')
    created_at: Mapped[datetime.datetime] = mapped_column(DateTime(True), nullable=False, server_default=text('now()'), comment='创建时间')
    activated_at: Mapped[Optional[datetime.datetime]] = mapped_column(DateTime(True), comment='激活时间')
    activated_by: Mapped[Optional[str]] = mapped_column(String(36), comment='激活者用户ID')


class TagChangeHistory(Base):
    __tablename__ = 'tag_change_history'
    __table_args__ = (
        PrimaryKeyConstraint('id', name='tag_change_history_pkey'),
        Index('ix_tag_change_history_version', 'from_version', 'to_version'),
        {'comment': '标签变更历史表，记录标签池的所有变更记录'}
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, comment='主键，UUID格式')
    from_version: Mapped[Optional[int]] = mapped_column(Integer, comment='变更前版本')
    to_version: Mapped[int] = mapped_column(Integer, nullable=False, comment='变更后版本')
    pool_type: Mapped[str] = mapped_column(String(20), nullable=False, comment='标签池类型：scene/product')
    change_type: Mapped[str] = mapped_column(String(20), nullable=False, comment='变更类型：new_tag/remove_tag/merge_tags/activate_version/rollback')
    tag_name: Mapped[Optional[str]] = mapped_column(String(50), comment='标签名称')
    change_details: Mapped[Optional[dict]] = mapped_column(JSON, comment='变更详情')
    reason: Mapped[Optional[str]] = mapped_column(Text, comment='变更原因')
    created_by: Mapped[Optional[str]] = mapped_column(String(36), comment='创建者用户ID')
    created_at: Mapped[datetime.datetime] = mapped_column(DateTime(True), nullable=False, server_default=text('now()'), comment='创建时间')


class BatchRetagTasks(Base):
    __tablename__ = 'batch_retag_tasks'
    __table_args__ = (
        PrimaryKeyConstraint('id', name='batch_retag_tasks_pkey'),
        Index('ix_batch_retag_tasks_status', 'status'),
        {'comment': '批量重打标任务表，记录批量重打标的执行状态'}
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, comment='主键，UUID格式')
    tag_pool_version: Mapped[int] = mapped_column(Integer, nullable=False, comment='目标标签池版本')
    pool_type: Mapped[str] = mapped_column(String(20), nullable=False, comment='标签池类型：scene/product')
    total_tasks: Mapped[int] = mapped_column(Integer, nullable=False, comment='总任务数')
    completed_tasks: Mapped[int] = mapped_column(Integer, nullable=False, server_default=text('0'), comment='已完成任务数')
    failed_tasks: Mapped[int] = mapped_column(Integer, nullable=False, server_default=text("0"), comment='失败任务数')
    status: Mapped[str] = mapped_column(String(20), nullable=False, server_default=text("'pending'"), comment='状态：pending/running/completed/failed/cancelled')
    started_at: Mapped[Optional[datetime.datetime]] = mapped_column(DateTime(True), comment='开始时间')
    completed_at: Mapped[Optional[datetime.datetime]] = mapped_column(DateTime(True), comment='完成时间')
    error_message: Mapped[Optional[str]] = mapped_column(Text, comment='错误消息')
    created_by: Mapped[Optional[str]] = mapped_column(String(36), comment='创建者用户ID')
    created_at: Mapped[datetime.datetime] = mapped_column(DateTime(True), nullable=False, server_default=text('now()'), comment='创建时间')


class RetagFailures(Base):
    __tablename__ = 'retag_failures'
    __table_args__ = (
        PrimaryKeyConstraint('id', name='retag_failures_pkey'),
        Index('ix_retag_failures_batch', 'batch_id'),
        Index('ix_retag_failures_task', 'task_id'),
        {'comment': '重打标失败记录表，记录重打标失败的详细信息'}
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, comment='主键，UUID格式')
    batch_id: Mapped[Optional[str]] = mapped_column(String(36), comment='批量任务ID')
    task_id: Mapped[str] = mapped_column(String(36), nullable=False, comment='任务ID')
    error_type: Mapped[Optional[str]] = mapped_column(String(50), comment='错误类型：url_expired/ai_error/db_error/other')
    error_message: Mapped[Optional[str]] = mapped_column(Text, comment='错误消息')
    retry_count: Mapped[int] = mapped_column(Integer, nullable=False, server_default=text('0'), comment='重试次数')
    created_at: Mapped[datetime.datetime] = mapped_column(DateTime(True), nullable=False, server_default=text('now()'), comment='创建时间')


class Teams(Base):
    __tablename__ = 'teams'
    __table_args__ = (
        PrimaryKeyConstraint('id', name='teams_pkey'),
        Index('ix_teams_status', 'status'),
        {'comment': '团队基本信息表，存储团队的金豆余额和基本信息'}
    )

    id: Mapped[str] = mapped_column(String(64), primary_key=True, comment='团队ID')
    name: Mapped[str] = mapped_column(String(100), nullable=False, comment='团队名称')
    description: Mapped[Optional[str]] = mapped_column(String(255), comment='团队描述')
    balance: Mapped[Decimal] = mapped_column(Numeric(12, 2), nullable=False, server_default=text('0.00'), comment='团队金豆余额')
    total_consumed: Mapped[Decimal] = mapped_column(Numeric(12, 2), nullable=False, server_default=text('0.00'), comment='团队总消费金额')
    member_count: Mapped[int] = mapped_column(Integer, nullable=False, server_default=text('0'), comment='成员数量')
    status: Mapped[str] = mapped_column(String(20), nullable=False, server_default=text("'active'"), comment='状态：active/disabled')
    settings: Mapped[Optional[dict]] = mapped_column(JSON, comment='团队配置（限额、预警等）')
    created_at: Mapped[datetime.datetime] = mapped_column(DateTime(True), nullable=False, server_default=text('now()'), comment='创建时间')
    updated_at: Mapped[datetime.datetime] = mapped_column(DateTime(True), nullable=False, server_default=text('now()'), comment='更新时间')


class BillingRecords(Base):
    __tablename__ = 'billing_records'
    __table_args__ = (
        PrimaryKeyConstraint('id', name='billing_records_pkey'),
        UniqueConstraint('idempotency_key', name='billing_records_idempotency_key'),
        Index('ix_billing_records_user_id', 'user_id'),
        Index('ix_billing_records_team_id', 'team_id'),
        Index('ix_billing_records_operation_type', 'operation_type'),
        Index('ix_billing_records_related_id', 'related_id'),
        Index('ix_billing_records_created_at', 'created_at'),
        {'comment': '资金扣费记录表，支持幂等性、原子扣减、退款和结算'}
    )

    id: Mapped[str] = mapped_column(String(64), primary_key=True, comment='主键，UUID格式')
    idempotency_key: Mapped[str] = mapped_column(String(128), nullable=False, unique=True, comment='幂等键，同一 key 只执行一次')
    user_id: Mapped[str] = mapped_column(String(36), nullable=False, comment='用户ID')
    team_id: Mapped[Optional[str]] = mapped_column(String(64), comment='团队ID（team_gold 操作时必填）')
    operation_type: Mapped[str] = mapped_column(String(20), nullable=False, comment='操作类型：deduct/refund/settle')
    credit_type: Mapped[str] = mapped_column(String(20), nullable=False, comment='资金类型：personal_gold/personal_silver/team_gold')
    amount: Mapped[Decimal] = mapped_column(Numeric(12, 2), nullable=False, comment='操作金额（正数）')
    balance_before: Mapped[Optional[Decimal]] = mapped_column(Numeric(12, 2), comment='操作前余额')
    balance_after: Mapped[Optional[Decimal]] = mapped_column(Numeric(12, 2), comment='操作后余额')
    related_id: Mapped[Optional[str]] = mapped_column(String(64), comment='关联记录ID（退款/结算关联原扣费记录）')
    task_id: Mapped[Optional[str]] = mapped_column(String(36), comment='关联任务ID')
    description: Mapped[Optional[str]] = mapped_column(String(255), comment='描述')
    extra_data: Mapped[Optional[dict]] = mapped_column(JSON, comment='扩展信息')
    status: Mapped[str] = mapped_column(String(20), nullable=False, server_default=text("'completed'"), comment='状态：completed/failed')
    created_at: Mapped[datetime.datetime] = mapped_column(DateTime(True), nullable=False, server_default=text('now()'), comment='创建时间')


class TeamConsumptionRecords(Base):
    __tablename__ = 'team_consumption_records'
    __table_args__ = (
        PrimaryKeyConstraint('id', name='team_consumption_records_pkey'),
        Index('ix_team_records_team_time', 'team_id', 'created_at'),
        Index('ix_team_records_user_time', 'user_id', 'created_at'),
        Index('ix_team_records_type', 'team_id', 'operation_type'),
        {'comment': '团队消费记录表，记录团队内每笔消费的详细信息'}
    )

    id: Mapped[str] = mapped_column(String(64), primary_key=True, comment='主键')
    team_id: Mapped[str] = mapped_column(String(64), nullable=False, comment='团队ID')
    user_id: Mapped[str] = mapped_column(String(36), nullable=False, comment='消费的用户ID')
    username: Mapped[Optional[str]] = mapped_column(String(50), comment='用户名（冗余字段）')
    amount: Mapped[Decimal] = mapped_column(Numeric(12, 2), nullable=False, comment='变动金额（消费为负数，充值/退款为正数）')
    balance_before: Mapped[Optional[Decimal]] = mapped_column(Numeric(12, 2), comment='变动前余额')
    balance_after: Mapped[Optional[Decimal]] = mapped_column(Numeric(12, 2), comment='变动后余额')
    operation_type: Mapped[str] = mapped_column(String(20), nullable=False, comment='操作类型：consumption/refund/recharge')
    related_id: Mapped[Optional[str]] = mapped_column(String(64), comment='关联ID（任务ID/订单ID）')
    description: Mapped[Optional[str]] = mapped_column(String(255), comment='描述说明')
    extra_data: Mapped[Optional[dict]] = mapped_column('metadata', JSON, comment='扩展信息（任务类型、产品信息等）')
    created_at: Mapped[datetime.datetime] = mapped_column(DateTime(True), nullable=False, server_default=text('now()'), comment='创建时间')

