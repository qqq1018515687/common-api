from pathlib import Path

from src.storage.database.task_manager import TaskManager


ROOT = Path(__file__).parent
TASK_SOURCE = ROOT.joinpath("src/storage/database/task_manager.py").read_text(encoding="utf-8")
BILLING_SOURCE = ROOT.joinpath("src/storage/database/billing_manager.py").read_text(encoding="utf-8")
NODE_SOURCE = ROOT.joinpath("src/graphs/node.py").read_text(encoding="utf-8")
MAIN_SOURCE = ROOT.joinpath("src/main.py").read_text(encoding="utf-8")


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


def test_recovery_timeout_uses_original_pending_time():
    assert 'snapshot.get("pendingSince")' in MAIN_SOURCE
    recovery_section = MAIN_SOURCE.split("def _trigger_third_party_task_recovery", 1)[1]
    assert 'recovery_status == "terminal_failure"' in recovery_section
    assert 'int(result.get("code", -1)) == 807' not in recovery_section


def test_single_image_channels_keep_only_the_last_result():
    result = {
        "imageUrls": ["preview", "final"],
        "files": [{"file_url": "preview"}, {"file_url": "final"}],
        "previewUrl": "preview",
        "metadata": {
            "localProvider": {
                "commonPublicUrl": "preview",
                "commonPublicUrls": ["preview", "final"],
                "imageUrls": ["preview", "final"],
                "rawImageUrls": ["raw-preview", "raw-final"],
            },
        },
        "raw_response": {"data": [{"fileUrl": "preview"}, {"fileUrl": "final"}]},
    }

    normalized = TaskManager._normalize_single_image_channel_result("tudou", result)

    assert normalized["imageUrls"] == ["final"]
    assert normalized["files"] == [{"file_url": "final"}]
    assert normalized["previewUrl"] == "final"
    assert normalized["metadata"]["localProvider"]["commonPublicUrl"] == "final"
    assert normalized["metadata"]["localProvider"]["commonPublicUrls"] == ["final"]
    assert normalized["metadata"]["localProvider"]["imageUrls"] == ["final"]
    assert normalized["metadata"]["localProvider"]["rawImageUrls"] == ["raw-preview", "raw-final"]
    assert normalized["raw_response"] == result["raw_response"]
    assert len(result["imageUrls"]) == 2


def test_multi_image_channel_result_is_unchanged():
    result = {"imageUrls": ["first", "second"]}

    assert TaskManager._normalize_single_image_channel_result("runninghub", result) is result


def test_mars_exclusive_channel_keeps_legacy_free_key():
    assert TaskManager._normalize_task_channel_from_label("免费") == "free"
    assert TaskManager._normalize_task_channel_from_label("火星特供") == "free"
