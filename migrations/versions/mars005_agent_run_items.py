"""replace mars assistant messages with compact agent runs

Revision ID: mars005_agent_run_items
Revises: v4w5x6y7z8a9
Create Date: 2026-09-10 12:00:00.000000
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB


revision: str = "mars005_agent_run_items"
down_revision: Union[str, Sequence[str], None] = "v4w5x6y7z8a9"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _table_exists(table_name: str) -> bool:
    return table_name in sa.inspect(op.get_bind()).get_table_names()


def _column_names(table_name: str) -> set[str]:
    return {column["name"] for column in sa.inspect(op.get_bind()).get_columns(table_name)}


def _index_names(table_name: str) -> set[str]:
    return {index["name"] for index in sa.inspect(op.get_bind()).get_indexes(table_name)}


def _validate_existing_run_schema() -> None:
    inspector = sa.inspect(op.get_bind())
    columns = {column["name"]: column for column in inspector.get_columns("mars_agent_runs")}
    expected_types = {
        "id": (sa.String, 64, False),
        "conversation_id": (sa.String, 64, False),
        "user_id": (sa.String, 64, False),
        "team_id": (sa.String, 64, True),
        "model": (sa.String, 128, True),
        "provider": (sa.String, 64, True),
        "provider_task_id": (sa.String, 255, True),
        "status": (sa.String, 32, False),
        "idempotency_key": (sa.String, 255, False),
        "continuation_of_run_id": (sa.String, 64, True),
        "tool_name": (sa.String, 255, None),
        "tool_arguments": (JSONB, None, True),
        "input_resources": (JSONB, None, True),
        "result_artifact_ids": (JSONB, None, True),
        "error": (JSONB, None, True),
        "created_at": (sa.BigInteger, None, False),
        "updated_at": (sa.BigInteger, None, False),
        "completed_at": (sa.BigInteger, None, True),
    }
    if set(columns) != set(expected_types):
        raise RuntimeError("existing mars_agent_runs schema is incompatible; refusing destructive migration")
    for name, (type_class, length, nullable) in expected_types.items():
        column = columns[name]
        column_type = column["type"]
        if not isinstance(column_type, type_class):
            raise RuntimeError(f"mars_agent_runs.{name} has incompatible type")
        if length is not None and getattr(column_type, "length", None) != length:
            raise RuntimeError(f"mars_agent_runs.{name} has incompatible length")
        if nullable is not None and column.get("nullable") is not nullable:
            raise RuntimeError(f"mars_agent_runs.{name} has incompatible nullability")
    primary_key = inspector.get_pk_constraint("mars_agent_runs")
    if primary_key.get("constrained_columns") != ["id"]:
        raise RuntimeError("mars_agent_runs has incompatible primary key")


def upgrade() -> None:
    for obsolete_table in ("mars_agent_resource_bindings", "mars_agent_items"):
        if _table_exists(obsolete_table):
            op.drop_table(obsolete_table)

    if _table_exists("mars_assistant_messages"):
        op.drop_table("mars_assistant_messages")

    if _table_exists("mars_assistant_sessions"):
        op.execute("""
            UPDATE mars_assistant_sessions
            SET metadata = jsonb_strip_nulls(jsonb_build_object(
                'activeEditBaseArtifactId', CASE
                    WHEN jsonb_typeof(metadata->'activeEditBaseArtifactId') = 'string'
                    THEN metadata->'activeEditBaseArtifactId'
                    ELSE NULL
                END,
                'latestGeneratedArtifactId', CASE
                    WHEN jsonb_typeof(metadata->'latestGeneratedArtifactId') = 'string'
                    THEN metadata->'latestGeneratedArtifactId'
                    ELSE NULL
                END
            ))
            WHERE metadata IS NOT NULL
        """)
        with op.batch_alter_table("mars_assistant_sessions") as batch_op:
            session_columns = _column_names("mars_assistant_sessions")
            if "task_state" in session_columns:
                batch_op.drop_column("task_state")
            if "image_asset_state" in session_columns:
                batch_op.drop_column("image_asset_state")
        session_indexes = _index_names("mars_assistant_sessions")
        for obsolete_index in (
            "idx_mars_assistant_sessions_user_updated",
            "idx_mars_assistant_sessions_team_updated",
        ):
            if obsolete_index in session_indexes:
                op.drop_index(obsolete_index, table_name="mars_assistant_sessions")

    if _table_exists("mars_assistant_artifacts"):
        op.execute("""
            UPDATE mars_assistant_artifacts
            SET metadata = jsonb_strip_nulls(jsonb_build_object(
                'runId', CASE WHEN jsonb_typeof(metadata->'runId') = 'string' THEN metadata->'runId' ELSE NULL END,
                'sequence', CASE WHEN jsonb_typeof(metadata->'sequence') = 'number' THEN metadata->'sequence' ELSE NULL END,
                'frame', CASE
                    WHEN jsonb_typeof(metadata->'frame') = 'object'
                    THEN jsonb_strip_nulls(jsonb_build_object(
                        'index', CASE WHEN jsonb_typeof(metadata->'frame'->'index') = 'number' THEN metadata->'frame'->'index' ELSE NULL END,
                        'title', CASE WHEN jsonb_typeof(metadata->'frame'->'title') = 'string' THEN metadata->'frame'->'title' ELSE NULL END
                    ))
                    ELSE NULL
                END,
                'frameIndex', CASE WHEN jsonb_typeof(metadata->'frameIndex') = 'number' THEN metadata->'frameIndex' ELSE NULL END,
                'frameTitle', CASE WHEN jsonb_typeof(metadata->'frameTitle') = 'string' THEN metadata->'frameTitle' ELSE NULL END
            ))
            WHERE metadata IS NOT NULL
        """)
        with op.batch_alter_table("mars_assistant_artifacts") as batch_op:
            if "prompt" in _column_names("mars_assistant_artifacts"):
                batch_op.drop_column("prompt")
            if "source_image_url" in _column_names("mars_assistant_artifacts"):
                batch_op.drop_column("source_image_url")
        artifact_indexes = _index_names("mars_assistant_artifacts")
        for obsolete_index in (
            "idx_mars_assistant_artifacts_session_created",
            "idx_mars_assistant_artifacts_message",
        ):
            if obsolete_index in artifact_indexes:
                op.drop_index(obsolete_index, table_name="mars_assistant_artifacts")

    if _table_exists("mars_assistant_attachments"):
        op.execute("""
            UPDATE mars_assistant_attachments
            SET metadata = jsonb_strip_nulls(jsonb_build_object(
                'summary', CASE WHEN jsonb_typeof(metadata->'summary') = 'string' THEN metadata->'summary' ELSE NULL END,
                'contentLength', CASE WHEN jsonb_typeof(metadata->'contentLength') = 'number' THEN metadata->'contentLength' ELSE NULL END
            ))
            WHERE metadata IS NOT NULL
        """)

    if _table_exists("mars_agent_runs"):
        _validate_existing_run_schema()
        op.execute("""
            UPDATE mars_agent_runs
            SET tool_arguments = jsonb_strip_nulls(jsonb_build_object(
                'requestedImageCount', CASE WHEN jsonb_typeof(tool_arguments->'requestedImageCount') = 'number' THEN tool_arguments->'requestedImageCount' ELSE NULL END,
                'sequenceStart', CASE WHEN jsonb_typeof(tool_arguments->'sequenceStart') = 'number' THEN tool_arguments->'sequenceStart' ELSE NULL END,
                'requestedAspectRatio', CASE WHEN jsonb_typeof(tool_arguments->'requestedAspectRatio') = 'string' THEN tool_arguments->'requestedAspectRatio' ELSE NULL END,
                'model', CASE WHEN jsonb_typeof(tool_arguments->'model') = 'string' THEN tool_arguments->'model' ELSE NULL END
            ))
            WHERE tool_name = 'generate_images'
        """)
        op.execute("DELETE FROM mars_agent_runs WHERE tool_name IS DISTINCT FROM 'generate_images'")
        op.execute("UPDATE mars_agent_runs SET input_resources = '[]'::jsonb, result_artifact_ids = '[]'::jsonb")
        duplicate = op.get_bind().execute(sa.text("""
            SELECT 1
            FROM mars_agent_runs
            GROUP BY user_id, conversation_id, idempotency_key
            HAVING COUNT(*) > 1
            LIMIT 1
        """)).first()
        if duplicate:
            raise RuntimeError("duplicate mars_agent_runs idempotency keys prevent safe migration")
        with op.batch_alter_table("mars_agent_runs") as batch_op:
            batch_op.alter_column("tool_name", existing_type=sa.String(length=255), nullable=False)

    if not _table_exists("mars_agent_runs"):
        op.create_table(
            "mars_agent_runs",
            sa.Column("id", sa.String(length=64), nullable=False),
            sa.Column("conversation_id", sa.String(length=64), nullable=False),
            sa.Column("user_id", sa.String(length=64), nullable=False),
            sa.Column("team_id", sa.String(length=64), nullable=True),
            sa.Column("model", sa.String(length=128), nullable=True),
            sa.Column("provider", sa.String(length=64), nullable=True),
            sa.Column("provider_task_id", sa.String(length=255), nullable=True),
            sa.Column("status", sa.String(length=32), nullable=False),
            sa.Column("idempotency_key", sa.String(length=255), nullable=False),
            sa.Column("continuation_of_run_id", sa.String(length=64), nullable=True),
            sa.Column("tool_name", sa.String(length=255), nullable=False),
            sa.Column("tool_arguments", JSONB(), nullable=True),
            sa.Column("input_resources", JSONB(), nullable=True),
            sa.Column("result_artifact_ids", JSONB(), nullable=True),
            sa.Column("error", JSONB(), nullable=True),
            sa.Column("created_at", sa.BigInteger(), nullable=False),
            sa.Column("updated_at", sa.BigInteger(), nullable=False),
            sa.Column("completed_at", sa.BigInteger(), nullable=True),
            sa.PrimaryKeyConstraint("id", name="mars_agent_runs_pkey"),
            sa.UniqueConstraint(
                "user_id",
                "conversation_id",
                "idempotency_key",
                name="uq_mars_agent_runs_owner_conversation_idempotency",
            ),
            sa.CheckConstraint(
                "tool_name = 'generate_images'",
                name="ck_mars_agent_runs_generate_images_only",
            ),
            comment="Mars Agent compact run records",
        )
        op.create_index(
            "ix_mars_agent_runs_conversation_created",
            "mars_agent_runs",
            ["conversation_id", "created_at"],
        )
        op.create_index(
            "ix_mars_agent_runs_user_updated",
            "mars_agent_runs",
            ["user_id", "updated_at"],
        )
        op.create_index(
            "ix_mars_agent_runs_provider_task",
            "mars_agent_runs",
            ["provider", "provider_task_id"],
        )
    else:
        inspector = sa.inspect(op.get_bind())
        unique_constraints = {
            constraint["name"]: constraint.get("column_names") or []
            for constraint in inspector.get_unique_constraints("mars_agent_runs")
            if constraint.get("name")
        }
        expected_unique_columns = ["user_id", "conversation_id", "idempotency_key"]
        existing_unique_columns = unique_constraints.get("uq_mars_agent_runs_owner_conversation_idempotency")
        if existing_unique_columns is not None and existing_unique_columns != expected_unique_columns:
            raise RuntimeError("mars_agent_runs has incompatible idempotency constraint")
        if existing_unique_columns is None:
            op.create_unique_constraint(
                "uq_mars_agent_runs_owner_conversation_idempotency",
                "mars_agent_runs",
                expected_unique_columns,
            )
        check_constraints = {
            constraint["name"]: str(constraint.get("sqltext") or "")
            for constraint in inspector.get_check_constraints("mars_agent_runs")
            if constraint.get("name")
        }
        if "ck_mars_agent_runs_generate_images_only" in check_constraints:
            op.drop_constraint(
                "ck_mars_agent_runs_generate_images_only",
                "mars_agent_runs",
                type_="check",
            )
        op.create_check_constraint(
            "ck_mars_agent_runs_generate_images_only",
            "mars_agent_runs",
            "tool_name = 'generate_images'",
        )
        indexes = {
            index["name"]: index.get("column_names") or []
            for index in inspector.get_indexes("mars_agent_runs")
        }
        for index_name, columns in (
            ("ix_mars_agent_runs_conversation_created", ["conversation_id", "created_at"]),
            ("ix_mars_agent_runs_user_updated", ["user_id", "updated_at"]),
            ("ix_mars_agent_runs_provider_task", ["provider", "provider_task_id"]),
        ):
            if index_name in indexes and indexes[index_name] != columns:
                raise RuntimeError(f"mars_agent_runs has incompatible index: {index_name}")
            if index_name not in indexes:
                op.create_index(index_name, "mars_agent_runs", columns)


def downgrade() -> None:
    raise RuntimeError("mars005 deletes server chat data and cannot be downgraded safely")
