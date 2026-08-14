"""CLI integration tests using Click's CliRunner."""

import json
from unittest.mock import ANY, AsyncMock, MagicMock, patch

import httpx
import pytest
import responses as resp
import respx
from click.testing import CliRunner
from conftest import (
    BASE_URL,
    COMPANIES_RESPONSE,
    CSV_RESPONSE,
    ENRICHMENT_AGENT_JSONL_RESPONSE,
    ENRICHMENT_AGENT_RESPONSE,
    JSONL_RESPONSE,
    JSONL_STREAM_LINES,
    JSONL_STREAM_RESPONSE,
    JWT_REFRESH_URL,
    ORGANIZATION_LISTS_RESPONSE,
    ORGANIZATIONS_RESPONSE,
    SIGNALS_DATA_CHANGES_RESPONSE,
    SIGNALS_JSONL_RESPONSE,
    SIGNALS_NEWS_RESPONSE,
    STATIC_LIST_RESPONSE,
    DYNAMIC_LIST_RESPONSE,
)

from vainu_cli.cli import main
from vainu_cli.common import DEFAULT_TIMEOUT_SECONDS


@pytest.fixture
def runner() -> CliRunner:
    return CliRunner()


# ── companies search ──────────────────────────────────────────────────────────


class TestCompaniesSearch:
    def test_language_is_passed_to_client(self, runner):
        with patch("vainu_cli.cli.VainuAPIKeySyncClient") as MockClient:
            instance = MockClient.return_value
            instance.companies.return_value = COMPANIES_RESPONSE
            instance.close = MagicMock()

            result = runner.invoke(
                main,
                [
                    "--api-key",
                    "test-key",
                    "companies",
                    "--query",
                    "?country=FI",
                    "--language",
                    "fi",
                ],
                catch_exceptions=False,
            )

        assert result.exit_code == 0
        MockClient.assert_called_once_with(
            api_key="test-key",
            base_url=BASE_URL,
            language="fi",
            timeout=DEFAULT_TIMEOUT_SECONDS,
        )

    @resp.activate
    def test_api_key_from_env(self, runner):
        resp.add(resp.GET, f"{BASE_URL}/v2/companies/", json=COMPANIES_RESPONSE)
        result = runner.invoke(
            main,
            ["companies", "--query", "?country=FI"],
            env={"VAINU_API_KEY": "env-key"},
            catch_exceptions=False,
        )
        assert result.exit_code == 0
        data = json.loads(result.output)
        assert data["count"] == 1

    @resp.activate
    def test_api_key_from_flag(self, runner):
        resp.add(resp.GET, f"{BASE_URL}/v2/companies/", json=COMPANIES_RESPONSE)
        result = runner.invoke(
            main,
            ["--api-key", "flag-key", "companies", "--query", "?country=FI"],
            catch_exceptions=False,
        )
        assert result.exit_code == 0

    @resp.activate
    def test_output_written_to_file(self, runner, tmp_path):
        resp.add(resp.GET, f"{BASE_URL}/v2/companies/", json=COMPANIES_RESPONSE)
        out = tmp_path / "result.json"
        result = runner.invoke(
            main,
            [
                "--api-key",
                "test-key",
                "companies",
                "--query",
                "?country=FI",
                "--output",
                str(out),
            ],
            catch_exceptions=False,
        )
        assert result.exit_code == 0
        assert out.exists()
        assert json.loads(out.read_text())["count"] == 1

    @resp.activate
    def test_payload_from_stdin(self, runner):
        resp.add(resp.POST, f"{BASE_URL}/v2/companies/", json=COMPANIES_RESPONSE)
        result = runner.invoke(
            main,
            ["--api-key", "test-key", "companies", "--payload", "-"],
            input='{"filter": {}}',
            catch_exceptions=False,
        )
        assert result.exit_code == 0

    @resp.activate
    def test_payload_from_file(self, runner, tmp_path):
        resp.add(resp.POST, f"{BASE_URL}/v2/companies/", json=COMPANIES_RESPONSE)
        payload_file = tmp_path / "payload.json"
        payload_file.write_text('{"filter": {}}')
        result = runner.invoke(
            main,
            [
                "--api-key",
                "test-key",
                "companies",
                "--payload",
                str(payload_file),
            ],
            catch_exceptions=False,
        )
        assert result.exit_code == 0

    @resp.activate
    def test_payload_path_alias_from_file(self, runner, tmp_path):
        resp.add(resp.POST, f"{BASE_URL}/v2/companies/", json=COMPANIES_RESPONSE)
        payload_file = tmp_path / "payload.json"
        payload_file.write_text('{"filter": {}}')
        result = runner.invoke(
            main,
            [
                "--api-key",
                "test-key",
                "companies",
                "--payload-path",
                str(payload_file),
            ],
            catch_exceptions=False,
        )
        assert result.exit_code == 0

    def test_query_and_payload_mutually_exclusive(self, runner):
        result = runner.invoke(
            main,
            [
                "--api-key",
                "test-key",
                "companies",
                "--query",
                "?country=FI",
                "--payload",
                "-",
            ],
        )
        assert result.exit_code != 0
        assert "mutually exclusive" in result.output

    def test_missing_auth_fails_with_helpful_message(self, runner):
        result = runner.invoke(
            main,
            ["companies", "--query", "?country=FI"],
            env={},
        )
        assert result.exit_code != 0
        assert "API key" in result.output or "VAINU_API_KEY" in result.output

    @resp.activate
    def test_jwt_auth_method(self, runner):
        resp.add(
            resp.POST,
            JWT_REFRESH_URL,
            json={"access": "jwt-access", "expires_in": 3600},
        )
        resp.add(resp.GET, f"{BASE_URL}/v2/companies/", json=COMPANIES_RESPONSE)

        result = runner.invoke(
            main,
            [
                "--auth-method",
                "jwt",
                "--jwt-token",
                "refresh-token",
                "companies",
                "--query",
                "?country=FI",
            ],
            catch_exceptions=False,
        )
        assert result.exit_code == 0

    def test_jwt_missing_token(self, runner):
        result = runner.invoke(
            main,
            ["--auth-method", "jwt", "companies", "--query", "?country=FI"],
            env={},
        )
        assert result.exit_code != 0
        assert "JWT authentication requires --jwt-token" in result.output

    def test_neither_query_nor_payload_fails(self, runner):
        result = runner.invoke(
            main,
            ["--api-key", "test-key", "companies"],
        )
        assert result.exit_code != 0

    def test_invalid_json_payload_fails(self, runner):
        result = runner.invoke(
            main,
            ["--api-key", "test-key", "companies", "--payload", "-"],
            input="not valid json",
        )
        assert result.exit_code != 0
        assert "JSON" in result.output

    @resp.activate
    def test_task_duration_is_logged_at_debug(self, runner):
        resp.add(resp.GET, f"{BASE_URL}/v2/companies/", json=COMPANIES_RESPONSE)
        with patch("vainu_cli.cli.logger.debug") as mock_debug:
            result = runner.invoke(
                main,
                ["-v", "--api-key", "test-key", "companies", "--query", "?country=FI"],
                catch_exceptions=False,
            )

        assert result.exit_code == 0
        mock_debug.assert_any_call("Task '%s' %s in %.3fs", "companies", "completed", ANY)


# ── companies export ──────────────────────────────────────────────────────────


class TestCompaniesExport:
    def test_export_writes_file(self, runner, tmp_path):
        out = tmp_path / "export.json"

        async_result_mock = MagicMock()
        async_result_mock.download_to_file = AsyncMock(return_value=None)
        async_result_mock.download_url = "https://downloads.vainu.io/r.json"
        async_result_mock.duration = 1

        with patch("vainu_cli.cli.VainuAPIKeyClient") as MockClient:
            instance = MockClient.return_value
            instance.companies_async = AsyncMock(return_value=async_result_mock)
            instance.close = AsyncMock()
            result = runner.invoke(
                main,
                [
                    "--api-key",
                    "test-key",
                    "companies-async",
                    "--query",
                    "?country=FI",
                    "--output",
                    str(out),
                ],
                catch_exceptions=False,
            )

        assert result.exit_code == 0
        async_result_mock.download_to_file.assert_called_once_with(str(out))

    def test_export_requires_output(self, runner):
        result = runner.invoke(
            main,
            ["--api-key", "test-key", "companies-async", "--query", "?country=FI"],
        )
        assert result.exit_code != 0
        assert "output" in result.output.lower() or "Missing option" in result.output

    def test_export_payload_path_alias(self, runner, tmp_path):
        payload_file = tmp_path / "payload.json"
        payload_file.write_text('{"filter": {}}')
        out = tmp_path / "export.json"

        async_result_mock = MagicMock()
        async_result_mock.download_to_file = AsyncMock(return_value=None)
        async_result_mock.download_url = "https://downloads.vainu.io/r.json"
        async_result_mock.duration = 1

        with patch("vainu_cli.cli.VainuAPIKeyClient") as MockClient:
            instance = MockClient.return_value
            instance.companies_async = AsyncMock(return_value=async_result_mock)
            instance.close = AsyncMock()

            result = runner.invoke(
                main,
                [
                    "--api-key",
                    "test-key",
                    "companies-async",
                    "--payload-path",
                    str(payload_file),
                    "--output",
                    str(out),
                ],
                catch_exceptions=False,
            )

        assert result.exit_code == 0
        instance.companies_async.assert_awaited_once_with(payload={"filter": {}}, format="json")

    def test_export_reports_result_url_and_skips_saved_message(self, runner, tmp_path):
        out = tmp_path / "export.json"

        async_result_mock = MagicMock()
        async_result_mock.download_to_file = AsyncMock(return_value=False)
        async_result_mock.result_url = "https://api/v3/async_result/123"

        with patch("vainu_cli.cli.VainuAPIKeyClient") as MockClient:
            instance = MockClient.return_value
            instance.companies_async = AsyncMock(return_value=async_result_mock)
            instance.close = AsyncMock()
            result = runner.invoke(
                main,
                [
                    "--api-key",
                    "test-key",
                    "companies-async",
                    "--query",
                    "?country=FI",
                    "--output",
                    str(out),
                ],
                catch_exceptions=False,
            )

        assert result.exit_code == 0
        assert "Result exists in result_url:" in result.output
        assert "Export saved to" not in result.output


# ── organizations search ──────────────────────────────────────────────────────


class TestOrganizationsSearch:
    @resp.activate
    def test_organizations_search_with_payload_stdin(self, runner):
        resp.add(resp.POST, f"{BASE_URL}/v3/organizations/", json=ORGANIZATIONS_RESPONSE)
        result = runner.invoke(
            main,
            ["--api-key", "test-key", "organizations", "--payload", "-"],
            input='{"query": "vainu"}',
            catch_exceptions=False,
        )
        assert result.exit_code == 0
        data = json.loads(result.output)
        assert data["count"] == 1

    def test_organizations_search_requires_payload(self, runner):
        result = runner.invoke(
            main,
            ["--api-key", "test-key", "organizations"],
        )
        assert result.exit_code != 0

    @resp.activate
    def test_organizations_search_payload_path_alias(self, runner, tmp_path):
        resp.add(
            resp.POST,
            f"{BASE_URL}/v3/organizations/?format=json",
            json=ORGANIZATIONS_RESPONSE,
        )
        payload_file = tmp_path / "payload.json"
        payload_file.write_text('{"query": "vainu"}')
        result = runner.invoke(
            main,
            [
                "--api-key",
                "test-key",
                "organizations",
                "--payload-path",
                str(payload_file),
            ],
            catch_exceptions=False,
        )
        assert result.exit_code == 0

    @resp.activate
    def test_organizations_search_accepts_format(self, runner):
        resp.add(
            resp.POST,
            f"{BASE_URL}/v3/organizations/?format=jsonl",
            body=JSONL_RESPONSE,
        )
        result = runner.invoke(
            main,
            ["--api-key", "test-key", "organizations", "--payload", "-", "--format", "jsonl"],
            input='{"query": "vainu"}',
            catch_exceptions=False,
        )
        assert result.exit_code == 0
        assert result.output == f"{JSONL_RESPONSE}\n"

    @resp.activate
    def test_organizations_search_writes_jsonl_to_file(self, runner, tmp_path):
        """jsonl streams by default, so the file is newline-terminated."""
        resp.add(
            resp.POST,
            f"{BASE_URL}/v3/organizations/?format=jsonl",
            body=JSONL_RESPONSE,
        )
        output_file = tmp_path / "organizations.jsonl"
        result = runner.invoke(
            main,
            [
                "--api-key",
                "test-key",
                "organizations",
                "--payload",
                "-",
                "--format",
                "jsonl",
                "--output",
                str(output_file),
            ],
            input='{"query": "vainu"}',
            catch_exceptions=False,
        )
        assert result.exit_code == 0
        assert output_file.read_text() == f"{JSONL_RESPONSE}\n"

    @resp.activate
    def test_organizations_search_no_stream_writes_raw_jsonl_to_file(self, runner, tmp_path):
        """--no-stream buffers and copies the body verbatim, trailing byte included."""
        resp.add(
            resp.POST,
            f"{BASE_URL}/v3/organizations/?format=jsonl",
            body=JSONL_RESPONSE,
        )
        output_file = tmp_path / "organizations.jsonl"
        result = runner.invoke(
            main,
            [
                "--api-key",
                "test-key",
                "organizations",
                "--payload",
                "-",
                "--format",
                "jsonl",
                "--no-stream",
                "--output",
                str(output_file),
            ],
            input='{"query": "vainu"}',
            catch_exceptions=False,
        )
        assert result.exit_code == 0
        assert output_file.read_text() == JSONL_RESPONSE


class TestOrganizationsExport:
    def test_organizations_export_payload_path_alias(self, runner, tmp_path):
        payload_file = tmp_path / "payload.json"
        payload_file.write_text('{"query": "vainu"}')
        out = tmp_path / "export.json"

        async_result_mock = MagicMock()
        async_result_mock.download_to_file = AsyncMock(return_value=None)
        async_result_mock.download_url = "https://downloads.vainu.io/r.json"
        async_result_mock.duration = 1

        with patch("vainu_cli.cli.VainuAPIKeyClient") as MockClient:
            instance = MockClient.return_value
            instance.organizations_async = AsyncMock(return_value=async_result_mock)
            instance.close = AsyncMock()

            result = runner.invoke(
                main,
                [
                    "--api-key",
                    "test-key",
                    "organizations-async",
                    "--payload-path",
                    str(payload_file),
                    "--format",
                    "jsonl",
                    "--output",
                    str(out),
                ],
                catch_exceptions=False,
            )

        assert result.exit_code == 0
        instance.organizations_async.assert_awaited_once_with(
            payload={"query": "vainu"}, format="jsonl"
        )

    def test_organizations_export_reports_result_url(self, runner, tmp_path):
        payload_file = tmp_path / "payload.json"
        payload_file.write_text('{"query": "vainu"}')
        out = tmp_path / "export.json"

        async_result_mock = MagicMock()
        async_result_mock.download_to_file = AsyncMock(return_value=False)
        async_result_mock.result_url = "https://api/v3/async_result/123"

        with patch("vainu_cli.cli.VainuAPIKeyClient") as MockClient:
            instance = MockClient.return_value
            instance.organizations_async = AsyncMock(return_value=async_result_mock)
            instance.close = AsyncMock()

            result = runner.invoke(
                main,
                [
                    "--api-key",
                    "test-key",
                    "organizations-async",
                    "--payload-path",
                    str(payload_file),
                    "--output",
                    str(out),
                ],
                catch_exceptions=False,
            )

        assert result.exit_code == 0
        assert "Result exists in result_url:" in result.output


# ── enrichment agent ──────────────────────────────────────────────────────────


class TestEnrichmentAgent:
    @resp.activate
    def test_enrichment_agent_with_flags(self, runner):
        resp.add(
            resp.POST,
            f"{BASE_URL}/v3/enrichment_agent/?format=json",
            json=ENRICHMENT_AGENT_RESPONSE,
        )
        result = runner.invoke(
            main,
            [
                "--api-key",
                "test-key",
                "enrichment-agent",
                "--prompt",
                "12345",
                "--database",
                "FI",
                "--business-id",
                "FI01320292",
            ],
            catch_exceptions=False,
        )
        assert result.exit_code == 0
        assert "main_business_activity" in json.loads(result.output)["response"]
        sent = json.loads(resp.calls[0].request.body)
        assert sent == {"prompt": "12345", "database": "FI", "business_id": "FI01320292"}

    @resp.activate
    def test_flags_override_payload_file(self, runner, tmp_path):
        """A saved payload holds the prompt; --business-id varies per run."""
        resp.add(
            resp.POST,
            f"{BASE_URL}/v3/enrichment_agent/?format=json",
            json=ENRICHMENT_AGENT_RESPONSE,
        )
        payload_file = tmp_path / "payload.json"
        payload_file.write_text(
            '{"prompt": "12345", "database": "FI", "business_id": "FI23365096", "refresh": false}'
        )
        result = runner.invoke(
            main,
            [
                "--api-key",
                "test-key",
                "enrichment-agent",
                "--payload",
                str(payload_file),
                "--business-id",
                "FI01320292",
                "--refresh",
            ],
            catch_exceptions=False,
        )
        assert result.exit_code == 0
        sent = json.loads(resp.calls[0].request.body)
        assert sent["business_id"] == "FI01320292"
        assert sent["prompt"] == "12345"
        assert sent["refresh"] is True

    @resp.activate
    def test_payload_from_stdin(self, runner):
        resp.add(
            resp.POST,
            f"{BASE_URL}/v3/enrichment_agent/?format=json",
            json=ENRICHMENT_AGENT_RESPONSE,
        )
        result = runner.invoke(
            main,
            ["--api-key", "test-key", "enrichment-agent", "--payload", "-"],
            input='{"prompt": "12345", "database": "FI", "business_id": "FI01320292"}',
            catch_exceptions=False,
        )
        assert result.exit_code == 0

    def test_missing_prompt_and_business_id_is_a_usage_error(self, runner):
        result = runner.invoke(
            main, ["--api-key", "test-key", "enrichment-agent", "--database", "FI"]
        )
        assert result.exit_code != 0
        assert "--prompt" in result.output
        assert "--business-id" in result.output

    def test_rejects_non_object_payload(self, runner):
        result = runner.invoke(
            main,
            ["--api-key", "test-key", "enrichment-agent", "--payload", "-"],
            input="[1, 2, 3]",
        )
        assert result.exit_code != 0
        assert "JSON object" in result.output

    def test_rejects_csv_format(self, runner):
        result = runner.invoke(
            main,
            [
                "--api-key",
                "test-key",
                "enrichment-agent",
                "--prompt",
                "12345",
                "--database",
                "FI",
                "--business-id",
                "FI01320292",
                "--format",
                "csv",
            ],
        )
        assert result.exit_code != 0
        assert "csv" in result.output

    @resp.activate
    def test_writes_jsonl_to_file(self, runner, tmp_path):
        """A single enrichment result is one document — jsonl is copied verbatim, not streamed."""
        resp.add(
            resp.POST,
            f"{BASE_URL}/v3/enrichment_agent/?format=jsonl",
            body=ENRICHMENT_AGENT_JSONL_RESPONSE,
        )
        output_file = tmp_path / "enrichment.jsonl"
        result = runner.invoke(
            main,
            [
                "--api-key",
                "test-key",
                "enrichment-agent",
                "--prompt",
                "12345",
                "--database",
                "FI",
                "--business-id",
                "FI01320292",
                "--format",
                "jsonl",
                "--output",
                str(output_file),
            ],
            catch_exceptions=False,
        )
        assert result.exit_code == 0
        assert output_file.read_text() == ENRICHMENT_AGENT_JSONL_RESPONSE

    def test_request_timeout_is_passed_to_the_client(self, runner):
        with patch("vainu_cli.cli.VainuAPIKeySyncClient") as MockClient:
            MockClient.return_value.enrichment_agent.return_value = ENRICHMENT_AGENT_RESPONSE
            result = runner.invoke(
                main,
                [
                    "--api-key",
                    "test-key",
                    "enrichment-agent",
                    "--prompt",
                    "12345",
                    "--database",
                    "FI",
                    "--business-id",
                    "FI01320292",
                    "--request-timeout",
                    "600",
                ],
                catch_exceptions=False,
            )
        assert result.exit_code == 0
        assert MockClient.call_args.kwargs["timeout"] == 600

    def test_async_mode_uses_the_async_client(self, runner):
        with patch("vainu_cli.cli.VainuAPIKeyClient") as MockClient:
            instance = MockClient.return_value
            instance.enrichment_agent = AsyncMock(return_value=ENRICHMENT_AGENT_RESPONSE)
            instance.close = AsyncMock()
            result = runner.invoke(
                main,
                [
                    "--api-key",
                    "test-key",
                    "--async-mode",
                    "enrichment-agent",
                    "--prompt",
                    "12345",
                    "--database",
                    "FI",
                    "--business-id",
                    "FI01320292",
                ],
                catch_exceptions=False,
            )
        assert result.exit_code == 0
        assert "main_business_activity" in json.loads(result.output)["response"]
        instance.enrichment_agent.assert_awaited_once()


# ── signals ───────────────────────────────────────────────────────────────────


class TestSignalsNews:
    @resp.activate
    def test_signals_news_with_payload_stdin(self, runner):
        resp.add(resp.POST, f"{BASE_URL}/v3/signals/news/", json=SIGNALS_NEWS_RESPONSE)
        result = runner.invoke(
            main,
            ["--api-key", "test-key", "signals-news", "--payload", "-"],
            input='{"query": {"?ALL": [{"?IN": {"tags": [43543]}}]}}',
            catch_exceptions=False,
        )
        assert result.exit_code == 0
        data = json.loads(result.output)
        assert data[0]["id"] == "65f0a1b2c3d4e5f6a7b8c9d0"

    def test_signals_news_requires_payload(self, runner):
        result = runner.invoke(main, ["--api-key", "test-key", "signals-news"])
        assert result.exit_code != 0

    @resp.activate
    def test_signals_news_payload_path_alias(self, runner, tmp_path):
        resp.add(
            resp.POST,
            f"{BASE_URL}/v3/signals/news/?format=json",
            json=SIGNALS_NEWS_RESPONSE,
        )
        payload_file = tmp_path / "payload.json"
        payload_file.write_text('{"query": {}}')
        result = runner.invoke(
            main,
            ["--api-key", "test-key", "signals-news", "--payload-path", str(payload_file)],
            catch_exceptions=False,
        )
        assert result.exit_code == 0

    @resp.activate
    def test_signals_news_writes_jsonl_to_file(self, runner, tmp_path):
        """jsonl streams by default, so the file is newline-terminated."""
        resp.add(
            resp.POST,
            f"{BASE_URL}/v3/signals/news/?format=jsonl",
            body=SIGNALS_JSONL_RESPONSE,
        )
        output_file = tmp_path / "signals.jsonl"
        result = runner.invoke(
            main,
            [
                "--api-key",
                "test-key",
                "signals-news",
                "--payload",
                "-",
                "--format",
                "jsonl",
                "--output",
                str(output_file),
            ],
            input='{"query": {}}',
            catch_exceptions=False,
        )
        assert result.exit_code == 0
        assert output_file.read_text() == f"{SIGNALS_JSONL_RESPONSE}\n"

    @resp.activate
    def test_signals_news_no_stream_writes_raw_jsonl_to_file(self, runner, tmp_path):
        """--no-stream buffers and copies the body verbatim, trailing byte included."""
        resp.add(
            resp.POST,
            f"{BASE_URL}/v3/signals/news/?format=jsonl",
            body=SIGNALS_JSONL_RESPONSE,
        )
        output_file = tmp_path / "signals.jsonl"
        result = runner.invoke(
            main,
            [
                "--api-key",
                "test-key",
                "signals-news",
                "--payload",
                "-",
                "--format",
                "jsonl",
                "--no-stream",
                "--output",
                str(output_file),
            ],
            input='{"query": {}}',
            catch_exceptions=False,
        )
        assert result.exit_code == 0
        assert output_file.read_text() == SIGNALS_JSONL_RESPONSE

    def test_signals_news_rejects_csv_format(self, runner):
        result = runner.invoke(
            main,
            ["--api-key", "test-key", "signals-news", "--payload", "-", "--format", "csv"],
            input='{"query": {}}',
        )
        assert result.exit_code != 0
        assert "csv" in result.output

    @resp.activate
    def test_task_duration_is_logged_at_debug(self, runner):
        resp.add(resp.POST, f"{BASE_URL}/v3/signals/news/", json=SIGNALS_NEWS_RESPONSE)
        with patch("vainu_cli.cli.logger.debug") as mock_debug:
            result = runner.invoke(
                main,
                ["-v", "--api-key", "test-key", "signals-news", "--payload", "-"],
                input='{"query": {}}',
                catch_exceptions=False,
            )

        assert result.exit_code == 0
        mock_debug.assert_any_call("Task '%s' %s in %.3fs", "signals-news", "completed", ANY)


class TestSignalsDataChanges:
    @resp.activate
    def test_signals_data_changes_with_payload_stdin(self, runner):
        resp.add(
            resp.POST,
            f"{BASE_URL}/v3/signals/data-changes/",
            json=SIGNALS_DATA_CHANGES_RESPONSE,
        )
        result = runner.invoke(
            main,
            ["--api-key", "test-key", "signals-data-changes", "--payload", "-"],
            input='{"query": {"?ALL": [{"?IN": {"tags": [8000037]}}]}}',
            catch_exceptions=False,
        )
        assert result.exit_code == 0
        data = json.loads(result.output)
        assert data[0]["dynamic_values"][0]["key"] == "new_financial_statement"

    def test_signals_data_changes_requires_payload(self, runner):
        result = runner.invoke(main, ["--api-key", "test-key", "signals-data-changes"])
        assert result.exit_code != 0

    def test_signals_data_changes_async_mode_uses_async_client(self, runner):
        with patch("vainu_cli.cli.VainuAPIKeyClient") as MockClient:
            instance = MockClient.return_value
            instance.signals_data_changes = AsyncMock(return_value=SIGNALS_DATA_CHANGES_RESPONSE)
            instance.close = AsyncMock()

            result = runner.invoke(
                main,
                [
                    "--api-key",
                    "test-key",
                    "--async-mode",
                    "signals-data-changes",
                    "--payload",
                    "-",
                ],
                input='{"query": {}}',
                catch_exceptions=False,
            )

        assert result.exit_code == 0
        instance.signals_data_changes.assert_awaited_once_with(payload={"query": {}}, format="json")


# ── --stream ──────────────────────────────────────────────────────────────────


class TestStreaming:
    @resp.activate
    def test_jsonl_streams_without_an_explicit_flag(self, runner):
        """Streaming is the default for line-oriented formats."""
        resp.add(
            resp.POST,
            f"{BASE_URL}/v3/signals/news/?format=jsonl",
            body=JSONL_STREAM_RESPONSE,
        )
        result = runner.invoke(
            main,
            ["--api-key", "test-key", "signals-news", "--payload", "-", "--format", "jsonl"],
            input='{"query": {}}',
            catch_exceptions=False,
        )
        assert result.exit_code == 0
        # Blank lines are dropped on the streaming path but kept by a buffered echo.
        assert result.output.splitlines() == JSONL_STREAM_LINES

    @resp.activate
    def test_no_stream_buffers_the_body(self, runner):
        resp.add(
            resp.POST,
            f"{BASE_URL}/v3/signals/news/?format=jsonl",
            body=JSONL_STREAM_RESPONSE,
        )
        result = runner.invoke(
            main,
            [
                "--api-key",
                "test-key",
                "signals-news",
                "--payload",
                "-",
                "--format",
                "jsonl",
                "--no-stream",
            ],
            input='{"query": {}}',
            catch_exceptions=False,
        )
        assert result.exit_code == 0
        assert result.output == f"{JSONL_STREAM_RESPONSE}\n"

    @resp.activate
    def test_json_does_not_stream_by_default(self, runner):
        resp.add(resp.POST, f"{BASE_URL}/v3/signals/news/", json=SIGNALS_NEWS_RESPONSE)
        result = runner.invoke(
            main,
            ["--api-key", "test-key", "signals-news", "--payload", "-"],
            input='{"query": {}}',
            catch_exceptions=False,
        )
        assert result.exit_code == 0
        assert json.loads(result.output)[0]["id"] == "65f0a1b2c3d4e5f6a7b8c9d0"

    @resp.activate
    def test_csv_streams_by_default(self, runner):
        resp.add(resp.POST, f"{BASE_URL}/v3/organizations/?format=csv", body=CSV_RESPONSE)
        result = runner.invoke(
            main,
            ["--api-key", "test-key", "organizations", "--payload", "-", "--format", "csv"],
            input='{"query": {}}',
            catch_exceptions=False,
        )
        assert result.exit_code == 0
        assert result.output.splitlines() == CSV_RESPONSE.splitlines()

    @resp.activate
    def test_signals_news_stream_writes_lines_to_stdout(self, runner):
        resp.add(
            resp.POST,
            f"{BASE_URL}/v3/signals/news/?format=jsonl",
            body=JSONL_STREAM_RESPONSE,
        )
        result = runner.invoke(
            main,
            [
                "--api-key",
                "test-key",
                "signals-news",
                "--payload",
                "-",
                "--format",
                "jsonl",
                "--stream",
            ],
            input='{"query": {}}',
            catch_exceptions=False,
        )
        assert result.exit_code == 0
        assert result.output.splitlines() == JSONL_STREAM_LINES

    @resp.activate
    def test_signals_news_stream_writes_lines_to_file(self, runner, tmp_path):
        resp.add(
            resp.POST,
            f"{BASE_URL}/v3/signals/news/?format=jsonl",
            body=JSONL_STREAM_RESPONSE,
        )
        output_file = tmp_path / "signals.jsonl"
        result = runner.invoke(
            main,
            [
                "--api-key",
                "test-key",
                "signals-news",
                "--payload",
                "-",
                "--format",
                "jsonl",
                "--stream",
                "--output",
                str(output_file),
            ],
            input='{"query": {}}',
            catch_exceptions=False,
        )
        assert result.exit_code == 0
        assert output_file.read_text() == "".join(f"{line}\n" for line in JSONL_STREAM_LINES)

    @resp.activate
    def test_organizations_stream_csv(self, runner):
        resp.add(resp.POST, f"{BASE_URL}/v3/organizations/?format=csv", body=CSV_RESPONSE)
        result = runner.invoke(
            main,
            [
                "--api-key",
                "test-key",
                "organizations",
                "--payload",
                "-",
                "--format",
                "csv",
                "--stream",
            ],
            input='{"query": {}}',
            catch_exceptions=False,
        )
        assert result.exit_code == 0
        assert result.output.splitlines() == CSV_RESPONSE.splitlines()

    def test_stream_rejects_json_format(self, runner):
        result = runner.invoke(
            main,
            ["--api-key", "test-key", "signals-news", "--payload", "-", "--stream"],
            input='{"query": {}}',
        )
        assert result.exit_code != 0
        assert "--stream requires --format" in result.output

    def test_signals_news_stream_async_mode(self, runner):
        with respx.mock:
            respx.post(f"{BASE_URL}/v3/signals/news/?format=jsonl").mock(
                return_value=httpx.Response(200, text=JSONL_STREAM_RESPONSE)
            )
            result = runner.invoke(
                main,
                [
                    "--api-key",
                    "test-key",
                    "--async-mode",
                    "signals-news",
                    "--payload",
                    "-",
                    "--format",
                    "jsonl",
                    "--stream",
                ],
                input='{"query": {}}',
                catch_exceptions=False,
            )
        assert result.exit_code == 0
        assert result.output.splitlines() == JSONL_STREAM_LINES


# ── --version ─────────────────────────────────────────────────────────────────


class TestVersion:
    def test_version_flag(self, runner):
        result = runner.invoke(main, ["--version"])
        assert result.exit_code == 0
        assert "0.1.0" in result.output


# ── OAuth via CLI ─────────────────────────────────────────────────────────────


class TestOAuthCLI:
    @resp.activate
    def test_oauth_auth_method(self, runner):
        resp.add(
            resp.POST,
            f"{BASE_URL}/oauth/token/",
            json={"access_token": "tok", "token_type": "Bearer", "expires_in": 3600},
        )
        resp.add(resp.POST, f"{BASE_URL}/v2/companies/", json=COMPANIES_RESPONSE)

        result = runner.invoke(
            main,
            [
                "--auth-method",
                "oauth",
                "--client-id",
                "my-client",
                "--client-secret",
                "my-secret",
                "companies",
                "--payload",
                "-",
            ],
            input='{"filter": {}}',
            catch_exceptions=False,
        )
        assert result.exit_code == 0

    def test_oauth_missing_credentials(self, runner):
        result = runner.invoke(
            main,
            [
                "--auth-method",
                "oauth",
                "companies",
                "--query",
                "?country=FI",
            ],
            env={},
        )
        assert result.exit_code != 0
        assert any(kw in result.output for kw in ("client-id", "client_id", "OAuth"))


# ── lists ─────────────────────────────────────────────────────────────────────


class TestLists:
    @resp.activate
    def test_lists_all(self, runner):
        resp.add(
            resp.GET,
            f"{BASE_URL}/v3/lists/organizations/?format=json",
            json=ORGANIZATION_LISTS_RESPONSE,
        )
        result = runner.invoke(
            main,
            ["--api-key", "test-key", "lists"],
            catch_exceptions=False,
        )
        assert result.exit_code == 0
        data = json.loads(result.output)
        assert data[0]["id"] == "63d8de4eb7dfe9f5896fa539"

    @resp.activate
    def test_lists_static_create(self, runner, tmp_path):
        resp.add(
            resp.POST,
            f"{BASE_URL}/v3/lists/organizations/static/?format=json",
            json=STATIC_LIST_RESPONSE,
            status=201,
        )
        payload_file = tmp_path / "payload.json"
        payload_file.write_text('{"name": "My Static List", "country": "FI"}')
        result = runner.invoke(
            main,
            [
                "--api-key",
                "test-key",
                "lists",
                "static",
                "create",
                "--payload",
                str(payload_file),
            ],
            catch_exceptions=False,
        )
        assert result.exit_code == 0
        assert json.loads(result.output)["name"] == "My Static List"

    @resp.activate
    def test_lists_static_add(self, runner):
        resp.add(
            resp.PATCH,
            f"{BASE_URL}/v3/lists/organizations/static/63d8de4eb7dfe9f5896fa540/add/",
            status=204,
        )
        result = runner.invoke(
            main,
            [
                "--api-key",
                "test-key",
                "lists",
                "static",
                "add",
                "63d8de4eb7dfe9f5896fa540",
                "--payload",
                "-",
            ],
            input='["FI01234567"]',
            catch_exceptions=False,
        )
        assert result.exit_code == 0
        assert "Added 1 business ID(s)" in result.output

    @resp.activate
    def test_lists_dynamic_update(self, runner, tmp_path):
        resp.add(
            resp.PATCH,
            f"{BASE_URL}/v3/lists/organizations/dynamic/69e61e048c5d1ae30b426a1b/?format=json",
            json=DYNAMIC_LIST_RESPONSE,
        )
        payload_file = tmp_path / "payload.json"
        payload_file.write_text('{"name": "Swedish Manufacturers"}')
        result = runner.invoke(
            main,
            [
                "--api-key",
                "test-key",
                "lists",
                "dynamic",
                "update",
                "69e61e048c5d1ae30b426a1b",
                "--payload",
                str(payload_file),
            ],
            catch_exceptions=False,
        )
        assert result.exit_code == 0
        assert json.loads(result.output)["country"] == "SE"

    def test_lists_static_add_rejects_object_payload(self, runner):
        result = runner.invoke(
            main,
            [
                "--api-key",
                "test-key",
                "lists",
                "static",
                "add",
                "63d8de4eb7dfe9f5896fa540",
                "--payload",
                "-",
            ],
            input='{"business_ids": ["FI01234567"]}',
        )
        assert result.exit_code != 0
        assert "JSON array" in result.output

    @resp.activate
    def test_lists_delete(self, runner):
        resp.add(
            resp.DELETE,
            f"{BASE_URL}/v3/lists/organizations/63d8de4eb7dfe9f5896fa539/",
            status=204,
        )
        result = runner.invoke(
            main,
            [
                "--api-key",
                "test-key",
                "lists",
                "delete",
                "63d8de4eb7dfe9f5896fa539",
            ],
            catch_exceptions=False,
        )
        assert result.exit_code == 0
        assert "Deleted list 63d8de4eb7dfe9f5896fa539" in result.output
