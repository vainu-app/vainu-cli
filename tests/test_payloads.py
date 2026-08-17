"""Unit tests for `--payload` value resolution (inline JSON, file path, stdin)."""

import io

import click
import pytest

from vainu_cli.payloads import load_payload, load_query_or_payload


class TestLoadPayload:
    def test_inline_object(self):
        assert load_payload('{"query": "vainu"}') == {"query": "vainu"}

    def test_inline_array(self):
        assert load_payload('["FI01320292", "FI23365096"]') == ["FI01320292", "FI23365096"]

    def test_inline_tolerates_leading_whitespace(self):
        assert load_payload('  \n {"a": 1}') == {"a": 1}

    def test_file_path(self, tmp_path):
        payload_file = tmp_path / "payload.json"
        payload_file.write_text('{"a": 1}')
        assert load_payload(str(payload_file)) == {"a": 1}

    def test_stdin(self, monkeypatch):
        monkeypatch.setattr("sys.stdin", io.StringIO('{"a": 1}'))
        assert load_payload("-") == {"a": 1}

    def test_missing_file_raises_usage_error(self, tmp_path):
        with pytest.raises(click.UsageError, match="Cannot read --payload file"):
            load_payload(str(tmp_path / "nope.json"))

    def test_unreadable_inline_json_names_the_source(self):
        with pytest.raises(click.UsageError, match=r"--payload \(inline JSON\) is not valid JSON"):
            load_payload('{"a": ')

    def test_invalid_file_json_names_the_file(self, tmp_path):
        payload_file = tmp_path / "payload.json"
        payload_file.write_text("not json")
        with pytest.raises(click.UsageError, match=r"--payload \(file .*\) is not valid JSON"):
            load_payload(str(payload_file))

    def test_braces_inside_a_path_do_not_trigger_inline_parsing(self, tmp_path):
        """Only a leading brace means inline JSON — one further in is still a path."""
        payload_file = tmp_path / "{weird}.json"
        payload_file.write_text('{"a": 1}')
        assert load_payload(str(payload_file)) == {"a": 1}


class TestLoadQueryOrPayload:
    def test_query_passes_through(self):
        assert load_query_or_payload("?country=FI", None) == "?country=FI"

    def test_payload_is_parsed(self):
        assert load_query_or_payload(None, '{"a": 1}') == {"a": 1}

    def test_both_is_an_error(self):
        with pytest.raises(click.UsageError, match="mutually exclusive"):
            load_query_or_payload("?country=FI", '{"a": 1}')

    def test_neither_is_an_error(self):
        with pytest.raises(click.UsageError, match="Provide either"):
            load_query_or_payload(None, None)
