"""Resumable download of async export files from their presigned S3 links."""

import enum
import gzip
import logging
import re
import shutil
import subprocess
import zlib
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

import requests
import urllib3

from vainu_cli.common import DEFAULT_TIMEOUT_SECONDS

_LOGGER = logging.getLogger(__name__)

_CHUNK_SIZE = 1024 * 1024
_MAX_ATTEMPTS = 5
# Reading `response.raw` directly raises urllib3's errors, not requests' wrappers.
_RETRYABLE_ERRORS = (
    requests.RequestException,
    subprocess.CalledProcessError,
    urllib3.exceptions.HTTPError,
)


class Downloader(enum.StrEnum):
    PYTHON = "python"
    CURL = "curl"


@dataclass(frozen=True)
class _StoredObject:
    etag: str
    gzipped: bool
    size: int


def _probe(url: str) -> _StoredObject:
    """Returns the stored object's ETag, encoding and size, read with a one-byte range."""
    with requests.get(
        url, headers={"Range": "bytes=0-0"}, stream=True, timeout=DEFAULT_TIMEOUT_SECONDS
    ) as response:
        response.raise_for_status()
        headers = response.headers
    if response.status_code == 206:
        # `Content-Range: bytes 0-0/27313288`
        size = int(headers["Content-Range"].rpartition("/")[2])
    elif "Content-Length" in headers:
        size = int(headers["Content-Length"])
    else:
        raise RuntimeError(f"Export at {url} reports no size (status {response.status_code})!")
    # S3 does not negotiate encoding: an object stored gzipped is always served gzipped.
    return _StoredObject(
        etag=re.sub(r"\W", "", headers.get("ETag", "")),
        gzipped=headers.get("Content-Encoding") == "gzip",
        size=size,
    )


def _fetch_python(url: str, part: Path) -> None:
    """Appends the rest of the stored object to `part`, without decoding it."""
    offset = part.stat().st_size if part.exists() else 0
    headers = {"Range": f"bytes={offset}-"} if offset else {}
    with requests.get(
        url, headers=headers, stream=True, timeout=DEFAULT_TIMEOUT_SECONDS
    ) as response:
        response.raise_for_status()
        # A server ignoring the range sends the whole object again: start over.
        mode = "ab" if response.status_code == 206 else "wb"
        with part.open(mode) as file:
            for chunk in response.raw.stream(_CHUNK_SIZE, decode_content=False):
                file.write(chunk)


def _fetch_curl(url: str, part: Path) -> None:
    """Appends the rest of the stored object to `part` with the native curl binary."""
    curl = shutil.which("curl")
    if curl is None:
        raise RuntimeError("curl is not installed. Install curl or use the python downloader.")
    # No --compressed: keep the stored gzip bytes so a resumed range lines up with them.
    # The speed limit aborts a stalled transfer, like the python downloader's read timeout.
    subprocess.run(
        [
            curl,
            "--location",
            "--fail",
            "--silent",
            "--show-error",
            "--connect-timeout",
            str(DEFAULT_TIMEOUT_SECONDS),
            "--speed-limit",
            "1",
            "--speed-time",
            str(DEFAULT_TIMEOUT_SECONDS),
            "--continue-at",
            "-",
            "--output",
            str(part),
            url,
        ],
        check=True,
    )


_FETCHERS: dict[Downloader, Callable[[str, Path], None]] = {
    Downloader.CURL: _fetch_curl,
    Downloader.PYTHON: _fetch_python,
}


def _size(path: Path) -> int:
    return path.stat().st_size if path.exists() else 0


def _finish(*, gunzip: bool, output: Path, part: Path) -> None:
    """Moves the complete `part` into `output`, gunzipping it on the way when asked."""
    if not gunzip:
        part.replace(output)
        return
    tmp = output.with_name(f"{output.name}.tmp")
    try:
        # gzip verifies the CRC32 in the trailer, so a corrupt download fails here.
        with gzip.open(part, "rb") as source, tmp.open("wb") as target:
            shutil.copyfileobj(source, target, _CHUNK_SIZE)
    except (EOFError, OSError, zlib.error) as err:
        tmp.unlink(missing_ok=True)
        part.unlink(missing_ok=True)
        raise RuntimeError(
            f"Downloaded export is corrupt ({err}); the partial file was removed."
        ) from err
    tmp.replace(output)
    part.unlink()


def download_export(
    *,
    downloader: Downloader = Downloader.PYTHON,
    keep_gzip: bool = False,
    output: str,
    url: str,
) -> None:
    """Downloads the export at `url` to `output`, resuming after interruptions.

    1. Probe the stored object's ETag, size and encoding with a one-byte range request.
    2. Fetch its raw bytes into `<output>.<etag>.part`, resuming from the part's size after
       a failure. The ETag in the name keeps a part from being resumed with another object.
    3. Gunzip the part (unless `keep_gzip`) into `output`; nothing is written there until
       the whole file has been received and verified.
    """
    stored = _probe(url)
    output_path = Path(output)
    part = output_path.with_name(f"{output_path.name}.{stored.etag}.part")
    fetch = _FETCHERS[downloader]
    last_error: Exception | None = None
    for attempt in range(1, _MAX_ATTEMPTS + 1):
        if _size(part) >= stored.size:
            break
        try:
            fetch(url, part)
        except _RETRYABLE_ERRORS as err:
            last_error = err
            _LOGGER.warning(
                "Download attempt %s failed at `%s` of `%s` bytes: %s",
                attempt,
                _size(part),
                stored.size,
                err,
            )
    received = _size(part)
    if received > stored.size:
        part.unlink()
        raise RuntimeError(
            f"Received `{received}` bytes but the export has `{stored.size}`; "
            "the partial file was removed."
        )
    if received < stored.size:
        raise RuntimeError(
            f"Download incomplete after {_MAX_ATTEMPTS} attempts: `{received}` of "
            f"`{stored.size}` bytes kept in {part}."
        ) from last_error
    _finish(gunzip=stored.gzipped and not keep_gzip, output=output_path, part=part)
    _LOGGER.info("Downloaded `%s` bytes to %s", stored.size, output)
