from contextlib import contextmanager
import sys
import types
import unittest
from unittest.mock import patch

sqlalchemy_stub = types.ModuleType("sqlalchemy")
sqlalchemy_stub.text = lambda statement: statement
sys.modules.setdefault("sqlalchemy", sqlalchemy_stub)

database_stub = types.ModuleType("storage.database.db")
database_stub.get_engine = lambda: None
sys.modules.setdefault("storage.database.db", database_stub)

from storage.database import mars_assistant_session_manager as manager


class FakeResult:
    def __init__(self, row):
        self.row = row

    def mappings(self):
        return self

    def first(self):
        return self.row


class FakeConnection:
    def __init__(self, row):
        self.rows = list(row) if isinstance(row, list) else None
        self.row = row if self.rows is None else None
        self.calls = []

    def execute(self, statement, params):
        self.calls.append((str(statement), params))
        if self.rows is not None:
            return FakeResult(self.rows.pop(0) if self.rows else None)
        return FakeResult(self.row)


class FakeEngine:
    def __init__(self, connection):
        self.connection = connection

    @contextmanager
    def begin(self):
        yield self.connection


def install_fake_database(test_case, row):
    connection = FakeConnection(row)
    for name in (
        "ensure_mars_assistant_session_table",
        "ensure_mars_assistant_message_table",
        "ensure_mars_assistant_artifact_table",
        "ensure_mars_assistant_attachment_tables",
    ):
        test_case.enterContext(patch.object(manager, name, lambda: None))
    test_case.enterContext(patch.object(manager, "get_engine", lambda: FakeEngine(connection)))
    return connection


class MarsAssistantSessionManagerTest(unittest.TestCase):
    def test_patch_state_updates_only_explicit_fields(self):
        connection = install_fake_database(self, {"session_id": "session-1", "user_id": "user-1"})

        result = manager.patch_session_state(
            session_id="session-1",
            user_id="user-1",
            task_state={"status": "running"},
            image_asset_state=None,
            metadata=None,
            update_fields={"task_state"},
        )

        sql, _ = connection.calls[0]
        self.assertEqual(result["user_id"], "user-1")
        self.assertIn("task_state = CAST(:task_state AS JSONB)", sql)
        self.assertNotIn("image_asset_state = CAST(:image_asset_state AS JSONB)", sql)
        self.assertNotIn("metadata = CAST(:metadata AS JSONB)", sql)
        self.assertIn("WHERE mars_assistant_sessions.user_id = EXCLUDED.user_id", sql)
        self.assertIn("RETURNING *", sql)

    def test_metadata_patch_merges_existing_keys(self):
        connection = install_fake_database(self, {"session_id": "session-1", "user_id": "user-1"})

        manager.patch_session_state(
            session_id="session-1",
            user_id="user-1",
            metadata={"activeEditBaseArtifactId": "artifact-2"},
            update_fields={"metadata"},
        )

        sql, _ = connection.calls[0]
        self.assertIn("jsonb_typeof(mars_assistant_sessions.metadata) = 'object'", sql)
        self.assertIn("ELSE '{}'::jsonb", sql)
        self.assertIn("|| CAST(:metadata AS JSONB)", sql)

    def test_patch_state_uses_atomic_generated_image_merge(self):
        connection = install_fake_database(self, {"session_id": "session-1", "user_id": "user-1"})

        manager.patch_session_state(
            session_id="session-1",
            user_id="user-1",
            image_asset_state={"generatedImages": [{"id": "image-2"}]},
            update_fields={"image_asset_state"},
            merge_generated_images=True,
        )

        sql, params = connection.calls[0]
        self.assertIn("jsonb_array_elements", sql)
        self.assertIn("DISTINCT ON (item->>'id')", sql)
        self.assertIn("jsonb_typeof(mars_assistant_sessions.image_asset_state) = 'object'", sql)
        self.assertIn("jsonb_typeof(mars_assistant_sessions.image_asset_state->'generatedImages') = 'array'", sql)
        self.assertIn("mars_assistant_sessions.image_asset_state", sql)
        self.assertIn('"image-2"', params["image_asset_state"])

    def test_owner_conflicts_are_rejected(self):
        cases = [
            (
                manager.upsert_session_state,
                {"session_id": "session-1", "user_id": "user-2"},
                "会话不存在或无权访问",
            ),
            (
                manager.upsert_session_message,
                {"message_id": "message-1", "session_id": "session-1", "user_id": "user-2", "role": "user"},
                "消息不存在或无权访问",
            ),
            (
                manager.upsert_session_artifact,
                {"artifact_id": "artifact-1", "session_id": "session-1", "user_id": "user-2", "artifact_type": "image"},
                "产物不存在或无权访问",
            ),
            (
                manager.upsert_attachment,
                {
                    "attachment_id": "attachment-1",
                    "session_id": "session-1",
                    "user_id": "user-2",
                    "name": "image.png",
                    "mime_type": "image/png",
                    "kind": "image",
                    "size": 10,
                },
                "附件不存在或无权访问",
            ),
        ]
        for operation, kwargs, error in cases:
            with self.subTest(operation=operation.__name__):
                connection = install_fake_database(self, None)
                with self.assertRaisesRegex(PermissionError, error):
                    operation(**kwargs)
                sql, _ = connection.calls[0]
                self.assertIn("EXCLUDED.user_id", sql)
                self.assertIn("RETURNING *", sql)
                if operation is not manager.upsert_session_state:
                    self.assertIn("FROM mars_assistant_sessions", sql)
                    self.assertIn("session_id = :session_id AND user_id = :user_id", sql)

    def test_attachment_content_requires_owned_parent(self):
        connection = install_fake_database(self, None)

        with self.assertRaisesRegex(PermissionError, "附件不存在或无权访问"):
            manager.upsert_attachment_content(
                attachment_id="attachment-1",
                session_id="session-1",
                user_id="user-2",
                full_text="content",
                summary=None,
                structured_json=None,
            )

        sql, params = connection.calls[0]
        self.assertIn("session_id = :session_id", sql)
        self.assertIn("user_id = :user_id", sql)
        self.assertIn("FOR UPDATE", sql)
        self.assertEqual(params["user_id"], "user-2")

    def test_child_resources_require_owned_session_on_insert(self):
        cases = [
            (
                manager.upsert_session_message,
                {"message_id": "message-1", "session_id": "session-1", "user_id": "user-1", "role": "user"},
            ),
            (
                manager.upsert_session_artifact,
                {"artifact_id": "artifact-1", "session_id": "session-1", "user_id": "user-1", "artifact_type": "image"},
            ),
            (
                manager.upsert_attachment,
                {
                    "attachment_id": "attachment-1",
                    "session_id": "session-1",
                    "user_id": "user-1",
                    "name": "image.png",
                    "mime_type": "image/png",
                    "kind": "image",
                    "size": 10,
                },
            ),
        ]
        for operation, kwargs in cases:
            with self.subTest(operation=operation.__name__):
                connection = install_fake_database(self, {"id": "created", "user_id": "user-1"})
                operation(**kwargs)
                sql, _ = connection.calls[0]
                self.assertIn("FROM mars_assistant_sessions", sql)
                self.assertIn("session_id = :session_id AND user_id = :user_id", sql)


if __name__ == "__main__":
    unittest.main()
