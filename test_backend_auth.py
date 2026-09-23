import asyncio
from pathlib import Path

import pytest
from fastapi import HTTPException

from api import tasks
from utils.backend_auth import require_backend_authorization


ROOT = Path(__file__).parent
AUTH_SOURCE = ROOT.joinpath("src/utils/backend_auth.py").read_text(encoding="utf-8")


def test_backend_auth_accepts_deployed_service_token_names():
    assert '"COZE_BACKEND_TOKEN"' in AUTH_SOURCE
    assert '"COMMON_SERVICE_TOKEN"' in AUTH_SOURCE
    assert '"BILLING_SERVICE_TOKEN"' in AUTH_SOURCE
    assert "hmac.compare_digest" in AUTH_SOURCE


def test_non_coze_service_token_authorizes_backend_requests(monkeypatch):
    monkeypatch.delenv("COZE_BACKEND_TOKEN", raising=False)
    monkeypatch.delenv("BILLING_SERVICE_TOKEN", raising=False)
    monkeypatch.setenv("COMMON_SERVICE_TOKEN", "common-test-token")

    require_backend_authorization("Bearer common-test-token")
    with pytest.raises(HTTPException) as error:
        require_backend_authorization("Bearer wrong-token")
    assert error.value.status_code == 401


@pytest.mark.parametrize("request", [
    lambda: tasks.recover_third_party_task(None, authorization=None),
    lambda: tasks.list_stale_running_tasks(None, authorization=None),
    lambda: tasks.get_task("task-id", authorization=None),
    lambda: tasks.list_persist_pending_tasks(authorization=None, limit=1),
])
def test_legacy_task_routes_reject_missing_auth_with_non_coze_key(monkeypatch, request):
    monkeypatch.delenv("COZE_BACKEND_TOKEN", raising=False)
    monkeypatch.delenv("BILLING_SERVICE_TOKEN", raising=False)
    monkeypatch.setenv("COMMON_SERVICE_TOKEN", "common-test-token")

    with pytest.raises(HTTPException) as error:
        asyncio.run(request())
    assert error.value.status_code == 401
