"""Tests for application configuration and secure credential management."""

import pytest
from pydantic import SecretStr

from novabank.infrastructure.config import (
    AppConfig,
    delete_db_password_from_keyring,
    get_db_password_from_keyring,
    import_legacy_connection_csv,
    save_db_password_to_keyring,
)


def test_default_config():
    """Verify default configuration attributes."""
    config = AppConfig()
    assert config.env == "development"
    assert config.app_name == "NovaBank"
    assert config.db_host == "localhost"
    assert config.db_port == 3306
    assert config.db_user == "root"
    assert config.db_name == "novabank_db"
    assert config.ai_enabled is True
    assert "localhost:1234" in config.ai_base_url


def test_port_validation():
    """Verify port validator enforces valid port numbers."""
    with pytest.raises(ValueError, match="Port must be between 1 and 65535"):
        AppConfig(db_port=0)

    with pytest.raises(ValueError, match="Port must be between 1 and 65535"):
        AppConfig(db_port=70000)

    valid_config = AppConfig(db_port=3307)
    assert valid_config.db_port == 3307


def test_password_masking_in_repr():
    """Verify password secret masking in string and repr representations."""
    config = AppConfig(db_password=SecretStr("super_secret_pass"))
    config_repr = repr(config)
    assert "super_secret_pass" not in config_repr
    assert "**********" in config_repr or "SecretStr('**********')" in config_repr


def test_database_url_and_safe_url():
    """Verify database URLs: full URL has password, safe URL masks password."""
    config = AppConfig(
        db_host="127.0.0.1",
        db_port=3306,
        db_user="bank_admin",
        db_password=SecretStr("mypassword123"),
        db_name="test_db",
    )
    assert config.database_url == "mysql+pymysql://bank_admin:mypassword123@127.0.0.1:3306/test_db"
    assert config.safe_database_url == "mysql+pymysql://bank_admin:***@127.0.0.1:3306/test_db"


def test_environment_variable_override(monkeypatch):
    """Verify settings pick up BMS_ prefixed environment variables."""
    monkeypatch.setenv("BMS_DB_HOST", "db.internal.bank")
    monkeypatch.setenv("BMS_DB_PORT", "3307")
    monkeypatch.setenv("BMS_DB_USER", "teller_app")
    monkeypatch.setenv("BMS_DB_NAME", "production_bms")
    monkeypatch.setenv("BMS_AI_ENABLED", "false")

    config = AppConfig()
    assert config.db_host == "db.internal.bank"
    assert config.db_port == 3307
    assert config.db_user == "teller_app"
    assert config.db_name == "production_bms"
    assert config.ai_enabled is False


def test_keyring_password_storage(monkeypatch):
    """Verify secure storage and retrieval via mock keyring."""
    fake_vault = {}

    def mock_set_password(service, username, password):
        fake_vault[(service, username)] = password

    def mock_get_password(service, username):
        return fake_vault.get((service, username))

    def mock_delete_password(service, username):
        fake_vault.pop((service, username), None)

    monkeypatch.setattr("keyring.set_password", mock_set_password)
    monkeypatch.setattr("keyring.get_password", mock_get_password)
    monkeypatch.setattr("keyring.delete_password", mock_delete_password)

    test_user = "test_teller_99"
    test_pass = "SecureVaultP@ss99"

    # Save to vault
    save_db_password_to_keyring(test_user, test_pass)
    assert get_db_password_from_keyring(test_user) == test_pass

    # Verify AppConfig falls back to keyring when db_password is empty
    config = AppConfig(db_user=test_user, db_password=SecretStr(""))
    assert config.resolve_db_password() == test_pass
    assert (
        config.database_url == f"mysql+pymysql://{test_user}:{test_pass}@localhost:3306/novabank_db"
    )

    # Delete from vault
    delete_db_password_from_keyring(test_user)
    assert get_db_password_from_keyring(test_user) is None


def test_import_legacy_csv_file_not_found():
    """Verify import raises FileNotFoundError for non-existent path."""
    with pytest.raises(FileNotFoundError):
        import_legacy_connection_csv("non_existent_file.csv")


def test_import_legacy_csv_malformed(tmp_path):
    """Verify import raises ValueError on malformed row."""
    bad_csv = tmp_path / "bad.csv"
    bad_csv.write_text("localhost,sys,root\n", encoding="utf-8")  # only 3 fields

    with pytest.raises(ValueError, match="Invalid format in legacy connection CSV"):
        import_legacy_connection_csv(bad_csv)


def test_import_legacy_csv_success_and_deletion(tmp_path, monkeypatch):
    """Verify successful parsing of legacy CSV and secure file deletion."""
    fake_vault = {}
    monkeypatch.setattr("keyring.set_password", lambda s, u, p: fake_vault.update({(s, u): p}))

    legacy_csv = tmp_path / "BMS_MySQL_ConnectionString.csv"
    # Legacy CSV format: [sLocalHost, sDatabase, sUser, sPWD]
    legacy_csv.write_text("127.0.0.1,narDB,root,sasa\n", encoding="utf-8")

    parsed, deleted = import_legacy_connection_csv(
        legacy_csv,
        store_in_keyring=True,
        delete_csv_after_import=True,
    )

    assert parsed["host"] == "127.0.0.1"
    assert parsed["database"] == "narDB"
    assert parsed["user"] == "root"
    assert parsed["password"] == "sasa"
    assert deleted is True

    # Assert legacy CSV was physically wiped
    assert not legacy_csv.exists()
