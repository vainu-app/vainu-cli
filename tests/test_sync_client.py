"""Unit tests for the synchronous Vainu client."""

import json
import time

import pytest
import requests
import responses as resp
from conftest import (
    ASYNC_JOB_ACCEPTED,
    ASYNC_JOB_COMPLETED,
    ASYNC_JOB_PROCESS,
    ASYNC_JOB_SUBMIT_RESPONSE,
    BASE_URL,
    COMPANIES_RESPONSE,
    CSV_RESPONSE,
    DYNAMIC_LIST_RESPONSE,
    ENRICHMENT_AGENT_JSONL_RESPONSE,
    ENRICHMENT_AGENT_RESPONSE,
    JSONL_RESPONSE,
    JSONL_STREAM_LINES,
    JSONL_STREAM_RESPONSE,
    JWT_REFRESH_URL,
    JWT_TOKEN_RESPONSE,
    OAUTH_TOKEN_RESPONSE,
    ORGANIZATION_FIELDS_RESPONSE,
    ORGANIZATION_LISTS_RESPONSE,
    ORGANIZATIONS_COUNT_ERROR_RESPONSE,
    ORGANIZATIONS_COUNT_RESPONSE,
    ORGANIZATIONS_COUNT_SCHEDULED_RESPONSE,
    ORGANIZATIONS_RESPONSE,
    SIGNALS_DATA_CHANGES_RESPONSE,
    SIGNALS_JSONL_RESPONSE,
    SIGNALS_NEWS_RESPONSE,
    STATIC_LIST_RESPONSE,
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
    def test_companies_get_sends_accept_language_header(self):
        resp.add(resp.GET, f"{BASE_URL}/v2/companies/", json=COMPANIES_RESPONSE)
        client = VainuAPIKeySyncClient(api_key="secret-key", language="fi")
        client.companies(payload="?country=FI")
        assert resp.calls[0].request.headers["Accept-Language"] == "fi"

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

    @resp.activate
    def test_companies_400_returns_api_error_body_as_json(self):
        # 4xx responses are intentionally returned to the caller (see
        # _raise_for_status_with_body) so the CLI can surface the API's error
        # message without a Python traceback.
        resp.add(
            resp.GET,
            f"{BASE_URL}/v2/companies/",
            json={"detail": "Invalid query parameter: foo"},
            status=400,
        )
        client = VainuAPIKeySyncClient(api_key="test-key")
        result = client.companies(payload="?country=FI")
        assert result == {"detail": "Invalid query parameter: foo"}

    @resp.activate
    def test_companies_400_returns_api_error_body_as_text(self):
        # Same as above for non-JSON error bodies — exercised via a non-JSON
        # response format so parse_response returns the raw text.
        resp.add(
            resp.GET,
            f"{BASE_URL}/v2/companies/",
            body="Bad request payload",
            status=400,
        )
        client = VainuAPIKeySyncClient(api_key="test-key")
        result = client.companies(payload="?country=FI", format="csv")
        assert result == "Bad request payload"


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
        resp.add(
            resp.POST, f"{BASE_URL}/v3/organizations/?format=json", json=ORGANIZATIONS_RESPONSE
        )
        client = VainuAPIKeySyncClient(api_key="test-key")
        result = client.organizations(payload={"query": "vainu"})
        assert result["count"] == 1

    @resp.activate
    def test_organizations_post_uses_explicit_format(self):
        resp.add(resp.POST, f"{BASE_URL}/v3/organizations/?format=jsonl", body=JSONL_RESPONSE)
        client = VainuAPIKeySyncClient(api_key="test-key")
        result = client.organizations(payload={"query": "vainu"}, format="jsonl")
        assert result == JSONL_RESPONSE

    @resp.activate
    def test_companies_get_returns_raw_jsonl_text(self):
        resp.add(resp.GET, f"{BASE_URL}/v2/companies/", body=JSONL_RESPONSE)
        client = VainuAPIKeySyncClient(api_key="test-key")
        result = client.companies(payload="?country=FI", format="jsonl")
        assert result == JSONL_RESPONSE


class TestVainuAPIKeySyncClientOrganizationsCount:
    COUNT_URL = f"{BASE_URL}/v3/organizations/count/?format=json"
    QUERY = {"query": {"?GTE": {"financial_data.revenue": 1000000}}, "database": "NO"}

    @resp.activate
    def test_returns_count_metadata(self):
        resp.add(resp.POST, self.COUNT_URL, json=ORGANIZATIONS_COUNT_RESPONSE)
        client = VainuAPIKeySyncClient(api_key="test-key")
        result = client.organizations_count(payload=self.QUERY)
        assert result["count"] == 180086
        assert result["status"] == "ready"
        assert len(resp.calls) == 1

    @resp.activate
    def test_no_wait_returns_scheduled_reply_as_is(self):
        resp.add(resp.POST, self.COUNT_URL, json=ORGANIZATIONS_COUNT_SCHEDULED_RESPONSE)
        client = VainuAPIKeySyncClient(api_key="test-key")
        result = client.organizations_count(payload=self.QUERY, wait=False)
        assert result["count"] is None
        assert result["status"] == "scheduled"
        assert len(resp.calls) == 1

    @resp.activate
    def test_wait_polls_until_status_ready(self):
        resp.add(resp.POST, self.COUNT_URL, json=ORGANIZATIONS_COUNT_SCHEDULED_RESPONSE)
        resp.add(resp.POST, self.COUNT_URL, json=ORGANIZATIONS_COUNT_SCHEDULED_RESPONSE)
        resp.add(resp.POST, self.COUNT_URL, json=ORGANIZATIONS_COUNT_RESPONSE)
        client = VainuAPIKeySyncClient(api_key="test-key")
        result = client.organizations_count(payload=self.QUERY, wait=True, poll_interval=0)
        assert result["count"] == 180086
        assert len(resp.calls) == 3

    @resp.activate
    def test_wait_stops_on_error_status(self):
        resp.add(resp.POST, self.COUNT_URL, json=ORGANIZATIONS_COUNT_ERROR_RESPONSE)
        client = VainuAPIKeySyncClient(api_key="test-key")
        result = client.organizations_count(payload=self.QUERY, wait=True, poll_interval=0)
        assert result["status"] == "error"
        assert len(resp.calls) == 1

    @resp.activate
    def test_wait_treats_body_without_status_as_final(self):
        """A rejected payload comes back as a 400 body, which carries no `status`."""
        resp.add(resp.POST, self.COUNT_URL, json={"detail": "No database permission"}, status=400)
        client = VainuAPIKeySyncClient(api_key="test-key")
        result = client.organizations_count(payload=self.QUERY, wait=True, poll_interval=0)
        assert result == {"detail": "No database permission"}
        assert len(resp.calls) == 1

    @resp.activate
    def test_wait_times_out_while_still_scheduled(self):
        resp.add(resp.POST, self.COUNT_URL, json=ORGANIZATIONS_COUNT_SCHEDULED_RESPONSE)
        client = VainuAPIKeySyncClient(api_key="test-key")
        with pytest.raises(TimeoutError, match="scheduled"):
            client.organizations_count(
                payload=self.QUERY, wait=True, poll_interval=0, max_wait_seconds=0
            )

    @resp.activate
    def test_transient_connection_error_is_retried(self):
        resp.add(resp.POST, self.COUNT_URL, body=requests.exceptions.ConnectionError("boom"))
        resp.add(resp.POST, self.COUNT_URL, json=ORGANIZATIONS_COUNT_SCHEDULED_RESPONSE)
        resp.add(resp.POST, self.COUNT_URL, json=ORGANIZATIONS_COUNT_RESPONSE)
        client = VainuAPIKeySyncClient(api_key="test-key")
        result = client.organizations_count(payload=self.QUERY, wait=True, poll_interval=0)
        assert result["count"] == 180086

    @resp.activate
    def test_transient_timeout_is_retried(self):
        resp.add(resp.POST, self.COUNT_URL, body=requests.exceptions.Timeout("slow"))
        resp.add(resp.POST, self.COUNT_URL, json=ORGANIZATIONS_COUNT_RESPONSE)
        client = VainuAPIKeySyncClient(api_key="test-key")
        result = client.organizations_count(payload=self.QUERY, wait=True, poll_interval=0)
        assert result["count"] == 180086

    @resp.activate
    def test_raises_after_max_consecutive_failures(self):
        # responses repeats the last registered response, so every attempt fails.
        resp.add(resp.POST, self.COUNT_URL, body=requests.exceptions.ConnectionError("boom"))
        client = VainuAPIKeySyncClient(api_key="test-key")
        with pytest.raises(requests.exceptions.ConnectionError):
            client.organizations_count(payload=self.QUERY, wait=True, poll_interval=0)
        assert len(resp.calls) == VainuAPIKeySyncClient.ASYNC_POLL_MAX_RETRIES + 1

    @resp.activate
    def test_success_resets_the_retry_budget(self):
        """Failures scattered between successes must not add up to the cap."""
        failure = requests.exceptions.ConnectionError("boom")
        for _ in range(VainuAPIKeySyncClient.ASYNC_POLL_MAX_RETRIES):
            resp.add(resp.POST, self.COUNT_URL, body=failure)
            resp.add(resp.POST, self.COUNT_URL, json=ORGANIZATIONS_COUNT_SCHEDULED_RESPONSE)
        resp.add(resp.POST, self.COUNT_URL, json=ORGANIZATIONS_COUNT_RESPONSE)
        client = VainuAPIKeySyncClient(api_key="test-key")
        result = client.organizations_count(payload=self.QUERY, wait=True, poll_interval=0)
        assert result["count"] == 180086

    @resp.activate
    def test_recount_is_dropped_from_follow_up_polls(self):
        """Resending `recount` would restart the count and never converge."""
        resp.add(resp.POST, self.COUNT_URL, json=ORGANIZATIONS_COUNT_SCHEDULED_RESPONSE)
        resp.add(resp.POST, self.COUNT_URL, json=ORGANIZATIONS_COUNT_RESPONSE)
        client = VainuAPIKeySyncClient(api_key="test-key")
        client.organizations_count(
            payload={**self.QUERY, "recount": True, "recount_if_cache_max_age": 3600},
            wait=True,
            poll_interval=0,
        )
        first, second = (json.loads(call.request.body) for call in resp.calls)
        assert first["recount"] is True
        assert "recount" not in second
        # The cache threshold is harmless once a count lands, so it keeps riding along.
        assert second["recount_if_cache_max_age"] == 3600
        assert second["query"] == self.QUERY["query"]

    @resp.activate
    def test_order_is_never_sent(self):
        """A payload written for /organizations/ must be countable as-is."""
        resp.add(resp.POST, self.COUNT_URL, json=ORGANIZATIONS_COUNT_SCHEDULED_RESPONSE)
        resp.add(resp.POST, self.COUNT_URL, json=ORGANIZATIONS_COUNT_RESPONSE)
        client = VainuAPIKeySyncClient(api_key="test-key")
        client.organizations_count(
            payload={**self.QUERY, "order": "-financial_data.revenue", "limit": 50},
            wait=True,
            poll_interval=0,
        )
        for call in resp.calls:
            body = json.loads(call.request.body)
            assert "order" not in body
            # Keys the API merely ignores are left untouched.
            assert body["limit"] == 50

    @resp.activate
    def test_caller_payload_is_not_mutated(self):
        resp.add(resp.POST, self.COUNT_URL, json=ORGANIZATIONS_COUNT_RESPONSE)
        payload = {**self.QUERY, "recount": True}
        client = VainuAPIKeySyncClient(api_key="test-key")
        client.organizations_count(payload=payload, wait=True, poll_interval=0)
        assert payload["recount"] is True


class TestVainuAPIKeySyncClientEnrichmentAgent:
    @resp.activate
    def test_enrichment_agent_post_returns_structured_response(self):
        resp.add(
            resp.POST,
            f"{BASE_URL}/v3/enrichment_agent/?format=json",
            json=ENRICHMENT_AGENT_RESPONSE,
        )
        client = VainuAPIKeySyncClient(api_key="test-key")
        result = client.enrichment_agent(
            payload={
                "prompt": "12345",
                "database": "FI",
                "business_id": "FI01320292",
                "refresh": False,
            }
        )
        assert "main_business_activity" in result["response"]
        assert json.loads(resp.calls[0].request.body)["business_id"] == "FI01320292"

    @resp.activate
    def test_enrichment_agent_post_uses_explicit_format(self):
        resp.add(
            resp.POST,
            f"{BASE_URL}/v3/enrichment_agent/?format=jsonl",
            body=ENRICHMENT_AGENT_JSONL_RESPONSE,
        )
        client = VainuAPIKeySyncClient(api_key="test-key")
        result = client.enrichment_agent(
            payload={"prompt": "12345", "database": "FI", "business_id": "FI01320292"},
            format="jsonl",
        )
        assert result == ENRICHMENT_AGENT_JSONL_RESPONSE

    def test_timeout_override_reaches_the_session(self):
        client = VainuAPIKeySyncClient(api_key="test-key", timeout=600)
        assert client._timeout == 600


class TestVainuAPIKeySyncClientOrganizationLists:
    @resp.activate
    def test_organization_fields_get(self):
        resp.add(
            resp.GET,
            f"{BASE_URL}/v3/organizations_fields/?api_versions=v3",
            json=ORGANIZATION_FIELDS_RESPONSE,
        )
        client = VainuAPIKeySyncClient(api_key="test-key")
        result = client.organization_fields()
        assert isinstance(result, list)
        assert result[0]["api"]["v3"]["path"] == "address.street"

    @resp.activate
    def test_organization_lists_get(self):
        resp.add(
            resp.GET,
            f"{BASE_URL}/v3/lists/organizations/?format=json",
            json=ORGANIZATION_LISTS_RESPONSE,
        )
        client = VainuAPIKeySyncClient(api_key="test-key")
        result = client.organization_lists()
        assert isinstance(result, list)
        assert result[0]["type"] == "dynamic-organization-list"

    @resp.activate
    def test_organization_list_static_create(self):
        resp.add(
            resp.POST,
            f"{BASE_URL}/v3/lists/organizations/static/?format=json",
            json=STATIC_LIST_RESPONSE,
            status=201,
        )
        client = VainuAPIKeySyncClient(api_key="test-key")
        result = client.organization_list_static_create(
            {"name": "My Static List", "country": "FI", "business_ids": ["FI01234567"]}
        )
        assert result["id"] == STATIC_LIST_RESPONSE["id"]

    @resp.activate
    def test_organization_list_static_add(self):
        resp.add(
            resp.PATCH,
            f"{BASE_URL}/v3/lists/organizations/static/63d8de4eb7dfe9f5896fa540/add/",
            status=204,
        )
        client = VainuAPIKeySyncClient(api_key="test-key")
        client.organization_list_static_add("63d8de4eb7dfe9f5896fa540", ["FI01234567"])

    @resp.activate
    def test_organization_list_dynamic_update(self):
        resp.add(
            resp.PATCH,
            f"{BASE_URL}/v3/lists/organizations/dynamic/69e61e048c5d1ae30b426a1b/?format=json",
            json=DYNAMIC_LIST_RESPONSE,
        )
        client = VainuAPIKeySyncClient(api_key="test-key")
        result = client.organization_list_dynamic_update(
            "69e61e048c5d1ae30b426a1b",
            {"name": "Swedish Manufacturers"},
        )
        assert result["country"] == "SE"


class TestVainuAPIKeySyncClientSignals:
    @resp.activate
    def test_signals_news_post_returns_list(self):
        resp.add(resp.POST, f"{BASE_URL}/v3/signals/news/?format=json", json=SIGNALS_NEWS_RESPONSE)
        client = VainuAPIKeySyncClient(api_key="test-key")
        result = client.signals_news(payload={"query": {"?ALL": [{"?IN": {"tags": [43543]}}]}})
        assert isinstance(result, list)
        assert result[0]["tags"] == [{"id": 43543, "value": "Funding"}]

    @resp.activate
    def test_signals_news_post_uses_explicit_format(self):
        resp.add(
            resp.POST, f"{BASE_URL}/v3/signals/news/?format=jsonl", body=SIGNALS_JSONL_RESPONSE
        )
        client = VainuAPIKeySyncClient(api_key="test-key")
        result = client.signals_news(payload={"query": {}}, format="jsonl")
        assert result == SIGNALS_JSONL_RESPONSE

    @resp.activate
    def test_signals_data_changes_post_returns_list(self):
        resp.add(
            resp.POST,
            f"{BASE_URL}/v3/signals/data-changes/?format=json",
            json=SIGNALS_DATA_CHANGES_RESPONSE,
        )
        client = VainuAPIKeySyncClient(api_key="test-key")
        result = client.signals_data_changes(payload={"query": {}})
        assert isinstance(result, list)
        assert result[0]["dynamic_values"][0]["key"] == "new_financial_statement"

    @resp.activate
    def test_signals_data_changes_post_uses_explicit_format(self):
        resp.add(
            resp.POST,
            f"{BASE_URL}/v3/signals/data-changes/?format=jsonl",
            body=SIGNALS_JSONL_RESPONSE,
        )
        client = VainuAPIKeySyncClient(api_key="test-key")
        result = client.signals_data_changes(payload={"query": {}}, format="jsonl")
        assert result == SIGNALS_JSONL_RESPONSE


class TestVainuAPIKeySyncClientStreaming:
    @resp.activate
    def test_stream_signals_news_yields_lines(self):
        resp.add(
            resp.POST,
            f"{BASE_URL}/v3/signals/news/?format=jsonl",
            body=JSONL_STREAM_RESPONSE,
        )
        client = VainuAPIKeySyncClient(api_key="test-key")
        with client.stream_signals_news(payload={"query": {}}) as lines:
            assert list(lines) == JSONL_STREAM_LINES

    @resp.activate
    def test_stream_signals_data_changes_yields_lines(self):
        resp.add(
            resp.POST,
            f"{BASE_URL}/v3/signals/data-changes/?format=jsonl",
            body=JSONL_STREAM_RESPONSE,
        )
        client = VainuAPIKeySyncClient(api_key="test-key")
        with client.stream_signals_data_changes(payload={"query": {}}) as lines:
            assert list(lines) == JSONL_STREAM_LINES

    @resp.activate
    def test_stream_organizations_yields_lines(self):
        resp.add(
            resp.POST,
            f"{BASE_URL}/v3/organizations/?format=jsonl",
            body=JSONL_RESPONSE,
        )
        client = VainuAPIKeySyncClient(api_key="test-key")
        with client.stream_organizations(payload={"query": {}}) as lines:
            assert list(lines) == JSONL_RESPONSE.splitlines()

    @resp.activate
    def test_stream_companies_post_yields_csv_lines(self):
        resp.add(resp.POST, f"{BASE_URL}/v2/companies/?format=csv", body=CSV_RESPONSE)
        client = VainuAPIKeySyncClient(api_key="test-key")
        with client.stream_companies(payload={"filter": {}}, format="csv") as lines:
            rows = list(lines)
        assert rows[0] == "business_id,name"
        assert rows == CSV_RESPONSE.splitlines()

    @resp.activate
    def test_stream_companies_accepts_query_string_payload(self):
        resp.add(resp.GET, f"{BASE_URL}/v2/companies/", body=JSONL_RESPONSE)
        client = VainuAPIKeySyncClient(api_key="test-key")
        with client.stream_companies(payload="?country=FI") as lines:
            assert list(lines) == JSONL_RESPONSE.splitlines()
        assert "format=jsonl" in resp.calls[0].request.url

    def test_stream_rejects_json_format(self):
        client = VainuAPIKeySyncClient(api_key="test-key")
        with pytest.raises(ValueError, match="cannot be streamed"):  # noqa: SIM117
            with client.stream_signals_news(payload={"query": {}}, format="json"):
                pass

    @resp.activate
    def test_stream_yields_swallowed_error_body(self):
        """400/403/404 bodies are returned rather than raised, as in the buffered path."""
        resp.add(
            resp.POST,
            f"{BASE_URL}/v3/signals/news/?format=jsonl",
            json={"detail": "invalid order by value"},
            status=400,
        )
        client = VainuAPIKeySyncClient(api_key="test-key")
        with client.stream_signals_news(payload={"query": {}}) as lines:
            assert list(lines) == ['{"detail": "invalid order by value"}']

    @resp.activate
    def test_stream_raises_on_server_error(self):
        resp.add(
            resp.POST,
            f"{BASE_URL}/v3/signals/news/?format=jsonl",
            json={"detail": "boom"},
            status=500,
        )
        client = VainuAPIKeySyncClient(api_key="test-key")
        with pytest.raises(requests.HTTPError):  # noqa: SIM117
            with client.stream_signals_news(payload={"query": {}}):
                pass


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


class TestVainuOAuthSyncClientPersistentCache:
    """Token reuse across client instances — i.e. across CLI invocations."""

    @resp.activate
    def test_second_client_reuses_the_stored_token(self):
        resp.add(resp.POST, f"{BASE_URL}/oauth/token/", json=OAUTH_TOKEN_RESPONSE)
        resp.add(resp.POST, f"{BASE_URL}/v2/companies/", json=COMPANIES_RESPONSE)
        resp.add(resp.POST, f"{BASE_URL}/v2/companies/", json=COMPANIES_RESPONSE)

        VainuOAuthSyncClient(client_id="id", client_secret="secret", token_cache=True).companies(
            payload={"filter": {}}
        )
        VainuOAuthSyncClient(client_id="id", client_secret="secret", token_cache=True).companies(
            payload={"filter": {}}
        )

        token_calls = [c for c in resp.calls if "/oauth/token/" in c.request.url]
        assert len(token_calls) == 1

    @resp.activate
    def test_disabled_cache_mints_a_token_per_client(self):
        resp.add(resp.POST, f"{BASE_URL}/oauth/token/", json=OAUTH_TOKEN_RESPONSE)
        resp.add(resp.POST, f"{BASE_URL}/v2/companies/", json=COMPANIES_RESPONSE)
        resp.add(resp.POST, f"{BASE_URL}/oauth/token/", json=OAUTH_TOKEN_RESPONSE)
        resp.add(resp.POST, f"{BASE_URL}/v2/companies/", json=COMPANIES_RESPONSE)

        for _ in range(2):
            VainuOAuthSyncClient(
                client_id="id", client_secret="secret", token_cache=False
            ).companies(payload={"filter": {}})

        token_calls = [c for c in resp.calls if "/oauth/token/" in c.request.url]
        assert len(token_calls) == 2

    @resp.activate
    def test_revoked_cached_token_is_dropped_and_retried_once(self):
        resp.add(resp.POST, f"{BASE_URL}/oauth/token/", json=OAUTH_TOKEN_RESPONSE)
        resp.add(resp.POST, f"{BASE_URL}/v2/companies/", json=COMPANIES_RESPONSE)
        # Second invocation: the cached token has been revoked server-side.
        resp.add(resp.POST, f"{BASE_URL}/v2/companies/", json={"detail": "invalid"}, status=401)
        resp.add(resp.POST, f"{BASE_URL}/oauth/token/", json=OAUTH_TOKEN_RESPONSE)
        resp.add(resp.POST, f"{BASE_URL}/v2/companies/", json=COMPANIES_RESPONSE)

        VainuOAuthSyncClient(client_id="id", client_secret="secret", token_cache=True).companies(
            payload={"filter": {}}
        )
        result = VainuOAuthSyncClient(
            client_id="id", client_secret="secret", token_cache=True
        ).companies(payload={"filter": {}})

        assert result == COMPANIES_RESPONSE
        token_calls = [c for c in resp.calls if "/oauth/token/" in c.request.url]
        assert len(token_calls) == 2

    @resp.activate
    def test_a_freshly_minted_token_is_not_retried(self):
        """Bad credentials must surface, not double the API's 401 load."""
        resp.add(resp.POST, f"{BASE_URL}/oauth/token/", json=OAUTH_TOKEN_RESPONSE)
        resp.add(resp.POST, f"{BASE_URL}/v2/companies/", json={"detail": "invalid"}, status=401)

        client = VainuOAuthSyncClient(client_id="id", client_secret="secret", token_cache=True)
        with pytest.raises(requests.HTTPError):
            client.companies(payload={"filter": {}})

        companies_calls = [c for c in resp.calls if "/v2/companies/" in c.request.url]
        assert len(companies_calls) == 1

    @resp.activate
    def test_streaming_retries_once_on_a_revoked_cached_token(self):
        resp.add(resp.POST, f"{BASE_URL}/oauth/token/", json=OAUTH_TOKEN_RESPONSE)
        resp.add(resp.POST, f"{BASE_URL}/v2/companies/", json=COMPANIES_RESPONSE)
        resp.add(
            resp.POST,
            f"{BASE_URL}/v3/organizations/",
            json={"detail": "invalid"},
            status=401,
        )
        resp.add(resp.POST, f"{BASE_URL}/oauth/token/", json=OAUTH_TOKEN_RESPONSE)
        resp.add(resp.POST, f"{BASE_URL}/v3/organizations/", body=JSONL_RESPONSE)

        VainuOAuthSyncClient(client_id="id", client_secret="secret", token_cache=True).companies(
            payload={"filter": {}}
        )
        client = VainuOAuthSyncClient(client_id="id", client_secret="secret", token_cache=True)
        with client.stream_organizations(payload={"query": {}}) as lines:
            assert list(lines) == JSONL_RESPONSE.splitlines()

        org_calls = [c for c in resp.calls if "/v3/organizations/" in c.request.url]
        assert len(org_calls) == 2


# ── VainuJWTSyncClient ───────────────────────────────────────────────────────


class TestVainuJWTSyncClientTokenManagement:
    @resp.activate
    def test_fetches_token_on_first_request(self):
        resp.add(resp.POST, JWT_REFRESH_URL, json=JWT_TOKEN_RESPONSE)
        resp.add(resp.POST, f"{BASE_URL}/v2/companies/", json=COMPANIES_RESPONSE)

        client = VainuJWTSyncClient(refresh_token="refresh-token")
        client.companies(payload={"filter": {}})

        token_call = resp.calls[0]
        assert b"refresh" in token_call.request.body

    @resp.activate
    def test_caches_token_on_second_request(self):
        resp.add(resp.POST, JWT_REFRESH_URL, json=JWT_TOKEN_RESPONSE)
        resp.add(resp.POST, f"{BASE_URL}/v2/companies/", json=COMPANIES_RESPONSE)
        resp.add(resp.POST, f"{BASE_URL}/v2/companies/", json=COMPANIES_RESPONSE)

        client = VainuJWTSyncClient(refresh_token="refresh-token")
        client.companies(payload={"filter": {}})
        client.companies(payload={"filter": {}})

        token_calls = [c for c in resp.calls if JWT_REFRESH_URL in c.request.url]
        assert len(token_calls) == 1

    @resp.activate
    def test_refreshes_expired_token(self):
        resp.add(resp.POST, JWT_REFRESH_URL, json=JWT_TOKEN_RESPONSE)
        resp.add(resp.POST, f"{BASE_URL}/v2/companies/", json=COMPANIES_RESPONSE)
        resp.add(resp.POST, JWT_REFRESH_URL, json=JWT_TOKEN_RESPONSE)
        resp.add(resp.POST, f"{BASE_URL}/v2/companies/", json=COMPANIES_RESPONSE)

        client = VainuJWTSyncClient(refresh_token="refresh-token")
        client.companies(payload={"filter": {}})
        client._token_expires_at = time.time() - 1
        client.companies(payload={"filter": {}})

        token_calls = [c for c in resp.calls if JWT_REFRESH_URL in c.request.url]
        assert len(token_calls) == 2

    @resp.activate
    def test_bearer_token_sent_in_header(self):
        resp.add(resp.POST, JWT_REFRESH_URL, json=JWT_TOKEN_RESPONSE)
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

    def test_download_to_file_skips_when_only_result_url_present(self, tmp_path):
        out = tmp_path / "out.json"
        result = AsyncResult(download_url=None, duration=1, result_url="https://api/v3/result/123")

        downloaded = result.download_to_file(str(out))

        assert downloaded is False
        assert not out.exists()
