import hmac
import time
import uuid
from datetime import datetime, timedelta, timezone
from typing import Any, Optional
from zoneinfo import ZoneInfo

from sqlalchemy import func
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.orm import Session

from storage.database.shared.model import (
    MarsSpecialQuotaAccounts,
    MarsSpecialQuotaTransactions,
    ReferralRewardRecords,
    Tasks,
    UserReferralRelations,
    Users,
)


DAILY_LIMIT = 5
REFERRAL_GRANT = 20
SUBMISSION_LEASE_SECONDS = 300
UNKNOWN_RECONCILE_HOURS = 24
UNKNOWN_PENDING_RELEASE_MINUTES = 10
SHANGHAI = ZoneInfo("Asia/Shanghai")
class MarsSpecialQuotaError(ValueError):
    def __init__(self, message: str, code: int = 400):
        super().__init__(message)
        self.code = code


class MarsSpecialQuotaManager:
    @staticmethod
    def choose_source(*, unlimited: bool, daily_used: int, permanent_remaining: int) -> Optional[str]:
        if unlimited:
            return "internal"
        if daily_used < DAILY_LIMIT:
            return "daily"
        if permanent_remaining > 0:
            return "permanent"
        return None

    @staticmethod
    def _now() -> datetime:
        return datetime.now(timezone.utc)

    @classmethod
    def _quota_date(cls) -> str:
        return cls._now().astimezone(SHANGHAI).date().isoformat()

    @classmethod
    def _next_reset_ms(cls) -> int:
        now = cls._now().astimezone(SHANGHAI)
        tomorrow = datetime.combine(now.date() + timedelta(days=1), datetime.min.time(), SHANGHAI)
        return int(tomorrow.timestamp() * 1000)

    @staticmethod
    def _serialize_task(task: Tasks) -> dict[str, Any]:
        return {
            "id": task.id,
            "user_id": task.user_id,
            "team_id": task.team_id,
            "platform": task.platform,
            "platform_task_id": task.platform_task_id,
            "type": task.type,
            "status": task.status,
            "workflow_parameters": task.workflow_parameters,
            "parameter_snapshot": task.parameter_snapshot,
            "result": task.result,
            "error": task.error,
            "batch_id": task.batch_id,
            "connection_mode": task.connection_mode,
            "created_at": task.created_at,
            "updated_at": task.updated_at,
            "completed_at": task.completed_at,
            "failed_at": task.failed_at,
        }

    @staticmethod
    def _ensure_account(db: Session, user_id: str) -> MarsSpecialQuotaAccounts:
        db.execute(
            pg_insert(MarsSpecialQuotaAccounts)
            .values(user_id=user_id, permanent_remaining=0)
            .on_conflict_do_nothing(index_elements=[MarsSpecialQuotaAccounts.user_id])
        )
        return (
            db.query(MarsSpecialQuotaAccounts)
            .filter(MarsSpecialQuotaAccounts.user_id == user_id)
            .with_for_update()
            .one()
        )

    @classmethod
    def _daily_used(cls, db: Session, user_id: str, quota_date: str) -> int:
        return int(
            db.query(func.count(MarsSpecialQuotaTransactions.id))
            .filter(
                MarsSpecialQuotaTransactions.user_id == user_id,
                MarsSpecialQuotaTransactions.transaction_type == "usage",
                MarsSpecialQuotaTransactions.source == "daily",
                MarsSpecialQuotaTransactions.quota_date == quota_date,
                MarsSpecialQuotaTransactions.status.in_(["reserved", "consumed"]),
            )
            .scalar()
            or 0
        )

    @classmethod
    def _status_data(
        cls,
        db: Session,
        user: Users,
        account: MarsSpecialQuotaAccounts,
    ) -> dict[str, Any]:
        quota_date = cls._quota_date()
        daily_used = cls._daily_used(db, user.user_id, quota_date)
        unlimited = user.tier == "internal_demo"
        return {
            "unlimited": unlimited,
            "daily_limit": DAILY_LIMIT,
            "daily_used": daily_used,
            "daily_remaining": max(0, DAILY_LIMIT - daily_used),
            "permanent_remaining": int(account.permanent_remaining or 0),
            "next_daily_reset_at": cls._next_reset_ms(),
        }

    @classmethod
    def get_status(cls, db: Session, user_id: str) -> dict[str, Any]:
        user = db.query(Users).filter(Users.user_id == user_id).first()
        if not user or user.account_status != "active":
            raise MarsSpecialQuotaError("用户不存在或账号不可用", 404)
        account = cls._ensure_account(db, user_id)
        return cls._status_data(db, user, account)

    @staticmethod
    def _validate_task_data(user_id: str, task_data: dict[str, Any]) -> tuple[str, str]:
        task_id = str(task_data.get("id") or "").strip()
        task_type = str(task_data.get("type") or "").strip()
        platform = str(task_data.get("platform") or "").strip()
        if not task_id:
            raise MarsSpecialQuotaError("task_data.id 不能为空")
        if platform != "local_sub2api":
            raise MarsSpecialQuotaError("火星特供任务 platform 必须为 local_sub2api")
        if task_type not in {"image", "video", "audio"}:
            raise MarsSpecialQuotaError("task_data.type 无效")
        incoming_user_id = str(task_data.get("user_id") or user_id).strip()
        if incoming_user_id != user_id:
            raise MarsSpecialQuotaError("task_data.user_id 与请求用户不一致", 403)
        return task_id, task_type

    @classmethod
    def create_task(cls, db: Session, user_id: str, task_data: dict[str, Any]) -> dict[str, Any]:
        task_id, task_type = cls._validate_task_data(user_id, task_data)
        user = (
            db.query(Users)
            .filter(Users.user_id == user_id)
            .with_for_update()
            .first()
        )
        if not user or user.account_status != "active":
            raise MarsSpecialQuotaError("用户不存在或账号不可用", 404)

        existing = db.query(Tasks).filter(Tasks.id == task_id).with_for_update().first()
        if existing:
            if existing.user_id != user_id or existing.platform != "local_sub2api":
                raise MarsSpecialQuotaError("task_id 已被其他任务占用", 409)
            usage = (
                db.query(MarsSpecialQuotaTransactions)
                .filter(
                    MarsSpecialQuotaTransactions.task_id == task_id,
                    MarsSpecialQuotaTransactions.transaction_type == "usage",
                    MarsSpecialQuotaTransactions.user_id == user_id,
                )
                .first()
            )
            if not usage:
                raise MarsSpecialQuotaError("任务存在但缺少火星特供预占流水", 409)
            return {
                "task": cls._serialize_task(existing),
                "status": existing.status,
                "quota_source": usage.source,
                "idempotent": True,
            }

        account = cls._ensure_account(db, user_id)
        quota_date = cls._quota_date()
        daily_used = cls._daily_used(db, user_id, quota_date)
        source = cls.choose_source(
            unlimited=user.tier == "internal_demo",
            daily_used=daily_used,
            permanent_remaining=int(account.permanent_remaining or 0),
        )
        if not source:
            raise MarsSpecialQuotaError("quota exhausted", 429)
        if source == "permanent":
            account.permanent_remaining -= 1
            account.updated_at = cls._now()

        now_ms = str(int(time.time() * 1000))
        platform_task_id = str(task_data.get("platform_task_id") or "").strip() or f"pending:{task_id}"
        task = Tasks(
            id=task_id,
            user_id=user_id,
            team_id=task_data.get("team_id"),
            platform="local_sub2api",
            platform_task_id=platform_task_id,
            type=task_type,
            status="running",
            workflow_parameters=task_data.get("workflow_parameters"),
            parameter_snapshot=task_data.get("parameter_snapshot"),
            batch_id=task_data.get("batch_id"),
            connection_mode=task_data.get("connection_mode") or "http",
            deduction_result=task_data.get("deduction_result"),
            created_at=now_ms,
            updated_at=now_ms,
            status_updated_at=now_ms,
            started_at=now_ms,
        )
        usage = MarsSpecialQuotaTransactions(
            id=str(uuid.uuid4()),
            idempotency_key=f"mars_special:usage:{task_id}",
            user_id=user_id,
            task_id=task_id,
            transaction_type="usage",
            source=source,
            amount=0 if source == "internal" else -1,
            status="reserved",
            quota_date=quota_date,
            extra_data={"platform": "local_sub2api"},
            created_at=cls._now(),
            updated_at=cls._now(),
        )
        db.add(task)
        db.add(usage)
        db.flush()
        return {
            "task": cls._serialize_task(task),
            "status": task.status,
            "quota_source": source,
            "idempotent": False,
        }

    @classmethod
    def _lock_task_and_usage(
        cls, db: Session, user_id: str, task_id: str
    ) -> tuple[Tasks, MarsSpecialQuotaTransactions]:
        task = db.query(Tasks).filter(Tasks.id == task_id).with_for_update().first()
        if not task or task.user_id != user_id or task.platform != "local_sub2api":
            raise MarsSpecialQuotaError("火星特供任务不存在或无权访问", 404)
        if task.is_deleted:
            raise MarsSpecialQuotaError("已删除任务不能更新", 409)
        usage = (
            db.query(MarsSpecialQuotaTransactions)
            .filter(
                MarsSpecialQuotaTransactions.task_id == task_id,
                MarsSpecialQuotaTransactions.transaction_type == "usage",
                MarsSpecialQuotaTransactions.user_id == user_id,
            )
            .with_for_update()
            .first()
        )
        if not usage:
            raise MarsSpecialQuotaError("任务缺少火星特供预占流水", 409)
        return task, usage

    @classmethod
    def acquire_submission(
        cls,
        db: Session,
        user_id: str,
        task_id: str,
        claimant_id: Optional[str],
        lease_seconds: Optional[int],
    ) -> dict[str, Any]:
        task, usage = cls._lock_task_and_usage(db, user_id, task_id)
        if task.status != "running" or usage.status != "reserved":
            return {
                "claimed": False,
                "claim_token": None,
                "lease_expires_at": None,
                "reason": "task_not_submittable",
                "task": cls._serialize_task(task),
            }

        extra = dict(usage.extra_data or {})
        if extra.get("provider_accepted_at"):
            return {
                "claimed": False,
                "claim_token": None,
                "lease_expires_at": extra.get("submission_lease_expires_at"),
                "reason": "provider_already_accepted",
                "task": cls._serialize_task(task),
            }

        now = cls._now()
        lease_expires_at = None
        raw_expiry = extra.get("submission_lease_expires_at")
        if isinstance(raw_expiry, str):
            try:
                lease_expires_at = datetime.fromisoformat(raw_expiry)
            except ValueError:
                lease_expires_at = None
        if lease_expires_at and lease_expires_at.tzinfo is None:
            lease_expires_at = lease_expires_at.replace(tzinfo=timezone.utc)

        clean_claimant_id = str(claimant_id or "").strip()
        if not clean_claimant_id:
            raise MarsSpecialQuotaError("claimant_id 不能为空")
        if lease_expires_at and lease_expires_at > now:
            return {
                "claimed": False,
                "claim_token": None,
                "lease_expires_at": lease_expires_at.isoformat(),
                "reason": "lease_held",
                "task": cls._serialize_task(task),
            }

        duration = min(max(int(lease_seconds or SUBMISSION_LEASE_SECONDS), 15), 300)
        claim_token = str(uuid.uuid4())
        lease_expires_at = now + timedelta(seconds=duration)
        usage.extra_data = {
            **extra,
            "submission_claimant_id": clean_claimant_id,
            "submission_claim_token": claim_token,
            "submission_claimed_at": now.isoformat(),
            "submission_lease_expires_at": lease_expires_at.isoformat(),
        }
        usage.updated_at = now
        db.flush()
        return {
            "claimed": True,
            "claim_token": claim_token,
            "lease_expires_at": lease_expires_at.isoformat(),
            "reason": "claimed",
            "task": cls._serialize_task(task),
        }

    @classmethod
    def provider_accepted(
        cls,
        db: Session,
        user_id: str,
        task_id: str,
        provider_task_id: Optional[str],
        result: Optional[Any],
        claim_token: Optional[str],
    ) -> dict[str, Any]:
        task, usage = cls._lock_task_and_usage(db, user_id, task_id)
        extra = dict(usage.extra_data or {})
        clean_provider_task_id = str(provider_task_id or "").strip()
        if not clean_provider_task_id:
            raise MarsSpecialQuotaError("provider_task_id 不能为空")
        if extra.get("provider_accepted_at"):
            accepted_provider_task_id = str(
                extra.get("provider_task_id") or task.platform_task_id or ""
            ).strip()
            if clean_provider_task_id == accepted_provider_task_id:
                return {
                    "task": cls._serialize_task(task),
                    "usage_status": usage.status,
                    "idempotent": True,
                }
            raise MarsSpecialQuotaError("provider_task_id 与已确认任务冲突", 409)
        if task.status in {"completed", "failed"}:
            return {"task": cls._serialize_task(task), "usage_status": usage.status, "idempotent": True}
        expected_claim_token = str(extra.get("submission_claim_token") or "")
        if not expected_claim_token or not claim_token or not hmac.compare_digest(claim_token, expected_claim_token):
            raise MarsSpecialQuotaError("提交 claim 无效或已过期", 409)
        # Expiry controls takeover. If this token is still current, no newer
        # worker has claimed the task, so a late provider acknowledgement is safe.
        task.platform_task_id = clean_provider_task_id
        if result is not None:
            task.result = result
        usage.extra_data = {
            **extra,
            "unknown": False,
            "provider_task_id": clean_provider_task_id,
            "provider_accepted_at": cls._now().isoformat(),
        }
        now_ms = str(int(time.time() * 1000))
        task.status = "running"
        task.confirmation_state = "confirmed"
        task.updated_at = now_ms
        task.status_updated_at = now_ms
        db.flush()
        return {"task": cls._serialize_task(task), "usage_status": usage.status, "idempotent": False}

    @classmethod
    def renew_submission(
        cls,
        db: Session,
        user_id: str,
        task_id: str,
        claim_token: Optional[str],
        lease_seconds: Optional[int],
    ) -> dict[str, Any]:
        task, usage = cls._lock_task_and_usage(db, user_id, task_id)
        if task.status != "running" or usage.status != "reserved":
            raise MarsSpecialQuotaError("任务已不可续租", 409)
        extra = dict(usage.extra_data or {})
        if extra.get("provider_accepted_at"):
            raise MarsSpecialQuotaError("供应商任务已确认，无需续租", 409)
        expected_claim_token = str(extra.get("submission_claim_token") or "")
        if not expected_claim_token or not claim_token or not hmac.compare_digest(
            claim_token, expected_claim_token
        ):
            raise MarsSpecialQuotaError("提交 claim 无效", 409)

        duration = min(max(int(lease_seconds or SUBMISSION_LEASE_SECONDS), 15), 300)
        now = cls._now()
        lease_expires_at = now + timedelta(seconds=duration)
        usage.extra_data = {
            **extra,
            "submission_lease_expires_at": lease_expires_at.isoformat(),
            "submission_renewed_at": now.isoformat(),
        }
        usage.updated_at = now
        db.flush()
        return {
            "renewed": True,
            "lease_expires_at": lease_expires_at.isoformat(),
            "task": cls._serialize_task(task),
        }

    @classmethod
    def _grant_account(cls, db: Session, user_id: str, amount: int) -> None:
        account = cls._ensure_account(db, user_id)
        account.permanent_remaining += amount
        account.updated_at = cls._now()

    @classmethod
    def _grant_referral_if_needed(cls, db: Session, task: Tasks) -> list[dict[str, Any]]:
        relation = (
            db.query(UserReferralRelations)
            .filter(UserReferralRelations.referee_user_id == task.user_id)
            .with_for_update()
            .first()
        )
        if not relation or relation.reward_status != "pending":
            return []

        completed_tasks = (
            db.query(Tasks)
            .filter(
                Tasks.user_id == relation.referee_user_id,
                Tasks.platform == "local_sub2api",
                Tasks.status == "completed",
                Tasks.is_deleted.is_(False),
            )
            .all()
        )
        valid_tasks = [row for row in completed_tasks if cls._has_valid_result(row.result)]
        if not valid_tasks:
            return []
        reward_task = min(
            valid_tasks,
            key=lambda row: (
                int(str(row.completed_at or row.updated_at or row.created_at or 0)),
                str(row.id),
            ),
        )

        historical_reward = (
            db.query(ReferralRewardRecords)
            .filter(ReferralRewardRecords.relation_id == relation.id)
            .first()
        )
        if historical_reward:
            relation.reward_status = "rewarded"
            relation.reward_granted_at = relation.reward_granted_at or historical_reward.created_at
            relation.first_completed_task_id = (
                relation.first_completed_task_id or historical_reward.task_id
            )
            relation.updated_at = cls._now()
            return []

        policy = relation.reward_policy_version or "gold_v1"
        recipients = [("grant_referrer", relation.referrer_user_id)]
        if policy == "mars_quota_v2":
            recipients.append(("grant_referee", relation.referee_user_id))

        grants = []
        for transaction_type, recipient_user_id in sorted(recipients, key=lambda item: item[1]):
            existing = (
                db.query(MarsSpecialQuotaTransactions)
                .filter(
                    MarsSpecialQuotaTransactions.idempotency_key
                    == f"mars_special:referral:{relation.id}:{transaction_type}"
                )
                .first()
            )
            if existing:
                grants.append({"user_id": recipient_user_id, "amount": existing.amount})
                continue
            cls._grant_account(db, recipient_user_id, REFERRAL_GRANT)
            grant = MarsSpecialQuotaTransactions(
                id=str(uuid.uuid4()),
                idempotency_key=f"mars_special:referral:{relation.id}:{transaction_type}",
                user_id=recipient_user_id,
                task_id=reward_task.id,
                transaction_type=transaction_type,
                source="referral",
                amount=REFERRAL_GRANT,
                status="completed",
                related_id=relation.id,
                extra_data={"policy_version": policy, "referee_user_id": relation.referee_user_id},
                created_at=cls._now(),
                updated_at=cls._now(),
            )
            db.add(grant)
            grants.append({"user_id": recipient_user_id, "amount": REFERRAL_GRANT})

        relation.reward_status = "rewarded"
        relation.reward_granted_at = cls._now()
        relation.first_completed_task_id = reward_task.id
        relation.updated_at = cls._now()
        return grants

    @staticmethod
    def _has_valid_result(result: Any) -> bool:
        if not isinstance(result, dict):
            return False

        def is_non_empty_output(value: Any) -> bool:
            if isinstance(value, str):
                return bool(value.strip())
            if isinstance(value, dict):
                return bool(value) and any(is_non_empty_output(item) for item in value.values())
            if isinstance(value, list):
                return any(is_non_empty_output(item) for item in value)
            return False

        for key in ("files", "imageUrls", "outputs"):
            values = result.get(key)
            if isinstance(values, list) and any(is_non_empty_output(value) for value in values):
                return True
        return False

    @classmethod
    def complete(
        cls,
        db: Session,
        user_id: str,
        task_id: str,
        provider_task_id: Optional[str],
        result: Optional[Any],
    ) -> dict[str, Any]:
        task, usage = cls._lock_task_and_usage(db, user_id, task_id)
        if task.status == "failed" or usage.status == "released":
            raise MarsSpecialQuotaError("失败任务不能改为完成", 409)
        effective_result = result if result is not None else task.result
        if not cls._has_valid_result(effective_result):
            raise MarsSpecialQuotaError("完成任务必须包含非空 files/imageUrls/outputs", 400)
        if task.status == "completed" and usage.status == "consumed":
            if provider_task_id:
                task.platform_task_id = provider_task_id.strip()
            if result is not None:
                task.result = result
            task.updated_at = str(int(time.time() * 1000))
            grants = cls._grant_referral_if_needed(db, task)
            db.flush()
            return {"task": cls._serialize_task(task), "usage_status": usage.status, "grants": grants, "idempotent": True}
        if provider_task_id:
            task.platform_task_id = provider_task_id.strip()
        if result is not None:
            task.result = result
        now_ms = str(int(time.time() * 1000))
        task.status = "completed"
        task.error = None
        task.completed_at = task.completed_at or now_ms
        task.failed_at = None
        task.status_updated_at = now_ms
        task.updated_at = now_ms
        task.confirmation_state = "confirmed"
        usage.status = "consumed"
        usage.updated_at = cls._now()
        grants = cls._grant_referral_if_needed(db, task)
        db.flush()
        return {"task": cls._serialize_task(task), "usage_status": usage.status, "grants": grants, "idempotent": False}

    @classmethod
    def fail(
        cls,
        db: Session,
        user_id: str,
        task_id: str,
        error: Optional[str],
        reason: Optional[str],
    ) -> dict[str, Any]:
        task, usage = cls._lock_task_and_usage(db, user_id, task_id)
        if task.status == "completed" or usage.status == "consumed":
            raise MarsSpecialQuotaError("已完成任务不能改为失败", 409)
        if task.status == "failed" and usage.status == "released":
            return {"task": cls._serialize_task(task), "usage_status": usage.status, "idempotent": True}
        cls._fail_locked_task(db, task, usage, error=error, reason=reason)
        db.flush()
        return {"task": cls._serialize_task(task), "usage_status": usage.status, "idempotent": False}

    @classmethod
    def _fail_locked_task(
        cls,
        db: Session,
        task: Tasks,
        usage: MarsSpecialQuotaTransactions,
        *,
        error: Optional[str],
        reason: Optional[str],
    ) -> None:
        if usage.source == "permanent" and usage.status == "reserved":
            cls._grant_account(db, task.user_id, 1)
        usage.status = "released"
        usage.updated_at = cls._now()
        usage.extra_data = {**(usage.extra_data or {}), "failure_reason": reason or error}
        now_ms = str(int(time.time() * 1000))
        task.status = "failed"
        task.error = error or reason or "火星特供任务明确失败"
        task.failed_at = task.failed_at or now_ms
        task.completed_at = None
        task.status_updated_at = now_ms
        task.updated_at = now_ms
        task.confirmation_state = "confirmed"
        task.final_reason = "provider_failed"

    @classmethod
    def mark_unknown(
        cls,
        db: Session,
        user_id: str,
        task_id: str,
        provider_task_id: Optional[str],
        result: Optional[Any],
        reason: Optional[str],
    ) -> dict[str, Any]:
        task, usage = cls._lock_task_and_usage(db, user_id, task_id)
        if usage.status in {"consumed", "released"}:
            return {"task": cls._serialize_task(task), "usage_status": usage.status, "idempotent": True}
        usage.updated_at = cls._now()
        usage.extra_data = {
            **(usage.extra_data or {}),
            "unknown": True,
            "unknown_reason": reason,
            "unknown_at": cls._now().isoformat(),
        }
        if provider_task_id:
            task.platform_task_id = provider_task_id.strip()
        if result is not None:
            task.result = result
        snapshot = dict(task.parameter_snapshot or {})
        snapshot["marsSpecialQuotaState"] = "unknown"
        snapshot["marsSpecialQuotaUnknownReason"] = reason
        task.parameter_snapshot = snapshot
        task.updated_at = str(int(time.time() * 1000))
        db.flush()
        return {"task": cls._serialize_task(task), "usage_status": usage.status, "idempotent": False}

    @classmethod
    def reconcile_reserved(cls, db: Session, limit: int = 100) -> dict[str, int]:
        unknown_cutoff = cls._now() - timedelta(hours=UNKNOWN_RECONCILE_HOURS)
        pending_release_cutoff = cls._now() - timedelta(minutes=UNKNOWN_PENDING_RELEASE_MINUTES)
        row_ids = (
            db.query(MarsSpecialQuotaTransactions.id)
            .filter(
                MarsSpecialQuotaTransactions.transaction_type == "usage",
                MarsSpecialQuotaTransactions.status == "reserved",
                (
                    func.coalesce(
                        MarsSpecialQuotaTransactions.extra_data["unknown"].as_boolean(), False
                    ).is_(False)
                    | (MarsSpecialQuotaTransactions.updated_at <= unknown_cutoff)
                    | (MarsSpecialQuotaTransactions.updated_at <= pending_release_cutoff)
                ),
            )
            .order_by(MarsSpecialQuotaTransactions.created_at.asc())
            .limit(min(max(limit, 1), 500))
            .all()
        )
        reconciled = 0
        released = 0
        for (row_id,) in row_ids:
            candidate = db.query(MarsSpecialQuotaTransactions).filter(
                MarsSpecialQuotaTransactions.id == row_id
            ).first()
            if not candidate or not candidate.task_id:
                continue
            task = db.query(Tasks).filter(Tasks.id == candidate.task_id).with_for_update().first()
            row = (
                db.query(MarsSpecialQuotaTransactions)
                .filter(MarsSpecialQuotaTransactions.id == row_id)
                .with_for_update()
                .first()
            )
            if not row or row.status != "reserved":
                continue
            if not task or task.platform != "local_sub2api" or task.is_deleted:
                continue
            is_unknown = isinstance(row.extra_data, dict) and row.extra_data.get("unknown") is True
            platform_task_id = str(task.platform_task_id or "").strip()
            has_real_provider_task_id = bool(platform_task_id) and not platform_task_id.startswith("pending:")
            if (
                is_unknown
                and not has_real_provider_task_id
                and not cls._has_valid_result(task.result)
                and row.updated_at <= pending_release_cutoff
            ):
                cls._fail_locked_task(
                    db,
                    task,
                    row,
                    error="供应商创建状态超时且未取得真实任务号，本次生成未完成",
                    reason="unknown_pending_without_provider_task_id",
                )
                row.extra_data = {
                    **(row.extra_data or {}),
                    "unknown": False,
                    "unknown_closed_at": cls._now().isoformat(),
                    "unknown_resolution": "released_without_provider_task_id",
                }
                released += 1
                continue
            if is_unknown and row.updated_at <= unknown_cutoff:
                row.status = "consumed"
                row.updated_at = cls._now()
                row.extra_data = {
                    **(row.extra_data or {}),
                    "unknown_closed_at": cls._now().isoformat(),
                    "unknown_resolution": "consumed_after_timeout",
                }
                now_ms = str(int(time.time() * 1000))
                task.status = "failed"
                task.error = "供应商状态长时间无法确认，次数已核销并转人工复核"
                task.failed_at = task.failed_at or now_ms
                task.completed_at = None
                task.status_updated_at = now_ms
                task.updated_at = now_ms
                task.confirmation_state = "confirmed"
                task.final_reason = "unknown_timeout_consumed"
                reconciled += 1
                continue
            if task.status == "completed":
                row.status = "consumed"
                row.updated_at = cls._now()
                cls._grant_referral_if_needed(db, task)
                reconciled += 1
            elif task.status in {"failed", "cancelled"}:
                if row.source == "permanent":
                    cls._grant_account(db, row.user_id, 1)
                row.status = "released"
                row.updated_at = cls._now()
                released += 1
        return {"consumed": reconciled, "released": released}
