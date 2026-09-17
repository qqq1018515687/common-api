from pathlib import Path


ROOT = Path(__file__).parent
AUTH_SOURCE = ROOT.joinpath("src/utils/backend_auth.py").read_text(encoding="utf-8")


def test_backend_auth_accepts_deployed_service_token_names():
    assert '"COZE_BACKEND_TOKEN"' in AUTH_SOURCE
    assert '"COMMON_SERVICE_TOKEN"' in AUTH_SOURCE
    assert '"BILLING_SERVICE_TOKEN"' in AUTH_SOURCE
    assert "hmac.compare_digest" in AUTH_SOURCE
