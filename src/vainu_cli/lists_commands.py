"""`vainu lists` commands for organization list management."""

from __future__ import annotations

import asyncio
from collections.abc import Callable
from typing import Any, TypeVar

import click

from vainu_cli.common import LISTS_RESPONSE_FORMATS, ResponseFormat
from vainu_cli.payloads import load_payload, option_payload

F = TypeVar("F", bound=Callable[..., Any])


def _option_lists_format(func: F) -> F:
    return click.option(
        "--format",
        "fmt",
        type=click.Choice(LISTS_RESPONSE_FORMATS),
        default="json",
        show_default=True,
        help="Response format.",
    )(func)


def _option_output(func: F) -> F:
    return click.option(
        "--output",
        default=None,
        type=click.Path(),
        help="Write response to file instead of stdout.",
    )(func)


def _run_lists_command(
    config: Any,
    *,
    task_name: str,
    sync_call: Callable[[Any], Any],
    async_call: Callable[[Any], Any],
) -> Any:
    from vainu_cli.cli import _make_async_client, _make_sync_client, _timed_task

    @_timed_task(task_name)
    def _run() -> Any:
        if config.async_mode:

            async def _async_run() -> Any:
                client = _make_async_client(config)
                try:
                    return await async_call(client)
                finally:
                    await client.close()

            return asyncio.run(_async_run())

        client = _make_sync_client(config)
        try:
            return sync_call(client)
        finally:
            client.close()

    return _run()


def _emit_result(result: Any, output: str | None) -> None:
    from vainu_cli.cli import _write_output

    _write_output(result, output)


def _emit_no_content(message: str) -> None:
    click.echo(message, err=True)


@click.group("lists", invoke_without_command=True)
@_option_lists_format
@_option_output
@click.pass_context
def lists_group(ctx: click.Context, fmt: ResponseFormat, output: str | None) -> None:
    """Manage organization lists (static and dynamic).

    Run without a subcommand to list all accessible lists. Requires OAuth, JWT,
    or `vainu login` — not a static API key alone.

    Docs: https://developers.vainu.com/v3/docs/list-management-apis
    """
    if ctx.invoked_subcommand is not None:
        return
    config = ctx.obj
    result = _run_lists_command(
        config,
        task_name="lists",
        sync_call=lambda client: client.organization_lists(format=fmt),
        async_call=lambda client: client.organization_lists(format=fmt),
    )
    _emit_result(result, output)


@lists_group.command("get")
@click.argument("list_id")
@_option_lists_format
@_option_output
@click.pass_obj
def lists_get(config: Any, list_id: str, fmt: ResponseFormat, output: str | None) -> None:
    """Retrieve one organization list by id."""
    result = _run_lists_command(
        config,
        task_name="lists-get",
        sync_call=lambda client: client.organization_list_get(list_id, format=fmt),
        async_call=lambda client: client.organization_list_get(list_id, format=fmt),
    )
    _emit_result(result, output)


@lists_group.command("delete")
@click.argument("list_id")
@click.pass_obj
def lists_delete(config: Any, list_id: str) -> None:
    """Delete an organization list by id (static or dynamic)."""
    _run_lists_command(
        config,
        task_name="lists-delete",
        sync_call=lambda client: client.organization_list_delete(list_id),
        async_call=lambda client: client.organization_list_delete(list_id),
    )
    _emit_no_content(f"Deleted list {list_id}")


@click.group("static", invoke_without_command=True)
@_option_lists_format
@_option_output
@click.pass_context
def static_group(ctx: click.Context, fmt: ResponseFormat, output: str | None) -> None:
    """Manage static organization lists (fixed business IDs)."""
    if ctx.invoked_subcommand is not None:
        return
    config = ctx.obj
    result = _run_lists_command(
        config,
        task_name="lists-static",
        sync_call=lambda client: client.organization_lists_static(format=fmt),
        async_call=lambda client: client.organization_lists_static(format=fmt),
    )
    _emit_result(result, output)


@static_group.command("get")
@click.argument("list_id")
@_option_lists_format
@_option_output
@click.pass_obj
def static_get(config: Any, list_id: str, fmt: ResponseFormat, output: str | None) -> None:
    """Retrieve one static list."""
    result = _run_lists_command(
        config,
        task_name="lists-static-get",
        sync_call=lambda client: client.organization_list_static_get(list_id, format=fmt),
        async_call=lambda client: client.organization_list_static_get(list_id, format=fmt),
    )
    _emit_result(result, output)


@static_group.command("create")
@option_payload(required=True)
@_option_lists_format
@_option_output
@click.pass_obj
def static_create(
    config: Any,
    payload_path: str,
    fmt: ResponseFormat,
    output: str | None,
) -> None:
    """Create a static list.

    Required payload fields: `name`, `country` (FI, SE, NO, DK, or NL).
    Optional: `business_ids` (array of prefixed business IDs).
    """
    payload = load_payload(payload_path)
    if not isinstance(payload, dict):
        raise click.UsageError("--payload must contain a JSON object for lists static create.")
    result = _run_lists_command(
        config,
        task_name="lists-static-create",
        sync_call=lambda client: client.organization_list_static_create(payload, format=fmt),
        async_call=lambda client: client.organization_list_static_create(payload, format=fmt),
    )
    _emit_result(result, output)


@static_group.command("update")
@click.argument("list_id")
@option_payload(required=True)
@_option_lists_format
@_option_output
@click.pass_obj
def static_update(
    config: Any,
    list_id: str,
    payload_path: str,
    fmt: ResponseFormat,
    output: str | None,
) -> None:
    """Partially update a static list (name, business_ids, permissions, etc.)."""
    payload = load_payload(payload_path)
    if not isinstance(payload, dict):
        raise click.UsageError("--payload must contain a JSON object for lists static update.")
    result = _run_lists_command(
        config,
        task_name="lists-static-update",
        sync_call=lambda client: client.organization_list_static_update(
            list_id, payload, format=fmt
        ),
        async_call=lambda client: client.organization_list_static_update(
            list_id, payload, format=fmt
        ),
    )
    _emit_result(result, output)


@static_group.command("delete")
@click.argument("list_id")
@click.pass_obj
def static_delete(config: Any, list_id: str) -> None:
    """Delete a static list."""
    _run_lists_command(
        config,
        task_name="lists-static-delete",
        sync_call=lambda client: client.organization_list_static_delete(list_id),
        async_call=lambda client: client.organization_list_static_delete(list_id),
    )
    _emit_no_content(f"Deleted static list {list_id}")


@static_group.command("add")
@click.argument("list_id")
@option_payload(required=True)
@click.pass_obj
def static_add(config: Any, list_id: str, payload_path: str) -> None:
    """Add business IDs to a static list.

    `--payload` must be a JSON array of business IDs, e.g. `["FI01234567"]`.
    """
    payload = load_payload(payload_path)
    if not isinstance(payload, list):
        raise click.UsageError(
            "--payload must be a JSON array of business IDs for lists static add."
        )
    _run_lists_command(
        config,
        task_name="lists-static-add",
        sync_call=lambda client: client.organization_list_static_add(list_id, payload),
        async_call=lambda client: client.organization_list_static_add(list_id, payload),
    )
    _emit_no_content(f"Added {len(payload)} business ID(s) to static list {list_id}")


@static_group.command("remove")
@click.argument("list_id")
@option_payload(required=True)
@click.pass_obj
def static_remove(config: Any, list_id: str, payload_path: str) -> None:
    """Remove business IDs from a static list.

    `--payload` must be a JSON array of business IDs.
    """
    payload = load_payload(payload_path)
    if not isinstance(payload, list):
        raise click.UsageError(
            "--payload must be a JSON array of business IDs for lists static remove."
        )
    _run_lists_command(
        config,
        task_name="lists-static-remove",
        sync_call=lambda client: client.organization_list_static_remove(list_id, payload),
        async_call=lambda client: client.organization_list_static_remove(list_id, payload),
    )
    _emit_no_content(f"Removed {len(payload)} business ID(s) from static list {list_id}")


@click.group("dynamic", invoke_without_command=True)
@_option_lists_format
@_option_output
@click.pass_context
def dynamic_group(ctx: click.Context, fmt: ResponseFormat, output: str | None) -> None:
    """Manage dynamic organization lists (VQL query-based membership)."""
    if ctx.invoked_subcommand is not None:
        return
    config = ctx.obj
    result = _run_lists_command(
        config,
        task_name="lists-dynamic",
        sync_call=lambda client: client.organization_lists_dynamic(format=fmt),
        async_call=lambda client: client.organization_lists_dynamic(format=fmt),
    )
    _emit_result(result, output)


@dynamic_group.command("get")
@click.argument("list_id")
@_option_lists_format
@_option_output
@click.pass_obj
def dynamic_get(config: Any, list_id: str, fmt: ResponseFormat, output: str | None) -> None:
    """Retrieve one dynamic list."""
    result = _run_lists_command(
        config,
        task_name="lists-dynamic-get",
        sync_call=lambda client: client.organization_list_dynamic_get(list_id, format=fmt),
        async_call=lambda client: client.organization_list_dynamic_get(list_id, format=fmt),
    )
    _emit_result(result, output)


@dynamic_group.command("create")
@option_payload(required=True)
@_option_lists_format
@_option_output
@click.pass_obj
def dynamic_create(
    config: Any,
    payload_path: str,
    fmt: ResponseFormat,
    output: str | None,
) -> None:
    """Create a dynamic list.

    Required payload fields: `name`, `country`, and `query` (serialized VQL string).
    """
    payload = load_payload(payload_path)
    if not isinstance(payload, dict):
        raise click.UsageError("--payload must contain a JSON object for lists dynamic create.")
    result = _run_lists_command(
        config,
        task_name="lists-dynamic-create",
        sync_call=lambda client: client.organization_list_dynamic_create(payload, format=fmt),
        async_call=lambda client: client.organization_list_dynamic_create(payload, format=fmt),
    )
    _emit_result(result, output)


@dynamic_group.command("update")
@click.argument("list_id")
@option_payload(required=True)
@_option_lists_format
@_option_output
@click.pass_obj
def dynamic_update(
    config: Any,
    list_id: str,
    payload_path: str,
    fmt: ResponseFormat,
    output: str | None,
) -> None:
    """Partially update a dynamic list (name, query, scoring, etc.)."""
    payload = load_payload(payload_path)
    if not isinstance(payload, dict):
        raise click.UsageError("--payload must contain a JSON object for lists dynamic update.")
    result = _run_lists_command(
        config,
        task_name="lists-dynamic-update",
        sync_call=lambda client: client.organization_list_dynamic_update(
            list_id, payload, format=fmt
        ),
        async_call=lambda client: client.organization_list_dynamic_update(
            list_id, payload, format=fmt
        ),
    )
    _emit_result(result, output)


@dynamic_group.command("delete")
@click.argument("list_id")
@click.pass_obj
def dynamic_delete(config: Any, list_id: str) -> None:
    """Delete a dynamic list."""
    _run_lists_command(
        config,
        task_name="lists-dynamic-delete",
        sync_call=lambda client: client.organization_list_dynamic_delete(list_id),
        async_call=lambda client: client.organization_list_dynamic_delete(list_id),
    )
    _emit_no_content(f"Deleted dynamic list {list_id}")


lists_group.add_command(static_group, name="static")
lists_group.add_command(dynamic_group, name="dynamic")
