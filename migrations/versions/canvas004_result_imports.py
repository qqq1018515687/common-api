"""Durable per-result import receipts, independent of canvas undo/history.

Existing tasks have no canvasTarget and are intentionally not auto-imported.
Downgrade refuses to remove duplicate-prevention history.
"""
from alembic import op
import sqlalchemy as sa
revision = 'canvas004'
down_revision = 'canvas003'
branch_labels = None
depends_on = None

def upgrade():
    op.create_table('canvas_result_imports',
        sa.Column('project_id', sa.String(64), sa.ForeignKey('canvas_projects.id'), primary_key=True),
        sa.Column('task_id', sa.String(128), primary_key=True),
        sa.Column('image_index', sa.Integer(), primary_key=True),
        sa.Column('asset_id', sa.String(64), sa.ForeignKey('canvas_assets.id'), nullable=False),
        sa.Column('created_at', sa.BigInteger(), nullable=False))

def downgrade():
    raise RuntimeError('Export result import receipts before destructive rollback.')
