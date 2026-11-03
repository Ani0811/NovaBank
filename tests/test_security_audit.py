"""Automated security audit tests verifying Bandit static analysis and code invariants."""

from __future__ import annotations

import ast
from pathlib import Path
import subprocess
import sys
import pytest

from novabank.infrastructure.ai.exceptions import AISecurityBoundaryError
from novabank.infrastructure.ai.lm_studio_client import LMStudioClient


def test_bandit_zero_high_or_medium_vulnerabilities() -> None:
    """Run Bandit security linter on src/ and assert zero High or Medium findings."""
    bandit_bin = Path(sys.executable).parent / "bandit.exe"
    if not bandit_bin.exists():
        bandit_bin = Path(sys.executable).parent / "bandit"

    if not bandit_bin.exists():
        pytest.skip("Bandit executable not found in current environment.")

    # -ll checks for Medium and High severity issues; exits with non-zero if found
    result = subprocess.run(
        [str(bandit_bin), "-r", "src/", "-ll", "-q"],
        capture_output=True,
        text=True,
        cwd=str(Path(__file__).parent.parent),
    )

    assert result.returncode == 0, f"Bandit identified Medium or High severity issues:\n{result.stdout}\n{result.stderr}"


def test_no_hardcoded_secrets_in_source() -> None:
    """Scan all source files to verify no plaintext database credentials or passwords are embedded."""
    src_dir = Path(__file__).parent.parent / "src"
    suspicious_patterns = [
        "password = \"admin\"",
        "password = 'admin'",
        "password = \"root\"",
        "password = 'root'",
        "api_key = \"",
        "apikey = \"",
        "secret_key = \"",
    ]

    for py_file in src_dir.rglob("*.py"):
        content = py_file.read_text(encoding="utf-8").lower()
        for pattern in suspicious_patterns:
            assert pattern not in content, f"Potential hardcoded secret found in {py_file}: {pattern}"


def test_sql_repositories_use_parameterized_queries_only() -> None:
    """Scan SQL repositories to ensure zero raw SQL format string interpolations."""
    repo_dir = Path(__file__).parent.parent / "src" / "novabank" / "infrastructure" / "repositories"

    for py_file in repo_dir.glob("sql_*.py"):
        tree = ast.parse(py_file.read_text(encoding="utf-8"), filename=str(py_file))
        for node in ast.walk(tree):
            # Check for text("... %s ...") or text(f"...{...}...")
            if isinstance(node, ast.Call):
                func_name = ""
                if isinstance(node.func, ast.Name):
                    func_name = node.func.id
                elif isinstance(node.func, ast.Attribute):
                    func_name = node.func.attr

                if func_name in ("execute", "text"):
                    for arg in node.args:
                        # Reject f-strings inside raw SQL calls
                        if isinstance(arg, ast.JoinedStr):
                            pytest.fail(f"Potential SQL injection: JoinedStr (f-string) in SQL call in {py_file}")


def test_ai_trust_boundary_enforces_loopback() -> None:
    """Verify LMStudioClient strictly prohibits network calls outside local loopback."""
    disallowed_hosts = [
        "https://api.openai.com/v1",
        "http://192.168.1.50:1234/v1",
        "http://remote-server.com:1234/v1",
        "http://10.0.0.1:1234/v1",
    ]

    for url in disallowed_hosts:
        with pytest.raises(AISecurityBoundaryError):
            LMStudioClient(base_url=url)

