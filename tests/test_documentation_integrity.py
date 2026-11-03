"""Unit test verifying documentation integrity and required files."""

from __future__ import annotations

from pathlib import Path

PROJECT_ROOT = Path(__file__).parent.parent.resolve()


def test_core_documentation_files_exist() -> None:
    """Verify all required project documentation files exist and have substantial content."""
    required_docs = [
        PROJECT_ROOT / "README.md",
        PROJECT_ROOT / "docs" / "DEVELOPER_GUIDE.md",
        PROJECT_ROOT / "docs" / "USER_MANUAL.md",
        PROJECT_ROOT / "docs" / "MIGRATION_GUIDE.md",
        PROJECT_ROOT / "TASKS.md",
        PROJECT_ROOT / "ARCHITECTURE.md",
        PROJECT_ROOT / "REQUIREMENTS.md",
    ]

    for doc in required_docs:
        assert doc.exists(), f"Required documentation file missing: {doc}"
        assert doc.stat().st_size > 500, f"Documentation file {doc} is too short ({doc.stat().st_size} bytes)"


def test_readme_links_and_sections() -> None:
    """Verify README.md contains standard architecture diagrams and guides."""
    readme = (PROJECT_ROOT / "README.md").read_text(encoding="utf-8")

    assert "# NovaBank Enterprise Banking System" in readme
    assert "System Architecture" in readme
    assert "DEVELOPER_GUIDE.md" in readme
    assert "USER_MANUAL.md" in readme
    assert "MIGRATION_GUIDE.md" in readme
    assert "Quick Start Guide" in readme
