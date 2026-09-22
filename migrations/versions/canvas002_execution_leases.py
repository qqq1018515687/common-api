"""Durable dispatch leases and monotonic result-import receipts.

Existing running rows are conservatively marked unknown: never replay a possibly
paid provider submission. Downgrade requires export because receipts prevent
user-deleted results from being resurrected.
"""
from alembic import op
import sqlalchemy as sa
revision = 'canvas002'
down_revision = 'canvas001'
branch_labels = None
depends_on = None

def upgrade():
    op.add_column('canvas_runs', sa.Column('lease_token', sa.String(64)))
    op.add_column('canvas_runs', sa.Column('lease_until', sa.BigInteger()))
    op.add_column('canvas_runs', sa.Column('started_at', sa.BigInteger()))
    op.create_index('ix_canvas_runs_dispatch', 'canvas_runs', ['status', 'lease_until', 'updated_at'])
    op.execute("UPDATE canvas_runs SET status='unknown', error='升级前任务，请核对已有任务结果，禁止重复提交' WHERE status='running'")
    for table in ('canvas_projects', 'canvas_revisions'):
        op.execute(f"UPDATE {table} SET document = document || jsonb_build_object('importedRunIds', COALESCE((SELECT jsonb_agg(DISTINCT n->'data'->>'runId') FROM jsonb_array_elements(document->'nodes') n WHERE n->'data'->>'runId' IS NOT NULL), '[]'::jsonb)) WHERE NOT document ? 'importedRunIds'")

def downgrade():
    raise RuntimeError('Export canvas execution receipts before destructive rollback.')
