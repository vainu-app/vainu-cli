"""Shared test fixtures."""

import pytest
from click.testing import CliRunner

BASE_URL = "https://api.vainu.io/api"
JWT_REFRESH_URL = "https://api.vainu.io/api/token_authentication/refresh/"

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
