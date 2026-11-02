"""Tests for RestoreManager and safeguarded database restoration procedures."""

from __future__ import annotations

import gzip
import io
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from novabank.infrastructure.backup.restore_manager import (
    RestoreManager,
    RestorePreflightReport,
    RestoreResult,
)
from novabank.infrastructure.config import AppConfig


@pytest.fixture
def sample_backup_gz(tmp_path: Path) -> Path:
    """Create a temporary valid compressed backup file with schema markers."""
    dump_text = (
        "-- MySQL dump 10.13  Distrib 8.0.32\n"
        "-- Host: localhost    Database: novabank_db\n"
        "-- ------------------------------------------------------\n"
        "CREATE TABLE `accounts` (\n"
        "  `account_number` varchar(12) NOT NULL,\n"
        "  `holder_name` varchar(100) NOT NULL\n"
        ");\n"
        "CREATE TABLE `transactions` (\n"
        "  `transaction_id` bigint NOT NULL\n"
        ");\n"
        "CREATE TABLE `audit_events` (\n"
        "  `event_id` bigint NOT NULL\n"
        ");\n"
    )
    p = tmp_path / "novabank_backup_valid.sql.gz"
    p.write_bytes(gzip.compress(dump_text.encode("utf-8")))
    return p


def test_confirmation_validation() -> None:
    """Verify strict confirmation requires exact matching database name."""
    assert RestoreManager.validate_confirmation("novabank_db", "novabank_db") is True
    assert RestoreManager.validate_confirmation("novabank_db", " novabank_db ") is True
    assert RestoreManager.validate_confirmation("novabank_db", "NOVABANK_DB") is False
    assert RestoreManager.validate_confirmation("novabank_db", "other_db") is False
    assert RestoreManager.validate_confirmation("novabank_db", "") is False


def test_inspect_backup_file_valid_compressed(sample_backup_gz: Path) -> None:
    """Verify preflight inspection accurately parses compressed backup header and table markers."""
    mgr = RestoreManager()
    report: RestorePreflightReport = mgr.inspect_backup_file(sample_backup_gz)

    assert report.is_valid is True
    assert report.is_compressed is True
    assert report.file_size_bytes > 0
    assert "accounts" in report.detected_schema_markers
    assert "transactions" in report.detected_schema_markers
    assert "audit_events" in report.detected_schema_markers
    assert "MySQL dump" in report.header_snippet


def test_inspect_backup_file_missing(tmp_path: Path) -> None:
    """Verify preflight report for non-existent file."""
    mgr = RestoreManager()
    missing_file = tmp_path / "does_not_exist.sql.gz"
    report = mgr.inspect_backup_file(missing_file)

    assert report.is_valid is False
    assert "does not exist" in (report.error_message or "")


def test_inspect_backup_file_corrupted(tmp_path: Path) -> None:
    """Verify preflight report for corrupt gzip file."""
    corrupt_file = tmp_path / "corrupt.sql.gz"
    corrupt_file.write_bytes(b"NOT A GZIP FILE RAW BYTES")

    mgr = RestoreManager()
    report = mgr.inspect_backup_file(corrupt_file)

    assert report.is_valid is False
    assert "Corrupt or unreadable" in (report.error_message or "")


def test_restore_database_confirmation_mismatch_raises(sample_backup_gz: Path) -> None:
    """Verify attempting restore without exact confirmation raises ValueError."""
    mgr = RestoreManager()

    with pytest.raises(ValueError, match="Confirmation failed"):
        mgr.restore_database(
            backup_file=sample_backup_gz,
            target_database="novabank_db",
            confirmation_input="wrong_confirmation_name",
        )


def test_restore_database_dry_run(sample_backup_gz: Path) -> None:
    """Verify dry_run=True performs preflight checks and succeeds without executing mysql."""
    mgr = RestoreManager()

    res: RestoreResult = mgr.restore_database(
        backup_file=sample_backup_gz,
        target_database="novabank_db",
        confirmation_input="novabank_db",
        dry_run=True,
    )

    assert res.success is True
    assert res.database_name == "novabank_db"
    assert "Dry run successful" in res.message


def test_restore_database_successful_execution(sample_backup_gz: Path) -> None:
    """Verify restore streams decompressed dump to mysql stdin with secure env credentials."""
    cfg = AppConfig(
        db_host="127.0.0.1",
        db_port=3306,
        db_user="admin",
        db_name="novabank_db",
    )
    mgr = RestoreManager(config=cfg)

    captured_cmd: list[str] = []
    captured_data = bytearray()

    def mock_popen(cmd, *args, **kwargs):
        nonlocal captured_cmd
        captured_cmd = cmd
        proc = MagicMock()
        mock_stdin = MagicMock()
        mock_stdin.write.side_effect = lambda chunk: captured_data.extend(chunk)
        proc.stdin = mock_stdin
        proc.communicate.return_value = (b"", b"")
        proc.returncode = 0
        return proc

    with patch("subprocess.Popen", side_effect=mock_popen):
        res: RestoreResult = mgr.restore_database(
            backup_file=sample_backup_gz,
            target_database="novabank_db",
            confirmation_input="novabank_db",
            dry_run=False,
        )

    assert res.success is True
    assert "--host=127.0.0.1" in captured_cmd
    assert "--port=3306" in captured_cmd
    assert "--user=admin" in captured_cmd
    assert "novabank_db" in captured_cmd
    assert "Successfully restored" in res.message

    # Verify content was streamed to stdin
    assert b"CREATE TABLE `accounts`" in captured_data


def test_restore_database_client_failure(sample_backup_gz: Path) -> None:
    """Verify mysql client non-zero exit code returns failed RestoreResult."""
    mgr = RestoreManager()

    def mock_popen(*args, **kwargs):
        proc = MagicMock()
        proc.stdin = io.BytesIO()
        proc.communicate.return_value = (b"", b"ERROR 1049 (42000): Unknown database 'novabank_db'")
        proc.returncode = 1
        return proc

    with patch("subprocess.Popen", side_effect=mock_popen):
        res: RestoreResult = mgr.restore_database(
            backup_file=sample_backup_gz,
            target_database="novabank_db",
            confirmation_input="novabank_db",
            dry_run=False,
        )

    assert res.success is False
    assert "Unknown database" in (res.error_message or "")
