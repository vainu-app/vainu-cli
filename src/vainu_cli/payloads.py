"""The shared `--payload` option and the resolution of its value.

`--payload` accepts three interchangeable sources: inline JSON, a path to a JSON
file, or `-` to read stdin. Option and parsing live together here so that
`vainu organizations`, `vainu signals-*` and `vainu lists ...` cannot drift apart
on either the flag spelling or the error messages.
"""

from __future__ import annotations

import json
import sys
from collections.abc import Callable
from typing import Any, TypeVar

import click

F = TypeVar("F", bound=Callable[..., Any])

PAYLOAD_HELP = "JSON payload: inline JSON, a file path, or '-' to read from stdin."


def option_payload(required: bool = True) -> Callable[[F], F]:
    """The `--payload` / `--payload-path` option, with `payload_path` as the param name."""
    kwargs: dict[str, Any] = {
        "required": required,
        # click.Path() no longer describes the value exactly — it may be inline
        # JSON or '-' — but it validates nothing on its own and it keeps
        # filename completion for the common case.
        "type": click.Path(),
        "metavar": "JSON/FILE/-",
        "help": PAYLOAD_HELP,
    }
    if not required:
        kwargs["default"] = None
    return click.option(
        "--payload",
        "--payload-path",
        "payload_path",
        **kwargs,
    )


def _looks_like_json(value: str) -> bool:
    """Treat a value opening with an object or array brace as inline JSON.

    No filename starts that way in practice, so sniffing costs nothing and saves
    the caller a temp file or an `echo | vainu … --payload -` pipe.
    """
    return value.lstrip()[:1] in ("{", "[")


def _read_payload_source(value: str) -> tuple[str, str]:
    """Return the raw text for whichever source `value` names, plus a label for errors."""
    if value == "-":
        return sys.stdin.read(), "stdin"
    if _looks_like_json(value):
        return value, "inline JSON"
    try:
        with open(value) as fh:
            return fh.read(), f"file {value!r}"
    except OSError as exc:
        raise click.UsageError(f"Cannot read --payload file {value!r}: {exc.strerror}.") from exc


def load_payload(payload_path: str) -> dict | list:
    """Resolve a required `--payload` into the JSON value it names."""
    raw, source = _read_payload_source(payload_path)
    try:
        return json.loads(raw)
    except json.JSONDecodeError as exc:
        raise click.UsageError(f"--payload ({source}) is not valid JSON: {exc}") from exc


def load_query_or_payload(query: str | None, payload_path: str | None) -> str | dict | list:
    """Resolve the mutually exclusive `--query` / `--payload` pair for search commands."""
    if query and payload_path:
        raise click.UsageError("--query and --payload are mutually exclusive.")
    if not query and not payload_path:
        raise click.UsageError("Provide either --query or --payload.")
    if query:
        return query
    return load_payload(str(payload_path))
