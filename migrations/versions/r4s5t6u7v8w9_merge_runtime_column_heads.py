"""merge runtime column migration heads

Revision ID: r4s5t6u7v8w9
Revises: q3r4s5t6u7v8, i2j3k4l5m6n7
Create Date: 2026-08-03 11:40:00.000000
"""

from typing import Sequence, Union


revision: str = 'r4s5t6u7v8w9'
down_revision: Union[str, Sequence[str], None] = ('q3r4s5t6u7v8', 'i2j3k4l5m6n7')
branch_labels = None
depends_on = None


def upgrade() -> None:
    pass


def downgrade() -> None:
    pass
