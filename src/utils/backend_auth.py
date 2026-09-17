import hmac
import logging
import os
from typing import Optional

from fastapi import HTTPException


logger = logging.getLogger(__name__)


def _configured_backend_tokens() -> list[str]:
    tokens: list[str] = []
    for name in ("COZE_BACKEND_TOKEN", "COMMON_SERVICE_TOKEN", "BILLING_SERVICE_TOKEN"):
        value = os.getenv(name, "").strip()
        if value and value not in tokens:
            tokens.append(value)
    return tokens


def require_backend_authorization(authorization: Optional[str]) -> None:
    expected_tokens = _configured_backend_tokens()
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Missing backend authorization")
    if not expected_tokens:
        logger.error("Backend service token is not configured")
        raise HTTPException(status_code=503, detail="Backend authorization is not configured")
    supplied_token = authorization.removeprefix("Bearer ")
    if not any(hmac.compare_digest(supplied_token, token) for token in expected_tokens):
        raise HTTPException(status_code=401, detail="Invalid backend authorization")
