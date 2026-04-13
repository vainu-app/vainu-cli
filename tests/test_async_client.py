"""Unit tests for the async Vainu client."""

import time
from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pytest
import respx
from conftest import (
    ASYNC_JOB_ACCEPTED,
    ASYNC_JOB_COMPLETED,
    ASYNC_JOB_PROCESS,
    ASYNC_JOB_SUBMIT_RESPONSE,
    BASE_URL,
    COMPANIES_RESPONSE,
    OAUTH_TOKEN_RESPONSE,
    ORGANIZATIONS_RESPONSE,
)

from vainu_cli._async_client import (
    AsyncResult,
    VainuAPIKeyClient,
    VainuOAuthAPIClient,
)

# ── VainuAPIKeyClient ────────────────────────────────────────────────────────


class TestVainuAPIKeyClientInit:
    def test_raises_on_empty_key(self):
        with pytest.raises(ValueError, match="api_key"):
            VainuAPIKeyClient(api_key="")

    def test_stores_api_key(self):
        client = VainuAPIKeyClient(api_key="test-key")
        assert client.api_key == "test-key"

    def test_default_base_url(self):
        client = VainuAPIKeyClient(api_key="test-key")
        assert client._base_url == BASE_URL


class TestVainuAPIKeyClientCompanies:
    @respx.mock
    async def test_companies_get_sends_api_key_header(self):
        route = respx.get(f"{BASE_URL}/v2/companies/").mock(
            return_value=httpx.Response(200, json=COMPANIES_RESPONSE)
        )
        client = VainuAPIKeyClient(api_key="secret-key")
        await client.companies(payload="?country=FI")
        await client.close()
        assert route.calls[0].request.headers["API-Key"] == "secret-key"

    @respx.mock
    async def test_companies_get_returns_json(self):
        respx.get(f"{BASE_URL}/v2/companies/").mock(
            return_value=httpx.Response(200, json=COMPANIES_RESPONSE)
        )
        client = VainuAPIKeyClient(api_key="test-key")
        result = await client.companies(payload="?country=FI")
        await client.close()
        assert result["count"] == 1
        assert result["result"][0]["business_id"] == "FI01320292"

    @respx.mock
    async def test_companies_post_returns_json(self):
        respx.post(f"{BASE_URL}/v2/companies/").mock(
            return_value=httpx.Response(200, json=COMPANIES_RESPONSE)
        )
        client = VainuAPIKeyClient(api_key="test-key")
        result = await client.companies(payload={"filter": {}})
        await client.close()
        assert result["count"] == 1

    async def test_companies_invalid_payload(self):
        client = VainuAPIKeyClient(api_key="test-key")
        with pytest.raises(ValueError, match="payload must be str or dict"):
            await client.companies(payload=42)  # type: ignore[arg-type]
        await client.close()


class TestVainuAPIKeyClientCompaniesAsync:
    @respx.mock
    async def test_polling_cycle_accepted_then_completed(self):
        respx.get(f"{BASE_URL}/v2/companies/async/").mock(
            return_value=httpx.Response(200, json=ASYNC_JOB_SUBMIT_RESPONSE)
        )
        poll_url = f"{BASE_URL}/v2/companies/async/job123/"
        respx.get(poll_url).mock(
            side_effect=[
                httpx.Response(200, json=ASYNC_JOB_ACCEPTED),
                httpx.Response(200, json=ASYNC_JOB_COMPLETED),
            ]
        )

        client = VainuAPIKeyClient(api_key="test-key")
        client.ASYNC_POLL_INTERVAL = 0
        result = await client.companies_async(payload="?country=FI")
        await client.close()

        assert isinstance(result, AsyncResult)
        assert result.download_url == "https://downloads.vainu.io/result.json"

    @respx.mock
    async def test_polling_cycle_process_then_completed(self):
        respx.post(f"{BASE_URL}/v2/companies/async/").mock(
            return_value=httpx.Response(200, json=ASYNC_JOB_SUBMIT_RESPONSE)
        )
        poll_url = f"{BASE_URL}/v2/companies/async/job123/"
        respx.get(poll_url).mock(
            side_effect=[
                httpx.Response(200, json=ASYNC_JOB_PROCESS),
                httpx.Response(200, json=ASYNC_JOB_COMPLETED),
            ]
        )

        client = VainuAPIKeyClient(api_key="test-key")
        client.ASYNC_POLL_INTERVAL = 0
        result = await client.companies_async(payload={"filter": {}})
        await client.close()

        assert result.duration == 5

    @respx.mock
    async def test_raises_on_failure_state(self):
        respx.get(f"{BASE_URL}/v2/companies/async/").mock(
            return_value=httpx.Response(200, json=ASYNC_JOB_SUBMIT_RESPONSE)
        )
        poll_url = f"{BASE_URL}/v2/companies/async/job123/"
        respx.get(poll_url).mock(
            return_value=httpx.Response(200, json={"state": "failure", "progress": 0})
        )

        client = VainuAPIKeyClient(api_key="test-key")
        client.ASYNC_POLL_INTERVAL = 0
        with pytest.raises(RuntimeError, match="failure"):
            await client.companies_async(payload="?country=FI")
        await client.close()


class TestVainuAPIKeyClientOrganizations:
    @respx.mock
    async def test_organizations_post_returns_dict(self):
        respx.post(f"{BASE_URL}/v3/organizations/").mock(
            return_value=httpx.Response(200, json=ORGANIZATIONS_RESPONSE)
        )
        client = VainuAPIKeyClient(api_key="test-key")
        result = await client.organizations(payload={"query": "vainu"})
        await client.close()
        assert isinstance(result, dict)
        assert result["count"] == 1


# ── VainuOAuthAPIClient ──────────────────────────────────────────────────────


class TestVainuOAuthAPIClientInit:
    def test_raises_on_empty_credentials(self):
        with pytest.raises(ValueError):
            VainuOAuthAPIClient(client_id="", client_secret="secret")


class TestVainuOAuthAPIClientTokenManagement:
    @respx.mock
    async def test_fetches_token_on_first_request(self):
        respx.post(f"{BASE_URL}/oauth/token/").mock(
            return_value=httpx.Response(200, json=OAUTH_TOKEN_RESPONSE)
        )
        respx.post(f"{BASE_URL}/v2/companies/").mock(
            return_value=httpx.Response(200, json=COMPANIES_RESPONSE)
        )

        client = VainuOAuthAPIClient(client_id="id", client_secret="secret")
        await client.companies(payload={"filter": {}})
        await client.close()

        token_calls = [c for c in respx.calls if "/oauth/token/" in str(c.request.url)]
        assert len(token_calls) == 1

    @respx.mock
    async def test_caches_token_on_second_request(self):
        respx.post(f"{BASE_URL}/oauth/token/").mock(
            return_value=httpx.Response(200, json=OAUTH_TOKEN_RESPONSE)
        )
        respx.post(f"{BASE_URL}/v2/companies/").mock(
            return_value=httpx.Response(200, json=COMPANIES_RESPONSE)
        )

        client = VainuOAuthAPIClient(client_id="id", client_secret="secret")
        await client.companies(payload={"filter": {}})
        await client.companies(payload={"filter": {}})
        await client.close()

        token_calls = [c for c in respx.calls if "/oauth/token/" in str(c.request.url)]
        assert len(token_calls) == 1  # fetched only once

    @respx.mock
    async def test_bearer_token_in_header(self):
        respx.post(f"{BASE_URL}/oauth/token/").mock(
            return_value=httpx.Response(200, json=OAUTH_TOKEN_RESPONSE)
        )
        route = respx.post(f"{BASE_URL}/v2/companies/").mock(
            return_value=httpx.Response(200, json=COMPANIES_RESPONSE)
        )

        client = VainuOAuthAPIClient(client_id="id", client_secret="secret")
        await client.companies(payload={"filter": {}})
        await client.close()

        assert route.calls[0].request.headers["Authorization"] == "Bearer test-access-token"

    @respx.mock
    async def test_refreshes_expired_token(self):
        respx.post(f"{BASE_URL}/oauth/token/").mock(
            return_value=httpx.Response(200, json=OAUTH_TOKEN_RESPONSE)
        )
        respx.post(f"{BASE_URL}/v2/companies/").mock(
            return_value=httpx.Response(200, json=COMPANIES_RESPONSE)
        )

        client = VainuOAuthAPIClient(client_id="id", client_secret="secret")
        await client.companies(payload={"filter": {}})
        client._token_expires_at = time.time() - 1  # expire immediately
        await client.companies(payload={"filter": {}})
        await client.close()

        token_calls = [c for c in respx.calls if "/oauth/token/" in str(c.request.url)]
        assert len(token_calls) == 2


# ── AsyncResult ──────────────────────────────────────────────────────────────


class TestAsyncResult:
    @respx.mock
    async def test_json_downloads_and_parses(self):
        respx.get("https://downloads.vainu.io/result.json").mock(
            return_value=httpx.Response(200, json=COMPANIES_RESPONSE)
        )
        result = AsyncResult(download_url="https://downloads.vainu.io/result.json", duration=1)
        data = await result.json()
        assert data["count"] == 1

    async def test_download_to_file_calls_curl(self, tmp_path):
        out = tmp_path / "out.json"
        result = AsyncResult(download_url="https://downloads.vainu.io/result.json", duration=1)

        mock_proc = MagicMock()
        mock_proc.wait = AsyncMock(return_value=None)
        mock_proc.returncode = 0

        with patch("asyncio.create_subprocess_exec", return_value=mock_proc) as mock_exec:
            await result.download_to_file(str(out))

        mock_exec.assert_called_once_with(
            "curl",
            "-L",
            "-s",
            "-f",
            "-o",
            str(out),
            "--compressed",
            "https://downloads.vainu.io/result.json",
        )

    async def test_download_to_file_raises_on_curl_error(self, tmp_path):
        out = tmp_path / "out.json"
        result = AsyncResult(download_url="https://downloads.vainu.io/result.json", duration=1)

        mock_proc = MagicMock()
        mock_proc.wait = AsyncMock(return_value=None)
        mock_proc.returncode = 1  # curl failure

        with patch("asyncio.create_subprocess_exec", return_value=mock_proc):
            with pytest.raises(RuntimeError, match="curl exited"):
                await result.download_to_file(str(out))

    async def test_download_to_file_raises_when_curl_missing(self, tmp_path):
        out = tmp_path / "out.json"
        result = AsyncResult(download_url="https://downloads.vainu.io/result.json", duration=1)

        with patch("asyncio.create_subprocess_exec", side_effect=FileNotFoundError):
            with pytest.raises(RuntimeError, match="curl is not installed"):
                await result.download_to_file(str(out))
