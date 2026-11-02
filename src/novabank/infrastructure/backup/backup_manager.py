"""Safe Transactional Database Backup Utility using mysqldump and gzip stream compression."""

from __future__ import annotations

import gzip
import hashlib
import os
import shutil
import subprocess
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional, Union

from novabank.infrastructure.config import AppConfig


@dataclass(frozen=True)
class BackupResult:
    """Outcome metadata of a database backup operation."""

    success: bool
    file_path: Optional[Path]
    file_size_bytes: int
    timestamp: datetime
    duration_seconds: float
    checksum_sha256: Optional[str] = None
    error_message: Optional[str] = None


class BackupManager:
    """Manages transactional consistency backups of the NovaBank database."""

    DEFAULT_BACKUP_SUBDIR = "backups"

    def __init__(
        self,
        config: Optional[AppConfig] = None,
        backup_dir: Optional[Union[str, Path]] = None,
        mysqldump_binary: Optional[str] = None,
    ) -> None:
        self.config = config or AppConfig()
        if backup_dir:
            self.backup_dir = Path(backup_dir).resolve()
        else:
            self.backup_dir = Path(self.DEFAULT_BACKUP_SUBDIR).resolve()

        # Locate mysqldump binary
        self.mysqldump_binary = (
            mysqldump_binary
            or shutil.which("mysqldump")
            or shutil.which("mysqldump.exe")
            or "mysqldump"
        )

    def create_backup(
        self,
        target_db: Optional[str] = None,
        output_filename: Optional[str] = None,
        compress: bool = True,
    ) -> BackupResult:
        """Create a safe, transactionally consistent database backup.

        Args:
            target_db: Name of database to dump (defaults to config.db_name).
            output_filename: Custom filename (defaults to timestamped convention).
            compress: Whether to stream compress through gzip into .sql.gz.

        Returns:
            BackupResult with file status, duration, and SHA-256 checksum.
        """
        start_time = time.time()
        now = datetime.now(timezone.utc)
        db_name = target_db or self.config.db_name

        self.backup_dir.mkdir(parents=True, exist_ok=True)

        # Generate standard filename
        ext = ".sql.gz" if compress else ".sql"
        if output_filename:
            clean_name = (
                output_filename if output_filename.endswith(ext) else f"{output_filename}{ext}"
            )
        else:
            ts_str = now.strftime("%Y%m%d_%H%M%S")
            clean_name = f"{db_name}_backup_{ts_str}{ext}"

        dest_file = self.backup_dir / clean_name

        # Construct safe mysqldump argument list
        # Flags:
        # --single-transaction: Guarantees consistent snapshot without table locking
        # --quick: Streams row-by-row rather than loading full tables into memory
        # --routines: Includes stored procedures and functions
        # --triggers: Includes database triggers
        cmd = [
            self.mysqldump_binary,
            f"--host={self.config.db_host}",
            f"--port={self.config.db_port}",
            f"--user={self.config.db_user}",
            "--single-transaction",
            "--quick",
            "--routines",
            "--triggers",
            db_name,
        ]

        # Securely pass password via environment variable (never CLI argument)
        env = os.environ.copy()
        pwd = self.config.resolve_db_password()
        if pwd:
            env["MYSQL_PWD"] = pwd

        try:
            # Execute mysqldump process
            proc = subprocess.Popen(
                cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                env=env,
            )

            hasher = hashlib.sha256()

            if compress:
                with gzip.open(dest_file, "wb", compresslevel=9) as gz_out:
                    assert proc.stdout is not None
                    while True:
                        chunk = proc.stdout.read(65536)
                        if not chunk:
                            break
                        gz_out.write(chunk)
                        hasher.update(chunk)
            else:
                with open(dest_file, "wb") as f_out:
                    assert proc.stdout is not None
                    while True:
                        chunk = proc.stdout.read(65536)
                        if not chunk:
                            break
                        f_out.write(chunk)
                        hasher.update(chunk)

            _, stderr_bytes = proc.communicate()
            duration = time.time() - start_time

            if proc.returncode != 0:
                err_text = stderr_bytes.decode("utf-8", errors="replace")
                if dest_file.exists():
                    dest_file.unlink(missing_ok=True)
                return BackupResult(
                    success=False,
                    file_path=None,
                    file_size_bytes=0,
                    timestamp=now,
                    duration_seconds=duration,
                    error_message=f"mysqldump failed (code {proc.returncode}): {err_text}",
                )

            # Verify file integrity
            file_size = dest_file.stat().st_size
            if file_size == 0:
                dest_file.unlink(missing_ok=True)
                return BackupResult(
                    success=False,
                    file_path=None,
                    file_size_bytes=0,
                    timestamp=now,
                    duration_seconds=duration,
                    error_message="Backup file produced was empty (0 bytes).",
                )

            return BackupResult(
                success=True,
                file_path=dest_file,
                file_size_bytes=file_size,
                timestamp=now,
                duration_seconds=duration,
                checksum_sha256=hasher.hexdigest(),
            )

        except FileNotFoundError:
            duration = time.time() - start_time
            return BackupResult(
                success=False,
                file_path=None,
                file_size_bytes=0,
                timestamp=now,
                duration_seconds=duration,
                error_message=f"mysqldump binary '{self.mysqldump_binary}' not found on system PATH.",
            )
        except Exception as exc:
            duration = time.time() - start_time
            if dest_file.exists():
                dest_file.unlink(missing_ok=True)
            return BackupResult(
                success=False,
                file_path=None,
                file_size_bytes=0,
                timestamp=now,
                duration_seconds=duration,
                error_message=str(exc),
            )

    @classmethod
    def verify_backup_integrity(cls, file_path: Union[str, Path]) -> bool:
        """Validate backup file exists, is valid gzip (if .gz), and contains SQL markers."""
        p = Path(file_path)
        if not p.is_file() or p.stat().st_size < 10:
            return False

        try:
            if p.suffix == ".gz":
                with gzip.open(p, "rb") as gz:
                    header = gz.read(512)
            else:
                with open(p, "rb") as f:
                    header = f.read(512)

            # Must contain standard SQL or dump commentary markers
            return b"MySQL" in header or b"dump" in header or b"CREATE" in header or b"--" in header
        except Exception:
            return False

    def list_backups(self) -> list[dict[str, Union[str, int, datetime]]]:
        """List all available backup archives in backup_dir."""
        if not self.backup_dir.exists():
            return []

        backups = []
        for f in self.backup_dir.iterdir():
            if f.is_file() and (f.name.endswith(".sql") or f.name.endswith(".sql.gz")):
                stat = f.stat()
                backups.append(
                    {
                        "filename": f.name,
                        "path": str(f.resolve()),
                        "size_bytes": stat.st_size,
                        "modified_at": datetime.fromtimestamp(stat.st_mtime, tz=timezone.utc),
                        "is_compressed": f.name.endswith(".gz"),
                    }
                )

        return sorted(backups, key=lambda b: b["modified_at"], reverse=True)
