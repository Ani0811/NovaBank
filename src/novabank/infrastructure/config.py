"""Application configuration and secure credential management for NovaBank."""

from __future__ import annotations

import csv
from pathlib import Path
from typing import Optional

import keyring
from pydantic import Field, SecretStr, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

KEYRING_SERVICE_NAME = "NovaBank"


class AppConfig(BaseSettings):
    """Unified application settings loaded from environment variables and secure stores."""

    model_config = SettingsConfigDict(
        env_prefix="NOVABANK_",
        env_file=(".env", ".env.local"),
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # General Environment
    env: str = Field(
        default="development", description="Runtime environment (development, test, production)"
    )
    app_name: str = Field(default="NovaBank", description="Application display name")
    debug: bool = Field(default=False, description="Enable debug logging and diagnostic modes")

    # Database Settings (MySQL 8.0)
    db_host: str = Field(default="localhost", description="MySQL server hostname or IP")
    db_port: int = Field(default=3306, description="MySQL server port")
    db_user: str = Field(default="root", description="MySQL username")
    db_password: SecretStr = Field(default=SecretStr(""), description="MySQL password (masked)")
    db_name: str = Field(default="novabank_db", description="Database schema name")
    db_pool_size: int = Field(default=5, description="Connection pool size")
    db_max_overflow: int = Field(default=10, description="Max overflow connections")

    # Local AI Settings (LM Studio)
    ai_enabled: bool = Field(default=True, description="Enable local AI assistant features")
    ai_base_url: str = Field(
        default="http://localhost:1234/v1", description="LM Studio local REST endpoint"
    )
    ai_model: str = Field(
        default="llama-3.2-3b-instruct", description="Target model identifier in LM Studio"
    )
    ai_timeout_seconds: float = Field(
        default=10.0, description="Timeout in seconds for AI requests"
    )

    @field_validator("db_port")
    @classmethod
    def validate_port(cls, v: int) -> int:
        if not (1 <= v <= 65535):
            raise ValueError(f"Port must be between 1 and 65535, got {v}")
        return v

    def resolve_db_password(self) -> str:
        """Resolve database password from memory or Windows Credential Manager."""
        raw_pwd = self.db_password.get_secret_value()
        if raw_pwd:
            return raw_pwd
        # Fall back to Windows Credential Manager
        vault_pwd = get_db_password_from_keyring(self.db_user)
        return vault_pwd or ""

    @property
    def database_url(self) -> str:
        """Construct full SQLAlchemy connection URL with resolved credentials."""
        pwd = self.resolve_db_password()
        # Escape any special characters in password if needed
        return f"mysql+pymysql://{self.db_user}:{pwd}@{self.db_host}:{self.db_port}/{self.db_name}"

    @property
    def safe_database_url(self) -> str:
        """Construct safe SQLAlchemy connection URL with masked password for logging."""
        masked_pwd = "***" if self.resolve_db_password() else ""
        return f"mysql+pymysql://{self.db_user}:{masked_pwd}@{self.db_host}:{self.db_port}/{self.db_name}"


# ---------------------------------------------------------------------------
# Keyring (Windows Credential Manager) Utilities
# ---------------------------------------------------------------------------


def save_db_password_to_keyring(
    username: str, password: str, service: str = KEYRING_SERVICE_NAME
) -> None:
    """Securely persist database password into Windows Credential Manager."""
    if not username:
        raise ValueError("Username cannot be empty when storing credential.")
    try:
        keyring.set_password(service, username, password)
    except Exception:
        pass


def get_db_password_from_keyring(
    username: str, service: str = KEYRING_SERVICE_NAME
) -> Optional[str]:
    """Retrieve database password from Windows Credential Manager."""
    if not username:
        return None
    try:
        return keyring.get_password(service, username)
    except Exception:
        return None


def delete_db_password_from_keyring(username: str, service: str = KEYRING_SERVICE_NAME) -> None:
    """Delete database credential from Windows Credential Manager."""
    try:
        keyring.delete_password(service, username)
    except keyring.errors.PasswordDeleteError:
        pass


# ---------------------------------------------------------------------------
# Legacy CSV Migration Helper
# ---------------------------------------------------------------------------


def import_legacy_connection_csv(
    csv_path: str | Path,
    store_in_keyring: bool = True,
    delete_csv_after_import: bool = False,
) -> tuple[dict[str, str], bool]:
    """Import credentials from a legacy BMS_MySQL_ConnectionString.csv file.

    Format expected: [sLocalHost, sDatabase, sUser, sPWD]
    Returns a dictionary of parsed settings and a boolean indicating if the CSV was deleted.
    """
    path = Path(csv_path)
    if not path.is_file():
        raise FileNotFoundError(f"Legacy connection string file not found: {csv_path}")

    with path.open("r", encoding="utf-8", errors="replace") as f:
        reader = csv.reader(f)
        row = next(reader, None)

    if not row or len(row) < 4:
        raise ValueError(
            f"Invalid format in legacy connection CSV: expected at least 4 fields, got {row}"
        )

    host = row[0].strip()
    database = row[1].strip()
    user = row[2].strip()
    password = row[3].strip()

    if store_in_keyring and password:
        save_db_password_to_keyring(user, password)

    csv_deleted = False
    if delete_csv_after_import:
        path.unlink(missing_ok=True)
        csv_deleted = True

    return {
        "host": host,
        "database": database,
        "user": user,
        "password": password,
    }, csv_deleted
