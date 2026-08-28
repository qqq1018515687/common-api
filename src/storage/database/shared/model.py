from coze_coding_dev_sdk.database import Base

from decimal import Decimal
from sqlalchemy import BigInteger, Boolean, DateTime, Index, Integer, JSON, Numeric, PrimaryKeyConstraint, String, Text, UniqueConstraint, text, Identity
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
        Index('idx_tasks_status_created_at', 'status', 'created_at'),
        Index('idx_tasks_status_completed_at', 'status', 'completed_at'),
        Index('idx_tasks_status_failed_at', 'status', 'failed_at'),
        Index('idx_tasks_status_cancelled_at', 'status', 'cancelled_at'),
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
    channel: Mapped[Optional[str]] = mapped_column(String(32), comment='任务渠道归一键：local/r/t/free/other')
    workflow_parameters: Mapped[Optional[dict]] = mapped_column(JSON)
    parameter_snapshot: Mapped[Optional[dict]] = mapped_column(JSON)
    result: Mapped[Optional[dict]] = mapped_column(JSON)
    error: Mapped[Optional[str]] = mapped_column(Text)
    deduction_result: Mapped[Optional[dict]] = mapped_column(JSON, comment="扣费结果记录")
    completed_at: Mapped[Optional[str]] = mapped_column(String(20))
    failed_at: Mapped[Optional[str]] = mapped_column(String(20), comment="失败时间")
    cancelled_at: Mapped[Optional[str]] = mapped_column(String(20), comment="取消时间")
    status_updated_at: Mapped[Optional[str]] = mapped_column(String(20), comment="最近一次状态变更时间")
    started_at: Mapped[Optional[str]] = mapped_column(String(20), comment="任务真正开始执行的时间戳(毫秒字符串)")
    elapsed_time_seconds: Mapped[Optional[int]] = mapped_column(Integer, server_default=text('0'), comment="任务耗时(秒),由后端统一计算")
    batch_id: Mapped[Optional[str]] = mapped_column(String(36))
    connection_mode: Mapped[Optional[str]] = mapped_column(String(10), server_default=text("'sse'::character varying"))
    team_id: Mapped[Optional[str]] = mapped_column(String(64))
    is_deleted: Mapped[Optional[bool]] = mapped_column(Boolean, server_default=text("false"), comment="是否已删除（软删除标记）")
    user_friendly_message: Mapped[Optional[str]] = mapped_column(Text, comment="LLM 生成的用户友好错误提示")
    confirmation_state: Mapped[Optional[str]] = mapped_column(String(20), server_default=text("'none'::character varying"), comment="结果确认状态：none/pending/confirmed")
    final_reason: Mapped[Optional[str]] = mapped_column(String(32), comment="任务终态原因：user_cancelled/provider_failed/recovery_timeout_failed/submitted_unconfirmed_failed（退款裁决依据）")
    cancellation_source: Mapped[Optional[str]] = mapped_column(String(16), comment="取消来源：user=用户手动取消，system=系统/超时取消")
    deleted_image_urls: Mapped[Optional[list]] = mapped_column(JSON, comment="已删除的图片URL列表（图像级软删除）")
    result_fallback: Mapped[Optional[dict]] = mapped_column(JSON, comment="结果转存失败时保留的原始回退结果")

class FavoriteImages(Base):
    __tablename__ = 'favorite_images'
    __table_args__ = (
        PrimaryKeyConstraint('favorite_id', name='favorite_images_pkey'),
        UniqueConstraint('user_id', 'task_id', 'image_index', name='uq_favorite_images_user_task_image'),
        Index('ix_favorite_images_user_created', 'user_id', 'created_at'),
        Index('ix_favorite_images_task_id', 'task_id'),
        {'comment': 'Image-level user favorites with long-term object storage'}
    )

    favorite_id: Mapped[str] = mapped_column(String(36), primary_key=True, comment='Favorite record ID')
    user_id: Mapped[str] = mapped_column(String(36), nullable=False, comment='Owner user ID')
    task_id: Mapped[str] = mapped_column(String(36), nullable=False, comment='Source task ID')
    image_index: Mapped[int] = mapped_column(Integer, nullable=False, comment='Image index in task result')
    source_url: Mapped[str] = mapped_column(Text, nullable=False, comment='Original source URL')
    stored_url: Mapped[str] = mapped_column(Text, nullable=False, comment='Long-term stored URL')
    file_key: Mapped[Optional[str]] = mapped_column(String(512), comment='Object storage key')
    thumbnail_url: Mapped[Optional[str]] = mapped_column(Text, comment='Thumbnail URL')
    workflow_id: Mapped[Optional[str]] = mapped_column(String(128), comment='Workflow ID')
    workflow_name: Mapped[Optional[str]] = mapped_column(String(255), comment='Workflow display name')
    model_name: Mapped[Optional[str]] = mapped_column(String(128), comment='Model name')
    parameter_snapshot: Mapped[Optional[dict]] = mapped_column(JSON, comment='Task parameter snapshot')
    created_at: Mapped[int] = mapped_column(BigInteger, nullable=False, comment='Created timestamp in ms')


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
        UniqueConstraint('biz_key', name='uq_system_notifications_biz_key'),
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
    biz_key: Mapped[Optional[str]] = mapped_column(String(64), comment='业务标识：固定运营通知用（如 channel_status_t / channel_status_r），普通通知为空')


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


class TeamInvites(Base):
    __tablename__ = 'team_invites'
    __table_args__ = (
        PrimaryKeyConstraint('id', name='team_invites_pkey'),
        UniqueConstraint('code', name='team_invites_code_key'),
        Index('ix_team_invites_team_id', 'team_id'),
        Index('ix_team_invites_status', 'status'),
        Index('ix_team_invites_expires_at', 'expires_at'),
        {'comment': '团队邀请码表'}
    )

    id: Mapped[str] = mapped_column(String(64), primary_key=True, comment='邀请码ID')
    team_id: Mapped[str] = mapped_column(String(64), nullable=False, comment='团队ID')
    team_name: Mapped[str] = mapped_column(String(100), nullable=False, comment='团队名称快照')
    code: Mapped[str] = mapped_column(String(32), nullable=False, unique=True, comment='邀请码明文')
    status: Mapped[str] = mapped_column(String(20), nullable=False, server_default=text("'active'"), comment='状态：active/disabled')
    max_uses: Mapped[int] = mapped_column(Integer, nullable=False, server_default=text('1'), comment='最大使用次数')
    used_count: Mapped[int] = mapped_column(Integer, nullable=False, server_default=text('0'), comment='已使用次数')
    created_by_user_id: Mapped[str] = mapped_column(String(36), nullable=False, comment='创建人用户ID')
    created_by_username: Mapped[Optional[str]] = mapped_column(String(255), comment='创建人用户名快照')
    last_used_by_user_id: Mapped[Optional[str]] = mapped_column(String(36), comment='最近使用人用户ID')
    last_used_at: Mapped[Optional[datetime.datetime]] = mapped_column(DateTime(True), comment='最近使用时间')
    expires_at: Mapped[Optional[datetime.datetime]] = mapped_column(DateTime(True), comment='过期时间')
    note: Mapped[Optional[str]] = mapped_column(Text, comment='备注')
    created_at: Mapped[datetime.datetime] = mapped_column(DateTime(True), nullable=False, server_default=text('now()'), comment='创建时间')
    updated_at: Mapped[datetime.datetime] = mapped_column(DateTime(True), nullable=False, server_default=text('now()'), comment='更新时间')


class TeamInviteJoinRecords(Base):
    __tablename__ = 'team_invite_join_records'
    __table_args__ = (
        PrimaryKeyConstraint('id', name='team_invite_join_records_pkey'),
        Index('ix_team_invite_join_records_invite_id', 'invite_id'),
        Index('ix_team_invite_join_records_team_id', 'team_id'),
        Index('ix_team_invite_join_records_user_id', 'user_id'),
        {'comment': '团队邀请码加入记录表'}
    )

    id: Mapped[str] = mapped_column(String(64), primary_key=True, comment='加入记录ID')
    invite_id: Mapped[str] = mapped_column(String(64), nullable=False, comment='邀请码ID')
    code: Mapped[str] = mapped_column(String(32), nullable=False, comment='使用的邀请码快照')
    team_id: Mapped[str] = mapped_column(String(64), nullable=False, comment='加入的团队ID')
    team_name: Mapped[str] = mapped_column(String(100), nullable=False, comment='加入的团队名称快照')
    user_id: Mapped[str] = mapped_column(String(36), nullable=False, comment='加入用户ID')
    username: Mapped[Optional[str]] = mapped_column(String(255), comment='加入用户名快照')
    created_at: Mapped[datetime.datetime] = mapped_column(DateTime(True), nullable=False, server_default=text('now()'), comment='加入时间')


class UserReferralProfiles(Base):
    __tablename__ = 'user_referral_profiles'
    __table_args__ = (
        PrimaryKeyConstraint('id', name='user_referral_profiles_pkey'),
        UniqueConstraint('user_id', name='user_referral_profiles_user_id_key'),
        UniqueConstraint('referral_code', name='user_referral_profiles_referral_code_key'),
        Index('ix_user_referral_profiles_referral_code', 'referral_code'),
        {'comment': '用户推荐码档案表'}
    )

    id: Mapped[str] = mapped_column(String(64), primary_key=True, comment='档案ID')
    user_id: Mapped[str] = mapped_column(String(36), nullable=False, unique=True, comment='用户ID')
    referral_code: Mapped[str] = mapped_column(String(32), nullable=False, unique=True, comment='推荐码')
    created_at: Mapped[datetime.datetime] = mapped_column(DateTime(True), nullable=False, server_default=text('now()'), comment='创建时间')
    updated_at: Mapped[datetime.datetime] = mapped_column(DateTime(True), nullable=False, server_default=text('now()'), comment='更新时间')


class UserReferralRelations(Base):
    __tablename__ = 'user_referral_relations'
    __table_args__ = (
        PrimaryKeyConstraint('id', name='user_referral_relations_pkey'),
        UniqueConstraint('referee_user_id', name='user_referral_relations_referee_user_id_key'),
        Index('ix_user_referral_relations_referrer_user_id', 'referrer_user_id'),
        Index('ix_user_referral_relations_bound_at', 'bound_at'),
        {'comment': '用户邀请关系表'}
    )

    id: Mapped[str] = mapped_column(String(64), primary_key=True, comment='关系ID')
    referrer_user_id: Mapped[str] = mapped_column(String(36), nullable=False, comment='邀请人用户ID')
    referee_user_id: Mapped[str] = mapped_column(String(36), nullable=False, unique=True, comment='被邀请人用户ID')
    referral_code: Mapped[str] = mapped_column(String(32), nullable=False, comment='绑定时使用的推荐码快照')
    reward_status: Mapped[str] = mapped_column(String(20), nullable=False, server_default=text("'pending'"), comment='奖励状态：pending/rewarded/ineligible')
    bound_at: Mapped[datetime.datetime] = mapped_column(DateTime(True), nullable=False, server_default=text('now()'), comment='绑定时间')
    reward_granted_at: Mapped[Optional[datetime.datetime]] = mapped_column(DateTime(True), comment='奖励发放时间')
    first_completed_task_id: Mapped[Optional[str]] = mapped_column(String(36), comment='触发奖励的首个有效任务ID')
    created_at: Mapped[datetime.datetime] = mapped_column(DateTime(True), nullable=False, server_default=text('now()'), comment='创建时间')
    updated_at: Mapped[datetime.datetime] = mapped_column(DateTime(True), nullable=False, server_default=text('now()'), comment='更新时间')


class ReferralRewardRecords(Base):
    __tablename__ = 'referral_reward_records'
    __table_args__ = (
        PrimaryKeyConstraint('id', name='referral_reward_records_pkey'),
        UniqueConstraint('relation_id', name='referral_reward_records_relation_id_key'),
        UniqueConstraint('task_id', name='referral_reward_records_task_id_key'),
        Index('ix_referral_reward_records_referrer_user_id', 'referrer_user_id'),
        Index('ix_referral_reward_records_referee_user_id', 'referee_user_id'),
        Index('ix_referral_reward_records_created_at', 'created_at'),
        {'comment': '邀请奖励发放记录表'}
    )

    id: Mapped[str] = mapped_column(String(64), primary_key=True, comment='奖励记录ID')
    relation_id: Mapped[str] = mapped_column(String(64), nullable=False, unique=True, comment='邀请关系ID')
    referrer_user_id: Mapped[str] = mapped_column(String(36), nullable=False, comment='邀请人用户ID')
    referee_user_id: Mapped[str] = mapped_column(String(36), nullable=False, comment='被邀请人用户ID')
    task_id: Mapped[str] = mapped_column(String(36), nullable=False, unique=True, comment='触发任务ID')
    reward_credit_type: Mapped[str] = mapped_column(String(20), nullable=False, server_default=text("'personal_gold'"), comment='奖励资金类型')
    reward_amount: Mapped[Decimal] = mapped_column(Numeric(12, 2), nullable=False, comment='奖励金额')
    billing_record_id: Mapped[Optional[str]] = mapped_column(String(64), comment='账本记录ID')
    description: Mapped[Optional[str]] = mapped_column(String(255), comment='奖励描述')
    extra_data: Mapped[Optional[dict]] = mapped_column(JSON, comment='扩展信息')
    created_at: Mapped[datetime.datetime] = mapped_column(DateTime(True), nullable=False, server_default=text('now()'), comment='创建时间')


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
    operation_type: Mapped[str] = mapped_column(String(20), nullable=False, comment='操作类型：deduct/refund/settle/reward/exchange_out/exchange_in')
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


class WalletExchangeRecords(Base):
    __tablename__ = 'wallet_exchange_records'
    __table_args__ = (
        PrimaryKeyConstraint('id', name='wallet_exchange_records_pkey'),
        UniqueConstraint('idempotency_key', name='wallet_exchange_records_idempotency_key'),
        Index('ix_wallet_exchange_records_user_id', 'user_id'),
        Index('ix_wallet_exchange_records_status', 'status'),
        Index('ix_wallet_exchange_records_created_at', 'created_at'),
        {'comment': '钱包金豆换银豆主记录表'}
    )

    id: Mapped[str] = mapped_column(String(64), primary_key=True, comment='兑换记录ID')
    idempotency_key: Mapped[str] = mapped_column(String(128), nullable=False, unique=True, comment='幂等键')
    user_id: Mapped[str] = mapped_column(String(36), nullable=False, comment='用户ID')
    exchange_direction: Mapped[str] = mapped_column(String(32), nullable=False, server_default=text("'gold_to_silver'"), comment='兑换方向')
    gold_amount: Mapped[Decimal] = mapped_column(Numeric(12, 2), nullable=False, comment='兑换消耗金豆')
    silver_amount: Mapped[int] = mapped_column(Integer, nullable=False, comment='兑换获得银豆')
    exchange_rate: Mapped[int] = mapped_column(Integer, nullable=False, server_default=text('1000'), comment='兑换比例')
    gold_balance_before: Mapped[Optional[Decimal]] = mapped_column(Numeric(12, 2), comment='兑换前金豆余额')
    gold_balance_after: Mapped[Optional[Decimal]] = mapped_column(Numeric(12, 2), comment='兑换后金豆余额')
    silver_balance_before: Mapped[Optional[int]] = mapped_column(Integer, comment='兑换前银豆余额')
    silver_balance_after: Mapped[Optional[int]] = mapped_column(Integer, comment='兑换后银豆余额')
    out_billing_record_id: Mapped[Optional[str]] = mapped_column(String(64), comment='转出账本记录ID')
    in_billing_record_id: Mapped[Optional[str]] = mapped_column(String(64), comment='转入账本记录ID')
    status: Mapped[str] = mapped_column(String(20), nullable=False, server_default=text("'completed'"), comment='状态：completed/failed')
    description: Mapped[Optional[str]] = mapped_column(String(255), comment='描述')
    extra_data: Mapped[Optional[dict]] = mapped_column(JSON, comment='扩展信息')
    created_at: Mapped[datetime.datetime] = mapped_column(DateTime(True), nullable=False, server_default=text('now()'), comment='创建时间')


class RechargeCodeBatches(Base):
    __tablename__ = 'recharge_code_batches'
    __table_args__ = (
        PrimaryKeyConstraint('id', name='recharge_code_batches_pkey'),
        Index('ix_recharge_code_batches_status', 'status'),
        Index('ix_recharge_code_batches_created_at', 'created_at'),
        {'comment': '金豆兑换码批次表'}
    )

    id: Mapped[str] = mapped_column(String(64), primary_key=True, comment='批次ID')
    name: Mapped[str] = mapped_column(String(100), nullable=False, comment='批次名称')
    credit_type: Mapped[str] = mapped_column(String(20), nullable=False, comment='gold/personal_gold/team_gold')
    amount: Mapped[Decimal] = mapped_column(Numeric(12, 2), nullable=False, comment='单码充值金额')
    code_count: Mapped[int] = mapped_column(Integer, nullable=False, comment='生成数量')
    status: Mapped[str] = mapped_column(String(20), nullable=False, server_default=text("'active'"), comment='active/disabled')
    channel: Mapped[Optional[str]] = mapped_column(String(32), comment='售卖/发放渠道')
    expires_at: Mapped[Optional[datetime.datetime]] = mapped_column(DateTime(True), comment='过期时间')
    note: Mapped[Optional[str]] = mapped_column(Text, comment='备注')
    created_by: Mapped[str] = mapped_column(String(36), nullable=False, comment='创建管理员')
    created_at: Mapped[datetime.datetime] = mapped_column(DateTime(True), nullable=False, server_default=text('now()'), comment='创建时间')
    updated_at: Mapped[datetime.datetime] = mapped_column(DateTime(True), nullable=False, server_default=text('now()'), comment='更新时间')


class RechargeCodes(Base):
    __tablename__ = 'recharge_codes'
    __table_args__ = (
        PrimaryKeyConstraint('id', name='recharge_codes_pkey'),
        UniqueConstraint('code_hash', name='recharge_codes_code_hash_key'),
        Index('ix_recharge_codes_batch', 'batch_id'),
        Index('ix_recharge_codes_status', 'status'),
        Index('ix_recharge_codes_used_by', 'used_by'),
        Index('ix_recharge_codes_suffix', 'code_suffix'),
        Index('ix_recharge_codes_order_id', 'order_id'),
        {'comment': '金豆兑换码表，仅保存 hash 和后缀'}
    )

    id: Mapped[str] = mapped_column(String(64), primary_key=True, comment='兑换码ID')
    batch_id: Mapped[str] = mapped_column(String(64), nullable=False, comment='批次ID')
    order_id: Mapped[Optional[str]] = mapped_column(String(64), comment='关联充值订单ID')
    code_hash: Mapped[str] = mapped_column(String(128), nullable=False, unique=True, comment='兑换码哈希')
    code_suffix: Mapped[str] = mapped_column(String(12), nullable=False, comment='兑换码后缀')
    credit_type: Mapped[str] = mapped_column(String(20), nullable=False, comment='gold/personal_gold/team_gold')
    amount: Mapped[Decimal] = mapped_column(Numeric(12, 2), nullable=False, comment='充值金额')
    status: Mapped[str] = mapped_column(String(20), nullable=False, server_default=text("'unused'"), comment='unused/used/disabled/expired')
    used_by: Mapped[Optional[str]] = mapped_column(String(36), comment='兑换用户')
    used_team_id: Mapped[Optional[str]] = mapped_column(String(64), comment='团队码入账团队')
    used_at: Mapped[Optional[datetime.datetime]] = mapped_column(DateTime(True), comment='兑换时间')
    billing_record_id: Mapped[Optional[str]] = mapped_column(String(64), comment='个人金豆账单ID')
    team_record_id: Mapped[Optional[str]] = mapped_column(String(64), comment='团队金豆流水ID')
    expires_at: Mapped[Optional[datetime.datetime]] = mapped_column(DateTime(True), comment='过期时间')
    created_by: Mapped[str] = mapped_column(String(36), nullable=False, comment='创建管理员')
    created_at: Mapped[datetime.datetime] = mapped_column(DateTime(True), nullable=False, server_default=text('now()'), comment='创建时间')
    updated_at: Mapped[datetime.datetime] = mapped_column(DateTime(True), nullable=False, server_default=text('now()'), comment='更新时间')


class RechargeRedemptions(Base):
    __tablename__ = 'recharge_redemptions'
    __table_args__ = (
        PrimaryKeyConstraint('id', name='recharge_redemptions_pkey'),
        UniqueConstraint('code_id', name='recharge_redemptions_code_id_key'),
        Index('ix_recharge_redemptions_user_time', 'user_id', 'created_at'),
        Index('ix_recharge_redemptions_team_time', 'team_id', 'created_at'),
        {'comment': '金豆兑换记录表'}
    )

    id: Mapped[str] = mapped_column(String(64), primary_key=True, comment='兑换记录ID')
    code_id: Mapped[str] = mapped_column(String(64), nullable=False, unique=True, comment='兑换码ID')
    user_id: Mapped[str] = mapped_column(String(36), nullable=False, comment='兑换用户')
    team_id: Mapped[Optional[str]] = mapped_column(String(64), comment='入账团队')
    credit_type: Mapped[str] = mapped_column(String(20), nullable=False, comment='实际入账类型 personal_gold/team_gold')
    amount: Mapped[Decimal] = mapped_column(Numeric(12, 2), nullable=False, comment='充值金额')
    balance_before: Mapped[Optional[Decimal]] = mapped_column(Numeric(12, 2), comment='入账前余额')
    balance_after: Mapped[Optional[Decimal]] = mapped_column(Numeric(12, 2), comment='入账后余额')
    billing_record_id: Mapped[Optional[str]] = mapped_column(String(64), comment='个人金豆账单ID')
    team_record_id: Mapped[Optional[str]] = mapped_column(String(64), comment='团队金豆流水ID')
    status: Mapped[str] = mapped_column(String(20), nullable=False, server_default=text("'completed'"), comment='completed/failed')
    error_message: Mapped[Optional[str]] = mapped_column(Text, comment='失败原因')
    extra_data: Mapped[Optional[dict]] = mapped_column('metadata', JSON, comment='扩展信息')
    created_at: Mapped[datetime.datetime] = mapped_column(DateTime(True), nullable=False, server_default=text('now()'), comment='创建时间')


class RechargeOrders(Base):
    __tablename__ = 'recharge_orders'
    __table_args__ = (
        PrimaryKeyConstraint('id', name='recharge_orders_pkey'),
        UniqueConstraint('order_no', name='recharge_orders_order_no_key'),
        UniqueConstraint('external_order_id', name='recharge_orders_external_order_id_key'),
        Index('ix_recharge_orders_order_no', 'order_no'),
        Index('ix_recharge_orders_user_id_created_at', 'user_id', 'created_at'),
        Index('ix_recharge_orders_status', 'status'),
        Index('ix_recharge_orders_channel', 'channel'),
        Index('ix_recharge_orders_source_type', 'source_type'),
        Index('ix_recharge_orders_created_at', 'created_at'),
        {'comment': '金豆充值订单表'}
    )

    id: Mapped[str] = mapped_column(String(64), primary_key=True, comment='订单ID')
    order_no: Mapped[str] = mapped_column(String(40), nullable=False, unique=True, comment='订单号')
    user_id: Mapped[Optional[str]] = mapped_column(String(36), comment='下单用户ID')
    team_id: Mapped[Optional[str]] = mapped_column(String(64), comment='关联团队ID')
    package_id: Mapped[Optional[str]] = mapped_column(String(64), comment='套餐ID')
    package_name: Mapped[Optional[str]] = mapped_column(String(100), comment='套餐名称')
    amount_paid: Mapped[Decimal] = mapped_column(Numeric(12, 2), nullable=False, comment='订单面额（真源）')
    credited_amount: Mapped[Optional[Decimal]] = mapped_column(Numeric(12, 2), comment='实际已入账金额（按已兑码累加）')
    currency: Mapped[str] = mapped_column(String(8), nullable=False, server_default=text("'CNY'"), comment='币种')
    channel: Mapped[str] = mapped_column(String(32), nullable=False, server_default=text("'manual'"), comment='渠道：wechat/xianyu/manual/campaign/compensation/ldxp')
    source_type: Mapped[str] = mapped_column(String(20), nullable=False, server_default=text("'paid'"), comment='来源类型：paid/manual/compensation/campaign')
    status: Mapped[str] = mapped_column(String(20), nullable=False, server_default=text("'paid'"), comment='状态：pending_payment/paid/issued/redeemed/refunded/cancelled/exception')
    external_order_id: Mapped[Optional[str]] = mapped_column(String(128), unique=True, comment='外部支付订单号')
    external_ref: Mapped[Optional[str]] = mapped_column(String(255), comment='外部参考信息')
    paid_at: Mapped[Optional[datetime.datetime]] = mapped_column(DateTime(True), comment='支付时间')
    issued_at: Mapped[Optional[datetime.datetime]] = mapped_column(DateTime(True), comment='首次发码时间')
    redeemed_at: Mapped[Optional[datetime.datetime]] = mapped_column(DateTime(True), comment='全量兑换完成时间')
    refunded_at: Mapped[Optional[datetime.datetime]] = mapped_column(DateTime(True), comment='退款时间')
    cancelled_at: Mapped[Optional[datetime.datetime]] = mapped_column(DateTime(True), comment='取消时间')
    issued_code_count: Mapped[int] = mapped_column(Integer, nullable=False, server_default=text('0'), comment='已发码数量')
    refund_amount: Mapped[Optional[Decimal]] = mapped_column(Numeric(12, 2), comment='退款金额')
    operator_id: Mapped[Optional[str]] = mapped_column(String(64), comment='人工介入者 user_id')
    note: Mapped[Optional[str]] = mapped_column(Text, comment='备注')
    extra_data: Mapped[Optional[dict]] = mapped_column('metadata', JSON, comment='扩展信息')
    created_at: Mapped[datetime.datetime] = mapped_column(DateTime(True), nullable=False, server_default=text('now()'), comment='创建时间')
    updated_at: Mapped[datetime.datetime] = mapped_column(DateTime(True), nullable=False, server_default=text('now()'), comment='更新时间')


class RechargeFailedAttempts(Base):
    __tablename__ = 'recharge_failed_attempts'
    __table_args__ = (
        PrimaryKeyConstraint('id', name='recharge_failed_attempts_pkey'),
        Index('ix_failed_attempts_user_time', 'user_id', 'created_at'),
        Index('ix_failed_attempts_ip_time', 'ip', 'created_at'),
        Index('ix_failed_attempts_code_hash', 'code_hash', 'created_at'),
        {'comment': '兑换失败尝试记录表（风控/防刷）'}
    )

    id: Mapped[str] = mapped_column(String(64), primary_key=True, comment='记录ID')
    user_id: Mapped[Optional[str]] = mapped_column(String(36), comment='尝试用户')
    ip: Mapped[Optional[str]] = mapped_column(String(64), comment='请求IP')
    code_suffix: Mapped[Optional[str]] = mapped_column(String(12), comment='兑换码后缀')
    code_hash: Mapped[Optional[str]] = mapped_column(String(128), comment='兑换码哈希')
    reason_type: Mapped[Optional[str]] = mapped_column(String(32), comment='失败类型：invalid_code/expired/already_used/no_team/blocked_account/unknown')
    reason: Mapped[Optional[str]] = mapped_column(String(255), comment='失败原因描述')
    created_at: Mapped[datetime.datetime] = mapped_column(DateTime(True), nullable=False, server_default=text('now()'), comment='创建时间')


class RechargeReversalRequests(Base):
    __tablename__ = 'recharge_reversal_requests'
    __table_args__ = (
        PrimaryKeyConstraint('id', name='recharge_reversal_requests_pkey'),
        UniqueConstraint('order_id', name='recharge_reversal_requests_order_id_key'),
        Index('ix_reversal_requests_status', 'status'),
        Index('ix_reversal_requests_created_at', 'created_at'),
        {'comment': '充值订单冲正申请表'}
    )

    id: Mapped[str] = mapped_column(String(64), primary_key=True, comment='申请ID')
    order_id: Mapped[str] = mapped_column(String(64), nullable=False, comment='订单ID')
    order_no: Mapped[Optional[str]] = mapped_column(String(40), comment='订单号')
    user_id: Mapped[Optional[str]] = mapped_column(String(36), comment='下单用户ID')
    team_id: Mapped[Optional[str]] = mapped_column(String(64), comment='关联团队ID')
    requested_by: Mapped[Optional[str]] = mapped_column(String(64), comment='申请人 user_id')
    reason: Mapped[str] = mapped_column(Text, nullable=False, comment='冲正原因')
    status: Mapped[str] = mapped_column(String(20), nullable=False, server_default=text("'pending'"), comment='pending/approved/rejected/completed')
    resolution_note: Mapped[Optional[str]] = mapped_column(Text, comment='处理备注')
    resolved_by: Mapped[Optional[str]] = mapped_column(String(64), comment='处理人 user_id')
    resolved_at: Mapped[Optional[datetime.datetime]] = mapped_column(DateTime(True), comment='处理时间')
    created_at: Mapped[datetime.datetime] = mapped_column(DateTime(True), nullable=False, server_default=text('now()'), comment='创建时间')
    updated_at: Mapped[datetime.datetime] = mapped_column(DateTime(True), nullable=False, server_default=text('now()'), comment='更新时间')


class SeatMaps(Base):
    """Seat map data storage with version control"""
    __tablename__ = 'seat_maps'
    __table_args__ = (
        PrimaryKeyConstraint('id', name='seat_maps_pkey'),
        Index('ix_seat_maps_version', 'version', unique=False),
        Index('ix_seat_maps_updated_at', 'updated_at', unique=False),
        UniqueConstraint('version', name='uq_seat_maps_version'),
        {'comment': 'Seat map data storage table'}
    )

    id: Mapped[int] = mapped_column(Integer, Identity(always=False, start=1, increment=1), primary_key=True, comment='Primary key (auto-increment)')
    version: Mapped[int] = mapped_column(Integer, nullable=False, comment='Version number (optimistic lock)')
    departments: Mapped[list] = mapped_column(JSON, nullable=False, comment='Department list (JSON array)')
    rows: Mapped[list] = mapped_column(JSON, nullable=False, comment='Seat row list (JSON array)')
    seats: Mapped[list] = mapped_column(JSON, nullable=False, comment='Seat list (JSON array)')
    updated_at: Mapped[datetime.datetime] = mapped_column(DateTime(True), server_default=text('now()'), nullable=False, comment='Last update time')
    updated_by_label: Mapped[Optional[str]] = mapped_column(String(40), comment='Updater label')
    created_at: Mapped[datetime.datetime] = mapped_column(DateTime(True), server_default=text('now()'), nullable=False, comment='Creation time')


class OpsBriefingRawItems(Base):
    """运营晨报原始采集资料"""
    __tablename__ = 'ops_briefing_raw_items'
    __table_args__ = (
        PrimaryKeyConstraint('id', name='ops_briefing_raw_items_pkey'),
        UniqueConstraint('url', name='uq_ops_briefing_raw_items_url'),
        Index('ix_ops_briefing_raw_items_date', 'briefing_date'),
        Index('ix_ops_briefing_raw_items_source', 'source_name'),
        Index('ix_ops_briefing_raw_items_category', 'category'),
        {'comment': '美国亚马逊运营晨报原始采集资料'}
    )

    id: Mapped[str] = mapped_column(String(64), primary_key=True, comment='记录ID')
    briefing_date: Mapped[str] = mapped_column(String(10), nullable=False, comment='晨报日期 YYYY-MM-DD')
    title: Mapped[str] = mapped_column(String(500), nullable=False, comment='标题')
    source_name: Mapped[str] = mapped_column(String(120), nullable=False, comment='来源名称')
    source_type: Mapped[str] = mapped_column(String(40), nullable=False, comment='official/news/trend/product_signal')
    url: Mapped[str] = mapped_column(Text, nullable=False, unique=True, comment='原文链接')
    published_at: Mapped[Optional[datetime.datetime]] = mapped_column(DateTime(True), comment='原文发布时间')
    collected_at: Mapped[datetime.datetime] = mapped_column(DateTime(True), nullable=False, server_default=text('now()'), comment='采集时间')
    category: Mapped[str] = mapped_column(String(60), nullable=False, comment='分类')
    credibility: Mapped[str] = mapped_column(String(20), nullable=False, server_default=text("'medium'"), comment='可信度 high/medium/low')
    summary: Mapped[Optional[str]] = mapped_column(Text, comment='原始摘要')
    raw_payload: Mapped[Optional[dict]] = mapped_column(JSON, comment='原始扩展数据')
    collector_id: Mapped[Optional[str]] = mapped_column(String(80), comment='采集器标识')
    created_at: Mapped[datetime.datetime] = mapped_column(DateTime(True), nullable=False, server_default=text('now()'), comment='创建时间')
    updated_at: Mapped[datetime.datetime] = mapped_column(DateTime(True), nullable=False, server_default=text('now()'), comment='更新时间')


class OpsDailyBriefings(Base):
    """运营晨报生成结果"""
    __tablename__ = 'ops_daily_briefings'
    __table_args__ = (
        PrimaryKeyConstraint('id', name='ops_daily_briefings_pkey'),
        UniqueConstraint('briefing_date', name='uq_ops_daily_briefings_date'),
        Index('ix_ops_daily_briefings_status', 'status'),
        {'comment': '美国亚马逊运营晨报每日结果'}
    )

    id: Mapped[str] = mapped_column(String(64), primary_key=True, comment='晨报ID')
    briefing_date: Mapped[str] = mapped_column(String(10), nullable=False, unique=True, comment='晨报日期 YYYY-MM-DD')
    status: Mapped[str] = mapped_column(String(20), nullable=False, server_default=text("'empty'"), comment='ready/empty/partial_failed')
    summary: Mapped[Optional[str]] = mapped_column(Text, comment='今日一句话总结')
    official_updates: Mapped[Optional[list]] = mapped_column(JSON, comment='Amazon 官方动态')
    ecommerce_news: Mapped[Optional[list]] = mapped_column(JSON, comment='行业资讯快报')
    product_signals: Mapped[Optional[list]] = mapped_column(JSON, comment='公开选品信号')
    action_items: Mapped[Optional[list]] = mapped_column(JSON, comment='今日建议动作')
    warnings: Mapped[Optional[list]] = mapped_column(JSON, comment='数据质量提示')
    source_stats: Mapped[Optional[dict]] = mapped_column(JSON, comment='来源统计')
    generated_at: Mapped[Optional[datetime.datetime]] = mapped_column(DateTime(True), comment='生成时间')
    created_at: Mapped[datetime.datetime] = mapped_column(DateTime(True), nullable=False, server_default=text('now()'), comment='创建时间')
    updated_at: Mapped[datetime.datetime] = mapped_column(DateTime(True), nullable=False, server_default=text('now()'), comment='更新时间')
