"""System Settings and Infrastructure Diagnostics View."""

from __future__ import annotations

import sys
from decimal import Decimal, InvalidOperation
from typing import TYPE_CHECKING, Optional

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
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
        layout.setContentsMargins(28, 20, 28, 24)
        layout.setSpacing(14)

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
        db_layout.setSpacing(10)

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
        self.diag_output.setFixedHeight(85)
        diag_layout.addWidget(self.diag_output)

        layout.addWidget(diag_card)

        # 4. Automated Interest & Fee Accrual Card
        interest_card = QFrame()
        interest_card.setProperty("class", "CardFrame")
        int_layout = QVBoxLayout(interest_card)
        int_layout.setSpacing(10)

        int_header = QHBoxLayout()
        int_title = QLabel("AUTOMATED INTEREST & APY ACCRUAL ENGINE")
        int_title.setProperty("class", "CardTitle")
        int_header.addWidget(int_title)
        int_header.addStretch()

        self.interest_status_pill = QLabel("Engine Ready")
        self.interest_status_pill.setProperty("class", "StatusIndicatorPill")
        self.interest_status_pill.setProperty("status", "success")
        int_header.addWidget(self.interest_status_pill)
        int_layout.addLayout(int_header)

        int_desc = QLabel(
            "Batch calculate and credit monthly compounding interest (APY) to all active customer savings accounts "
            "meeting the minimum qualifying balance requirement. All interest credits are cryptographically journaled."
        )
        int_desc.setStyleSheet("font-size: 12px; color: #64748B;")
        int_desc.setWordWrap(True)
        int_layout.addWidget(int_desc)

        int_grid = QGridLayout()
        int_grid.setSpacing(12)

        int_grid.addWidget(QLabel("Annual Percentage Yield (APY %):"), 0, 0)
        self.apy_rate_edit = QLineEdit("2.50")
        self.apy_rate_edit.setStyleSheet("font-size: 13px; font-weight: 600;")
        int_grid.addWidget(self.apy_rate_edit, 0, 1)

        int_grid.addWidget(QLabel("Minimum Qualifying Balance ($):"), 0, 2)
        self.min_bal_edit = QLineEdit("100.00")
        self.min_bal_edit.setStyleSheet("font-size: 13px; font-weight: 600;")
        int_grid.addWidget(self.min_bal_edit, 0, 3)

        int_layout.addLayout(int_grid)

        int_actions = QHBoxLayout()
        self.interest_result_lbl = QLabel("No interest posting executed in current session.")
        self.interest_result_lbl.setStyleSheet("font-size: 12px; color: #475569; font-weight: 500;")
        int_actions.addWidget(self.interest_result_lbl, stretch=1)

        self.post_interest_btn = QPushButton("Post Monthly Interest")
        self.post_interest_btn.setProperty("class", "PrimaryButton")
        self.post_interest_btn.setIcon(get_icon("check", color="#FFFFFF", size=14))
        self.post_interest_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.post_interest_btn.clicked.connect(self._on_post_interest_clicked)
        int_actions.addWidget(self.post_interest_btn)

        int_layout.addLayout(int_actions)
        layout.addWidget(interest_card)

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

    def _on_post_interest_clicked(self) -> None:
        """Trigger monthly compounding interest calculation across all qualifying accounts."""
        if not self.banking_service:
            QMessageBox.warning(self, "Service Offline", "Banking Service is currently offline.")
            return

        try:
            rate_val = Decimal(self.apy_rate_edit.text().strip().replace("%", ""))
            min_val = Decimal(self.min_bal_edit.text().strip().replace("$", "").replace(",", ""))
            if rate_val < Decimal("0.00") or min_val < Decimal("0.00"):
                raise InvalidOperation("Values cannot be negative")
        except (InvalidOperation, ValueError):
            QMessageBox.warning(
                self,
                "Invalid Parameters",
                "Please enter valid positive decimal numbers for APY percentage and minimum balance.",
            )
            return

        confirm = QMessageBox.question(
            self,
            "Confirm Interest Posting",
            f"Are you sure you want to execute monthly interest accrual?\n\n"
            f"• Annual APY Rate: {rate_val:.2f}%\n"
            f"• Minimum Qualifying Balance: ${min_val:,.2f} USD\n\n"
            f"This will immediately credit and journal interest to all qualifying accounts.",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )

        if confirm != QMessageBox.StandardButton.Yes:
            return

        self.post_interest_btn.setEnabled(False)
        self.interest_status_pill.setText("Calculating...")
        self.interest_status_pill.setProperty("status", "warning")
        self.interest_status_pill.style().unpolish(self.interest_status_pill)
        self.interest_status_pill.style().polish(self.interest_status_pill)

        if self.task_runner:
            self.task_runner.run_async(
                lambda: self.banking_service.accrue_interest(
                    annual_rate_percentage=rate_val,
                    min_qualifying_balance=min_val,
                    actor="teller_admin",
                ),
                on_result=self._on_interest_success,
                on_error=self._on_interest_error,
                on_finished=lambda: self.post_interest_btn.setEnabled(True),
            )
        else:
            try:
                res = self.banking_service.accrue_interest(
                    annual_rate_percentage=rate_val,
                    min_qualifying_balance=min_val,
                    actor="teller_admin",
                )
                self._on_interest_success(res)
            except Exception as exc:
                self._on_interest_error(exc, "")
            finally:
                self.post_interest_btn.setEnabled(True)

    def _on_interest_success(self, credited_dtos: list) -> None:
        try:
            self.interest_status_pill.setText("Interest Posted")
            self.interest_status_pill.setProperty("status", "success")
            self.interest_status_pill.style().unpolish(self.interest_status_pill)
            self.interest_status_pill.style().polish(self.interest_status_pill)

            total_amount = sum((tx.amount for tx in credited_dtos), Decimal("0.00"))
            summary = (
                f"Successfully posted interest to {len(credited_dtos)} accounts totaling ${total_amount:,.2f} USD."
            )
            self.interest_result_lbl.setText(summary)
            QMessageBox.information(self, "Interest Accrual Complete", summary)
        except RuntimeError:
            pass

    def _on_interest_error(self, exc: Exception, tb: str) -> None:
        try:
            self.interest_status_pill.setText("Run Failed")
            self.interest_status_pill.setProperty("status", "danger")
            self.interest_status_pill.style().unpolish(self.interest_status_pill)
            self.interest_status_pill.style().polish(self.interest_status_pill)
            self.interest_result_lbl.setText(f"Error: {exc}")
            QMessageBox.critical(self, "Accrual Failed", f"Failed to post interest:\n{exc}")
        except RuntimeError:
            pass
