"""add task confirmation state

Revision ID: p2q3r4s5t6u7
Revises: n1o2p3q4r5s6
Create Date: 2026-07-31 18:20:00.000000
"""

from alembic import op
import sqlalchemy as sa


revision = 'p2q3r4s5t6u7'
down_revision = 'n1o2p3q4r5s6'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        'tasks',
        sa.Column(
            'confirmation_state',
            sa.String(length=20),
            nullable=False,
            server_default='none',
            comment='结果确认状态：none/pending/confirmed'
        )
    )
    op.execute(
        """
        UPDATE tasks
        SET confirmation_state = CASE
            WHEN status = 'running'
             AND (
                (parameter_snapshot->>'confirmationState') = 'pending'
                OR COALESCE(user_friendly_message, '') LIKE '%结果确认中%'
             ) THEN 'pending'
            WHEN status IN ('completed', 'failed', 'cancelled') THEN 'confirmed'
            ELSE 'none'
        END
        """
    )


def downgrade() -> None:
    op.drop_column('tasks', 'confirmation_state')
