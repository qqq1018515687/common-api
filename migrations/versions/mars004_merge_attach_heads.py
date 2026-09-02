"""merge runtime configs and mars attachment heads

Revision ID: mars004_merge_attach_heads
Revises: mars003_attach_store, w1x2y3z4a5b6
Create Date: 2026-09-02 18:05:00.000000
"""

from typing import Sequence, Union


revision: str = 'mars004_merge_attach_heads'
down_revision: Union[str, Sequence[str], None] = ('mars003_attach_store', 'w1x2y3z4a5b6')
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    pass


def downgrade() -> None:
    pass
