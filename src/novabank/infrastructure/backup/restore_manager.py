"""Safe Database Restore Wizard and Manager with safeguards against accidental data loss."""

from __future__ import annotations

import gzip
import os
import shutil
import subprocess
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Optional, Union

from novabank.infrastructure.config import AppConfig


@dataclass(frozen=True)
class RestorePreflightReport:
    """Pre-execution inspection of a backup file."""

    is_valid: bool
    file_path: Path
    file_size_bytes: int
    is_compressed: bool
    detected_schema_markers: tuple[str, ...]
    header_snippet: str
    error_message: Optional[str] = None


@dataclass(frozen=True)
class RestoreResult:
    """Outcome of a database restore operation."""

    success: bool
    database_name: str
    duration_seconds: float
    message: str
    error_message: Optional[str] = None


class RestoreManager:
    """Safeguarded manager for inspecting and restoring database backups."""

    KNOWN_TABLE_MARKERS = ("accounts", "transactions", "audit_events", "alembic_version")

    def __init__(
        self,
        config: Optional[AppConfig] = None,
        mysql_binary: Optional[str] = None,
    ) -> None:
        self.config = config or AppConfig()
        self.mysql_binary = (
            mysql_binary or shutil.which("mysql") or shutil.which("mysql.exe") or "mysql"
        )

    def inspect_backup_file(self, file_path: Union[str, Path]) -> RestorePreflightReport:
        """Inspect a backup file's headers and table definitions without modifying the database."""
        path = Path(file_path).resolve()
        if not path.is_file():
            return RestorePreflightReport(
                is_valid=False,
                file_path=path,
                file_size_bytes=0,
                is_compressed=False,
                detected_schema_markers=(),
                header_snippet="",
                error_message=f"Backup file does not exist: {path}",
            )

        file_size = path.stat().st_size
        is_gz = path.name.endswith(".gz")

        try:
            detected_markers: list[str] = []
            if is_gz:
                with gzip.open(path, "rt", encoding="utf-8", errors="replace") as gz:
                    header_lines = [gz.readline() for _ in range(50)]
                    # Read sample for table markers
                    sample_content = "".join(header_lines) + gz.read(65536)
            else:
                with open(path, "r", encoding="utf-8", errors="replace") as f:
                    header_lines = [f.readline() for _ in range(50)]
                    sample_content = "".join(header_lines) + f.read(65536)

            for marker in self.KNOWN_TABLE_MARKERS:
                if f"`{marker}`" in sample_content or f" {marker} " in sample_content:
                    detected_markers.append(marker)

            header_snippet = "".join(header_lines[:15]).strip()

            return RestorePreflightReport(
                is_valid=True,
                file_path=path,
                file_size_bytes=file_size,
                is_compressed=is_gz,
                detected_schema_markers=tuple(detected_markers),
                header_snippet=header_snippet,
            )
        except Exception as exc:
            return RestorePreflightReport(
                is_valid=False,
                file_path=path,
                file_size_bytes=file_size,
                is_compressed=is_gz,
                detected_schema_markers=(),
                header_snippet="",
                error_message=f"Corrupt or unreadable backup file: {exc}",
            )

    @classmethod
    def validate_confirmation(
        cls,
        expected_db_name: str,
        user_confirmation_input: str,
    ) -> bool:
        """Enforce exact case-sensitive matching of the database name before proceeding."""
        if not expected_db_name or not user_confirmation_input:
            return False
        return expected_db_name.strip() == user_confirmation_input.strip()

    def restore_database(
        self,
        backup_file: Union[str, Path],
        target_database: str,
        confirmation_input: str,
        *,
        dry_run: bool = False,
    ) -> RestoreResult:
        """Safely restore database from a verified backup archive.

        Args:
            backup_file: Path to .sql or .sql.gz backup file.
            target_database: The name of the target database schema.
            confirmation_input: Explicit typed confirmation matching target_database.
            dry_run: If True, executes preflight checks without calling mysql client.

        Raises:
            ValueError: If confirmation does not match target database name.
        """
        start_time = time.time()

        # Safeguard 1: Strict Confirmation Validation
        if not self.validate_confirmation(target_database, confirmation_input):
            raise ValueError(
                f"Confirmation failed: Typed confirmation '{confirmation_input}' does not "
                f"match target database '{target_database}'. Operation aborted."
            )

        # Safeguard 2: Preflight Inspection
        preflight = self.inspect_backup_file(backup_file)
        if not preflight.is_valid:
            duration = time.time() - start_time
            return RestoreResult(
                success=False,
                database_name=target_database,
                duration_seconds=duration,
                message="Preflight check failed.",
                error_message=preflight.error_message,
            )

        if dry_run:
            duration = time.time() - start_time
            return RestoreResult(
                success=True,
                database_name=target_database,
                duration_seconds=duration,
                message=f"Dry run successful. Validated backup with schema markers: {list(preflight.detected_schema_markers)}",
            )

        # Construct safe mysql client command
        cmd = [
            self.mysql_binary,
            f"--host={self.config.db_host}",
            f"--port={self.config.db_port}",
            f"--user={self.config.db_user}",
            target_database,
        ]

        env = os.environ.copy()
        pwd = self.config.resolve_db_password()
        if pwd:
            env["MYSQL_PWD"] = pwd

        try:
            proc = subprocess.Popen(
                cmd,
                stdin=subprocess.PIPE,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                env=env,
            )

            # Stream backup file into mysql stdin
            if preflight.is_compressed:
                with gzip.open(preflight.file_path, "rb") as gz_in:
                    assert proc.stdin is not None
                    while True:
                        chunk = gz_in.read(65536)
                        if not chunk:
                            break
                        proc.stdin.write(chunk)
            else:
                with open(preflight.file_path, "rb") as f_in:
                    assert proc.stdin is not None
                    while True:
                        chunk = f_in.read(65536)
                        if not chunk:
                            break
                        proc.stdin.write(chunk)

            proc.stdin.close()
            _, stderr_bytes = proc.communicate()
            duration = time.time() - start_time

            if proc.returncode != 0:
                err_text = stderr_bytes.decode("utf-8", errors="replace")
                return RestoreResult(
                    success=False,
                    database_name=target_database,
                    duration_seconds=duration,
                    message="mysql client execution failed.",
                    error_message=f"Restore failed with exit code {proc.returncode}: {err_text}",
                )

            return RestoreResult(
                success=True,
                database_name=target_database,
                duration_seconds=duration,
                message=f"Successfully restored database '{target_database}' in {duration:.2f}s.",
            )

        except FileNotFoundError:
            duration = time.time() - start_time
            return RestoreResult(
                success=False,
                database_name=target_database,
                duration_seconds=duration,
                message="mysql binary not found.",
                error_message=f"mysql binary '{self.mysql_binary}' was not found on PATH.",
            )
        except Exception as exc:
            duration = time.time() - start_time
            return RestoreResult(
                success=False,
                database_name=target_database,
                duration_seconds=duration,
                message="Unexpected restore error.",
                error_message=str(exc),
            )
