"""reassert task status length

Revision ID: taskstatus001
Revises: billtask001
Create Date: 2026-09-11 14:10:00.000000

Some deployed databases recorded the earlier status expansion revision while the
physical column remained VARCHAR(10). Reassert the authoritative schema on the
current head so submitted_unconfirmed can always be persisted.
"""

from typing import Sequence, Union

from alembic import op


revision: str = "taskstatus001"
down_revision: Union[str, Sequence[str], None] = "billtask001"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute("ALTER TABLE tasks ALTER COLUMN status TYPE VARCHAR(32)")


def downgrade() -> None:
    # Narrowing this column would make active submitted_unconfirmed rows invalid.
    pass
