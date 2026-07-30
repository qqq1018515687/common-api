"""merge task fallback migration heads

Revision ID: n1o2p3q4r5s6
Revises: l5m6n7o8p9q0, m1n2o3p4q5r6
Create Date: 2026-07-30 17:05:00.000000

"""
from typing import Sequence, Union


revision: str = "n1o2p3q4r5s6"
down_revision: Union[str, Sequence[str], None] = ("l5m6n7o8p9q0", "m1n2o3p4q5r6")
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    pass


def downgrade() -> None:
    pass
