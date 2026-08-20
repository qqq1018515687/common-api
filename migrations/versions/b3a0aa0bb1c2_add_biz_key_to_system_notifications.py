"""add biz_key to system_notifications

Revision ID: b3a0aa0bb1c2
Revises: u7v8w9x0y1z2
Create Date: 2026-08-20 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'b3a0aa0bb1c2'
down_revision: Union[str, Sequence[str], None] = 'u7v8w9x0y1z2'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.add_column(
        'system_notifications',
        sa.Column('biz_key', sa.String(64), nullable=True, comment='业务标识：固定运营通知用（如 channel_status_t / channel_status_r），普通通知为空'),
    )
    op.create_unique_constraint(
        'uq_system_notifications_biz_key',
        'system_notifications',
        ['biz_key'],
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_constraint(
        'uq_system_notifications_biz_key',
        'system_notifications',
        type_='unique',
    )
    op.drop_column('system_notifications', 'biz_key')