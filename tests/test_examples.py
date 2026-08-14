"""Tests for bundled example payloads."""

from pathlib import Path

import pytest
from click.testing import CliRunner

from vainu_cli.cli import main
from vainu_cli.examples import examples_dir, list_examples, resolve_example


class TestExamplesModule:
    def test_examples_dir_exists(self):
        root = examples_dir()
        assert root.is_dir()
        assert (root / "organizations_api").is_dir()
        assert (root / "signals_api").is_dir()

    def test_list_examples_includes_known_file(self):
        paths = list_examples(category="organizations_api")
        names = [p.name for p in paths]
        assert "08-simple-filtering-example-using-v3organizations.json" in names

    def test_resolve_by_partial_name(self):
        path = resolve_example("08-simple-filtering")
        assert path.name == "08-simple-filtering-example-using-v3organizations.json"

    def test_resolve_by_category_and_file(self):
        path = resolve_example("signals_api/01-news-signals-for-one-company.json")
        assert path.name == "01-news-signals-for-one-company.json"

    def test_resolve_missing_raises(self):
        with pytest.raises(FileNotFoundError, match="not found"):
            resolve_example("no-such-payload.json")


class TestExamplesCLI:
    @pytest.fixture
    def runner(self) -> CliRunner:
        return CliRunner()

    def test_examples_list(self, runner):
        result = runner.invoke(main, ["examples", "list"], catch_exceptions=False)
        assert result.exit_code == 0
        assert "organizations_api/08-simple-filtering" in result.output

    def test_examples_list_category(self, runner):
        result = runner.invoke(
            main,
            ["examples", "list", "--category", "signals_api"],
            catch_exceptions=False,
        )
        assert result.exit_code == 0
        assert "signals_api/01-news-signals-for-one-company.json" in result.output
        assert "organizations_api/" not in result.output

    def test_examples_path(self, runner):
        result = runner.invoke(
            main,
            ["examples", "path", "08-simple-filtering"],
            catch_exceptions=False,
        )
        assert result.exit_code == 0
        path = Path(result.output.strip())
        assert path.is_file()
        assert path.name.startswith("08-simple-filtering")

    def test_examples_path_missing(self, runner):
        result = runner.invoke(
            main,
            ["examples", "path", "does-not-exist"],
            catch_exceptions=False,
        )
        assert result.exit_code != 0
        assert "not found" in result.output.lower()
