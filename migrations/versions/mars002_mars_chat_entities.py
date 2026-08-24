"""add mars assistant chat message and artifact tables

Revision ID: mars002_mars_chat_entities
Revises: s1t2u3v4w5x
Create Date: 2026-08-24 23:30:00.000000
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB


revision: str = 'mars002_mars_chat_entities'
down_revision: Union[str, Sequence[str], None] = 's1t2u3v4w5x'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _inspector() -> sa.engine.Inspector:
    return sa.inspect(op.get_bind())


def _table_exists(table_name: str) -> bool:
    return table_name in _inspector().get_table_names()


def _index_exists(table_name: str, index_name: str) -> bool:
    return any(index['name'] == index_name for index in _inspector().get_indexes(table_name))


def upgrade() -> None:
    if not _table_exists('mars_assistant_messages'):
        op.create_table(
            'mars_assistant_messages',
            sa.Column('id', sa.String(length=64), nullable=False),
            sa.Column('session_id', sa.String(length=64), nullable=False),
            sa.Column('user_id', sa.String(length=64), nullable=False),
            sa.Column('team_id', sa.String(length=64), nullable=True),
            sa.Column('role', sa.String(length=16), nullable=False),
            sa.Column('content', sa.Text(), nullable=True),
            sa.Column('status', sa.String(length=20), nullable=True),
            sa.Column('model', sa.String(length=64), nullable=True),
            sa.Column('error', sa.Text(), nullable=True),
            sa.Column('attachment_ids', JSONB(), nullable=True),
            sa.Column('quoted_message', JSONB(), nullable=True),
            sa.Column('skill_payload', JSONB(), nullable=True),
            sa.Column('metadata', JSONB(), nullable=True),
            sa.Column('created_at', sa.BigInteger(), nullable=False),
            sa.Column('updated_at', sa.BigInteger(), nullable=False),
            sa.PrimaryKeyConstraint('id', name='mars_assistant_messages_pkey'),
            comment='火星助手消息表',
        )

    if not _table_exists('mars_assistant_artifacts'):
        op.create_table(
            'mars_assistant_artifacts',
            sa.Column('id', sa.String(length=64), nullable=False),
            sa.Column('session_id', sa.String(length=64), nullable=False),
            sa.Column('message_id', sa.String(length=64), nullable=True),
            sa.Column('user_id', sa.String(length=64), nullable=False),
            sa.Column('team_id', sa.String(length=64), nullable=True),
            sa.Column('artifact_type', sa.String(length=32), nullable=False),
            sa.Column('artifact_role', sa.String(length=32), nullable=True),
            sa.Column('url', sa.Text(), nullable=True),
            sa.Column('file_key', sa.String(length=512), nullable=True),
            sa.Column('prompt', sa.Text(), nullable=True),
            sa.Column('source_artifact_id', sa.String(length=64), nullable=True),
            sa.Column('source_image_url', sa.Text(), nullable=True),
            sa.Column('metadata', JSONB(), nullable=True),
            sa.Column('created_at', sa.BigInteger(), nullable=False),
            sa.Column('updated_at', sa.BigInteger(), nullable=False),
            sa.PrimaryKeyConstraint('id', name='mars_assistant_artifacts_pkey'),
            comment='火星助手产物表',
        )

    if not _index_exists('mars_assistant_messages', 'ix_mars_assistant_messages_session_created'):
        op.create_index(
            'ix_mars_assistant_messages_session_created',
            'mars_assistant_messages',
            ['session_id', 'created_at'],
        )
    if not _index_exists('mars_assistant_messages', 'ix_mars_assistant_messages_user_created'):
        op.create_index(
            'ix_mars_assistant_messages_user_created',
            'mars_assistant_messages',
            ['user_id', 'created_at'],
        )
    if not _index_exists('mars_assistant_artifacts', 'ix_mars_assistant_artifacts_session_created'):
        op.create_index(
            'ix_mars_assistant_artifacts_session_created',
            'mars_assistant_artifacts',
            ['session_id', 'created_at'],
        )
    if not _index_exists('mars_assistant_artifacts', 'ix_mars_assistant_artifacts_message'):
        op.create_index(
            'ix_mars_assistant_artifacts_message',
            'mars_assistant_artifacts',
            ['message_id'],
        )


def downgrade() -> None:
    pass
