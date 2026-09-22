"""Owner-scoped native tool-calling audit. No signed URLs or model secrets.

Downgrade refuses to discard the conversation/audit trail.
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB
revision = 'canvas003'
down_revision = 'canvas002'
branch_labels = None
depends_on = None

def upgrade():
    op.create_table('canvas_assistant_turns',
        sa.Column('id', sa.String(64), primary_key=True),
        sa.Column('project_id', sa.String(64), sa.ForeignKey('canvas_projects.id'), nullable=False),
        sa.Column('user_id', sa.String(64), nullable=False),
        sa.Column('revision', sa.Integer(), nullable=False),
        sa.Column('status', sa.String(16), nullable=False),
        sa.Column('request', JSONB(), nullable=False),
        sa.Column('response', JSONB()),
        sa.Column('error', sa.Text()),
        sa.Column('created_at', sa.BigInteger(), nullable=False),
        sa.Column('updated_at', sa.BigInteger(), nullable=False))
    op.create_index('ix_canvas_assistant_project', 'canvas_assistant_turns', ['project_id', 'created_at'])
    op.create_index('ix_canvas_assistant_user', 'canvas_assistant_turns', ['user_id', 'created_at'])

def downgrade():
    raise RuntimeError('Export canvas conversation history before destructive rollback.')
