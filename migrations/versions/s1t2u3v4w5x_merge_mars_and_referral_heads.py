"""merge mars and referral heads

Revision ID: s1t2u3v4w5x
Revises: mars001_mars_assistant_sessions, r7s8t9u0v1w2
Create Date: 2026-08-24 21:55:00.000000
"""

from typing import Sequence, Union


revision: str = 's1t2u3v4w5x'
down_revision: Union[str, Sequence[str], None] = (
    'mars001_mars_assistant_sessions',
    'r7s8t9u0v1w2',
)
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    pass


def downgrade() -> None:
    pass
