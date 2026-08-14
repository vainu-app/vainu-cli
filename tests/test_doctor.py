"""Tests for `vainu doctor`."""

from __future__ import annotations

from unittest.mock import patch

import pytest
from click.testing import CliRunner

from vainu_cli.cli import main


@pytest.fixture
def runner() -> CliRunner:
    return CliRunner()


class TestDoctor:
    def test_doctor_all_ok_with_api_key(self, runner, monkeypatch):
        monkeypatch.setenv("VAINU_API_KEY", "test-key")
        with patch("vainu_cli.setup_commands.shutil.which", return_value="/usr/local/bin/vainu"):
            result = runner.invoke(main, ["doctor"], catch_exceptions=False)
        assert result.exit_code == 0
        assert "All checks passed" in result.output
        assert "API key" in result.output

    def test_doctor_fails_without_auth(self, runner):
        with patch("vainu_cli.setup_commands.shutil.which", return_value="/usr/local/bin/vainu"):
            result = runner.invoke(main, ["doctor"], catch_exceptions=False)
        assert result.exit_code == 1
        assert "Auth: not configured" in result.output

    def test_doctor_warns_when_vainu_not_on_path(self, runner, monkeypatch):
        monkeypatch.setenv("VAINU_API_KEY", "test-key")
        with patch("vainu_cli.setup_commands.shutil.which", return_value=None):
            result = runner.invoke(main, ["doctor"], catch_exceptions=False)
        assert result.exit_code == 1
        assert "not found on PATH" in result.output

    def test_doctor_lists_examples(self, runner, monkeypatch):
        monkeypatch.setenv("VAINU_API_KEY", "test-key")
        with patch("vainu_cli.setup_commands.shutil.which", return_value="/usr/local/bin/vainu"):
            result = runner.invoke(main, ["doctor"], catch_exceptions=False)
        assert "Examples: OK" in result.output
