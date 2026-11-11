"""Tests for the resumable export download."""

import gzip
import subprocess
from pathlib import Path
from unittest.mock import patch

import pytest
import responses as resp
from conftest import add_fake_s3

from vainu_cli._download import Downloader, download_export

_URL = "https://vainu-exports.s3.amazonaws.com/u/job.jsonl?Signature=abc"
_PLAIN = b"".join(b'{"business_id": "FI%08d"}\n' % i for i in range(300))
_GZIPPED = gzip.compress(_PLAIN, mtime=0)
_PART_NAME = "export.jsonl.fedab521270c4.part"


def _corrupt(data: bytes) -> bytes:
    """Flips one byte in the compressed body, so the gzip CRC no longer matches."""
    middle = len(data) // 2
    return data[:middle] + bytes([data[middle] ^ 0xFF]) + data[middle + 1 :]


# ── failures ──────────────────────────────────────────────────────────────────


@resp.activate
def test_corrupt_gzip_fails_and_removes_the_part(tmp_path):
    add_fake_s3(_URL, _corrupt(_GZIPPED), gzipped=True)
    out = tmp_path / "export.jsonl"
    with pytest.raises(RuntimeError, match="corrupt"):
        download_export(output=str(out), url=_URL)
    assert sorted(path.name for path in tmp_path.iterdir()) == []


@resp.activate
def test_oversized_part_is_discarded(tmp_path):
    add_fake_s3(_URL, _GZIPPED, gzipped=True)
    (tmp_path / _PART_NAME).write_bytes(_GZIPPED + b"junk")
    out = tmp_path / "export.jsonl"
    with pytest.raises(RuntimeError, match="partial file was removed"):
        download_export(output=str(out), url=_URL)
    assert sorted(path.name for path in tmp_path.iterdir()) == []


@resp.activate
def test_gives_up_after_max_attempts_and_keeps_the_part(tmp_path):
    data = _PLAIN * 4
    add_fake_s3(_URL, data, max_body=len(data) // 10)
    out = tmp_path / "export.jsonl"
    with pytest.raises(RuntimeError, match="incomplete after 5 attempts") as raised:
        download_export(output=str(out), url=_URL)
    part = tmp_path / _PART_NAME
    assert f"kept in {part}" in str(raised.value)
    assert part.read_bytes() == data[: 5 * (len(data) // 10)]
    assert not out.exists()


@resp.activate
def test_curl_downloader_needs_curl(tmp_path):
    add_fake_s3(_URL, _GZIPPED, gzipped=True)
    out = tmp_path / "export.jsonl"
    with (
        patch("vainu_cli._download.shutil.which", return_value=None),
        pytest.raises(RuntimeError, match="curl is not installed"),
    ):
        download_export(downloader=Downloader.CURL, output=str(out), url=_URL)
    assert not out.exists()


# ── downloads ─────────────────────────────────────────────────────────────────


@resp.activate
def test_gunzips_a_gzip_stored_export(tmp_path):
    ranges = add_fake_s3(_URL, _GZIPPED, gzipped=True)
    out = tmp_path / "export.jsonl"
    download_export(output=str(out), url=_URL)
    assert out.read_bytes() == _PLAIN
    assert ranges == ["bytes=0-0", None]
    assert [path.name for path in tmp_path.iterdir()] == ["export.jsonl"]


@resp.activate
def test_keep_gzip_writes_the_stored_bytes(tmp_path):
    add_fake_s3(_URL, _GZIPPED, gzipped=True)
    out = tmp_path / "export.jsonl.gz"
    download_export(keep_gzip=True, output=str(out), url=_URL)
    assert out.read_bytes() == _GZIPPED


@resp.activate
def test_plain_export_is_copied_as_is(tmp_path):
    add_fake_s3(_URL, _PLAIN)
    out = tmp_path / "export.jsonl"
    download_export(output=str(out), url=_URL)
    assert out.read_bytes() == _PLAIN


@resp.activate
def test_resumes_after_dropped_connections(tmp_path):
    third = len(_GZIPPED) // 3 + 1
    ranges = add_fake_s3(_URL, _GZIPPED, gzipped=True, max_body=third)
    out = tmp_path / "export.jsonl"
    download_export(output=str(out), url=_URL)
    assert out.read_bytes() == _PLAIN
    assert ranges == ["bytes=0-0", None, f"bytes={third}-", f"bytes={2 * third}-"]


@resp.activate
def test_resumes_a_part_left_by_an_earlier_run(tmp_path):
    ranges = add_fake_s3(_URL, _GZIPPED, gzipped=True)
    (tmp_path / _PART_NAME).write_bytes(_GZIPPED[:100])
    out = tmp_path / "export.jsonl"
    download_export(output=str(out), url=_URL)
    assert out.read_bytes() == _PLAIN
    assert ranges == ["bytes=0-0", "bytes=100-"]


@resp.activate
def test_starts_over_when_the_server_ignores_the_range(tmp_path):
    add_fake_s3(_URL, _GZIPPED, gzipped=True, ranges_supported=False)
    (tmp_path / _PART_NAME).write_bytes(b"stale bytes")
    out = tmp_path / "export.jsonl"
    download_export(output=str(out), url=_URL)
    assert out.read_bytes() == _PLAIN


@resp.activate
def test_curl_downloader_appends_raw_bytes_and_is_retried(tmp_path):
    add_fake_s3(_URL, _GZIPPED, gzipped=True)
    calls: list[list[str]] = []

    def _fake_curl(argv, check):
        assert check is True
        calls.append(argv)
        if len(calls) == 1:
            raise subprocess.CalledProcessError(56, argv)  # 56: failure receiving data
        part = Path(argv[argv.index("--output") + 1])
        part.write_bytes(_GZIPPED)

    out = tmp_path / "export.jsonl"
    with (
        patch("vainu_cli._download.shutil.which", return_value="/usr/bin/curl"),
        patch("vainu_cli._download.subprocess.run", side_effect=_fake_curl),
    ):
        download_export(downloader=Downloader.CURL, output=str(out), url=_URL)

    assert out.read_bytes() == _PLAIN
    assert len(calls) == 2
    argv = calls[-1]
    assert argv[0] == "/usr/bin/curl"
    assert argv[-1] == _URL
    assert argv[argv.index("--continue-at") + 1] == "-"
    assert argv[argv.index("--output") + 1] == str(tmp_path / _PART_NAME)
    # Decoding on the fly would break resuming: ranges count the stored gzip bytes.
    assert "--compressed" not in argv
