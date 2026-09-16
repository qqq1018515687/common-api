import secrets
import uuid
from datetime import datetime, timezone
from typing import Any, Optional

from sqlalchemy import func
from sqlalchemy.orm import Session

from storage.database.amounts import gold_amount_to_number
from storage.database.shared.model import (
    ReferralRewardRecords,
    MarsSpecialQuotaTransactions,
    UserReferralProfiles,
    UserReferralRelations,
    Users,
)


REFERRAL_CODE_ALPHABET = "ABCDEFGHJKLMNPQRSTUVWXYZ23456789"


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _normalize_code(value: str) -> str:
    return "".join(ch for ch in str(value or "").strip().upper() if ch.isalnum())


def _to_epoch_ms(value: Optional[datetime]) -> Optional[int]:
    if not value:
        return None
    if value.tzinfo is None:
        value = value.replace(tzinfo=timezone.utc)
    return int(value.timestamp() * 1000)


def _generate_referral_code() -> str:
    return "HX" + "".join(secrets.choice(REFERRAL_CODE_ALPHABET) for _ in range(8))


def _ensure_profile(db: Session, user_id: str) -> UserReferralProfiles:
    profile = (
        db.query(UserReferralProfiles)
        .filter(UserReferralProfiles.user_id == user_id)
        .first()
    )
    if profile:
        return profile

    while True:
        code = _generate_referral_code()
        exists = (
            db.query(UserReferralProfiles)
            .filter(UserReferralProfiles.referral_code == code)
            .first()
        )
        if not exists:
            break

    profile = UserReferralProfiles(
        id=str(uuid.uuid4()),
        user_id=user_id,
        referral_code=code,
        created_at=_now(),
        updated_at=_now(),
    )
    db.add(profile)
    db.flush()
    return profile


def _serialize_profile(profile: UserReferralProfiles) -> dict[str, Any]:
    return {
        "user_id": profile.user_id,
        "referral_code": profile.referral_code,
        "created_at": _to_epoch_ms(profile.created_at),
    }


def _serialize_relation(relation: UserReferralRelations) -> dict[str, Any]:
    return {
        "id": relation.id,
        "referrer_user_id": relation.referrer_user_id,
        "referee_user_id": relation.referee_user_id,
        "referral_code": relation.referral_code,
        "reward_status": relation.reward_status,
        "bound_at": _to_epoch_ms(relation.bound_at),
        "reward_granted_at": _to_epoch_ms(relation.reward_granted_at),
        "first_completed_task_id": relation.first_completed_task_id,
        "reward_policy_version": relation.reward_policy_version,
    }


def _serialize_reward(record: ReferralRewardRecords) -> dict[str, Any]:
    return {
        "id": record.id,
        "relation_id": record.relation_id,
        "referrer_user_id": record.referrer_user_id,
        "referee_user_id": record.referee_user_id,
        "task_id": record.task_id,
        "reward_credit_type": record.reward_credit_type,
        "reward_amount": gold_amount_to_number(record.reward_amount),
        "billing_record_id": record.billing_record_id,
        "description": record.description,
        "metadata": record.extra_data,
        "created_at": _to_epoch_ms(record.created_at),
    }


def get_or_create_profile(db: Session, user_id: str) -> dict[str, Any]:
    user = db.query(Users).filter(Users.user_id == user_id).first()
    if not user:
        raise ValueError("用户不存在")
    profile = _ensure_profile(db, user_id)
    relation = (
        db.query(UserReferralRelations)
        .filter(UserReferralRelations.referee_user_id == user_id)
        .first()
    )
    reward_count = (
        db.query(func.count(ReferralRewardRecords.id))
        .filter(ReferralRewardRecords.referrer_user_id == user_id)
        .scalar()
        or 0
    )
    reward_total = (
        db.query(func.coalesce(func.sum(ReferralRewardRecords.reward_amount), 0))
        .filter(ReferralRewardRecords.referrer_user_id == user_id)
        .scalar()
    )
    reward_rows = (
        db.query(ReferralRewardRecords)
        .filter(ReferralRewardRecords.referrer_user_id == user_id)
        .order_by(ReferralRewardRecords.created_at.desc())
        .limit(20)
        .all()
    )
    quota_reward_count = (
        db.query(func.count(MarsSpecialQuotaTransactions.id))
        .filter(
            MarsSpecialQuotaTransactions.user_id == user_id,
            MarsSpecialQuotaTransactions.transaction_type == "grant_referrer",
            MarsSpecialQuotaTransactions.status == "completed",
        )
        .scalar()
        or 0
    )
    quota_reward_total = (
        db.query(func.coalesce(func.sum(MarsSpecialQuotaTransactions.amount), 0))
        .filter(
            MarsSpecialQuotaTransactions.user_id == user_id,
            MarsSpecialQuotaTransactions.transaction_type == "grant_referrer",
            MarsSpecialQuotaTransactions.status == "completed",
        )
        .scalar()
        or 0
    )
    return {
        "profile": _serialize_profile(profile),
        "bound_relation": _serialize_relation(relation) if relation else None,
        "reward_summary": {
            "reward_count": int(reward_count),
            "reward_total": gold_amount_to_number(reward_total),
            "quota_reward_count": int(quota_reward_count),
            "quota_reward_total": int(quota_reward_total),
        },
        "reward_records": [_serialize_reward(row) for row in reward_rows],
    }


def apply_referral_on_register(db: Session, user: Users, referral_code: str) -> None:
    normalized_code = _normalize_code(referral_code)
    if not normalized_code:
        raise ValueError("邀请码不能为空")

    referrer_profile = (
        db.query(UserReferralProfiles)
        .filter(UserReferralProfiles.referral_code == normalized_code)
        .first()
    )
    if not referrer_profile:
        raise ValueError("邀请码不存在")
    if referrer_profile.user_id == user.user_id:
        raise ValueError("不能绑定自己的邀请码")

    existing_relation = (
        db.query(UserReferralRelations)
        .filter(UserReferralRelations.referee_user_id == user.user_id)
        .first()
    )
    if existing_relation:
        raise ValueError("该账号已绑定邀请码")

    relation = UserReferralRelations(
        id=str(uuid.uuid4()),
        referrer_user_id=referrer_profile.user_id,
        referee_user_id=user.user_id,
        referral_code=normalized_code,
        reward_status="pending",
        reward_policy_version="mars_quota_v2",
        bound_at=_now(),
        created_at=_now(),
        updated_at=_now(),
    )
    db.add(relation)
