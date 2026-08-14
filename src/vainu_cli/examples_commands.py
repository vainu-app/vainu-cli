"""`vainu examples list` and `vainu examples path` commands."""

from __future__ import annotations

import click

from vainu_cli.examples import examples_dir, list_examples, resolve_example


@click.group("examples")
def examples_group() -> None:
    """List and resolve bundled example API payloads."""


@examples_group.command("list")
@click.option(
    "--category",
    type=click.Choice(["organizations_api", "signals_api"]),
    default=None,
    help="Only list examples from this category.",
)
def examples_list_cmd(category: str | None) -> None:
    """Print bundled example payload paths relative to the examples root."""
    root = examples_dir()
    for path in list_examples(category=category):
        click.echo(path.relative_to(root))


@examples_group.command("path")
@click.argument("name")
def examples_path_cmd(name: str) -> None:
    """Print the absolute path to a bundled example payload."""
    try:
        click.echo(resolve_example(name))
    except FileNotFoundError as exc:
        raise click.ClickException(str(exc)) from exc
