"""Store durable, revocable image comparison shares.

The image bytes live in a private, permanent object prefix. Downgrade removes
the share records but cannot recover images that were already deleted on revoke;
export active shares and their objects before rolling back this revision.
"""

from alembic import op
import sqlalchemy as sa


revision = 'imagecompare001'
down_revision = 'canvas005'
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        'image_comparison_shares',
        sa.Column('token', sa.String(length=64), primary_key=True),
        sa.Column('owner_user_id', sa.String(length=64), nullable=False),
        sa.Column('title', sa.String(length=160), nullable=False),
        sa.Column('description', sa.String(length=1000), nullable=False, server_default=''),
        sa.Column('before_object_key', sa.String(length=512), nullable=False),
        sa.Column('after_object_key', sa.String(length=512), nullable=False),
        sa.Column('before_mime_type', sa.String(length=32), nullable=False),
        sa.Column('after_mime_type', sa.String(length=32), nullable=False),
        sa.Column('created_at', sa.BigInteger(), nullable=False),
        sa.Column('revoked_at', sa.BigInteger(), nullable=True),
    )
    op.create_index(
        'ix_image_comparison_shares_owner_created',
        'image_comparison_shares',
        ['owner_user_id', 'created_at'],
    )


def downgrade():
    op.drop_index('ix_image_comparison_shares_owner_created', table_name='image_comparison_shares')
    op.drop_table('image_comparison_shares')
