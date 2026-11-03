"""Smoke test verifying PyInstaller specification and compiled binary execution."""

from __future__ import annotations

from pathlib import Path
import subprocess
import sys
import pytest

PROJECT_ROOT = Path(__file__).parent.parent.resolve()
SPEC_FILE = PROJECT_ROOT / "packaging" / "novabank.spec"
EXE_PATH = PROJECT_ROOT / "dist" / "NovaBank" / "NovaBank.exe"


def test_spec_file_exists() -> None:
    """Verify PyInstaller specification file exists and references correct entrypoint."""
    assert SPEC_FILE.exists(), "packaging/novabank.spec must exist"
    content = SPEC_FILE.read_text(encoding="utf-8")
    assert "main.py" in content
    assert "styles.qss" in content


def test_binary_executable_smoke() -> None:
    """Verify compiled NovaBank.exe exists and executes --version cleanly."""
    if not EXE_PATH.exists():
        pytest.skip("dist/NovaBank/NovaBank.exe not built yet.")

    res = subprocess.run(
        [str(EXE_PATH), "--version"],
        capture_output=True,
        text=True,
        timeout=10,
    )
    assert res.returncode == 0, f"NovaBank.exe --version failed with code {res.returncode}: {res.stderr}"
    assert "NovaBank v1.0.0" in res.stdout
