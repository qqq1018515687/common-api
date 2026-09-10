"""expand task status for async submission

Revision ID: v4w5x6y7z8a9
Revises: mars004_merge_attach_heads
Create Date: 2026-09-10 12:00:00.000000

`submitted_unconfirmed` is an authoritative non-terminal state used while a
third-party provider has not returned its platform task ID. The previous
VARCHAR(10) column could not store that state.
"""

from typing import Sequence, Union

from alembic import op


revision: str = "v4w5x6y7z8a9"
down_revision: Union[str, Sequence[str], None] = "mars004_merge_attach_heads"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute("ALTER TABLE tasks ALTER COLUMN status TYPE VARCHAR(32)")


def downgrade() -> None:
    # Downgrade is intentionally guarded because truncating an active async
    # state would corrupt task recovery semantics.
    op.execute(
        """
        DO $$
        BEGIN
            IF EXISTS (SELECT 1 FROM tasks WHERE length(status) > 10) THEN
                RAISE EXCEPTION 'cannot narrow tasks.status while long status values exist';
            END IF;
        END $$
        """
    )
    op.execute("ALTER TABLE tasks ALTER COLUMN status TYPE VARCHAR(10)")
