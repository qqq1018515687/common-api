from decimal import Decimal
from pathlib import Path
import sys


sys.path.insert(0, str(Path(__file__).parent / "src"))

from storage.database.billing_task_projection import (  # noqa: E402
    build_billing_task_projection,
    build_terminal_deduction_result,
    is_refundable_billing_skeleton,
    merge_billing_metadata,
    validate_idempotency_record,
)


ROOT = Path(__file__).parent
BILLING_SOURCE = ROOT.joinpath("src/storage/database/billing_manager.py").read_text(encoding="utf-8")
MIGRATION_SOURCE = ROOT.joinpath(
    "migrations/versions/billtask001_backfill_tudou_tasks_from_billing.py"
).read_text(encoding="utf-8")
STATUS_MIGRATION_SOURCE = ROOT.joinpath(
    "migrations/versions/taskstatus001_reassert_task_status_length.py"
).read_text(encoding="utf-8")
REPAIR_MIGRATION_SOURCE = ROOT.joinpath(
    "migrations/versions/billtask002_repair_resultless_completed_billing_tasks.py"
).read_text(encoding="utf-8")
START_SCRIPT_SOURCE = ROOT.joinpath("scripts/http_run.sh").read_text(encoding="utf-8")


def test_builds_tudou_generation_skeleton_with_deducted_billing_result():
    projection = build_billing_task_projection(
        task_id="task-1",
        user_id="user-1",
        team_id="team-1",
        billing_record_id="bill-1",
        amount=Decimal("40.00"),
        mode="team_gold",
        billing_metadata={
            "platform": "tudou",
            "task_type": "generate",
            "workflow": "02",
            "workflow_name": "图像编辑",
            "model_key": "banana_pro_tudou",
            "model_display_name": "Banana Pro",
        },
    )

    assert projection is not None
    assert projection["platform"] == "tudou"
    assert projection["platform_task_id"] == "pending:task-1"
    assert projection["type"] == "image"
    assert projection["status"] == "submitted_unconfirmed"
    assert projection["parameter_snapshot"]["workflowId"] == "02"
    assert projection["workflow_parameters"]["model_key"] == "banana_pro_tudou"
    assert projection["deduction_result"] == {
        "billing_record_id": "bill-1",
        "status": "deducted",
        "amount": 40,
        "mode": "team_gold",
    }


def test_task_status_schema_is_reasserted_by_migration_and_runtime_fallbacks():
    expected_ddl = "ALTER TABLE tasks ALTER COLUMN status TYPE VARCHAR(32)"

    assert expected_ddl in STATUS_MIGRATION_SOURCE
    assert expected_ddl in START_SCRIPT_SOURCE


def test_non_generation_billing_does_not_create_task_projection():
    projection = build_billing_task_projection(
        task_id="order-1",
        user_id="user-1",
        team_id=None,
        billing_record_id="bill-2",
        amount=10,
        mode="personal_gold",
        billing_metadata={"source": "recharge", "task_type": "exchange", "title": "金豆兑换"},
    )

    assert projection is None


def test_explicit_generation_type_supports_provider_generic_projection():
    projection = build_billing_task_projection(
        task_id="task-generic",
        user_id="user-1",
        team_id=None,
        billing_record_id="bill-generic",
        amount=2,
        mode="personal_gold",
        billing_metadata={"provider": "future-provider", "task_type": "video"},
    )

    assert projection is not None
    assert projection["platform"] == "future-provider"
    assert projection["type"] == "video"


def test_generation_type_from_main_metadata_creates_projection():
    projection = build_billing_task_projection(
        task_id="task-main",
        user_id="user-1",
        team_id=None,
        billing_record_id="bill-main",
        amount=2,
        mode="personal_gold",
        billing_metadata={"platform": "tudou", "model_key": "banana2_tudou"},
        metadata={"type": "generate", "workflow": "02"},
    )

    assert projection is not None
    assert projection["platform"] == "tudou"


def test_agent_billing_is_not_projected_to_normal_tasks():
    projection = build_billing_task_projection(
        task_id="agent-task",
        user_id="user-1",
        team_id=None,
        billing_record_id="bill-agent",
        amount=2,
        mode="personal_gold",
        metadata={"type": "generate", "workflow": "02", "agent_step_id": "step-1"},
    )

    assert projection is None


def test_projection_identity_is_preserved_in_persisted_metadata():
    merged = merge_billing_metadata(
        extra_data={"model_key": "banana2_tudou"},
        billing_metadata={"platform": "tudou"},
        metadata={"type": "generate", "agent_step_id": "step-1"},
    )

    assert merged["type"] == "generate"
    assert merged["agent_step_id"] == "step-1"


def test_tudou_provider_without_explicit_projection_signal_is_ignored():
    projection = build_billing_task_projection(
        task_id="task-2",
        user_id="user-1",
        team_id=None,
        billing_record_id="bill-3",
        amount=3,
        mode="personal_gold",
        extra_data={"provider": "tudou", "model_name": "gpt_image_2_tudou"},
    )

    assert projection is None


def test_explicit_projection_flag_allows_task_without_task_type():
    projection = build_billing_task_projection(
        task_id="task-2",
        user_id="user-1",
        team_id=None,
        billing_record_id="bill-3",
        amount=3,
        mode="personal_gold",
        extra_data={"provider": "tudou", "project_to_tasks": True},
    )

    assert projection is not None
    assert projection["parameter_snapshot"]["billingProjection"] is True
    assert build_terminal_deduction_result(
        projection, status="refunded", record_id="refund-1"
    ) == {
        "billing_record_id": "bill-3",
        "status": "refunded",
        "amount": 3,
        "mode": "personal_gold",
        "refunded_record_id": "refund-1",
    }
    enriched = {"deduction_result": {**projection["deduction_result"], "team_id": "team-1"}}
    assert build_terminal_deduction_result(
        enriched, status="settled", record_id="settle-1"
    )["team_id"] == "team-1"


def test_idempotency_replay_requires_every_identity_field_and_amount():
    existing = {
        "operation_type": "deduct",
        "user_id": "user-1",
        "credit_type": "personal_gold",
        "amount": Decimal("2.00"),
        "task_id": "task-1",
        "related_id": None,
    }
    expected = {
        "operation_type": "deduct",
        "user_id": "user-1",
        "credit_type": "personal_gold",
        "amount": 2,
        "task_id": "task-1",
        "related_id": None,
    }

    assert validate_idempotency_record(existing, **expected) is None
    for field in expected:
        conflicting = dict(expected)
        conflicting[field] = "different" if field != "amount" else 3
        assert validate_idempotency_record(existing, **conflicting) == field


def test_only_unresolved_resultless_billing_projection_can_be_failed_by_refund():
    skeleton = {
        "platform_task_id": "pending:task-1",
        "result": None,
        "parameter_snapshot": {"billingProjection": True},
    }
    assert is_refundable_billing_skeleton(**skeleton) is True
    assert is_refundable_billing_skeleton(**{**skeleton, "platform_task_id": "provider-1"}) is False
    assert is_refundable_billing_skeleton(**{**skeleton, "result": {"files": []}}) is False
    assert is_refundable_billing_skeleton(**{**skeleton, "parameter_snapshot": {}}) is False


def test_billing_settlement_does_not_complete_generation_skeleton():
    ensure_section = BILLING_SOURCE.split("def _ensure_billing_task(", 1)[1].split(
        "def get_balance", 1
    )[0]
    assert 'terminal_status == "settled" and is_refundable_billing_skeleton' not in ensure_section
    assert 'task.status = "completed"' not in ensure_section
    assert 'terminal_status == "refunded" and is_refundable_billing_skeleton' in ensure_section
    assert "WHEN t.settle_id IS NOT NULL THEN 'completed'" in MIGRATION_SOURCE
    assert "'banana2_tudou'" in MIGRATION_SOURCE
    assert "COALESCE(d.extra_data->>'workflow', '') = '02'" in MIGRATION_SOURCE
    assert "agent_run_id" in MIGRATION_SOURCE
    assert "agent_step_id" in MIGRATION_SOURCE
    assert 'db_task.status == "completed"' in ROOT.joinpath(
        "src/storage/database/task_manager.py"
    ).read_text(encoding="utf-8")


def test_repair_migration_removes_resultless_billing_projections_from_success_stats():
    assert 'down_revision: Union[str, Sequence[str], None] = "marsquota002"' in REPAIR_MIGRATION_SOURCE
    assert "SET status = 'failed'" in REPAIR_MIGRATION_SOURCE
    assert "platform_task_id LIKE 'pending:%'" in REPAIR_MIGRATION_SOURCE
    assert "parameter_snapshot->>'billingProjection'" in REPAIR_MIGRATION_SOURCE
    assert "result IS NULL" in REPAIR_MIGRATION_SOURCE
    assert "result_fallback IS NULL" in REPAIR_MIGRATION_SOURCE
    assert "final_reason = 'persistence_failed'" in REPAIR_MIGRATION_SOURCE
