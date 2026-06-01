"""backfill existing registered users to internal demo tier

Revision ID: a2b3c4d5e6f7
Revises: f8a9b0c1d2e3
Create Date: 2026-06-01 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op


revision: str = "a2b3c4d5e6f7"
down_revision: Union[str, Sequence[str], None] = "f8a9b0c1d2e3"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Existing users before commercial registration pricing should keep demo cost.
    # New registrations on/after 2026-06-01 stay commercial_registered.
    op.execute(
        "update users set tier = 'internal_demo' "
        "where tier is null "
        "or tier in ('standard', 'pro', 'enterprise') "
        "or (tier = 'commercial_registered' "
        "and created_at < timestamptz '2026-06-01 00:00:00+00')"
    )


def downgrade() -> None:
    # Data downgrade is intentionally not reversible: after this migration runs,
    # internal_demo can also be assigned manually by admins.
    pass
