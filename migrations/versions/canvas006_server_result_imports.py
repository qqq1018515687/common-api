"""Durable server delivery of opted-in task results to creative canvas.

Existing successful tasks with an explicit canvas target are backfilled. The
existing import receipts remain the authority for preventing duplicate cards.
Downgrade would discard pending deliveries, so it is intentionally refused.
"""
import sqlalchemy as sa
from alembic import op

revision = 'canvas006'
down_revision = 'imagecompare001'
branch_labels = None
depends_on = None


def upgrade():
    op.create_table('canvas_import_jobs',
        sa.Column('task_id', sa.String(128), primary_key=True),
        sa.Column('project_id', sa.String(64), sa.ForeignKey('canvas_projects.id'), nullable=False),
        sa.Column('user_id', sa.String(64), nullable=False),
        sa.Column('status', sa.String(20), nullable=False, server_default='pending'),
        sa.Column('attempts', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('next_attempt_at', sa.BigInteger(), nullable=False),
        sa.Column('lease_token', sa.String(36)),
        sa.Column('lease_until', sa.BigInteger()),
        sa.Column('source_fingerprint', sa.String(32), nullable=False),
        sa.Column('last_error', sa.Text()),
        sa.Column('created_at', sa.BigInteger(), nullable=False),
        sa.Column('updated_at', sa.BigInteger(), nullable=False))
    op.create_index('ix_canvas_import_jobs_due', 'canvas_import_jobs', ['status', 'next_attempt_at'])
    op.create_index('ix_canvas_import_jobs_project', 'canvas_import_jobs', ['project_id', 'created_at'])
    op.execute("CREATE INDEX ix_tasks_canvas_import_candidates ON tasks (status, updated_at) WHERE parameter_snapshot::jsonb ? 'canvasTarget'")
    op.execute("""INSERT INTO canvas_import_jobs
        (task_id,project_id,user_id,status,attempts,next_attempt_at,source_fingerprint,created_at,updated_at)
        SELECT t.id,p.id,t.user_id,'pending',0,
          CAST(EXTRACT(EPOCH FROM now()) * 1000 AS BIGINT),md5(jsonb_build_object('result',t.result::jsonb,'fallback',t.result_fallback::jsonb,'deleted',t.deleted_image_urls::jsonb)::text),
          CAST(EXTRACT(EPOCH FROM now()) * 1000 AS BIGINT),CAST(EXTRACT(EPOCH FROM now()) * 1000 AS BIGINT)
        FROM tasks t JOIN canvas_projects p ON p.id=t.parameter_snapshot::jsonb->'canvasTarget'->>'projectId' AND p.user_id=t.user_id AND p.status='active'
        JOIN users u ON u.user_id=t.user_id AND u.account_status='active'
        WHERE t.status IN ('success','completed') AND t.type='image' AND t.platform<>'canvas'
          AND COALESCE(t.is_deleted,false)=false AND (t.result IS NOT NULL OR t.result_fallback IS NOT NULL)
          AND t.parameter_snapshot::jsonb ? 'canvasTarget'
        ON CONFLICT (task_id) DO NOTHING""")


def downgrade():
    raise RuntimeError('Pending canvas imports would be lost. Export and drain canvas_import_jobs before rollback.')
