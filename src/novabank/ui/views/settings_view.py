"""System Settings and Infrastructure Diagnostics View."""

from __future__ import annotations

import sys
from typing import TYPE_CHECKING, Optional

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPlainTextEdit,
    QPushButton,
    QScrollArea,
    QVBoxLayout,
    QWidget,
)

from novabank.infrastructure.config import AppConfig
from novabank.infrastructure.db.diagnostics import DatabaseStatus, check_database_connectivity
from novabank.ui.resources.icons import get_icon

if TYPE_CHECKING:
    from novabank.application.services.banking_service import BankingService
    from novabank.ui.workers.task_runner import TaskRunner


class SettingsView(QWidget):
    """Institutional system settings, database diagnostics, and security vault status."""

    def __init__(
        self,
        banking_service: Optional[BankingService] = None,
        task_runner: Optional[TaskRunner] = None,
        parent: Optional[QWidget] = None,
    ) -> None:
        super().__init__(parent)
        self.banking_service = banking_service
        self.task_runner = task_runner
        self.config = AppConfig()

        self._setup_ui()

    def _setup_ui(self) -> None:
        root_layout = QVBoxLayout(self)
        root_layout.setContentsMargins(0, 0, 0, 0)
        root_layout.setSpacing(0)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        scroll.setStyleSheet("background: transparent;")

        container = QWidget()
        layout = QVBoxLayout(container)
        layout.setContentsMargins(28, 24, 28, 28)
        layout.setSpacing(20)

        # 1. Header Section
        header_row = QHBoxLayout()
        header_text = QVBoxLayout()
        header_text.setSpacing(2)

        title = QLabel("System Settings & Infrastructure")
        title.setStyleSheet("font-size: 20px; font-weight: 700; color: #172033;")
        subtitle = QLabel("Database connectivity, credential vault parameters, and platform diagnostics.")
        subtitle.setStyleSheet("font-size: 13px; color: #64748B;")
        header_text.addWidget(title)
        header_text.addWidget(subtitle)
        header_row.addLayout(header_text, stretch=1)

        layout.addLayout(header_row)

        # 2. Database Connectivity Card
        db_card = QFrame()
        db_card.setProperty("class", "CardFrame")
        db_layout = QVBoxLayout(db_card)
        db_layout.setSpacing(16)

        db_header = QHBoxLayout()
        db_title = QLabel("DATABASE CONFIGURATION")
        db_title.setProperty("class", "CardTitle")
        db_header.addWidget(db_title)
        db_header.addStretch()

        self.db_status_pill = QLabel("Checking Connectivity...")
        self.db_status_pill.setProperty("class", "StatusIndicatorPill")
        self.db_status_pill.setProperty("status", "warning")
        db_header.addWidget(self.db_status_pill)
        db_layout.addLayout(db_header)

        grid = QGridLayout()
        grid.setSpacing(12)

        grid.addWidget(QLabel("Database Host:"), 0, 0)
        self.host_val = QLineEdit(self.config.db_host)
        self.host_val.setReadOnly(True)
        grid.addWidget(self.host_val, 0, 1)

        grid.addWidget(QLabel("Database Port:"), 0, 2)
        self.port_val = QLineEdit(str(self.config.db_port))
        self.port_val.setReadOnly(True)
        grid.addWidget(self.port_val, 0, 3)

        grid.addWidget(QLabel("Database Name:"), 1, 0)
        self.name_val = QLineEdit(self.config.db_name)
        self.name_val.setReadOnly(True)
        grid.addWidget(self.name_val, 1, 1)

        grid.addWidget(QLabel("Database User:"), 1, 2)
        self.user_val = QLineEdit(self.config.db_user)
        self.user_val.setReadOnly(True)
        grid.addWidget(self.user_val, 1, 3)

        db_layout.addLayout(grid)
        layout.addWidget(db_card)

        # 3. Security & Keyring Vault Card
        sec_card = QFrame()
        sec_card.setProperty("class", "CardFrame")
        sec_layout = QVBoxLayout(sec_card)
        sec_layout.setSpacing(14)

        sec_title = QLabel("CREDENTIAL VAULT & SECURITY")
        sec_title.setProperty("class", "CardTitle")
        sec_layout.addWidget(sec_title)

        sec_grid = QGridLayout()
        sec_grid.setSpacing(12)

        sec_grid.addWidget(QLabel("Keyring Service:"), 0, 0)
        self.keyring_service = QLineEdit("novabank_db")
        self.keyring_service.setReadOnly(True)
        sec_grid.addWidget(self.keyring_service, 0, 1)

        sec_grid.addWidget(QLabel("Local Security Backend:"), 0, 2)
        backend_name = "Windows DPAPI (Keyring)" if sys.platform == "win32" else "System Secret Storage"
        self.keyring_backend = QLineEdit(backend_name)
        self.keyring_backend.setReadOnly(True)
        sec_grid.addWidget(self.keyring_backend, 0, 3)

        sec_layout.addLayout(sec_grid)
        layout.addWidget(sec_card)

        # 4. Diagnostics & Health Runner Card
        diag_card = QFrame()
        diag_card.setProperty("class", "CardFrame")
        diag_layout = QVBoxLayout(diag_card)
        diag_layout.setSpacing(14)

        diag_header = QHBoxLayout()
        diag_title = QLabel("DIAGNOSTICS & TELEMETRY")
        diag_title.setProperty("class", "CardTitle")
        diag_header.addWidget(diag_title)
        diag_header.addStretch()

        self.run_diag_btn = QPushButton("Run Connection Diagnostics")
        self.run_diag_btn.setProperty("class", "SecondaryButton")
        self.run_diag_btn.setIcon(get_icon("refresh", color="#172033", size=14))
        self.run_diag_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.run_diag_btn.clicked.connect(self.run_diagnostics)
        diag_header.addWidget(self.run_diag_btn)
        diag_layout.addLayout(diag_header)

        self.diag_output = QPlainTextEdit()
        self.diag_output.setReadOnly(True)
        self.diag_output.setStyleSheet(
            "font-family: Consolas, 'Courier New', monospace; font-size: 12px; background-color: #F8FAFC; border: 1px solid #E2E8F0;"
        )
        self.diag_output.setPlaceholderText("Click 'Run Connection Diagnostics' to verify MySQL and local services...")
        self.diag_output.setFixedHeight(120)
        diag_layout.addWidget(self.diag_output)

        layout.addWidget(diag_card)
        layout.addStretch()

        scroll.setWidget(container)
        root_layout.addWidget(scroll)

    def run_diagnostics(self) -> None:
        """Run connectivity check and output report."""
        if self.task_runner:
            self.task_runner.run_async(
                self._check_diagnostics_worker,
                on_result=self._on_diagnostics_result,
                on_error=self._on_diagnostics_error,
            )
        else:
            res = self._check_diagnostics_worker()
            self._on_diagnostics_result(res)

    def _check_diagnostics_worker(self) -> dict:
        try:
            diag = check_database_connectivity(self.config)
            is_connected = diag.status == DatabaseStatus.CONNECTED
            legacy_found = bool(diag.legacy_schema and diag.legacy_schema.database_exists)
            return {
                "success": is_connected,
                "version": diag.server_version or "N/A",
                "legacy": legacy_found,
                "error": diag.error_message or "None",
            }
        except Exception as exc:
            return {
                "success": False,
                "version": "N/A",
                "legacy": False,
                "error": str(exc),
            }

    def _on_diagnostics_result(self, result: dict) -> None:
        success = result.get("success", False)
        status_txt = "Connected" if success else "In-Memory / Standby"
        status_val = "success" if success else "warning"

        self.db_status_pill.setText(status_txt)
        self.db_status_pill.setProperty("status", status_val)
        self.db_status_pill.style().unpolish(self.db_status_pill)
        self.db_status_pill.style().polish(self.db_status_pill)

        report = (
            f"[SYSTEM DIAGNOSTIC RUN REPORT]\n"
            f"Database Host: {self.config.db_host}:{self.config.db_port}\n"
            f"Database Name: {self.config.db_name}\n"
            f"Connection Healthy: {'YES' if success else 'NO (Falling back to in-memory demo if offline)'}\n"
            f"Server Engine Version: {result.get('version')}\n"
            f"Legacy BMS Tables: {'DETECTED' if result.get('legacy') else 'NONE'}\n"
            f"Last Reported Error: {result.get('error')}\n"
        )
        self.diag_output.setPlainText(report)

    def _on_diagnostics_error(self, exc: Exception, tb: str) -> None:
        self.db_status_pill.setText("Diagnostic Error")
        self.db_status_pill.setProperty("status", "danger")
        self.db_status_pill.style().unpolish(self.db_status_pill)
        self.db_status_pill.style().polish(self.db_status_pill)
        self.diag_output.setPlainText(f"Diagnostics runner encountered an exception:\n{exc}")
