"""Baseline workspace sanity and architectural boundary tests."""
import os
from pathlib import Path
import pytest
import novabank


def test_package_metadata():
    """Verify package import and version metadata."""
    assert novabank.__version__ == "0.1.0"


def test_clean_architecture_directories():
    """Verify that all architectural layer packages exist."""
    package_root = Path(novabank.__file__).parent
    assert (package_root / "domain").is_dir()
    assert (package_root / "application").is_dir()
    assert (package_root / "infrastructure").is_dir()
    assert (package_root / "ui").is_dir()


def test_legacy_source_isolated_and_intact():
    """Verify legacy source directory is preserved and completely untouched."""
    legacy_dir = Path(r"C:\Github\BMS_CONSOLE-main\BMS_CONSOLE-main")
    assert legacy_dir.is_dir(), "Legacy directory must exist"
    
    bms_script = legacy_dir / "BMS.Py310.py"
    tables_script = legacy_dir / "BMS_Tables.Py.310.py"
    
    assert bms_script.is_file(), "Legacy BMS.Py310.py must be preserved"
    assert tables_script.is_file(), "Legacy BMS_Tables.Py.310.py must be preserved"
    
    # Assert legacy files are non-empty and retain their expected byte lengths
    assert bms_script.stat().st_size == 42283
    assert tables_script.stat().st_size == 8927


def test_no_plaintext_csv_credentials_in_repo():
    """Verify no plaintext CSV credential files exist in the repository."""
    repo_root = Path(novabank.__file__).parent.parent.parent
    csv_files = list(repo_root.glob("**/*.csv"))
    # Only test fixtures are allowed to have CSVs
    leaked_csvs = [f for f in csv_files if "tests" not in str(f)]
    assert len(leaked_csvs) == 0, f"Found prohibited plaintext CSV files: {leaked_csvs}"
