from __future__ import annotations

from decimal import Decimal
from typing import Any, Dict, Optional


_GENERATION_TYPES = {"generate": "image", "image": "image", "video": "video", "audio": "audio"}
_TUDOU_MODELS = {
    "banana2_tudou",
    "banana_pro_tudou",
    "gpt_image_2_tudou",
    "gpt_image_2_5_flare_tudou",
}


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
    if isinstance(billing_metadata, dict):
        merged.update(billing_metadata)
    if isinstance(metadata, dict):
        nested = metadata.get("billing_metadata")
        if isinstance(nested, dict):
            merged.update(nested)
    return merged


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
    team_id = team_id or merged.get("team_id")
    raw_type = str(merged.get("task_type") or merged.get("type") or "").strip().lower()
    platform = str(
        merged.get("platform") or merged.get("provider") or merged.get("selected_account") or ""
    ).strip().lower()
    model_key = str(merged.get("model_key") or merged.get("model_name") or "").strip()
    has_generation_context = any(
        merged.get(key) not in (None, "")
        for key in ("workflow", "workflow_id", "workflow_name", "model_key", "model_name")
    )
    is_tudou = platform == "tudou" or model_key in _TUDOU_MODELS or model_key.endswith("_tudou")

    task_type = _GENERATION_TYPES.get(raw_type)
    if task_type is None and (is_tudou or merged.get("source") == "aigc_frontend") and has_generation_context:
        task_type = "image"
    if task_type is None:
        return None
    if not platform:
        platform = "tudou" if is_tudou else "billing"

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
