"""Creative canvas projects, immutable revisions, private assets and executions.

Downgrade intentionally refuses destructive data loss; export projects/assets first.
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB

revision = 'canvas001'
down_revision = 'billtask003'
branch_labels = None
depends_on = None


def upgrade():
    op.create_table('canvas_projects',
        sa.Column('id', sa.String(64), primary_key=True),
        sa.Column('user_id', sa.String(64), nullable=False),
        sa.Column('title', sa.String(160), nullable=False),
        sa.Column('status', sa.String(16), nullable=False, server_default='active'),
        sa.Column('revision', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('document', JSONB(), nullable=False),
        sa.Column('created_at', sa.BigInteger(), nullable=False),
        sa.Column('updated_at', sa.BigInteger(), nullable=False),
        sa.CheckConstraint("status IN ('active', 'archived', 'deleted')"))
    op.create_index('ix_canvas_projects_owner', 'canvas_projects', ['user_id', 'updated_at'])
    op.create_table('canvas_revisions',
        sa.Column('project_id', sa.String(64), sa.ForeignKey('canvas_projects.id'), primary_key=True),
        sa.Column('revision', sa.Integer(), primary_key=True),
        sa.Column('mutation_id', sa.String(64), nullable=False),
        sa.Column('document', JSONB(), nullable=False),
        sa.Column('created_at', sa.BigInteger(), nullable=False),
        sa.UniqueConstraint('project_id', 'mutation_id', name='uq_canvas_mutation'))
    op.create_table('canvas_assets',
        sa.Column('id', sa.String(64), primary_key=True),
        sa.Column('user_id', sa.String(64), nullable=False),
        sa.Column('object_key', sa.String(1024), nullable=False, unique=True),
        sa.Column('file_name', sa.String(255), nullable=False),
        sa.Column('mime_type', sa.String(100), nullable=False),
        sa.Column('size', sa.BigInteger(), nullable=False),
        sa.Column('sha256', sa.String(64), nullable=False),
        sa.Column('created_at', sa.BigInteger(), nullable=False))
    op.create_index('ix_canvas_assets_owner', 'canvas_assets', ['user_id', 'created_at'])
    op.create_table('canvas_runs',
        sa.Column('id', sa.String(64), primary_key=True),
        sa.Column('project_id', sa.String(64), sa.ForeignKey('canvas_projects.id'), nullable=False),
        sa.Column('user_id', sa.String(64), nullable=False),
        sa.Column('node_id', sa.String(64), nullable=False),
        sa.Column('idempotency_key', sa.String(64), nullable=False),
        sa.Column('request_hash', sa.String(64), nullable=False),
        sa.Column('status', sa.String(32), nullable=False),
        sa.Column('request', JSONB(), nullable=False),
        sa.Column('result', JSONB(), nullable=True),
        sa.Column('task_id', sa.String(64), nullable=True),
        sa.Column('error', sa.Text(), nullable=True),
        sa.Column('created_at', sa.BigInteger(), nullable=False),
        sa.Column('updated_at', sa.BigInteger(), nullable=False),
        sa.UniqueConstraint('user_id', 'idempotency_key', name='uq_canvas_run_idempotency'))
    op.create_index('ix_canvas_runs_project', 'canvas_runs', ['project_id', 'created_at'])


def downgrade():
    raise RuntimeError('Canvas contains permanent user assets/history. Export and approve destructive rollback first.')
