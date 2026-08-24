"""add team invite tables

Revision ID: z1y2x3w4v5u6
Revises: d1e2f3a4b5c6
Create Date: 2026-08-24 17:30:00.000000
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = 'z1y2x3w4v5u6'
down_revision: Union[str, Sequence[str], None] = 'd1e2f3a4b5c6'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        'team_invites',
        sa.Column('id', sa.String(length=64), nullable=False),
        sa.Column('team_id', sa.String(length=64), nullable=False),
        sa.Column('team_name', sa.String(length=100), nullable=False),
        sa.Column('code', sa.String(length=32), nullable=False),
        sa.Column('status', sa.String(length=20), server_default='active', nullable=False),
        sa.Column('max_uses', sa.Integer(), server_default='1', nullable=False),
        sa.Column('used_count', sa.Integer(), server_default='0', nullable=False),
        sa.Column('created_by_user_id', sa.String(length=36), nullable=False),
        sa.Column('created_by_username', sa.String(length=255), nullable=True),
        sa.Column('last_used_by_user_id', sa.String(length=36), nullable=True),
        sa.Column('last_used_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('expires_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('note', sa.Text(), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.PrimaryKeyConstraint('id', name='team_invites_pkey'),
        sa.UniqueConstraint('code', name='team_invites_code_key'),
        comment='团队邀请码表',
    )
    op.create_index('ix_team_invites_team_id', 'team_invites', ['team_id'])
    op.create_index('ix_team_invites_status', 'team_invites', ['status'])
    op.create_index('ix_team_invites_expires_at', 'team_invites', ['expires_at'])

    op.create_table(
        'team_invite_join_records',
        sa.Column('id', sa.String(length=64), nullable=False),
        sa.Column('invite_id', sa.String(length=64), nullable=False),
        sa.Column('code', sa.String(length=32), nullable=False),
        sa.Column('team_id', sa.String(length=64), nullable=False),
        sa.Column('team_name', sa.String(length=100), nullable=False),
        sa.Column('user_id', sa.String(length=36), nullable=False),
        sa.Column('username', sa.String(length=255), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.PrimaryKeyConstraint('id', name='team_invite_join_records_pkey'),
        comment='团队邀请码加入记录表',
    )
    op.create_index('ix_team_invite_join_records_invite_id', 'team_invite_join_records', ['invite_id'])
    op.create_index('ix_team_invite_join_records_team_id', 'team_invite_join_records', ['team_id'])
    op.create_index('ix_team_invite_join_records_user_id', 'team_invite_join_records', ['user_id'])


def downgrade() -> None:
    op.drop_index('ix_team_invite_join_records_user_id', table_name='team_invite_join_records')
    op.drop_index('ix_team_invite_join_records_team_id', table_name='team_invite_join_records')
    op.drop_index('ix_team_invite_join_records_invite_id', table_name='team_invite_join_records')
    op.drop_table('team_invite_join_records')

    op.drop_index('ix_team_invites_expires_at', table_name='team_invites')
    op.drop_index('ix_team_invites_status', table_name='team_invites')
    op.drop_index('ix_team_invites_team_id', table_name='team_invites')
    op.drop_table('team_invites')
