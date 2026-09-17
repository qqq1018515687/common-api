import ast
from pathlib import Path
import unittest


MIGRATIONS_DIR = Path(__file__).parent / "migrations" / "versions"
MIGRATION_PATH = MIGRATIONS_DIR / "mars005_agent_run_items.py"


def read_revision_values(path: Path) -> dict:
    values = {}
    for node in ast.parse(path.read_text(encoding="utf-8")).body:
        if isinstance(node, ast.AnnAssign) and isinstance(node.target, ast.Name):
            if node.target.id in {"revision", "down_revision"}:
                values[node.target.id] = ast.literal_eval(node.value)
        elif isinstance(node, ast.Assign) and len(node.targets) == 1:
            target = node.targets[0]
            if isinstance(target, ast.Name) and target.id in {"revision", "down_revision"}:
                values[target.id] = ast.literal_eval(node.value)
    return values


class MarsAgentMigrationTest(unittest.TestCase):
    def test_revision_extends_the_only_previous_head(self):
        revisions = {}
        parents = set()
        for path in MIGRATIONS_DIR.glob("*.py"):
            values = read_revision_values(path)
            revision = values.get("revision")
            if not revision:
                continue
            revisions[revision] = path.name
            down_revision = values.get("down_revision")
            if isinstance(down_revision, tuple):
                parents.update(down_revision)
            elif down_revision:
                parents.add(down_revision)

        heads = set(revisions) - parents
        self.assertEqual(heads, {"billtask002"})
        self.assertEqual(
            read_revision_values(MIGRATION_PATH)["down_revision"],
            "v4w5x6y7z8a9",
        )

    def test_migration_replaces_messages_with_compact_runs(self):
        source = MIGRATION_PATH.read_text(encoding="utf-8")
        self.assertIn('op.drop_table("mars_assistant_messages")', source)
        self.assertIn('op.create_table(\n            "mars_agent_runs"', source)
        self.assertIn("uq_mars_agent_runs_owner_conversation_idempotency", source)
        self.assertIn('sa.Column("idempotency_key", sa.String(length=255), nullable=False)', source)
        for column_name in (
            "provider_task_id",
            "tool_arguments",
            "input_resources",
            "result_artifact_ids",
        ):
            self.assertIn(f'sa.Column("{column_name}"', source)
        self.assertIn('("mars_agent_resource_bindings", "mars_agent_items")', source)
        self.assertNotIn('op.create_table(\n            "mars_agent_items"', source)
        self.assertNotIn('op.create_table(\n            "mars_agent_resource_bindings"', source)

    def test_migration_clears_server_side_chat_payloads(self):
        source = MIGRATION_PATH.read_text(encoding="utf-8")
        self.assertIn('batch_op.drop_column("task_state")', source)
        self.assertIn('batch_op.drop_column("image_asset_state")', source)
        self.assertIn('batch_op.drop_column("prompt")', source)
        self.assertIn('batch_op.drop_column("source_image_url")', source)
        self.assertIn("jsonb_strip_nulls(jsonb_build_object", source)
        self.assertIn("UPDATE mars_assistant_attachments", source)

    def test_downgrade_rejects_irrecoverable_data_restore(self):
        source = MIGRATION_PATH.read_text(encoding="utf-8")
        self.assertIn("cannot be downgraded safely", source)
        self.assertNotIn('op.create_table(\n            "mars_assistant_messages"', source)

    def test_migration_uses_table_existence_checks(self):
        source = MIGRATION_PATH.read_text(encoding="utf-8")
        self.assertIn("sa.inspect(op.get_bind()).get_table_names()", source)
        self.assertIn('if _table_exists("mars_assistant_messages")', source)
        self.assertIn("_validate_existing_run_schema()", source)
        self.assertIn("refusing destructive migration", source)
        self.assertIn('if not _table_exists("mars_agent_runs")', source)
        self.assertIn("uq_mars_agent_runs_owner_conversation_idempotency", source)
        self.assertIn("DELETE FROM mars_agent_runs WHERE tool_name IS DISTINCT FROM 'generate_images'", source)
        self.assertIn("ck_mars_agent_runs_generate_images_only", source)
        self.assertIn("nullable=False", source)
        self.assertIn("result_artifact_ids = '[]'::jsonb", source)
        self.assertIn("jsonb_typeof(tool_arguments->'model') = 'string'", source)
        self.assertIn('type_="check"', source)

    def test_runtime_does_not_create_migration_owned_tables(self):
        manager_path = Path(__file__).parent / "src/storage/database/mars_assistant_session_manager.py"
        source = manager_path.read_text(encoding="utf-8")
        self.assertNotIn("CREATE TABLE IF NOT EXISTS", source)
        self.assertNotIn("CREATE INDEX IF NOT EXISTS", source)
        self.assertNotIn("mars_assistant_messages", source)

    def test_session_node_exposes_only_run_operations(self):
        node_path = Path(__file__).parent / "src/graphs/nodes/mars_assistant_session_node.py"
        source = node_path.read_text(encoding="utf-8")
        for operation in (
            'operation_type == "list_messages"',
            'operation_type == "upsert_message"',
            'operation_type == "append_item"',
            'operation_type == "list_items"',
            'operation_type == "upsert_resource_binding"',
            'operation_type == "list_resource_bindings"',
        ):
            self.assertNotIn(operation, source)
        self.assertNotIn("prompt=state.prompt", source)
        self.assertIn('else {}', source)

    def test_public_state_does_not_expose_server_chat_snapshots(self):
        state_source = (Path(__file__).parent / "src/graphs/state.py").read_text(encoding="utf-8")
        node_source = (Path(__file__).parent / "src/graphs/node.py").read_text(encoding="utf-8")
        for field_name in ("task_state", "image_asset_state", "merge_generated_images"):
            self.assertNotIn(f"{field_name}:", state_source)
            self.assertNotIn(f"{field_name}=input_data", node_source)


if __name__ == "__main__":
    unittest.main()
