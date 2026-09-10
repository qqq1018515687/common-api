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

    def all(self):
        return self.row or []


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
    test_case.enterContext(patch.object(manager, "get_engine", lambda: FakeEngine(connection)))
    return connection


class MarsAssistantSessionManagerTest(unittest.TestCase):
    def test_image_tool_arguments_keep_only_scalar_execution_metadata(self):
        result = manager._compact_image_tool_arguments({
            "instruction": "完整提示词",
            "requestedImageCount": 2,
            "sequenceStart": 4,
            "requestedAspectRatio": "1:1",
            "model": {"instruction": "嵌套提示词"},
        })

        self.assertEqual(result, {
            "requestedImageCount": 2,
            "sequenceStart": 4,
            "requestedAspectRatio": "1:1",
        })
        self.assertEqual(manager._compact_image_tool_arguments(["完整提示词"]), {})

    def test_artifact_metadata_keeps_only_execution_relationships(self):
        result = manager._compact_artifact_metadata({
            "runId": "run-1",
            "prompt": "顶层提示词",
            "frame": {"index": 1, "instruction": "嵌套指令"},
            "items": [{"prompt": "列表提示词", "sequence": 1}],
        })

        self.assertEqual(result, {
            "runId": "run-1",
            "frame": {"index": 1},
        })

    def test_session_metadata_keeps_only_artifact_pointers(self):
        result = manager._compact_session_metadata({
            "activeEditBaseArtifactId": "artifact-1",
            "latestGeneratedArtifactId": "artifact-2",
            "task_state": {"instruction": "不应保存"},
            "run": {"tool_arguments": {"prompt": "不应保存"}},
        })

        self.assertEqual(result, {
            "activeEditBaseArtifactId": "artifact-1",
            "latestGeneratedArtifactId": "artifact-2",
        })

    def test_attachment_metadata_keeps_only_parse_summary(self):
        result = manager._compact_attachment_metadata({
            "summary": "文档摘要",
            "contentLength": 128,
            "prompt": "不应保存",
            "run": {"instruction": "不应保存"},
        })

        self.assertEqual(result, {"summary": "文档摘要", "contentLength": 128})

    def test_patch_state_ignores_server_side_chat_payload_fields(self):
        connection = install_fake_database(self, {"session_id": "session-1", "user_id": "user-1"})

        result = manager.patch_session_state(
            session_id="session-1",
            user_id="user-1",
            metadata=None,
            update_fields={"task_state", "image_asset_state"},
        )

        sql, _ = connection.calls[0]
        self.assertEqual(result["user_id"], "user-1")
        self.assertNotIn("task_state = CAST(:task_state AS JSONB)", sql)
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

    def test_owner_conflicts_are_rejected(self):
        cases = [
            (
                manager.upsert_session_state,
                {"session_id": "session-1", "user_id": "user-2"},
                "会话不存在或无权访问",
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

    def test_create_agent_run_is_idempotent_and_serializes_payloads(self):
        connection = install_fake_database(self, [
            {"id": "attachment-1"},
            {"id": "artifact-1"},
            {"id": "run-existing", "user_id": "user-1"},
        ])

        result = manager.create_agent_run(
            run_id="run-new",
            conversation_id="session-1",
            user_id="user-1",
            idempotency_key="request-1",
            status="queued",
            provider_task_id="provider-task-1",
            tool_name="generate_images",
            tool_arguments={"prompt": "火星", "requestedImageCount": 2},
            input_resources=[{
                "resource_type": "attachment",
                "resource_id": "attachment-1",
                "binding_role": "product_reference",
                "unexpected": "不应保存",
            }],
            result_artifact_ids=["artifact-1"],
            error={"message": "可重试"},
        )

        sql, params = connection.calls[-1]
        self.assertEqual(result["id"], "run-existing")
        self.assertIn("FROM mars_assistant_sessions", sql)
        self.assertIn("session_id = :conversation_id AND user_id = :user_id", sql)
        self.assertIn("ON CONFLICT (user_id, conversation_id, idempotency_key)", sql)
        self.assertEqual(params["provider_task_id"], "provider-task-1")
        self.assertNotIn("prompt", params["tool_arguments"])
        self.assertIn('"requestedImageCount": 2', params["tool_arguments"])
        self.assertIn('"attachment-1"', params["input_resources"])
        self.assertNotIn("unexpected", params["input_resources"])
        self.assertIn('"artifact-1"', params["result_artifact_ids"])
        self.assertIn('"message": "可重试"', params["error"])

    def test_create_agent_run_requires_owned_continuation_parent(self):
        connection = install_fake_database(
            self,
            None,
        )

        with self.assertRaisesRegex(ValueError, "不属于当前用户和会话"):
            manager.create_agent_run(
                run_id="run-child",
                conversation_id="session-1",
                user_id="user-1",
                idempotency_key="request-child",
                status="queued",
                tool_name="generate_images",
                continuation_of_run_id="run-other-owner",
            )

        sql, params = connection.calls[0]
        self.assertIn("id = :continuation_of_run_id", sql)
        self.assertIn("conversation_id = :conversation_id", sql)
        self.assertIn("user_id = :user_id", sql)
        self.assertEqual(params["continuation_of_run_id"], "run-other-owner")

    def test_create_agent_run_rejects_non_image_tools(self):
        install_fake_database(self, None)

        with self.assertRaisesRegex(ValueError, "只允许创建 generate_images Run"):
            manager.create_agent_run(
                run_id="run-chat",
                conversation_id="session-1",
                user_id="user-1",
                idempotency_key="request-chat",
                status="queued",
                tool_name="chat_response",
            )

    def test_create_agent_run_rejects_non_array_resources(self):
        install_fake_database(self, None)

        with self.assertRaisesRegex(ValueError, "输入资源格式无效"):
            manager.create_agent_run(
                run_id="run-invalid-input",
                conversation_id="session-1",
                user_id="user-1",
                idempotency_key="request-invalid-input",
                status="queued",
                tool_name="generate_images",
                input_resources={},
            )
        with self.assertRaisesRegex(ValueError, "结果产物格式无效"):
            manager.create_agent_run(
                run_id="run-invalid-result",
                conversation_id="session-1",
                user_id="user-1",
                idempotency_key="request-invalid-result",
                status="queued",
                tool_name="generate_images",
                result_artifact_ids={},
            )

    def test_update_agent_run_serializes_result_fields(self):
        connection = install_fake_database(self, [
            {"id": "artifact-1"},
            {"id": "run-1", "status": "completed"},
        ])

        manager.update_agent_run(
            run_id="run-1",
            conversation_id="session-1",
            user_id="user-1",
            updates={
                "status": "completed",
                "result_artifact_ids": ["artifact-1"],
            },
        )

        sql, params = connection.calls[-1]
        self.assertIn("result_artifact_ids = CAST(:result_artifact_ids AS JSONB)", sql)
        self.assertIn('"artifact-1"', params["result_artifact_ids"])

    def test_update_agent_run_rejects_unknown_fields(self):
        install_fake_database(self, None)

        with self.assertRaisesRegex(ValueError, "不支持的 run 更新字段"):
            manager.update_agent_run(
                run_id="run-1",
                conversation_id="session-1",
                user_id="user-1",
                updates={"idempotency_key": "changed"},
            )

        with self.assertRaisesRegex(ValueError, "不支持的 run 更新字段"):
            manager.update_agent_run(
                run_id="run-1",
                conversation_id="session-1",
                user_id="user-1",
                updates={"continuation_of_run_id": "run-other"},
            )

        with self.assertRaisesRegex(ValueError, "结果产物格式无效"):
            manager.update_agent_run(
                run_id="run-1",
                conversation_id="session-1",
                user_id="user-1",
                updates={"result_artifact_ids": {}},
            )

    def test_list_agent_runs_filters_tool_and_status_by_creation_time(self):
        connection = install_fake_database(self, [[{"id": "run-1"}]])

        result = manager.list_agent_runs(
            "session-1",
            user_id="user-1",
            status="completed",
            tool_name="generate_images",
            limit=1,
        )

        sql, params = connection.calls[0]
        self.assertEqual(result, [{"id": "run-1"}])
        self.assertIn("r.status = :status", sql)
        self.assertIn("r.tool_name = :tool_name", sql)
        self.assertIn("ORDER BY r.created_at DESC", sql)
        self.assertEqual(params["status"], "completed")
        self.assertEqual(params["tool_name"], "generate_images")
        self.assertEqual(params["limit"], 1)

if __name__ == "__main__":
    unittest.main()
