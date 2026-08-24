import secrets
import uuid
from datetime import datetime, timedelta, timezone
from decimal import Decimal
import logging
from typing import Any, Optional

from sqlalchemy import func
from sqlalchemy.orm import Session

from storage.database.amounts import gold_amount_to_number, normalize_gold_amount
from storage.database.billing_manager import _insert_billing_record, _validate_gold_schema_for_credit_type
from storage.database.shared.model import (
    ReferralRewardRecords,
    Tasks,
    UserReferralProfiles,
    UserReferralRelations,
    Users,
)


logger = logging.getLogger(__name__)


REFERRAL_REWARD_AMOUNT = Decimal("3.00")
REFERRAL_BIND_WINDOW_HOURS = 24
REFERRAL_CODE_ALPHABET = "ABCDEFGHJKLMNPQRSTUVWXYZ23456789"
REGISTER_INVITE_GOLD_BONUS = Decimal("3.00")


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


def _has_effective_completed_generation_task(db: Session, user_id: str) -> bool:
    rows = (
        db.query(Tasks)
        .filter(
            Tasks.user_id == user_id,
            Tasks.status == "completed",
            Tasks.is_deleted.is_(False),
            Tasks.type.in_(["image", "video", "audio"]),
        )
        .all()
    )
    for task in rows:
        result = task.result_fallback if isinstance(task.result_fallback, dict) and task.result_fallback else task.result
        if isinstance(result, dict):
            for key in ("files", "imageUrls", "outputs"):
                value = result.get(key)
                if isinstance(value, list) and value:
                    return True
    return False


def _task_has_displayable_result(task: Tasks) -> bool:
    result = (
        task.result_fallback
        if isinstance(task.result_fallback, dict) and task.result_fallback
        else task.result
    )
    if not isinstance(result, dict):
        return False
    for key in ("files", "imageUrls", "outputs"):
        value = result.get(key)
        if isinstance(value, list) and value:
            return True
    return False


def _task_sort_key(task: Tasks) -> tuple[int, int, str]:
    completed_at = int(str(task.completed_at or 0) or 0)
    created_at = int(str(task.created_at or 0) or 0)
    return (completed_at, created_at, str(task.id or ""))


def _is_first_effective_completed_task(db: Session, user_id: str, task_id: str) -> bool:
    rows = (
        db.query(Tasks)
        .filter(
            Tasks.user_id == user_id,
            Tasks.status == "completed",
            Tasks.is_deleted.is_(False),
            Tasks.type.in_(["image", "video", "audio"]),
        )
        .all()
    )
    valid_rows = [task for task in rows if _task_has_displayable_result(task)]
    if not valid_rows:
        return False
    first_task = min(valid_rows, key=_task_sort_key)
    return str(first_task.id) == str(task_id)


def _get_bind_referral_eligibility(db: Session, user: Users) -> tuple[bool, Optional[str]]:
    existing_relation = (
        db.query(UserReferralRelations)
        .filter(UserReferralRelations.referee_user_id == user.user_id)
        .first()
    )
    if existing_relation:
        return False, "该账号已绑定推荐码"

    created_at = user.created_at if user.created_at and user.created_at.tzinfo else user.created_at.replace(tzinfo=timezone.utc)
    if _now() - created_at > timedelta(hours=REFERRAL_BIND_WINDOW_HOURS):
        return False, "注册已超过24小时"

    if _has_effective_completed_generation_task(db, user.user_id):
        return False, "已完成正式生成任务"

    return True, None


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
    can_bind_referral_code, bind_referral_code_block_reason = _get_bind_referral_eligibility(db, user)
    return {
        "profile": _serialize_profile(profile),
        "bound_relation": _serialize_relation(relation) if relation else None,
        "can_bind_referral_code": can_bind_referral_code,
        "bind_referral_code_block_reason": bind_referral_code_block_reason,
        "reward_summary": {
            "reward_count": int(reward_count),
            "reward_total": gold_amount_to_number(reward_total),
        },
        "reward_records": [_serialize_reward(row) for row in reward_rows],
    }


def bind_referral_code(db: Session, user_id: str, referral_code: str) -> dict[str, Any]:
    user = db.query(Users).filter(Users.user_id == user_id).first()
    if not user:
        raise ValueError("用户不存在")

    normalized_code = _normalize_code(referral_code)
    if not normalized_code:
        raise ValueError("推荐码不能为空")

    existing_relation = (
        db.query(UserReferralRelations)
        .filter(UserReferralRelations.referee_user_id == user_id)
        .first()
    )
    if existing_relation:
        raise ValueError("该账号已绑定推荐码，不能重复补填")

    created_at = user.created_at if user.created_at and user.created_at.tzinfo else user.created_at.replace(tzinfo=timezone.utc)
    if _now() - created_at > timedelta(hours=REFERRAL_BIND_WINDOW_HOURS):
        raise ValueError("注册已超过24小时，不能再补填推荐码")

    if _has_effective_completed_generation_task(db, user_id):
        raise ValueError("该账号已完成正式生成任务，不能再补填推荐码")

    referrer_profile = (
        db.query(UserReferralProfiles)
        .filter(UserReferralProfiles.referral_code == normalized_code)
        .first()
    )
    if not referrer_profile:
        raise ValueError("推荐码不存在")
    if referrer_profile.user_id == user_id:
        raise ValueError("不能绑定自己的推荐码")

    relation = UserReferralRelations(
        id=str(uuid.uuid4()),
        referrer_user_id=referrer_profile.user_id,
        referee_user_id=user_id,
        referral_code=normalized_code,
        reward_status="pending",
        bound_at=_now(),
        created_at=_now(),
        updated_at=_now(),
    )
    db.add(relation)
    db.flush()
    return _serialize_relation(relation)


def process_first_completed_task_reward(db: Session, task: Tasks) -> Optional[dict[str, Any]]:
    if task.status != "completed" or task.type not in ("image", "video", "audio"):
        return None

    if not _task_has_displayable_result(task):
        return None

    relation = (
        db.query(UserReferralRelations)
        .filter(UserReferralRelations.referee_user_id == task.user_id)
        .with_for_update()
        .first()
    )
    if not relation or relation.reward_status != "pending":
        return None

    if not _is_first_effective_completed_task(db, task.user_id, task.id):
        logger.info(
            "[referral-reward] 跳过非首个有效完成任务: user_id=%s task_id=%s",
            task.user_id,
            task.id,
        )
        return None

    existing_reward = (
        db.query(ReferralRewardRecords)
        .filter(ReferralRewardRecords.relation_id == relation.id)
        .first()
    )
    if existing_reward:
        relation.reward_status = "rewarded"
        relation.reward_granted_at = relation.reward_granted_at or _now()
        relation.updated_at = _now()
        db.add(relation)
        return _serialize_reward(existing_reward)

    inviter = db.query(Users).filter(Users.user_id == relation.referrer_user_id).with_for_update().first()
    if not inviter:
        relation.reward_status = "ineligible"
        relation.updated_at = _now()
        db.add(relation)
        return None

    schema_error = _validate_gold_schema_for_credit_type(db, "personal_gold")
    if schema_error:
        raise RuntimeError(schema_error.get("msg") or "金豆账本 schema 校验失败")

    reward_amount = normalize_gold_amount(REFERRAL_REWARD_AMOUNT)
    gold_before = inviter.gold_credits or Decimal("0.00")
    gold_after = gold_before + reward_amount
    inviter.gold_credits = gold_after

    billing_record_id = str(uuid.uuid4())
    reward_record_id = str(uuid.uuid4())
    description = "邀请奖励：被邀请用户完成首个正式生成任务"
    metadata = {
        "reward_type": "referral_first_completed_task",
        "relation_id": relation.id,
        "referee_user_id": relation.referee_user_id,
        "task_id": task.id,
    }

    _insert_billing_record(
        db=db,
        record_id=billing_record_id,
        idempotency_key=f"referral_reward:{relation.id}",
        user_id=inviter.user_id,
        team_id=None,
        operation_type="reward",
        credit_type="personal_gold",
        amount=reward_amount,
        balance_before=gold_before,
        balance_after=gold_after,
        related_id=relation.id,
        task_id=task.id,
        description=description,
        extra_data=metadata,
    )

    reward_record = ReferralRewardRecords(
        id=reward_record_id,
        relation_id=relation.id,
        referrer_user_id=relation.referrer_user_id,
        referee_user_id=relation.referee_user_id,
        task_id=task.id,
        reward_credit_type="personal_gold",
        reward_amount=reward_amount,
        billing_record_id=billing_record_id,
        description=description,
        extra_data=metadata,
        created_at=_now(),
    )
    db.add(inviter)
    db.add(reward_record)

    relation.reward_status = "rewarded"
    relation.reward_granted_at = _now()
    relation.first_completed_task_id = task.id
    relation.updated_at = _now()
    db.add(relation)

    return _serialize_reward(reward_record)


def apply_referral_on_register(db: Session, user: Users, referral_code: str) -> float:
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
        bound_at=_now(),
        created_at=_now(),
        updated_at=_now(),
    )
    db.add(relation)

    current_gold = Decimal(str(user.gold_credits or 0))
    user.gold_credits = current_gold + REGISTER_INVITE_GOLD_BONUS
    db.add(user)
    return gold_amount_to_number(REGISTER_INVITE_GOLD_BONUS)
