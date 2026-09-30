"""Authenticated storage reads for prompt vision inputs."""

import logging

from fastapi import APIRouter, Header, HTTPException
from fastapi.concurrency import run_in_threadpool
from fastapi.responses import Response
from pydantic import BaseModel

from storage.storage_manager import get_storage_manager
from utils.backend_auth import require_backend_authorization


logger = logging.getLogger(__name__)
router = APIRouter()
MAX_PROMPT_IMAGE_BYTES = 30 * 1024 * 1024
ALLOWED_PREFIXES = ("uploads/", "temp/", "favorites/")


class PromptImageReadRequest(BaseModel):
    file_key: str
    operator_user_id: str


@router.post("/prompt-images/read")
async def read_prompt_image(
    payload: PromptImageReadRequest,
    authorization: str | None = Header(default=None),
) -> Response:
    """Return bounded image bytes only to an authenticated backend for the owning user."""
    require_backend_authorization(authorization)
    key = payload.file_key.strip()
    owner = payload.operator_user_id.strip()
    if not owner or not key.startswith(ALLOWED_PREFIXES) or ".." in key or "//" in key or "\\" in key:
        raise HTTPException(status_code=400, detail="Invalid prompt image reference")

    storage_mgr = get_storage_manager()
    metadata = await run_in_threadpool(storage_mgr.get_file_metadata, key)
    if not metadata:
        raise HTTPException(status_code=404, detail="Prompt image not found")
    # Upload metadata is assigned by the website's authenticated upload proxy.
    if metadata.get("operator_user_id") != owner:
        raise HTTPException(status_code=403, detail="Prompt image owner mismatch")
    if await run_in_threadpool(storage_mgr.is_expired, key):
        raise HTTPException(status_code=410, detail="Prompt image expired")

    try:
        content = await run_in_threadpool(
            storage_mgr.storage.read_file,
            file_key=key,
            max_bytes=MAX_PROMPT_IMAGE_BYTES,
        )
    except ValueError as exc:
        raise HTTPException(status_code=413, detail="Prompt image exceeds size limit") from exc
    except Exception as exc:
        logger.exception("Prompt image storage read failed")
        raise HTTPException(status_code=502, detail="Prompt image storage read failed") from exc

    if not content:
        raise HTTPException(status_code=404, detail="Prompt image is empty")
    logger.info("Prompt image read succeeded: bytes=%s", len(content))
    return Response(
        content=content,
        media_type="application/octet-stream",
        headers={"Cache-Control": "no-store"},
    )
