"""`vainu fields` commands for organization field metadata."""

from __future__ import annotations

import asyncio
import json
from collections import Counter
from collections.abc import Callable, Iterable
from typing import Any, Literal, TypeVar

import click

ViewFormat = Literal["json", "table", "summary"]

F = TypeVar("F", bound=Callable[..., Any])


def _option_view(func: F) -> F:
    return click.option(
        "--view",
        type=click.Choice(["json", "table", "summary"]),
        default="table",
        show_default=True,
        help="How to present field metadata (json returns the raw API response).",
    )(func)


def _option_output(func: F) -> F:
    return click.option(
        "--output",
        default=None,
        type=click.Path(),
        help="Write response to file instead of stdout.",
    )(func)


def _field_path(field: dict[str, Any]) -> str:
    api = field.get("api") or {}
    v3 = api.get("v3") if isinstance(api, dict) else None
    if isinstance(v3, dict):
        return str(v3.get("path") or "")
    return ""


def _field_name(field: dict[str, Any], *, language: str = "en") -> str:
    names = field.get("names") or {}
    translations = names.get("translations") if isinstance(names, dict) else None
    if isinstance(translations, dict):
        return str(translations.get(language) or translations.get("en") or _field_path(field))
    return _field_path(field)


def _application_availability(field: dict[str, Any]) -> set[str]:
    apps = field.get("application_availability")
    if not isinstance(apps, list):
        return set()
    return {str(item) for item in apps}


def _is_filterable(field: dict[str, Any]) -> bool:
    apps = _application_availability(field)
    return "filter" in apps or "search" in apps


def _is_output(field: dict[str, Any]) -> bool:
    apps = _application_availability(field)
    return "export" in apps or "profile" in apps


def _requires_permission(field: dict[str, Any]) -> list[str]:
    perms = field.get("requires_permission")
    if not isinstance(perms, list):
        return []
    return [str(item) for item in perms if item]


def _field_type(field: dict[str, Any]) -> str:
    meta = field.get("meta_data") or {}
    if isinstance(meta, dict) and meta.get("type"):
        return str(meta["type"])
    return ""


def filter_organization_fields(
    fields: list[dict[str, Any]],
    *,
    category: str | None = None,
    database: str | None = None,
    search: str | None = None,
    filterable: bool = False,
    returnable: bool = False,
    permission_gated: bool = False,
) -> list[dict[str, Any]]:
    """Apply CLI filters to the organizations_fields payload."""
    result = fields
    if category:
        result = [field for field in result if field.get("main_category") == category]
    if database:
        result = [
            field
            for field in result
            if database in (field.get("databases") or [])
            or database in (field.get("countries") or [])
        ]
    if filterable:
        result = [field for field in result if _is_filterable(field)]
    if returnable:
        result = [field for field in result if _is_output(field)]
    if permission_gated:
        result = [field for field in result if _requires_permission(field)]
    if search:
        needle = search.casefold()
        result = [
            field
            for field in result
            if needle in _field_path(field).casefold()
            or needle in _field_name(field).casefold()
            or needle in str(field.get("description") or "").casefold()
        ]
    return result


def format_fields_table(fields: Iterable[dict[str, Any]]) -> str:
    """Render a compact, grep-friendly field catalog."""
    headers = ("path", "name", "filterable", "output", "permission", "type")
    rows: list[tuple[str, ...]] = []
    for field in fields:
        perms = _requires_permission(field)
        rows.append(
            (
                _field_path(field),
                _field_name(field),
                "yes" if _is_filterable(field) else "no",
                "yes" if _is_output(field) else "no",
                ",".join(perms) if perms else "",
                _field_type(field),
            )
        )
    widths = [len(header) for header in headers]
    for row in rows:
        widths = [max(width, len(value)) for width, value in zip(widths, row, strict=True)]

    def _format_row(values: tuple[str, ...]) -> str:
        return "  ".join(value.ljust(width) for value, width in zip(values, widths, strict=True))

    lines = [_format_row(headers), _format_row(tuple("-" * width for width in widths))]
    lines.extend(_format_row(row) for row in rows)
    return "\n".join(lines)


def format_fields_summary(fields: Iterable[dict[str, Any]]) -> str:
    """Summarize field counts, availability, and permission gates."""
    items = list(fields)
    categories = Counter(str(field.get("main_category") or "unknown") for field in items)
    filterable_count = sum(1 for field in items if _is_filterable(field))
    output_count = sum(1 for field in items if _is_output(field))
    both_count = sum(1 for field in items if _is_filterable(field) and _is_output(field))
    permission_gated = [field for field in items if _requires_permission(field)]
    permission_names = Counter(
        perm for field in permission_gated for perm in _requires_permission(field)
    )

    lines = [
        f"Total fields: {len(items)}",
        f"Filterable (filter/search): {filterable_count}",
        f"Output (export/profile): {output_count}",
        f"Both filterable and output: {both_count}",
        "",
        "By main_category:",
    ]
    for category, count in sorted(categories.items()):
        lines.append(f"  {category}: {count}")

    lines.extend(["", "Permission-gated fields:"])
    if not permission_gated:
        lines.append("  (none)")
    else:
        lines.append(f"  count: {len(permission_gated)}")
        for permission, count in sorted(permission_names.items()):
            lines.append(f"  {permission}: {count} fields")
        lines.append("")
        lines.append("  Examples:")
        for field in permission_gated[:8]:
            lines.append(f"    {_field_path(field)} ({', '.join(_requires_permission(field))})")

    return "\n".join(lines)


def _write_view_output(text: str, output: str | None) -> None:
    if output:
        with open(output, "w", encoding="utf-8") as handle:
            handle.write(text)
            if not text.endswith("\n"):
                handle.write("\n")
        click.echo(f"Wrote {output}", err=True)
    else:
        click.echo(text)


def _run_fields_command(
    config: Any,
    *,
    task_name: str,
    sync_call: Callable[[Any], list[dict[str, Any]]],
    async_call: Callable[[Any], Any],
) -> list[dict[str, Any]]:
    from vainu_cli.cli import _make_async_client, _make_sync_client, _timed_task

    @_timed_task(task_name)
    def _run() -> list[dict[str, Any]]:
        if config.async_mode:

            async def _async_run() -> list[dict[str, Any]]:
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


@click.group("fields")
def fields_group() -> None:
    """Inspect organization field metadata (filterable vs output fields)."""


@fields_group.command("organizations")
@_option_view
@_option_output
@click.option(
    "--api-version",
    default="v3",
    show_default=True,
    help="API version query parameter passed to organizations_fields.",
)
@click.option(
    "--category",
    default=None,
    help="Only show fields in this main_category (e.g. basic, contacts, financial_data).",
)
@click.option(
    "--database",
    default=None,
    help="Only show fields available for this database/country code (FI, SE, NO, DK, NL).",
)
@click.option(
    "--search",
    default=None,
    help="Case-insensitive substring match against path, English name, or description.",
)
@click.option(
    "--filterable",
    is_flag=True,
    help="Only fields usable in VQL filters (application_availability includes filter/search).",
)
@click.option(
    "--returnable",
    is_flag=True,
    help="Only fields usable in the fields output list (export/profile availability).",
)
@click.option(
    "--permission-gated",
    is_flag=True,
    help="Only fields that require an extra account permission to access.",
)
@click.pass_obj
def fields_organizations(
    config: Any,
    view: ViewFormat,
    output: str | None,
    api_version: str,
    category: str | None,
    database: str | None,
    search: str | None,
    filterable: bool,
    returnable: bool,
    permission_gated: bool,
) -> None:
    """List organization data fields and whether each is filterable or returnable.

    Fetches GET /v3/organizations_fields/. The response is field metadata (names,
    types, allowed operators) — not company records. Some fields are marked
    requires_permission (for example contact email/phone) and remain inaccessible
    until your Vainu account is entitled to them.
    """
    fields = _run_fields_command(
        config,
        task_name="fields-organizations",
        sync_call=lambda client: client.organization_fields(api_versions=api_version),
        async_call=lambda client: client.organization_fields(api_versions=api_version),
    )
    if not isinstance(fields, list):
        raise click.ClickException("Expected a JSON array from organizations_fields.")

    filtered = filter_organization_fields(
        fields,
        category=category,
        database=database,
        search=search,
        filterable=filterable,
        returnable=returnable,
        permission_gated=permission_gated,
    )

    if view == "json":
        text = json.dumps(filtered, indent=2, ensure_ascii=False)
    elif view == "summary":
        text = format_fields_summary(filtered)
    else:
        text = format_fields_table(filtered)

    _write_view_output(text, output)
