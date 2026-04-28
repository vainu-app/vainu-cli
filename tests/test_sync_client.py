"""Unit tests for the synchronous Vainu client."""

import time

import pytest
import responses as resp
from conftest import (
    ASYNC_JOB_ACCEPTED,
    ASYNC_JOB_COMPLETED,
    ASYNC_JOB_PROCESS,
    ASYNC_JOB_SUBMIT_RESPONSE,
    BASE_URL,
    COMPANIES_RESPONSE,
    JWT_REFRESH_URL,
    OAUTH_TOKEN_RESPONSE,
    ORGANIZATIONS_RESPONSE,
)

from vainu_cli._sync_client import (
    AsyncResult,
    VainuAPIKeySyncClient,
    VainuJWTSyncClient,
    VainuOAuthSyncClient,
)

# ── VainuAPIKeySyncClient ────────────────────────────────────────────────────


class TestVainuAPIKeySyncClientInit:
    def test_raises_on_empty_key(self):
        with pytest.raises(ValueError, match="api_key"):
            VainuAPIKeySyncClient(api_key="")

    def test_stores_api_key(self):
        client = VainuAPIKeySyncClient(api_key="test-key")
        assert client.api_key == "test-key"

    def test_default_base_url(self):
        client = VainuAPIKeySyncClient(api_key="test-key")
        assert client._base_url == BASE_URL

    def test_custom_base_url(self):
        client = VainuAPIKeySyncClient(api_key="test-key", base_url="https://custom.example.com")
        assert client._base_url == "https://custom.example.com"


class TestVainuAPIKeySyncClientCompanies:
    @resp.activate
    def test_companies_get_sends_api_key_header(self):
        resp.add(resp.GET, f"{BASE_URL}/v2/companies/", json=COMPANIES_RESPONSE)
        client = VainuAPIKeySyncClient(api_key="secret-key")
        client.companies(payload="?country=FI")
        assert resp.calls[0].request.headers["API-Key"] == "secret-key"

    @resp.activate
    def test_companies_get_returns_json(self):
        resp.add(resp.GET, f"{BASE_URL}/v2/companies/", json=COMPANIES_RESPONSE)
        client = VainuAPIKeySyncClient(api_key="test-key")
        result = client.companies(payload="?country=FI")
        assert result["count"] == 1
        assert result["result"][0]["business_id"] == "FI01320292"

    @resp.activate
    def test_companies_post_returns_json(self):
        resp.add(resp.POST, f"{BASE_URL}/v2/companies/", json=COMPANIES_RESPONSE)
        client = VainuAPIKeySyncClient(api_key="test-key")
        result = client.companies(payload={"query": {"country": "FI"}})
        assert result["count"] == 1

    def test_companies_invalid_payload_type(self):
        client = VainuAPIKeySyncClient(api_key="test-key")
        with pytest.raises(ValueError, match="payload must be str or dict"):
            client.companies(payload=123)  # type: ignore[arg-type]


class TestVainuAPIKeySyncClientCompaniesAsync:
    @resp.activate
    def test_polling_cycle_accepted_then_completed(self):
        resp.add(resp.GET, f"{BASE_URL}/v2/companies/async/", json=ASYNC_JOB_SUBMIT_RESPONSE)
        resp.add(resp.GET, f"{BASE_URL}/v2/companies/async/job123/", json=ASYNC_JOB_ACCEPTED)
        resp.add(resp.GET, f"{BASE_URL}/v2/companies/async/job123/", json=ASYNC_JOB_COMPLETED)

        client = VainuAPIKeySyncClient(api_key="test-key")
        client.ASYNC_POLL_INTERVAL = 0  # no sleep in tests
        result = client.companies_async(payload="?country=FI")

        assert isinstance(result, AsyncResult)
        assert result.download_url == "https://downloads.vainu.io/result.json"
        assert result.duration == 5

    @resp.activate
    def test_polling_cycle_process_then_completed(self):
        resp.add(resp.POST, f"{BASE_URL}/v2/companies/async/", json=ASYNC_JOB_SUBMIT_RESPONSE)
        resp.add(resp.GET, f"{BASE_URL}/v2/companies/async/job123/", json=ASYNC_JOB_PROCESS)
        resp.add(resp.GET, f"{BASE_URL}/v2/companies/async/job123/", json=ASYNC_JOB_COMPLETED)

        client = VainuAPIKeySyncClient(api_key="test-key")
        client.ASYNC_POLL_INTERVAL = 0
        result = client.companies_async(payload={"filter": {}})

        assert result.download_url == "https://downloads.vainu.io/result.json"

    @resp.activate
    def test_raises_on_failure_state(self):
        resp.add(resp.GET, f"{BASE_URL}/v2/companies/async/", json=ASYNC_JOB_SUBMIT_RESPONSE)
        resp.add(
            resp.GET,
            f"{BASE_URL}/v2/companies/async/job123/",
            json={"state": "failure", "progress": 0},
        )

        client = VainuAPIKeySyncClient(api_key="test-key")
        client.ASYNC_POLL_INTERVAL = 0
        with pytest.raises(RuntimeError, match="failure"):
            client.companies_async(payload="?country=FI")

    def test_raises_on_timeout(self, monkeypatch):
        # Make monotonic clock advance past the timeout on every call
        call_count = {"n": 0}

        def fast_clock():
            call_count["n"] += 1
            return call_count["n"] * 100_000  # large jumps

        monkeypatch.setattr(time, "monotonic", fast_clock)

        with resp.RequestsMock(assert_all_requests_are_fired=False) as rsps:
            rsps.add(resp.GET, f"{BASE_URL}/v2/companies/async/", json=ASYNC_JOB_SUBMIT_RESPONSE)
            rsps.add(
                resp.GET,
                f"{BASE_URL}/v2/companies/async/job123/",
                json=ASYNC_JOB_ACCEPTED,
            )

            client = VainuAPIKeySyncClient(api_key="test-key")
            client.ASYNC_POLL_INTERVAL = 0
            client._async_max_wait_seconds = 1
            with pytest.raises(TimeoutError):
                client.companies_async(payload="?country=FI")


class TestVainuAPIKeySyncClientOrganizations:
    @resp.activate
    def test_organizations_post(self):
        resp.add(resp.POST, f"{BASE_URL}/v3/organizations/", json=ORGANIZATIONS_RESPONSE)
        client = VainuAPIKeySyncClient(api_key="test-key")
        result = client.organizations(payload={"query": "vainu"})
        assert result["count"] == 1


# ── VainuOAuthSyncClient ─────────────────────────────────────────────────────


class TestVainuOAuthSyncClientInit:
    def test_raises_on_empty_credentials(self):
        with pytest.raises(ValueError, match="client_id"):
            VainuOAuthSyncClient(client_id="", client_secret="secret")

    def test_raises_on_empty_secret(self):
        with pytest.raises(ValueError, match="client_secret"):
            VainuOAuthSyncClient(client_id="id", client_secret="")


class TestVainuOAuthSyncClientTokenManagement:
    @resp.activate
    def test_fetches_token_on_first_request(self):
        resp.add(resp.POST, f"{BASE_URL}/oauth/token/", json=OAUTH_TOKEN_RESPONSE)
        resp.add(resp.POST, f"{BASE_URL}/v2/companies/", json=COMPANIES_RESPONSE)

        client = VainuOAuthSyncClient(client_id="id", client_secret="secret")
        client.companies(payload={"filter": {}})

        token_call = resp.calls[0]
        assert "client_credentials" in token_call.request.body

    @resp.activate
    def test_caches_token_on_second_request(self):
        resp.add(resp.POST, f"{BASE_URL}/oauth/token/", json=OAUTH_TOKEN_RESPONSE)
        resp.add(resp.POST, f"{BASE_URL}/v2/companies/", json=COMPANIES_RESPONSE)
        resp.add(resp.POST, f"{BASE_URL}/v2/companies/", json=COMPANIES_RESPONSE)

        client = VainuOAuthSyncClient(client_id="id", client_secret="secret")
        client.companies(payload={"filter": {}})
        client.companies(payload={"filter": {}})

        token_calls = [c for c in resp.calls if "/oauth/token/" in c.request.url]
        assert len(token_calls) == 1  # token fetched only once

    @resp.activate
    def test_refreshes_expired_token(self, monkeypatch):
        resp.add(resp.POST, f"{BASE_URL}/oauth/token/", json=OAUTH_TOKEN_RESPONSE)
        resp.add(resp.POST, f"{BASE_URL}/v2/companies/", json=COMPANIES_RESPONSE)
        resp.add(resp.POST, f"{BASE_URL}/oauth/token/", json=OAUTH_TOKEN_RESPONSE)
        resp.add(resp.POST, f"{BASE_URL}/v2/companies/", json=COMPANIES_RESPONSE)

        client = VainuOAuthSyncClient(client_id="id", client_secret="secret")
        client.companies(payload={"filter": {}})

        # Simulate token expiry by setting expiry in the past
        client._token_expires_at = time.time() - 1

        client.companies(payload={"filter": {}})

        token_calls = [c for c in resp.calls if "/oauth/token/" in c.request.url]
        assert len(token_calls) == 2  # token re-fetched after expiry

    @resp.activate
    def test_bearer_token_sent_in_header(self):
        resp.add(resp.POST, f"{BASE_URL}/oauth/token/", json=OAUTH_TOKEN_RESPONSE)
        resp.add(resp.POST, f"{BASE_URL}/v2/companies/", json=COMPANIES_RESPONSE)

        client = VainuOAuthSyncClient(client_id="id", client_secret="secret")
        client.companies(payload={"filter": {}})

        companies_call = resp.calls[1]
        assert companies_call.request.headers["Authorization"] == "Bearer test-access-token"


# ── VainuJWTSyncClient ───────────────────────────────────────────────────────


class TestVainuJWTSyncClientTokenManagement:
    @resp.activate
    def test_fetches_token_on_first_request(self):
        resp.add(resp.POST, JWT_REFRESH_URL, json=OAUTH_TOKEN_RESPONSE)
        resp.add(resp.POST, f"{BASE_URL}/v2/companies/", json=COMPANIES_RESPONSE)

        client = VainuJWTSyncClient(refresh_token="refresh-token")
        client.companies(payload={"filter": {}})

        token_call = resp.calls[0]
        assert "refresh_token" in token_call.request.body

    @resp.activate
    def test_caches_token_on_second_request(self):
        resp.add(resp.POST, JWT_REFRESH_URL, json=OAUTH_TOKEN_RESPONSE)
        resp.add(resp.POST, f"{BASE_URL}/v2/companies/", json=COMPANIES_RESPONSE)
        resp.add(resp.POST, f"{BASE_URL}/v2/companies/", json=COMPANIES_RESPONSE)

        client = VainuJWTSyncClient(refresh_token="refresh-token")
        client.companies(payload={"filter": {}})
        client.companies(payload={"filter": {}})

        token_calls = [c for c in resp.calls if JWT_REFRESH_URL in c.request.url]
        assert len(token_calls) == 1

    @resp.activate
    def test_refreshes_expired_token(self):
        resp.add(resp.POST, JWT_REFRESH_URL, json=OAUTH_TOKEN_RESPONSE)
        resp.add(resp.POST, f"{BASE_URL}/v2/companies/", json=COMPANIES_RESPONSE)
        resp.add(resp.POST, JWT_REFRESH_URL, json=OAUTH_TOKEN_RESPONSE)
        resp.add(resp.POST, f"{BASE_URL}/v2/companies/", json=COMPANIES_RESPONSE)

        client = VainuJWTSyncClient(refresh_token="refresh-token")
        client.companies(payload={"filter": {}})
        client._token_expires_at = time.time() - 1
        client.companies(payload={"filter": {}})

        token_calls = [c for c in resp.calls if JWT_REFRESH_URL in c.request.url]
        assert len(token_calls) == 2

    @resp.activate
    def test_bearer_token_sent_in_header(self):
        resp.add(resp.POST, JWT_REFRESH_URL, json=OAUTH_TOKEN_RESPONSE)
        resp.add(resp.POST, f"{BASE_URL}/v2/companies/", json=COMPANIES_RESPONSE)

        client = VainuJWTSyncClient(refresh_token="refresh-token")
        client.companies(payload={"filter": {}})

        companies_call = resp.calls[1]
        assert companies_call.request.headers["Authorization"] == "Bearer test-access-token"


# ── AsyncResult ──────────────────────────────────────────────────────────────


class TestAsyncResult:
    @resp.activate
    def test_json_downloads_and_parses(self):
        resp.add(
            resp.GET,
            "https://downloads.vainu.io/result.json",
            json=COMPANIES_RESPONSE,
        )
        result = AsyncResult(download_url="https://downloads.vainu.io/result.json", duration=1)
        data = result.json()
        assert data["count"] == 1

    @resp.activate
    def test_download_to_file_writes_bytes(self, tmp_path):
        content = b'{"result":[]}'
        resp.add(
            resp.GET,
            "https://downloads.vainu.io/result.json",
            body=content,
            stream=True,
        )
        out = tmp_path / "out.json"
        result = AsyncResult(download_url="https://downloads.vainu.io/result.json", duration=1)
        result.download_to_file(str(out))
        assert out.read_bytes() == content
