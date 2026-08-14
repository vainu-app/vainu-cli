"""Tests for `vainu update` / `vainu upgrade`."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest
from click.testing import CliRunner

from vainu_cli.cli import main


@pytest.fixture
def runner() -> CliRunner:
    return CliRunner()


class TestUpdate:
    def test_update_runs_uv_tool_upgrade(self, runner):
        completed = MagicMock(returncode=0)
        with (
            patch("vainu_cli.setup_commands.shutil.which", return_value="/usr/bin/uv"),
            patch("vainu_cli.setup_commands.subprocess.run", return_value=completed) as run,
        ):
            result = runner.invoke(main, ["update"], catch_exceptions=False)
        assert result.exit_code == 0
        run.assert_called_once_with(["uv", "tool", "upgrade", "vainu-cli"], check=False)
        assert "Updating vainu-cli" in result.output
        assert "Update complete" in result.output

    def test_upgrade_is_alias_for_update(self, runner):
        completed = MagicMock(returncode=0)
        with (
            patch("vainu_cli.setup_commands.shutil.which", return_value="/usr/bin/uv"),
            patch("vainu_cli.setup_commands.subprocess.run", return_value=completed) as run,
        ):
            result = runner.invoke(main, ["upgrade"], catch_exceptions=False)
        assert result.exit_code == 0
        run.assert_called_once_with(["uv", "tool", "upgrade", "vainu-cli"], check=False)

    def test_update_falls_back_to_pip_when_uv_missing(self, runner):
        completed = MagicMock(returncode=0)
        with (
            patch("vainu_cli.setup_commands.shutil.which", return_value=None),
            patch("vainu_cli.setup_commands.sys.executable", "/usr/bin/python"),
            patch("vainu_cli.setup_commands.subprocess.run", return_value=completed) as run,
        ):
            result = runner.invoke(main, ["update"], catch_exceptions=False)
        assert result.exit_code == 0
        run.assert_called_once_with(
            ["/usr/bin/python", "-m", "pip", "install", "--upgrade", "vainu-cli"],
            check=False,
        )

    def test_update_exits_nonzero_when_upgrade_fails(self, runner):
        completed = MagicMock(returncode=1)
        with (
            patch("vainu_cli.setup_commands.shutil.which", return_value="/usr/bin/uv"),
            patch("vainu_cli.setup_commands.subprocess.run", return_value=completed),
        ):
            result = runner.invoke(main, ["update"], catch_exceptions=False)
        assert result.exit_code == 1
        assert "Update failed" in result.output
