"""Shared test fixtures."""

import pytest
from click.testing import CliRunner

BASE_URL = "https://api.vainu.io/api"
JWT_REFRESH_URL = "https://api.vainu.io/api/token_authentication/refresh/"
OAUTH_TOKEN_URL = "https://api.vainu.io/api/oauth/token/"
OAUTH_REVOKE_URL = "https://api.vainu.io/api/oauth/revoke_token/"


@pytest.fixture(autouse=True)
def _isolate_auth_store(monkeypatch, tmp_path):
    """Make sure tests never see / write real user credentials.

    Forces the file-backend, points it at a tmp dir, and clears any VAINU_*
    env vars that could otherwise leak from the developer's shell.
    """
    monkeypatch.setenv("VAINU_AUTH_STORE", "file")
    # Off by default so token-refresh assertions count real network calls;
    # cache tests opt in with `token_cache=True`.
    monkeypatch.setenv("VAINU_TOKEN_CACHE", "0")
    monkeypatch.setattr(
        "vainu_cli.auth.storage.user_config_path",
        lambda *_, **__: tmp_path / "vainu-config",
    )
    for var in (
        "VAINU_API_KEY",
        "VAINU_CLIENT_ID",
        "VAINU_CLIENT_SECRET",
        "VAINU_JWT_REFRESH_TOKEN",
        "VAINU_ACCESS_TOKEN",
        "VAINU_REFRESH_TOKEN",
        "VAINU_TOKEN_EXPIRES_AT",
        "VAINU_AUTH_METHOD",
        "VAINU_BASE_URL",
        "VAINU_SCOPE",
    ):
        monkeypatch.delenv(var, raising=False)


COMPANIES_RESPONSE = {
    "result": [
        {
            "business_id": "FI01320292",
            "name": "Test Company Oy",
            "country": "FI",
        }
    ],
    "count": 1,
    "next": None,
}

ORGANIZATIONS_RESPONSE = {
    "result": [{"business_id": "FI01320292", "name": "Test Org"}],
    "count": 1,
    "next": None,
}

JSONL_RESPONSE = (
    '{"business_id":"FI01320292","name":"Test Org"}\n'
    '{"business_id":"FI99999999","name":"Another Org"}'
)

ASYNC_JOB_ACCEPTED = {"state": "accepted", "progress": 0}
ASYNC_JOB_PROCESS = {"state": "process", "progress": 50}
ASYNC_JOB_COMPLETED = {
    "state": "completed",
    "download_link": "https://downloads.vainu.io/result.json",
    "duration": 5,
}
ASYNC_JOB_SUBMIT_RESPONSE = {"link": f"{BASE_URL}/v2/companies/async/job123/"}

OAUTH_TOKEN_RESPONSE = {
    "access_token": "test-access-token",
    "token_type": "Bearer",
    "expires_in": 3600,
}

JWT_TOKEN_RESPONSE = {
    "access": "test-access-token",
    "expires_in": 3600,
}


@pytest.fixture
def runner() -> CliRunner:
    return CliRunner()
