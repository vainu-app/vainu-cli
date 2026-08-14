"""POSIX /bin/sh compatibility for scripts/install.sh.

Docs install with `curl … | sh`. On Debian/Ubuntu, sh is dash, which rejects
bash-only options such as `set -o pipefail`.
"""

from __future__ import annotations

import os
import stat
import subprocess
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
INSTALL_SH = REPO_ROOT / "scripts" / "install.sh"


def _run_piped_to_sh(
    *args: str, env: dict[str, str] | None = None
) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["sh", "-s", "--", *args],
        input=INSTALL_SH.read_text(encoding="utf-8"),
        capture_output=True,
        text=True,
        env=env,
        check=False,
    )


def _uv_stub_env(tmp_path: Path) -> dict[str, str]:
    # install.sh prepends "$HOME/.local/bin"; put the stub there so it stays first.
    local_bin = tmp_path / "home" / ".local" / "bin"
    local_bin.mkdir(parents=True)
    uv = local_bin / "uv"
    uv.write_text('#!/bin/sh\necho uv-stub "$@"\n', encoding="utf-8")
    uv.chmod(uv.stat().st_mode | stat.S_IEXEC)
    return {
        **os.environ,
        "HOME": str(tmp_path / "home"),
        "PATH": f"{local_bin}{os.pathsep}/usr/bin{os.pathsep}/bin",
    }


class TestInstallSh:
    def test_piped_to_posix_sh_help(self) -> None:
        result = _run_piped_to_sh("--help")
        assert result.returncode == 0, result.stderr
        assert "Usage:" in result.stdout

    def test_piped_to_posix_sh_installs_from_pypi_when_uv_present(self, tmp_path: Path) -> None:
        result = _run_piped_to_sh(env=_uv_stub_env(tmp_path))
        assert result.returncode == 0, result.stderr
        assert "uv-stub tool install vainu-cli" in result.stdout
        assert "Installing vainu-cli from PyPI" in result.stdout

    def test_local_flag_under_posix_sh(self, tmp_path: Path) -> None:
        result = subprocess.run(
            ["sh", str(INSTALL_SH), "--local"],
            capture_output=True,
            text=True,
            env=_uv_stub_env(tmp_path),
            check=False,
        )
        assert result.returncode == 0, result.stderr
        assert f"uv-stub tool install --editable {REPO_ROOT}" in result.stdout
