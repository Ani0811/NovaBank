"""Tests for BackupManager and transactional database backup procedures."""

from __future__ import annotations

import gzip
import io
from pathlib import Path
from unittest.mock import MagicMock, patch

from novabank.infrastructure.backup.backup_manager import BackupManager, BackupResult
from novabank.infrastructure.config import AppConfig


def test_backup_manager_initialization(tmp_path: Path) -> None:
    """Verify BackupManager sets backup directory and mysqldump binary."""
    mgr = BackupManager(backup_dir=tmp_path / "custom_backups", mysqldump_binary="mysqldump_test")
    assert mgr.backup_dir == (tmp_path / "custom_backups").resolve()
    assert mgr.mysqldump_binary == "mysqldump_test"


def test_backup_manager_command_construction(tmp_path: Path) -> None:
    """Verify mysqldump is invoked with single-transaction, quick, routines, and triggers."""
    cfg = AppConfig(
        db_host="db.internal.net",
        db_port=3307,
        db_user="dba_user",
        db_name="test_prod_db",
    )
    mgr = BackupManager(config=cfg, backup_dir=tmp_path)

    captured_cmd: list[str] = []
    captured_env: dict[str, str] = {}

    def mock_popen(cmd, *args, **kwargs):
        nonlocal captured_cmd, captured_env
        captured_cmd = cmd
        captured_env = kwargs.get("env", {})
        proc = MagicMock()
        proc.stdout = io.BytesIO(b"-- MySQL dump 10.13\nCREATE TABLE `accounts` (id INT);\n")
        proc.communicate.return_value = (b"", b"")
        proc.returncode = 0
        return proc

    with patch("subprocess.Popen", side_effect=mock_popen):
        res = mgr.create_backup(compress=True)

    assert res.success is True
    assert "--single-transaction" in captured_cmd
    assert "--quick" in captured_cmd
    assert "--routines" in captured_cmd
    assert "--triggers" in captured_cmd
    assert "--host=db.internal.net" in captured_cmd
    assert "--port=3307" in captured_cmd
    assert "--user=dba_user" in captured_cmd
    assert "test_prod_db" in captured_cmd

    # Ensure password is NOT leaked in CLI args
    assert not any("--password" in arg for arg in captured_cmd)


def test_backup_manager_successful_compressed_dump(tmp_path: Path) -> None:
    """Verify streaming compressed dump produces valid gzip with valid SHA-256."""
    mgr = BackupManager(backup_dir=tmp_path)
    sample_sql = b"-- MySQL dump 8.0\n-- Host: localhost\nCREATE TABLE `accounts` (id INT);\n"

    def mock_popen(*args, **kwargs):
        proc = MagicMock()
        proc.stdout = io.BytesIO(sample_sql)
        proc.communicate.return_value = (b"", b"")
        proc.returncode = 0
        return proc

    with patch("subprocess.Popen", side_effect=mock_popen):
        res: BackupResult = mgr.create_backup(output_filename="novabank_test.sql.gz", compress=True)

    assert res.success is True
    assert res.file_path is not None
    assert res.file_path.exists()
    assert res.checksum_sha256 is not None
    assert res.file_size_bytes > 0

    # Verify gzip contents
    with gzip.open(res.file_path, "rb") as gz:
        decompressed = gz.read()
    assert decompressed == sample_sql

    # Verify integrity helper
    assert BackupManager.verify_backup_integrity(res.file_path) is True


def test_backup_manager_uncompressed_dump(tmp_path: Path) -> None:
    """Verify uncompressed SQL dump creation."""
    mgr = BackupManager(backup_dir=tmp_path)
    sample_sql = b"-- MySQL dump\nINSERT INTO accounts VALUES (1);\n"

    def mock_popen(*args, **kwargs):
        proc = MagicMock()
        proc.stdout = io.BytesIO(sample_sql)
        proc.communicate.return_value = (b"", b"")
        proc.returncode = 0
        return proc

    with patch("subprocess.Popen", side_effect=mock_popen):
        res = mgr.create_backup(output_filename="plain.sql", compress=False)

    assert res.success is True
    assert res.file_path is not None
    assert res.file_path.name == "plain.sql"
    assert res.file_path.read_bytes() == sample_sql
    assert BackupManager.verify_backup_integrity(res.file_path) is True


def test_backup_manager_process_failure_cleans_up(tmp_path: Path) -> None:
    """Verify non-zero returncode deletes incomplete files and returns error message."""
    mgr = BackupManager(backup_dir=tmp_path)

    def mock_popen(*args, **kwargs):
        proc = MagicMock()
        proc.stdout = io.BytesIO(b"partial dump...")
        proc.communicate.return_value = (b"", b"Access denied for user 'root'@'localhost'")
        proc.returncode = 2
        return proc

    with patch("subprocess.Popen", side_effect=mock_popen):
        res = mgr.create_backup(output_filename="failed_backup.sql.gz")

    assert res.success is False
    assert res.file_path is None
    assert "Access denied" in (res.error_message or "")

    # Ensure no partial files left on disk
    assert not (tmp_path / "failed_backup.sql.gz").exists()


def test_backup_manager_binary_missing(tmp_path: Path) -> None:
    """Verify clean error when mysqldump is not on PATH."""
    mgr = BackupManager(backup_dir=tmp_path, mysqldump_binary="non_existent_binary_xyz")

    with patch("subprocess.Popen", side_effect=FileNotFoundError("No such file")):
        res = mgr.create_backup()

    assert res.success is False
    assert "not found on system PATH" in (res.error_message or "")


def test_backup_manager_list_backups(tmp_path: Path) -> None:
    """Verify listing existing backups in backup directory."""
    mgr = BackupManager(backup_dir=tmp_path)

    # Create dummy backup files
    (tmp_path / "backup_20260101.sql").write_text("-- MySQL dump 1", encoding="utf-8")
    (tmp_path / "backup_20260102.sql.gz").write_bytes(gzip.compress(b"-- MySQL dump 2"))
    (tmp_path / "other_file.txt").write_text("ignore", encoding="utf-8")

    backups = mgr.list_backups()
    assert len(backups) == 2
    filenames = [b["filename"] for b in backups]
    assert "backup_20260101.sql" in filenames
    assert "backup_20260102.sql.gz" in filenames
    assert "other_file.txt" not in filenames
