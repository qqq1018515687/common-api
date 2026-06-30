"""Seat map management workflow node."""
import logging
from typing import Optional

from coze_coding_utils.runtime_ctx.context import Context
from langchain_core.runnables import RunnableConfig
from langgraph.runtime import Runtime
from pydantic import BaseModel, Field

from storage.database.db import get_session
from storage.database.seat_map_manager import SeatMapManager

logger = logging.getLogger(__name__)


class SeatMapInput(BaseModel):
    """Seat map input - follows favorite_image pattern"""
    operation_type: str = Field(..., description="get_seat_map/update_seat_map/validate_schema")
    metadata: Optional[dict] = Field(default=None, description="Seat map payload container")


class SeatMapOutput(BaseModel):
    """Seat map output - standard response format"""
    response_data: dict = Field(default={}, description="Unified response data")


def _ok(data: dict, msg: str = "Operation succeeded") -> SeatMapOutput:
    """Success response"""
    return SeatMapOutput(response_data={"code": 0, "msg": msg, "data": data})


def _fail(msg: str, code: int = 1, error_code: str = "SEAT_MAP_ERROR", data: Optional[dict] = None) -> SeatMapOutput:
    """Failure response"""
    return SeatMapOutput(response_data={"code": code, "error_code": error_code, "msg": msg, "data": data})


def _payload(state: SeatMapInput) -> dict:
    """Extract seat map payload from metadata"""
    payload = state.metadata or {}
    return {
        "data": payload.get("data"),
        "expected_version": payload.get("expected_version"),
        "updated_by_label": payload.get("updated_by_label", "Anonymous editor")
    }


def seat_map_node(
    state: SeatMapInput,
    config: RunnableConfig,
    runtime: Runtime[Context],
) -> SeatMapOutput:
    """
    title: Seat map management
    desc: Manage company seat map data with version control
    integrations: database
    """
    ctx = runtime.context
    ctx  # Void context usage

    operation_type = state.operation_type
    payload = _payload(state)

    manager = SeatMapManager()
    db = get_session()

    try:
        if operation_type == "get_seat_map":
            success, result, error = manager.get_latest_seat_map(db)

            if success:
                return _ok(result, "Seat map retrieved successfully")
            else:
                return _fail(error or "Failed to retrieve seat map", code=2, error_code="GET_FAILED")

        elif operation_type == "update_seat_map":
            if not payload["data"]:
                return _fail("Missing seat map data", code=3, error_code="MISSING_DATA")

            success, result, error = manager.update_seat_map(
                db,
                payload["data"],
                payload["expected_version"],
                payload["updated_by_label"]
            )

            if success:
                return _ok(result, "Seat map updated successfully")
            elif error and ("Version conflict" in error or "updated by others" in error):
                return _fail(error, code=409, error_code="VERSION_CONFLICT", data=result)
            else:
                return _fail(error or "Failed to update seat map", code=4, error_code="UPDATE_FAILED")

        elif operation_type == "validate_schema":
            success, result, error = manager.validate_schema(db)

            if success:
                return _ok(result, "Schema validation succeeded")
            else:
                return _fail(error or "Schema validation failed", code=5, error_code="SCHEMA_ERROR")

        else:
            return _fail(f"Unknown operation type: {operation_type}", code=6, error_code="INVALID_OPERATION")

    except Exception as e:
        logger.error(f"seat_map_node error: {e}")
        return _fail(f"Internal error: {str(e)}", code=500, error_code="INTERNAL_ERROR")

    finally:
        db.close()