import secrets
import string
import uuid
from datetime import datetime, timedelta, timezone
from typing import Any, Optional

from sqlalchemy.orm import Session

from storage.database.shared.model import TeamInviteJoinRecords, TeamInvites, Teams, Users


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _to_epoch_ms(value: Optional[datetime]) -> Optional[int]:
    if value is None:
        return None
    if value.tzinfo is None:
        value = value.replace(tzinfo=timezone.utc)
    return int(value.timestamp() * 1000)


def _build_code(length: int = 8) -> str:
    alphabet = string.ascii_uppercase + string.digits
    return ''.join(secrets.choice(alphabet) for _ in range(length))


def _serialize_invite(invite: TeamInvites) -> dict[str, Any]:
    return {
        'id': invite.id,
        'team_id': invite.team_id,
        'team_name': invite.team_name,
        'code': invite.code,
        'status': invite.status,
        'max_uses': invite.max_uses,
        'used_count': invite.used_count,
        'created_by_user_id': invite.created_by_user_id,
        'created_by_username': invite.created_by_username,
        'last_used_by_user_id': invite.last_used_by_user_id,
        'last_used_at': _to_epoch_ms(invite.last_used_at),
        'expires_at': _to_epoch_ms(invite.expires_at),
        'note': invite.note,
        'created_at': _to_epoch_ms(invite.created_at),
        'updated_at': _to_epoch_ms(invite.updated_at),
    }


class TeamInviteManager:
    def ensure_team_admin_access(self, db: Session, *, operator_user_id: str, team_id: str) -> Users:
        operator = db.query(Users).filter(Users.user_id == operator_user_id).first()
        if not operator:
            raise ValueError('操作者不存在')
        if not operator.team_id:
            raise ValueError('操作者未加入任何团队')
        if operator.team_id != team_id:
            raise ValueError('当前管理员无权管理该团队的邀请码')
        if str(operator.role or '').lower() != 'admin':
            raise ValueError('只有团队管理员可以管理邀请码')
        return operator

    def create_invite(
        self,
        db: Session,
        *,
        team_id: str,
        created_by_user_id: str,
        team_name: Optional[str] = None,
        created_by_username: Optional[str] = None,
        max_uses: int = 1,
        expires_in_days: Optional[int] = 7,
        note: Optional[str] = None,
    ) -> TeamInvites:
        team = db.query(Teams).filter(Teams.id == team_id).first()
        if not team:
            raise ValueError('团队不存在')

        now = _now()
        expires_at = None if not expires_in_days else now + timedelta(days=max(1, expires_in_days))
        invite = TeamInvites(
            id=f'ti_{uuid.uuid4().hex}',
            team_id=team_id,
            team_name=(team_name or team.name or team_id).strip(),
            code=self._generate_unique_code(db),
            status='active',
            max_uses=max(1, int(max_uses or 1)),
            used_count=0,
            created_by_user_id=created_by_user_id,
            created_by_username=created_by_username,
            expires_at=expires_at,
            note=(note or '').strip() or None,
            created_at=now,
            updated_at=now,
        )
        db.add(invite)
        db.commit()
        db.refresh(invite)
        return invite

    def list_invites(self, db: Session, *, team_id: str) -> list[TeamInvites]:
        return (
            db.query(TeamInvites)
            .filter(TeamInvites.team_id == team_id)
            .order_by(TeamInvites.created_at.desc())
            .all()
        )

    def disable_invite(self, db: Session, *, invite_id: str, operator_user_id: str) -> TeamInvites:
        invite = db.query(TeamInvites).filter(TeamInvites.id == invite_id).first()
        if not invite:
            raise ValueError('邀请码不存在')
        self.ensure_team_admin_access(db, operator_user_id=operator_user_id, team_id=invite.team_id)
        invite.status = 'disabled'
        invite.updated_at = _now()
        db.add(invite)
        db.commit()
        db.refresh(invite)
        return invite

    def join_by_invite(self, db: Session, *, user_id: str, invite_code: str) -> tuple[TeamInvites, Users, TeamInviteJoinRecords]:
        normalized_code = (invite_code or '').strip().upper()
        if not normalized_code:
            raise ValueError('邀请码不能为空')

        invite = db.query(TeamInvites).filter(TeamInvites.code == normalized_code).with_for_update().first()
        if not invite:
            raise ValueError('邀请码不存在，请检查后重试')

        now = _now()
        if invite.status != 'active':
            raise ValueError('邀请码已停用')
        if invite.expires_at and invite.expires_at <= now:
            raise ValueError('邀请码已过期')
        if invite.used_count >= invite.max_uses:
            raise ValueError('邀请码已达使用上限')

        user = db.query(Users).filter(Users.user_id == user_id).with_for_update().first()
        if not user:
            raise ValueError('用户不存在')
        if user.account_status == 'deleted':
            raise ValueError('账号不可用')
        if user.team_id:
            raise ValueError('当前账号已加入团队，如需切换团队请联系管理员处理')

        user.team_id = invite.team_id
        user.updated_at = now
        invite.used_count += 1
        invite.last_used_by_user_id = user.user_id
        invite.last_used_at = now
        invite.updated_at = now

        join_record = TeamInviteJoinRecords(
            id=f'tij_{uuid.uuid4().hex}',
            invite_id=invite.id,
            code=invite.code,
            team_id=invite.team_id,
            team_name=invite.team_name,
            user_id=user.user_id,
            username=user.username,
            created_at=now,
        )
        db.add(join_record)
        db.add(invite)
        db.add(user)
        db.commit()
        db.refresh(invite)
        db.refresh(user)
        db.refresh(join_record)
        return invite, user, join_record

    def serialize_invite(self, invite: TeamInvites) -> dict[str, Any]:
        return _serialize_invite(invite)

    def serialize_join_record(self, record: TeamInviteJoinRecords) -> dict[str, Any]:
        return {
            'id': record.id,
            'invite_id': record.invite_id,
            'code': record.code,
            'team_id': record.team_id,
            'team_name': record.team_name,
            'user_id': record.user_id,
            'username': record.username,
            'created_at': _to_epoch_ms(record.created_at),
        }

    def _generate_unique_code(self, db: Session) -> str:
        for _ in range(20):
            code = _build_code()
            exists = db.query(TeamInvites).filter(TeamInvites.code == code).first()
            if not exists:
                return code
        raise RuntimeError('生成邀请码失败，请重试')
