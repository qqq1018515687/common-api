from __future__ import annotations

from decimal import Decimal, InvalidOperation
from typing import Any, Dict, Optional


_GENERATION_TYPES = {"generate": "image", "image": "image", "video": "video", "audio": "audio"}
def _json_number(value: Any) -> Any:
    if isinstance(value, Decimal):
        return int(value) if value == value.to_integral_value() else float(value)
    return value


def merge_billing_metadata(
    *,
    extra_data: Optional[Dict[str, Any]] = None,
    billing_metadata: Optional[Dict[str, Any]] = None,
    metadata: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """Merge persisted and request metadata, with explicit request values winning."""
    merged = dict(extra_data or {})
    if isinstance(metadata, dict):
        for key in (
            "type", "task_type", "project_to_tasks", "platform", "provider",
            "selected_account", "workflow", "workflow_id", "workflow_name",
            "model_name", "model_key", "source", "team_id", "agent_run_id",
            "agent_step_id",
        ):
            if metadata.get(key) is not None:
                merged[key] = metadata[key]
    if isinstance(billing_metadata, dict):
        merged.update(billing_metadata)
    if isinstance(metadata, dict):
        nested = metadata.get("billing_metadata")
        if isinstance(nested, dict):
            merged.update(nested)
    return merged


def validate_idempotency_record(
    existing: Dict[str, Any],
    *,
    operation_type: str,
    user_id: str,
    credit_type: str,
    amount: Any,
    task_id: Optional[str],
    related_id: Optional[str],
) -> Optional[str]:
    """Return the first conflicting idempotency field, or None for an exact replay."""
    expected = {
        "operation_type": operation_type,
        "user_id": user_id,
        "credit_type": credit_type,
        "task_id": task_id,
        "related_id": related_id,
    }
    for field, expected_value in expected.items():
        if str(existing.get(field) or "") != str(expected_value or ""):
            return field
    try:
        if Decimal(str(existing.get("amount"))) != Decimal(str(amount)):
            return "amount"
    except (InvalidOperation, TypeError, ValueError):
        return "amount"
    return None


def is_refundable_billing_skeleton(
    *, platform_task_id: Any, result: Any, parameter_snapshot: Any
) -> bool:
    if not isinstance(platform_task_id, str) or not platform_task_id.startswith("pending:"):
        return False
    if result not in (None, {}):
        return False
    snapshot = parameter_snapshot if isinstance(parameter_snapshot, dict) else {}
    return snapshot.get("billingProjection") is True


def build_billing_task_projection(
    *,
    task_id: Optional[str],
    user_id: str,
    team_id: Optional[str],
    billing_record_id: str,
    amount: Any,
    mode: str,
    extra_data: Optional[Dict[str, Any]] = None,
    billing_metadata: Optional[Dict[str, Any]] = None,
    metadata: Optional[Dict[str, Any]] = None,
) -> Optional[Dict[str, Any]]:
    """Build a task skeleton only when billing metadata identifies a generation task."""
    merged = merge_billing_metadata(
        extra_data=extra_data,
        billing_metadata=billing_metadata,
        metadata=metadata,
    )
    normalized_task_id = str(task_id or merged.get("task_id") or merged.get("billing_task_id") or "").strip()
    if not normalized_task_id:
        return None
    if str(merged.get("agent_run_id") or "").strip() or str(merged.get("agent_step_id") or "").strip():
        return None
    team_id = team_id or merged.get("team_id")
    raw_type = str(merged.get("task_type") or merged.get("type") or "").strip().lower()
    platform = str(
        merged.get("platform") or merged.get("provider") or merged.get("selected_account") or ""
    ).strip().lower()
    model_key = str(merged.get("model_key") or merged.get("model_name") or "").strip()
    task_type = _GENERATION_TYPES.get(raw_type)
    if task_type is None and merged.get("project_to_tasks") is True:
        task_type = "image"
    if task_type is None:
        return None
    if not platform:
        platform = "billing"

    workflow_id = merged.get("workflow_id") or merged.get("workflow")
    workflow_parameters = {
        key: value
        for key, value in merged.items()
        if value is not None
    }
    parameter_snapshot = {
        "workflowId": workflow_id,
        "workflowName": merged.get("workflow_name"),
        "modelName": merged.get("model_display_name"),
        "modelValue": model_key or None,
        "channelLabel": merged.get("channel_label"),
        "billingMetadata": merged,
        "billingProjection": True,
        "confirmationState": "pending",
        "pendingReason": "账单已扣费，等待生成平台返回任务ID",
    }
    parameter_snapshot = {key: value for key, value in parameter_snapshot.items() if value is not None}

    return {
        "id": normalized_task_id,
        "user_id": user_id,
        "team_id": team_id,
        "platform": platform,
        "platform_task_id": f"pending:{normalized_task_id}",
        "type": task_type,
        "status": "submitted_unconfirmed",
        "workflow_parameters": workflow_parameters,
        "parameter_snapshot": parameter_snapshot,
        "deduction_result": {
            "billing_record_id": billing_record_id,
            "status": "deducted",
            "amount": _json_number(amount),
            "mode": mode,
        },
    }


def build_terminal_deduction_result(
    projection: Dict[str, Any], *, status: str, record_id: str
) -> Dict[str, Any]:
    result = dict(projection["deduction_result"])
    result["status"] = status
    result[f"{status}_record_id"] = record_id
    return result
