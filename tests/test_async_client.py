"""Unit tests for the async Vainu client."""

import json
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
    CSV_RESPONSE,
    ENRICHMENT_AGENT_JSONL_RESPONSE,
    ENRICHMENT_AGENT_RESPONSE,
    JSONL_RESPONSE,
    JSONL_STREAM_LINES,
    JSONL_STREAM_RESPONSE,
    JWT_REFRESH_URL,
    JWT_TOKEN_RESPONSE,
    OAUTH_TOKEN_RESPONSE,
    ORGANIZATIONS_COUNT_ERROR_RESPONSE,
    ORGANIZATIONS_COUNT_RESPONSE,
    ORGANIZATIONS_COUNT_SCHEDULED_RESPONSE,
    ORGANIZATIONS_RESPONSE,
    SIGNALS_DATA_CHANGES_RESPONSE,
    SIGNALS_JSONL_RESPONSE,
    SIGNALS_NEWS_RESPONSE,
)

from vainu_cli._async_client import (
    AsyncResult,
    VainuAPIKeyClient,
    VainuJWTAPIClient,
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
    async def test_companies_get_sends_accept_language_header(self):
        route = respx.get(f"{BASE_URL}/v2/companies/").mock(
            return_value=httpx.Response(200, json=COMPANIES_RESPONSE)
        )
        client = VainuAPIKeyClient(api_key="secret-key", language="fi")
        await client.companies(payload="?country=FI")
        await client.close()
        assert route.calls[0].request.headers["Accept-Language"] == "fi"

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

    @respx.mock
    async def test_companies_400_returns_api_error_body_as_json(self):
        # 4xx responses are intentionally returned to the caller (see
        # _raise_for_status_with_body) so the CLI can surface the API's error
        # message without a Python traceback — same contract as the sync client.
        respx.get(f"{BASE_URL}/v2/companies/").mock(
            return_value=httpx.Response(400, json={"detail": "Invalid query parameter: foo"})
        )
        client = VainuAPIKeyClient(api_key="test-key")
        result = await client.companies(payload="?country=FI")
        await client.close()
        assert result == {"detail": "Invalid query parameter: foo"}

    @respx.mock
    async def test_companies_400_returns_api_error_body_as_text(self):
        respx.get(f"{BASE_URL}/v2/companies/").mock(
            return_value=httpx.Response(400, text="Bad request payload")
        )
        client = VainuAPIKeyClient(api_key="test-key")
        result = await client.companies(payload="?country=FI", format="csv")
        await client.close()
        assert result == "Bad request payload"

    @respx.mock
    async def test_companies_500_still_raises(self):
        respx.get(f"{BASE_URL}/v2/companies/").mock(return_value=httpx.Response(500, text="boom"))
        client = VainuAPIKeyClient(api_key="test-key")
        with pytest.raises(httpx.HTTPStatusError):
            await client.companies(payload="?country=FI")
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

    @respx.mock
    async def test_gateway_timeout_while_polling_is_retried(self):
        """A 504 from the load balancer says nothing about the job behind it."""
        respx.get(f"{BASE_URL}/v2/companies/async/").mock(
            return_value=httpx.Response(200, json=ASYNC_JOB_SUBMIT_RESPONSE)
        )
        poll_url = f"{BASE_URL}/v2/companies/async/job123/"
        respx.get(poll_url).mock(
            side_effect=[
                httpx.Response(504, text="<html>504 Gateway Time-out</html>"),
                httpx.Response(502, text="bad gateway"),
                httpx.Response(200, json=ASYNC_JOB_PROCESS),
                httpx.Response(503, text="unavailable"),
                httpx.Response(200, json=ASYNC_JOB_COMPLETED),
            ]
        )

        client = VainuAPIKeyClient(api_key="test-key")
        client.ASYNC_POLL_INTERVAL = 0
        result = await client.companies_async(payload="?country=FI")
        await client.close()

        assert result.download_url == "https://downloads.vainu.io/result.json"

    @respx.mock
    async def test_repeated_gateway_timeouts_still_raise(self):
        respx.get(f"{BASE_URL}/v2/companies/async/").mock(
            return_value=httpx.Response(200, json=ASYNC_JOB_SUBMIT_RESPONSE)
        )
        poll_url = f"{BASE_URL}/v2/companies/async/job123/"
        route = respx.get(poll_url).mock(return_value=httpx.Response(504, text="nope"))

        client = VainuAPIKeyClient(api_key="test-key")
        client.ASYNC_POLL_INTERVAL = 0
        with pytest.raises(httpx.HTTPStatusError):
            await client.companies_async(payload="?country=FI")
        await client.close()

        assert route.call_count == VainuAPIKeyClient.ASYNC_POLL_MAX_RETRIES + 1

    @respx.mock
    async def test_non_transient_poll_status_is_not_retried(self):
        respx.get(f"{BASE_URL}/v2/companies/async/").mock(
            return_value=httpx.Response(200, json=ASYNC_JOB_SUBMIT_RESPONSE)
        )
        poll_url = f"{BASE_URL}/v2/companies/async/job123/"
        route = respx.get(poll_url).mock(return_value=httpx.Response(405, text="nope"))

        client = VainuAPIKeyClient(api_key="test-key")
        client.ASYNC_POLL_INTERVAL = 0
        with pytest.raises(httpx.HTTPStatusError):
            await client.companies_async(payload="?country=FI")
        await client.close()

        assert route.call_count == 1


class TestVainuAPIKeyClientOrganizations:
    @respx.mock
    async def test_organizations_post_returns_dict(self):
        respx.post(f"{BASE_URL}/v3/organizations/?format=json").mock(
            return_value=httpx.Response(200, json=ORGANIZATIONS_RESPONSE)
        )
        client = VainuAPIKeyClient(api_key="test-key")
        result = await client.organizations(payload={"query": "vainu"})
        await client.close()
        assert isinstance(result, dict)
        assert result["count"] == 1

    @respx.mock
    async def test_organizations_post_uses_explicit_format(self):
        respx.post(f"{BASE_URL}/v3/organizations/?format=jsonl").mock(
            return_value=httpx.Response(200, text=JSONL_RESPONSE)
        )
        client = VainuAPIKeyClient(api_key="test-key")
        result = await client.organizations(payload={"query": "vainu"}, format="jsonl")
        await client.close()
        assert result == JSONL_RESPONSE

    @respx.mock
    async def test_companies_get_returns_raw_jsonl_text(self):
        respx.get(f"{BASE_URL}/v2/companies/").mock(
            return_value=httpx.Response(200, text=JSONL_RESPONSE)
        )
        client = VainuAPIKeyClient(api_key="test-key")
        result = await client.companies(payload="?country=FI", format="jsonl")
        await client.close()
        assert result == JSONL_RESPONSE


class TestVainuAPIKeyClientOrganizationsCount:
    COUNT_URL = f"{BASE_URL}/v3/organizations/count/?format=json"
    QUERY = {"query": {"?GTE": {"financial_data.revenue": 1000000}}, "database": "NO"}

    @respx.mock
    async def test_returns_count_metadata(self):
        route = respx.post(self.COUNT_URL).mock(
            return_value=httpx.Response(200, json=ORGANIZATIONS_COUNT_RESPONSE)
        )
        client = VainuAPIKeyClient(api_key="test-key")
        result = await client.organizations_count(payload=self.QUERY)
        await client.close()
        assert result["count"] == 180086
        assert route.call_count == 1

    @respx.mock
    async def test_no_wait_returns_scheduled_reply_as_is(self):
        respx.post(self.COUNT_URL).mock(
            return_value=httpx.Response(200, json=ORGANIZATIONS_COUNT_SCHEDULED_RESPONSE)
        )
        client = VainuAPIKeyClient(api_key="test-key")
        result = await client.organizations_count(payload=self.QUERY, wait=False)
        await client.close()
        assert result["status"] == "scheduled"
        assert result["count"] is None

    @respx.mock
    async def test_wait_polls_until_status_ready(self):
        route = respx.post(self.COUNT_URL).mock(
            side_effect=[
                httpx.Response(200, json=ORGANIZATIONS_COUNT_SCHEDULED_RESPONSE),
                httpx.Response(200, json=ORGANIZATIONS_COUNT_SCHEDULED_RESPONSE),
                httpx.Response(200, json=ORGANIZATIONS_COUNT_RESPONSE),
            ]
        )
        client = VainuAPIKeyClient(api_key="test-key")
        result = await client.organizations_count(payload=self.QUERY, wait=True, poll_interval=0)
        await client.close()
        assert result["count"] == 180086
        assert route.call_count == 3

    @respx.mock
    async def test_wait_stops_on_error_status(self):
        route = respx.post(self.COUNT_URL).mock(
            return_value=httpx.Response(200, json=ORGANIZATIONS_COUNT_ERROR_RESPONSE)
        )
        client = VainuAPIKeyClient(api_key="test-key")
        result = await client.organizations_count(payload=self.QUERY, wait=True, poll_interval=0)
        await client.close()
        assert result["status"] == "error"
        assert route.call_count == 1

    @respx.mock
    async def test_wait_treats_body_without_status_as_final(self):
        route = respx.post(self.COUNT_URL).mock(
            return_value=httpx.Response(400, json={"detail": "No database permission"})
        )
        client = VainuAPIKeyClient(api_key="test-key")
        result = await client.organizations_count(payload=self.QUERY, wait=True, poll_interval=0)
        await client.close()
        assert result == {"detail": "No database permission"}
        assert route.call_count == 1

    @respx.mock
    async def test_wait_times_out_while_still_scheduled(self):
        respx.post(self.COUNT_URL).mock(
            return_value=httpx.Response(200, json=ORGANIZATIONS_COUNT_SCHEDULED_RESPONSE)
        )
        client = VainuAPIKeyClient(api_key="test-key")
        with pytest.raises(TimeoutError, match="scheduled"):
            await client.organizations_count(
                payload=self.QUERY, wait=True, poll_interval=0, max_wait_seconds=0
            )
        await client.close()

    @respx.mock
    async def test_transient_transport_errors_are_retried(self):
        respx.post(self.COUNT_URL).mock(
            side_effect=[
                httpx.ConnectError("boom"),
                httpx.ReadError("truncated"),
                httpx.Response(200, json=ORGANIZATIONS_COUNT_SCHEDULED_RESPONSE),
                httpx.TimeoutException("slow"),
                httpx.Response(200, json=ORGANIZATIONS_COUNT_RESPONSE),
            ]
        )
        client = VainuAPIKeyClient(api_key="test-key")
        result = await client.organizations_count(payload=self.QUERY, wait=True, poll_interval=0)
        await client.close()
        assert result["count"] == 180086

    @respx.mock
    async def test_transient_server_errors_are_retried(self):
        respx.post(self.COUNT_URL).mock(
            side_effect=[
                httpx.Response(504, text="gateway timeout"),
                httpx.Response(200, json=ORGANIZATIONS_COUNT_SCHEDULED_RESPONSE),
                httpx.Response(429, text="slow down"),
                httpx.Response(200, json=ORGANIZATIONS_COUNT_RESPONSE),
            ]
        )
        client = VainuAPIKeyClient(api_key="test-key")
        result = await client.organizations_count(payload=self.QUERY, wait=True, poll_interval=0)
        await client.close()
        assert result["count"] == 180086

    @respx.mock
    async def test_non_transient_count_status_is_not_retried(self):
        route = respx.post(self.COUNT_URL).mock(return_value=httpx.Response(405, text="nope"))
        client = VainuAPIKeyClient(api_key="test-key")
        with pytest.raises(httpx.HTTPStatusError):
            await client.organizations_count(payload=self.QUERY, wait=True, poll_interval=0)
        await client.close()
        assert route.call_count == 1

    @respx.mock
    async def test_raises_after_max_consecutive_failures(self):
        route = respx.post(self.COUNT_URL).mock(side_effect=httpx.ConnectError)
        client = VainuAPIKeyClient(api_key="test-key")
        with pytest.raises(httpx.ConnectError):
            await client.organizations_count(payload=self.QUERY, wait=True, poll_interval=0)
        await client.close()
        assert route.call_count == VainuAPIKeyClient.ASYNC_POLL_MAX_RETRIES + 1

    @respx.mock
    async def test_success_resets_the_retry_budget(self):
        """Failures scattered between successes must not add up to the cap."""
        side_effect = []
        for _ in range(VainuAPIKeyClient.ASYNC_POLL_MAX_RETRIES):
            side_effect.append(httpx.ConnectError("boom"))
            side_effect.append(httpx.Response(200, json=ORGANIZATIONS_COUNT_SCHEDULED_RESPONSE))
        side_effect.append(httpx.Response(200, json=ORGANIZATIONS_COUNT_RESPONSE))
        respx.post(self.COUNT_URL).mock(side_effect=side_effect)
        client = VainuAPIKeyClient(api_key="test-key")
        result = await client.organizations_count(payload=self.QUERY, wait=True, poll_interval=0)
        await client.close()
        assert result["count"] == 180086

    @respx.mock
    async def test_order_is_never_sent(self):
        """A payload written for /organizations/ must be countable as-is."""
        route = respx.post(self.COUNT_URL).mock(
            side_effect=[
                httpx.Response(200, json=ORGANIZATIONS_COUNT_SCHEDULED_RESPONSE),
                httpx.Response(200, json=ORGANIZATIONS_COUNT_RESPONSE),
            ]
        )
        client = VainuAPIKeyClient(api_key="test-key")
        await client.organizations_count(
            payload={**self.QUERY, "order": "-financial_data.revenue", "limit": 50},
            wait=True,
            poll_interval=0,
        )
        await client.close()
        for call in route.calls:
            body = json.loads(call.request.content)
            assert "order" not in body
            assert body["limit"] == 50

    @respx.mock
    async def test_recount_is_dropped_from_follow_up_polls(self):
        """Resending `recount` would restart the count and never converge."""
        route = respx.post(self.COUNT_URL).mock(
            side_effect=[
                httpx.Response(200, json=ORGANIZATIONS_COUNT_SCHEDULED_RESPONSE),
                httpx.Response(200, json=ORGANIZATIONS_COUNT_RESPONSE),
            ]
        )
        client = VainuAPIKeyClient(api_key="test-key")
        payload = {**self.QUERY, "recount": True, "recount_if_cache_max_age": 3600}
        await client.organizations_count(payload=payload, wait=True, poll_interval=0)
        await client.close()
        first, second = (json.loads(call.request.content) for call in route.calls)
        assert first["recount"] is True
        assert "recount" not in second
        assert second["recount_if_cache_max_age"] == 3600
        # The caller's dict must survive untouched.
        assert payload["recount"] is True


class TestVainuAPIKeyClientEnrichmentAgent:
    @respx.mock
    async def test_enrichment_agent_post_returns_structured_response(self):
        route = respx.post(f"{BASE_URL}/v3/enrichment_agent/?format=json").mock(
            return_value=httpx.Response(200, json=ENRICHMENT_AGENT_RESPONSE)
        )
        client = VainuAPIKeyClient(api_key="test-key")
        result = await client.enrichment_agent(
            payload={
                "prompt": "12345",
                "database": "FI",
                "business_id": "FI01320292",
                "refresh": False,
            }
        )
        await client.close()
        assert "main_business_activity" in result["response"]
        assert json.loads(route.calls[0].request.content)["business_id"] == "FI01320292"

    @respx.mock
    async def test_enrichment_agent_post_uses_explicit_format(self):
        respx.post(f"{BASE_URL}/v3/enrichment_agent/?format=jsonl").mock(
            return_value=httpx.Response(200, text=ENRICHMENT_AGENT_JSONL_RESPONSE)
        )
        client = VainuAPIKeyClient(api_key="test-key")
        result = await client.enrichment_agent(
            payload={"prompt": "12345", "database": "FI", "business_id": "FI01320292"},
            format="jsonl",
        )
        await client.close()
        assert result == ENRICHMENT_AGENT_JSONL_RESPONSE

    async def test_timeout_override_reaches_the_http_client(self):
        client = VainuAPIKeyClient(api_key="test-key", timeout=600)
        assert client._http.timeout.read == 600
        await client.close()


class TestVainuAPIKeyClientSignals:
    @respx.mock
    async def test_signals_news_post_returns_list(self):
        respx.post(f"{BASE_URL}/v3/signals/news/?format=json").mock(
            return_value=httpx.Response(200, json=SIGNALS_NEWS_RESPONSE)
        )
        client = VainuAPIKeyClient(api_key="test-key")
        result = await client.signals_news(
            payload={"query": {"?ALL": [{"?IN": {"tags": [43543]}}]}}
        )
        await client.close()
        assert isinstance(result, list)
        assert result[0]["tags"] == [{"id": 43543, "value": "Funding"}]

    @respx.mock
    async def test_signals_news_post_uses_explicit_format(self):
        respx.post(f"{BASE_URL}/v3/signals/news/?format=jsonl").mock(
            return_value=httpx.Response(200, text=SIGNALS_JSONL_RESPONSE)
        )
        client = VainuAPIKeyClient(api_key="test-key")
        result = await client.signals_news(payload={"query": {}}, format="jsonl")
        await client.close()
        assert result == SIGNALS_JSONL_RESPONSE

    @respx.mock
    async def test_signals_data_changes_post_returns_list(self):
        respx.post(f"{BASE_URL}/v3/signals/data-changes/?format=json").mock(
            return_value=httpx.Response(200, json=SIGNALS_DATA_CHANGES_RESPONSE)
        )
        client = VainuAPIKeyClient(api_key="test-key")
        result = await client.signals_data_changes(payload={"query": {}})
        await client.close()
        assert isinstance(result, list)
        assert result[0]["dynamic_values"][0]["key"] == "new_financial_statement"

    @respx.mock
    async def test_signals_data_changes_post_uses_explicit_format(self):
        respx.post(f"{BASE_URL}/v3/signals/data-changes/?format=jsonl").mock(
            return_value=httpx.Response(200, text=SIGNALS_JSONL_RESPONSE)
        )
        client = VainuAPIKeyClient(api_key="test-key")
        result = await client.signals_data_changes(payload={"query": {}}, format="jsonl")
        await client.close()
        assert result == SIGNALS_JSONL_RESPONSE


class TestVainuAPIKeyClientStreaming:
    @staticmethod
    async def _collect(lines) -> list[str]:
        return [line async for line in lines]

    @respx.mock
    async def test_stream_signals_news_yields_lines(self):
        respx.post(f"{BASE_URL}/v3/signals/news/?format=jsonl").mock(
            return_value=httpx.Response(200, text=JSONL_STREAM_RESPONSE)
        )
        client = VainuAPIKeyClient(api_key="test-key")
        async with client.stream_signals_news(payload={"query": {}}) as lines:
            assert await self._collect(lines) == JSONL_STREAM_LINES
        await client.close()

    @respx.mock
    async def test_stream_signals_data_changes_yields_lines(self):
        respx.post(f"{BASE_URL}/v3/signals/data-changes/?format=jsonl").mock(
            return_value=httpx.Response(200, text=JSONL_STREAM_RESPONSE)
        )
        client = VainuAPIKeyClient(api_key="test-key")
        async with client.stream_signals_data_changes(payload={"query": {}}) as lines:
            assert await self._collect(lines) == JSONL_STREAM_LINES
        await client.close()

    @respx.mock
    async def test_stream_organizations_yields_lines(self):
        respx.post(f"{BASE_URL}/v3/organizations/?format=jsonl").mock(
            return_value=httpx.Response(200, text=JSONL_RESPONSE)
        )
        client = VainuAPIKeyClient(api_key="test-key")
        async with client.stream_organizations(payload={"query": {}}) as lines:
            assert await self._collect(lines) == JSONL_RESPONSE.splitlines()
        await client.close()

    @respx.mock
    async def test_stream_companies_post_yields_csv_lines(self):
        respx.post(f"{BASE_URL}/v2/companies/?format=csv").mock(
            return_value=httpx.Response(200, text=CSV_RESPONSE)
        )
        client = VainuAPIKeyClient(api_key="test-key")
        async with client.stream_companies(payload={"filter": {}}, format="csv") as lines:
            rows = await self._collect(lines)
        await client.close()
        assert rows[0] == "business_id,name"
        assert rows == CSV_RESPONSE.splitlines()

    @respx.mock
    async def test_stream_companies_accepts_query_string_payload(self):
        route = respx.get(f"{BASE_URL}/v2/companies/").mock(
            return_value=httpx.Response(200, text=JSONL_RESPONSE)
        )
        client = VainuAPIKeyClient(api_key="test-key")
        async with client.stream_companies(payload="?country=FI") as lines:
            assert await self._collect(lines) == JSONL_RESPONSE.splitlines()
        await client.close()
        assert "format=jsonl" in str(route.calls[0].request.url)

    async def test_stream_rejects_json_format(self):
        client = VainuAPIKeyClient(api_key="test-key")
        with pytest.raises(ValueError, match="cannot be streamed"):
            async with client.stream_signals_news(payload={"query": {}}, format="json"):
                pass
        await client.close()

    @respx.mock
    async def test_stream_yields_swallowed_error_body(self):
        """400/403/404 bodies are returned rather than raised, as in the buffered path."""
        respx.post(f"{BASE_URL}/v3/signals/news/?format=jsonl").mock(
            return_value=httpx.Response(400, json={"detail": "invalid order by value"})
        )
        client = VainuAPIKeyClient(api_key="test-key")
        async with client.stream_signals_news(payload={"query": {}}) as lines:
            assert await self._collect(lines) == ['{"detail":"invalid order by value"}']
        await client.close()

    @respx.mock
    async def test_stream_raises_on_server_error(self):
        respx.post(f"{BASE_URL}/v3/signals/news/?format=jsonl").mock(
            return_value=httpx.Response(500, json={"detail": "boom"})
        )
        client = VainuAPIKeyClient(api_key="test-key")
        with pytest.raises(httpx.HTTPStatusError):
            async with client.stream_signals_news(payload={"query": {}}):
                pass
        await client.close()

    @respx.mock
    async def test_stream_retries_once_on_a_revoked_cached_token(self):
        respx.post(f"{BASE_URL}/oauth/token/").mock(
            return_value=httpx.Response(200, json=OAUTH_TOKEN_RESPONSE)
        )
        respx.post(f"{BASE_URL}/v2/companies/").mock(
            return_value=httpx.Response(200, json=COMPANIES_RESPONSE)
        )
        route = respx.post(f"{BASE_URL}/v3/organizations/?format=jsonl").mock(
            side_effect=[
                httpx.Response(401, json={"detail": "invalid"}),
                httpx.Response(200, text=JSONL_RESPONSE),
            ]
        )

        primer = VainuOAuthAPIClient(client_id="id", client_secret="secret", token_cache=True)
        await primer.companies(payload={"filter": {}})
        await primer.close()

        client = VainuOAuthAPIClient(client_id="id", client_secret="secret", token_cache=True)
        async with client.stream_organizations(payload={"query": {}}) as lines:
            assert await self._collect(lines) == JSONL_RESPONSE.splitlines()
        await client.close()

        assert len(route.calls) == 2


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

    @respx.mock
    async def test_second_client_reuses_the_stored_token(self):
        respx.post(f"{BASE_URL}/oauth/token/").mock(
            return_value=httpx.Response(200, json=OAUTH_TOKEN_RESPONSE)
        )
        respx.post(f"{BASE_URL}/v2/companies/").mock(
            return_value=httpx.Response(200, json=COMPANIES_RESPONSE)
        )

        for _ in range(2):
            client = VainuOAuthAPIClient(client_id="id", client_secret="secret", token_cache=True)
            await client.companies(payload={"filter": {}})
            await client.close()

        token_calls = [c for c in respx.calls if "/oauth/token/" in str(c.request.url)]
        assert len(token_calls) == 1


# ── VainuJWTAPIClient ────────────────────────────────────────────────────────


class TestVainuJWTAPIClientTokenManagement:
    @respx.mock
    async def test_fetches_token_on_first_request(self):
        respx.post(JWT_REFRESH_URL).mock(return_value=httpx.Response(200, json=JWT_TOKEN_RESPONSE))
        respx.post(f"{BASE_URL}/v2/companies/").mock(
            return_value=httpx.Response(200, json=COMPANIES_RESPONSE)
        )

        client = VainuJWTAPIClient(refresh_token="refresh-token")
        await client.companies(payload={"filter": {}})
        await client.close()

        token_calls = [c for c in respx.calls if JWT_REFRESH_URL in str(c.request.url)]
        assert len(token_calls) == 1

    @respx.mock
    async def test_caches_token_on_second_request(self):
        respx.post(JWT_REFRESH_URL).mock(return_value=httpx.Response(200, json=JWT_TOKEN_RESPONSE))
        respx.post(f"{BASE_URL}/v2/companies/").mock(
            return_value=httpx.Response(200, json=COMPANIES_RESPONSE)
        )

        client = VainuJWTAPIClient(refresh_token="refresh-token")
        await client.companies(payload={"filter": {}})
        await client.companies(payload={"filter": {}})
        await client.close()

        token_calls = [c for c in respx.calls if JWT_REFRESH_URL in str(c.request.url)]
        assert len(token_calls) == 1

    @respx.mock
    async def test_bearer_token_in_header(self):
        respx.post(JWT_REFRESH_URL).mock(return_value=httpx.Response(200, json=JWT_TOKEN_RESPONSE))
        route = respx.post(f"{BASE_URL}/v2/companies/").mock(
            return_value=httpx.Response(200, json=COMPANIES_RESPONSE)
        )

        client = VainuJWTAPIClient(refresh_token="refresh-token")
        await client.companies(payload={"filter": {}})
        await client.close()

        assert route.calls[0].request.headers["Authorization"] == "Bearer test-access-token"

    @respx.mock
    async def test_refreshes_expired_token(self):
        respx.post(JWT_REFRESH_URL).mock(return_value=httpx.Response(200, json=JWT_TOKEN_RESPONSE))
        respx.post(f"{BASE_URL}/v2/companies/").mock(
            return_value=httpx.Response(200, json=COMPANIES_RESPONSE)
        )

        client = VainuJWTAPIClient(refresh_token="refresh-token")
        await client.companies(payload={"filter": {}})
        client._token_expires_at = time.time() - 1
        await client.companies(payload={"filter": {}})
        await client.close()

        token_calls = [c for c in respx.calls if JWT_REFRESH_URL in str(c.request.url)]
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

    async def test_download_to_file_skips_when_only_result_url_present(self, tmp_path):
        out = tmp_path / "out.json"
        result = AsyncResult(download_url=None, duration=1, result_url="https://api/v3/result/123")

        with patch("asyncio.create_subprocess_exec") as mock_exec:
            downloaded = await result.download_to_file(str(out))

        assert downloaded is False
        mock_exec.assert_not_called()
