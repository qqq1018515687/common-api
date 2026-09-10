from pathlib import Path


ROOT = Path(__file__).parent
TASK_SOURCE = ROOT.joinpath("src/storage/database/task_manager.py").read_text(encoding="utf-8")
BILLING_SOURCE = ROOT.joinpath("src/storage/database/billing_manager.py").read_text(encoding="utf-8")
NODE_SOURCE = ROOT.joinpath("src/graphs/node.py").read_text(encoding="utf-8")


def test_third_party_placeholder_is_a_submission_pending_state():
    assert 'task_data["status"] = "submitted_unconfirmed"' in TASK_SOURCE
    assert 'task_data["confirmation_state"] = "pending"' in TASK_SOURCE
    assert 'snapshot["confirmationState"] = "pending"' in TASK_SOURCE


def test_task_contract_preserves_authoritative_terminal_fields():
    for field in ("confirmation_state", "final_reason", "cancellation_source"):
        assert f'"{field}"' in NODE_SOURCE


def test_refund_and_settle_are_serialized_and_mutually_exclusive():
    assert 'lock_clause = " FOR UPDATE" if lock else ""' in BILLING_SOURCE
    assert "existing_refund = _find_existing_refund(db, original_record_id)" in BILLING_SOURCE
    assert '"already_processed": True' in BILLING_SOURCE
    settle_section = BILLING_SOURCE.split("def settle(", 1)[1]
    assert "_has_existing_refund(db, original_record_id)" in settle_section


def test_failed_task_refund_is_persisted_and_retried():
    assert '"status": "refunded"' in TASK_SOURCE
    assert 'updated_deduction["status"] = "settled"' in TASK_SOURCE
    assert "def retry_failed_task_refunds" in TASK_SOURCE
