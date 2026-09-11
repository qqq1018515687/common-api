from decimal import Decimal
from pathlib import Path
import sys


sys.path.insert(0, str(Path(__file__).parent / "src"))

from storage.database.billing_task_projection import (  # noqa: E402
    build_billing_task_projection,
    build_terminal_deduction_result,
)


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


def test_terminal_result_preserves_original_deduct_and_adds_terminal_record():
    projection = build_billing_task_projection(
        task_id="task-2",
        user_id="user-1",
        team_id=None,
        billing_record_id="bill-3",
        amount=3,
        mode="personal_gold",
        extra_data={"provider": "tudou", "model_name": "gpt_image_2_tudou"},
    )

    assert projection is not None
    assert build_terminal_deduction_result(
        projection, status="refunded", record_id="refund-1"
    ) == {
        "billing_record_id": "bill-3",
        "status": "refunded",
        "amount": 3,
        "mode": "personal_gold",
        "refunded_record_id": "refund-1",
    }
