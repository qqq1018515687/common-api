"""Favorite image workflow node."""
import logging
from typing import Optional

from coze_coding_utils.runtime_ctx.context import Context
from langchain_core.runnables import RunnableConfig
from langgraph.runtime import Runtime
from pydantic import BaseModel, Field, ValidationError

from storage.database.db import get_session
from storage.database.favorite_image_manager import (
    FavoriteImageAdd,
    FavoriteImageManager,
    FavoriteImageRemove,
)

logger = logging.getLogger(__name__)


class FavoriteImageInput(BaseModel):
    operation_type: str = Field(..., description="add_favorite_image/remove_favorite_image/list_favorite_images")
    user_id: Optional[str] = Field(default=None, description="User ID")
    task_id: Optional[str] = Field(default=None, description="Task ID")
    task_data: Optional[dict] = Field(default=None, description="Favorite payload")
    metadata: Optional[dict] = Field(default=None, description="Compatible favorite payload")
    limit: Optional[int] = Field(default=None, description="Page size")
    before_time: Optional[int] = Field(default=None, description="Cursor timestamp")


class FavoriteImageOutput(BaseModel):
    response_data: dict = Field(default={}, description="Unified response data")


def _ok(data: dict, msg: str = "Operation succeeded") -> FavoriteImageOutput:
    return FavoriteImageOutput(response_data={"code": 0, "msg": msg, "data": data})


def _fail(msg: str, code: int = 1, error_code: str = "FAVORITE_IMAGE_ERROR") -> FavoriteImageOutput:
    return FavoriteImageOutput(response_data={"code": code, "error_code": error_code, "msg": msg, "data": None})


def _payload(state: FavoriteImageInput) -> dict:
    data = {}
    if isinstance(state.metadata, dict):
        data.update(state.metadata)
    if isinstance(state.task_data, dict):
        data.update(state.task_data)
    if state.task_id and not data.get("task_id"):
        data["task_id"] = state.task_id
    if state.limit is not None and not data.get("limit"):
        data["limit"] = state.limit
    if state.before_time is not None and not data.get("before_time"):
        data["before_time"] = state.before_time
    return data


def favorite_image_node(
    state: FavoriteImageInput,
    config: RunnableConfig,
    runtime: Runtime[Context],
) -> FavoriteImageOutput:
    """
    title: Favorite image management
    desc: Add, remove and list image-level favorites stored independently from tasks.
    integrations: database, object storage
    """
    void_context = runtime.context
    void_context

    if not state.user_id:
        return _fail("Missing user_id", code=400, error_code="USER_ID_REQUIRED")

    operation_type = state.operation_type
    payload = _payload(state)
    db = get_session()
    try:
        manager = FavoriteImageManager()

        if operation_type == "add_favorite_image":
            favorite_in = FavoriteImageAdd(
                user_id=state.user_id,
                task_id=payload.get("task_id"),
                image_index=payload.get("image_index"),
                source_url=payload.get("source_url"),
                source_url_candidates=payload.get("source_url_candidates") or [],
                thumbnail_url=payload.get("thumbnail_url"),
                workflow_id=payload.get("workflow_id"),
                workflow_name=payload.get("workflow_name"),
                model_name=payload.get("model_name"),
                parameter_snapshot=payload.get("parameter_snapshot"),
            )
            success, favorite, error = manager.add_favorite_image(db, favorite_in)
            if not success or not favorite:
                return _fail(error or "Failed to add favorite image", code=400)
            return _ok({"favorite": favorite}, "Favorite image added")

        if operation_type == "remove_favorite_image":
            favorite_in = FavoriteImageRemove(
                user_id=state.user_id,
                favorite_id=payload.get("favorite_id"),
                task_id=payload.get("task_id"),
                image_index=payload.get("image_index"),
            )
            success, deleted, error = manager.remove_favorite_image(db, favorite_in)
            if not success:
                return _fail(error or "Failed to remove favorite image", code=400)
            message = "Favorite image removed" if deleted else "Favorite image was not present"
            return _ok({"message": message, "deleted": deleted}, message)

        if operation_type == "list_favorite_images":
            success, data, error = manager.list_favorite_images(
                db,
                user_id=state.user_id,
                limit=payload.get("limit") or state.limit or 60,
                before_time=payload.get("before_time") or state.before_time,
            )
            if not success or data is None:
                return _fail(error or "Failed to list favorite images", code=400)
            return _ok(data, "Favorite images listed")

        return _fail(f"Unsupported favorite image operation: {operation_type}", code=400, error_code="UNSUPPORTED_OPERATION")

    except ValidationError as exc:
        return _fail(str(exc), code=400, error_code="INVALID_REQUEST")
    except Exception as exc:
        logger.exception("Favorite image management failed")
        return _fail(f"Favorite image management failed: {exc}", code=500, error_code="INTERNAL_ERROR")
    finally:
        db.close()
