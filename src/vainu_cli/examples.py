"""Bundled example API payloads."""

from __future__ import annotations

from pathlib import Path

_PKG_DIR = Path(__file__).resolve().parent


def examples_dir() -> Path:
    """Return the directory containing bundled example payload JSON files."""
    bundled = _PKG_DIR / "example_payloads"
    if bundled.is_dir():
        return bundled
    checkout = _PKG_DIR.parent.parent / "example_payloads"
    if checkout.is_dir():
        return checkout
    raise FileNotFoundError(
        "Example payloads not found. Reinstall vainu-cli or run from a git checkout."
    )


def list_examples(*, category: str | None = None) -> list[Path]:
    """Return example payload paths, optionally filtered by category subdirectory."""
    root = examples_dir()
    paths: list[Path] = []
    for sub in sorted(root.iterdir()):
        if not sub.is_dir():
            continue
        if category is not None and sub.name != category:
            continue
        paths.extend(sorted(sub.glob("*.json")))
    return paths


def resolve_example(name: str) -> Path:
    """Resolve a payload by relative path, filename, or partial filename match."""
    root = examples_dir()
    direct = Path(name)
    if direct.is_file():
        return direct.resolve()

    if "/" in name or "\\" in name:
        nested = root / name
        if nested.is_file():
            return nested.resolve()

    exact = list(root.rglob(name))
    if len(exact) == 1:
        return exact[0].resolve()

    partial = [p for p in root.rglob("*.json") if name in p.name]
    if len(partial) == 1:
        return partial[0].resolve()
    if len(partial) > 1:
        rel = [str(p.relative_to(root)) for p in partial]
        raise FileNotFoundError(f"Ambiguous example {name!r}. Matches: {', '.join(rel)}")
    raise FileNotFoundError(f"Example payload not found: {name!r}. Run `vainu examples list`.")
