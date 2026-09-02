"""add mars assistant attachment persistence tables

Revision ID: mars003_mars_attachment_persistence
Revises: mars002_mars_chat_entities
Create Date: 2026-09-02 16:50:00.000000
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB


revision: str = 'mars003_mars_attachment_persistence'
down_revision: Union[str, Sequence[str], None] = 'mars002_mars_chat_entities'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _inspector() -> sa.engine.Inspector:
    return sa.inspect(op.get_bind())


def _table_exists(table_name: str) -> bool:
    return table_name in _inspector().get_table_names()


def _index_exists(table_name: str, index_name: str) -> bool:
    return any(index['name'] == index_name for index in _inspector().get_indexes(table_name))


def upgrade() -> None:
    if not _table_exists('mars_assistant_attachments'):
        op.create_table(
            'mars_assistant_attachments',
            sa.Column('id', sa.String(length=64), nullable=False),
            sa.Column('session_id', sa.String(length=64), nullable=False),
            sa.Column('user_id', sa.String(length=64), nullable=False),
            sa.Column('team_id', sa.String(length=64), nullable=True),
            sa.Column('name', sa.String(length=255), nullable=False),
            sa.Column('mime_type', sa.String(length=128), nullable=False),
            sa.Column('kind', sa.String(length=16), nullable=False),
            sa.Column('size', sa.BigInteger(), nullable=False),
            sa.Column('storage_provider', sa.String(length=32), nullable=True),
            sa.Column('storage_key', sa.String(length=512), nullable=True),
            sa.Column('public_url', sa.Text(), nullable=True),
            sa.Column('file_key', sa.String(length=512), nullable=True),
            sa.Column('expires_at', sa.BigInteger(), nullable=True),
            sa.Column('parse_status', sa.String(length=24), nullable=False, server_default=sa.text("'pending'")),
            sa.Column('parse_error', sa.Text(), nullable=True),
            sa.Column('text_preview', sa.Text(), nullable=True),
            sa.Column('metadata', JSONB(), nullable=True),
            sa.Column('created_at', sa.BigInteger(), nullable=False),
            sa.Column('updated_at', sa.BigInteger(), nullable=False),
            sa.PrimaryKeyConstraint('id', name='mars_assistant_attachments_pkey'),
            comment='火星助手附件表，保存会话附件原件元数据与存储位置',
        )

    if not _table_exists('mars_assistant_attachment_contents'):
        op.create_table(
            'mars_assistant_attachment_contents',
            sa.Column('attachment_id', sa.String(length=64), nullable=False),
            sa.Column('full_text', sa.Text(), nullable=True),
            sa.Column('summary', sa.Text(), nullable=True),
            sa.Column('structured_json', JSONB(), nullable=True),
            sa.Column('page_count', sa.Integer(), nullable=True),
            sa.Column('sheet_count', sa.Integer(), nullable=True),
            sa.Column('updated_at', sa.BigInteger(), nullable=False),
            sa.PrimaryKeyConstraint('attachment_id', name='mars_assistant_attachment_contents_pkey'),
            comment='火星助手附件解析结果表，保存全文、摘要与结构化内容',
        )

    if not _table_exists('mars_assistant_attachment_chunks'):
        op.create_table(
            'mars_assistant_attachment_chunks',
            sa.Column('id', sa.String(length=64), nullable=False),
            sa.Column('attachment_id', sa.String(length=64), nullable=False),
            sa.Column('chunk_index', sa.Integer(), nullable=False),
            sa.Column('chunk_text', sa.Text(), nullable=False),
            sa.Column('source_type', sa.String(length=32), nullable=True),
            sa.Column('source_label', sa.String(length=255), nullable=True),
            sa.Column('page_number', sa.Integer(), nullable=True),
            sa.Column('sheet_name', sa.String(length=255), nullable=True),
            sa.Column('token_estimate', sa.Integer(), nullable=True),
            sa.Column('created_at', sa.BigInteger(), nullable=False),
            sa.PrimaryKeyConstraint('id', name='mars_assistant_attachment_chunks_pkey'),
            comment='火星助手附件分块表，供后续检索和上下文拼装',
        )

    if not _index_exists('mars_assistant_attachments', 'ix_mars_assistant_attachments_session_created'):
        op.create_index('ix_mars_assistant_attachments_session_created', 'mars_assistant_attachments', ['session_id', 'created_at'])
    if not _index_exists('mars_assistant_attachments', 'ix_mars_assistant_attachments_user_created'):
        op.create_index('ix_mars_assistant_attachments_user_created', 'mars_assistant_attachments', ['user_id', 'created_at'])
    if not _index_exists('mars_assistant_attachment_chunks', 'ix_mars_assistant_attachment_chunks_attachment_index'):
        op.create_index('ix_mars_assistant_attachment_chunks_attachment_index', 'mars_assistant_attachment_chunks', ['attachment_id', 'chunk_index'])


def downgrade() -> None:
    pass
