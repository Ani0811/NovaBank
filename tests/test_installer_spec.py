"""Unit tests validating Inno Setup installer script structure and configuration."""

from __future__ import annotations

from pathlib import Path
import pytest

PROJECT_ROOT = Path(__file__).parent.parent.resolve()
ISS_FILE = PROJECT_ROOT / "packaging" / "installer.iss"


def test_installer_iss_exists() -> None:
    """Verify Inno Setup script exists in packaging/ directory."""
    assert ISS_FILE.exists(), f"Installer script not found at {ISS_FILE}"
    assert ISS_FILE.stat().st_size > 100, "Installer script is empty"


def test_installer_iss_mandatory_sections() -> None:
    """Verify all mandatory Inno Setup sections are defined."""
    content = ISS_FILE.read_text(encoding="utf-8")
    mandatory_sections = [
        "[Setup]",
        "[Languages]",
        "[Tasks]",
        "[Files]",
        "[Icons]",
        "[Run]",
        "[UninstallDelete]",
    ]
    for section in mandatory_sections:
        assert section in content, f"Missing section '{section}' in installer.iss"


def test_installer_setup_directives() -> None:
    """Verify correct AppName, 64-bit architecture, destination folder, and uninstaller icon."""
    content = ISS_FILE.read_text(encoding="utf-8")

    assert "#define MyAppName \"NovaBank\"" in content
    assert "#define MyAppExeName \"NovaBank.exe\"" in content
    assert "DefaultDirName={autopf}\\{#MyAppName}" in content
    assert "ArchitecturesInstallIn64BitMode=x64compatible" in content
    assert "UninstallDisplayIcon={app}\\{#MyAppExeName}" in content
    assert "OutputBaseFilename=NovaBank_Setup_v{#MyAppVersion}" in content


def test_installer_prerequisites_validator() -> None:
    """Verify build_installer validation logic passes for existing specification."""
    import sys
    sys.path.insert(0, str(PROJECT_ROOT / "packaging"))
    from build_installer import validate_installer_prerequisites

    assert validate_installer_prerequisites() is True

