import hmac
import logging
import os
from typing import Optional

from fastapi import HTTPException


logger = logging.getLogger(__name__)


def require_backend_authorization(authorization: Optional[str]) -> None:
    expected_token = os.getenv("COZE_BACKEND_TOKEN", "")
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Missing backend authorization")
    if not expected_token:
        logger.error("COZE_BACKEND_TOKEN is not configured")
        raise HTTPException(status_code=503, detail="Backend authorization is not configured")
    supplied_token = authorization.removeprefix("Bearer ")
    if not hmac.compare_digest(supplied_token, expected_token):
        raise HTTPException(status_code=401, detail="Invalid backend authorization")
