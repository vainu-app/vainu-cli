"""CLI integration tests using Click's CliRunner."""

import json
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
import responses as resp
from click.testing import CliRunner
from conftest import (
    BASE_URL,
    COMPANIES_RESPONSE,
    ORGANIZATIONS_RESPONSE,
)

from vainu_cli.cli import main


@pytest.fixture
def runner() -> CliRunner:
    return CliRunner()


# ── companies search ──────────────────────────────────────────────────────────


class TestCompaniesSearch:
    @resp.activate
    def test_api_key_from_env(self, runner):
        resp.add(resp.GET, f"{BASE_URL}/v2/companies/", json=COMPANIES_RESPONSE)
        result = runner.invoke(
            main,
            ["companies", "search", "--query", "?country=FI"],
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
            ["--api-key", "flag-key", "companies", "search", "--query", "?country=FI"],
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
                "search",
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
            ["--api-key", "test-key", "companies", "search", "--payload", "-"],
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
                "search",
                "--payload",
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
                "search",
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
            ["companies", "search", "--query", "?country=FI"],
            env={},
        )
        assert result.exit_code != 0
        assert "API key" in result.output or "VAINU_API_KEY" in result.output

    def test_jwt_not_implemented(self, runner):
        result = runner.invoke(
            main,
            ["--auth-method", "jwt", "companies", "search", "--query", "?country=FI"],
        )
        assert result.exit_code != 0
        assert "not yet implemented" in result.output

    def test_neither_query_nor_payload_fails(self, runner):
        result = runner.invoke(
            main,
            ["--api-key", "test-key", "companies", "search"],
        )
        assert result.exit_code != 0

    def test_invalid_json_payload_fails(self, runner):
        result = runner.invoke(
            main,
            ["--api-key", "test-key", "companies", "search", "--payload", "-"],
            input="not valid json",
        )
        assert result.exit_code != 0
        assert "JSON" in result.output


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
                    "companies",
                    "export",
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
            ["--api-key", "test-key", "companies", "export", "--query", "?country=FI"],
        )
        assert result.exit_code != 0
        assert "output" in result.output.lower() or "Missing option" in result.output


# ── organizations search ──────────────────────────────────────────────────────


class TestOrganizationsSearch:
    @resp.activate
    def test_organizations_search_with_payload_stdin(self, runner):
        resp.add(resp.POST, f"{BASE_URL}/v3/organizations/", json=ORGANIZATIONS_RESPONSE)
        result = runner.invoke(
            main,
            ["--api-key", "test-key", "organizations", "search", "--payload", "-"],
            input='{"query": "vainu"}',
            catch_exceptions=False,
        )
        assert result.exit_code == 0
        data = json.loads(result.output)
        assert data["count"] == 1

    def test_organizations_search_requires_payload(self, runner):
        result = runner.invoke(
            main,
            ["--api-key", "test-key", "organizations", "search"],
        )
        assert result.exit_code != 0


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
                "search",
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
                "search",
                "--query",
                "?country=FI",
            ],
            env={},
        )
        assert result.exit_code != 0
        assert any(kw in result.output for kw in ("client-id", "client_id", "OAuth"))
