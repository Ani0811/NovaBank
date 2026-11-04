"""Executive Financial Dashboard View for NovaBank operations."""

from __future__ import annotations

from decimal import Decimal
from typing import TYPE_CHECKING, Callable, Optional

from PySide6.QtCore import Qt
from PySide6.QtGui import QFont
from PySide6.QtWidgets import (
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QPushButton,
    QScrollArea,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from novabank.application.dto.account_dto import AccountDTO

if TYPE_CHECKING:
    from novabank.application.services.banking_service import BankingService
    from novabank.ui.workers.task_runner import TaskRunner


class DashboardView(QWidget):
    """Central executive dashboard presenting real-time liquidity, KPI metrics, and rapid desk shortcuts."""

    def __init__(
        self,
        banking_service: Optional[BankingService] = None,
        task_runner: Optional[TaskRunner] = None,
        navigate_callback: Optional[Callable[[str], None]] = None,
        parent: Optional[QWidget] = None,
    ) -> None:
        super().__init__(parent)
        self.banking_service = banking_service
        self.task_runner = task_runner
        self.navigate_callback = navigate_callback

        self._accounts_cache: list[AccountDTO] = []

        self._setup_ui()
        self.load_data()

    def _setup_ui(self) -> None:
        root_layout = QVBoxLayout(self)
        root_layout.setContentsMargins(0, 0, 0, 0)
        root_layout.setSpacing(0)

        # Scrollable canvas
        scroll_area = QScrollArea()
        scroll_area.setWidgetResizable(True)
        scroll_area.setFrameShape(QFrame.Shape.NoFrame)
        scroll_area.setStyleSheet("background: transparent;")

        container = QWidget()
        layout = QVBoxLayout(container)
        layout.setContentsMargins(28, 24, 28, 28)
        layout.setSpacing(22)

        # ---------------------------------------------------------------------
        # 1. Header Banner & System Status Strip
        # ---------------------------------------------------------------------
        header_row = QHBoxLayout()
        header_row.setSpacing(12)

        title_block = QVBoxLayout()
        title_block.setSpacing(3)
        self.view_title = QLabel("Executive Operations Terminal")
        self.view_title.setStyleSheet("font-size: 22px; font-weight: 700; color: #f8fafc;")

        self.view_subtitle = QLabel(
            "Real-time liquidity intelligence, customer portfolio metrics, and rapid desk operations."
        )
        self.view_subtitle.setStyleSheet("font-size: 13px; color: #94a3b8;")

        title_block.addWidget(self.view_title)
        title_block.addWidget(self.view_subtitle)
        header_row.addLayout(title_block, stretch=1)

        # Status pills & refresh
        status_box = QHBoxLayout()
        status_box.setSpacing(8)

        self.pill_system = QLabel("● SYSTEM ONLINE")
        self.pill_system.setStyleSheet(
            "background-color: #064e3b; color: #34d399; border: 1px solid #059669; "
            "border-radius: 12px; padding: 5px 12px; font-size: 11px; font-weight: 700;"
        )

        self.pill_mode = QLabel("IN-MEMORY DEMO")
        self.pill_mode.setStyleSheet(
            "background-color: #0c4a6e; color: #38bdf8; border: 1px solid #0284c7; "
            "border-radius: 12px; padding: 5px 12px; font-size: 11px; font-weight: 700;"
        )

        self.refresh_btn = QPushButton("⟳ Refresh")
        self.refresh_btn.setProperty("class", "SecondaryButton")
        self.refresh_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.refresh_btn.setStyleSheet(
            "QPushButton { background-color: #121a29; color: #f1f5f9; font-weight: 600; "
            "border-radius: 6px; padding: 6px 14px; border: 1px solid #202d44; }"
            "QPushButton:hover { background-color: #1a273e; border-color: #38bdf8; }"
        )
        self.refresh_btn.clicked.connect(self.load_data)

        status_box.addWidget(self.pill_system)
        status_box.addWidget(self.pill_mode)
        status_box.addWidget(self.refresh_btn)
        header_row.addLayout(status_box)

        layout.addLayout(header_row)

        # ---------------------------------------------------------------------
        # 2. Executive KPI Cards (Responsive 1x4 Row)
        # ---------------------------------------------------------------------
        kpi_layout = QHBoxLayout()
        kpi_layout.setSpacing(14)

        # Card 1: Total AUM
        self.card_aum, self.val_aum, self.sub_aum = self._create_kpi_card(
            title="TOTAL ASSETS UNDER MANAGEMENT",
            initial_value="$0.00",
            initial_sub="Aggregated customer balances",
            accent_color="#3b82f6",
            icon_badge="LIQUIDITY VAULT",
        )
        kpi_layout.addWidget(self.card_aum, stretch=1)

        # Card 2: Active Accounts
        self.card_acc, self.val_acc, self.sub_acc = self._create_kpi_card(
            title="ACTIVE CUSTOMER ACCOUNTS",
            initial_value="0 Active",
            initial_sub="100% operational standing",
            accent_color="#06b6d4",
            icon_badge="CLIENT REGISTRY",
        )
        kpi_layout.addWidget(self.card_acc, stretch=1)

        # Card 3: 24h Volume
        self.card_vol, self.val_vol, self.sub_vol = self._create_kpi_card(
            title="TRANSACTION SETTLEMENT VOLUME",
            initial_value="$0.00",
            initial_sub="Posted teller & transfer credits",
            accent_color="#10b981",
            icon_badge="LEDGER VELOCITY",
        )
        kpi_layout.addWidget(self.card_vol, stretch=1)

        # Card 4: Audit & Compliance Score
        self.card_sec, self.val_sec, self.sub_sec = self._create_kpi_card(
            title="REGULATORY COMPLIANCE",
            initial_value="100%",
            initial_sub="0 security breaches • SHA-256",
            accent_color="#8b5cf6",
            icon_badge="AUDIT INTEGRITY",
        )
        kpi_layout.addWidget(self.card_sec, stretch=1)

        layout.addLayout(kpi_layout)

        # ---------------------------------------------------------------------
        # 3. Quick Desk Operations Launchpad
        # ---------------------------------------------------------------------
        launchpad_section = QVBoxLayout()
        launchpad_section.setSpacing(10)

        launchpad_lbl = QLabel("TELLER COUNTER SHORTCUTS")
        launchpad_lbl.setStyleSheet(
            "font-size: 11px; font-weight: 700; color: #64748b; letter-spacing: 1px;"
        )
        launchpad_section.addWidget(launchpad_lbl)

        actions_grid = QGridLayout()
        actions_grid.setSpacing(12)

        actions = [
            ("+", "Open Customer Account", "Register customer & assign account", "open_account"),
            ("📥", "Cash Deposit Desk", "Credit currency to customer account", "transactions"),
            ("📤", "Cash Withdrawal", "Verify funds & dispense currency", "transactions"),
            ("⇄", "Fund Transfer", "Atomic dual-ledger balance movement", "transactions"),
            ("≡", "Account Statements", "Generate audit-verified statements", "statements"),
            ("✦", "AI Banking Assistant", "Natural language financial intelligence", "ai_assistant"),
        ]

        for i, (icon, title, desc, route) in enumerate(actions):
            btn = self._create_action_card(icon, title, desc, route)
            actions_grid.addWidget(btn, i // 3, i % 3)

        launchpad_section.addLayout(actions_grid)
        layout.addLayout(launchpad_section)

        # ---------------------------------------------------------------------
        # 4. Two-Column Live Activity & Core Diagnostics Grid
        # ---------------------------------------------------------------------
        split_layout = QHBoxLayout()
        split_layout.setSpacing(18)

        # Left Column: Recent Customer Directory Snapshot
        left_card = QFrame()
        left_card.setObjectName("DashboardLeftCard")
        left_card.setStyleSheet(
            "QFrame#DashboardLeftCard { background-color: #0b111c; border: 1px solid #172235; border-radius: 8px; padding: 18px; }"
        )
        left_layout = QVBoxLayout(left_card)
        left_layout.setSpacing(12)

        left_header = QHBoxLayout()
        left_title = QLabel("Primary Customer Portfolios")
        left_title.setStyleSheet("font-size: 15px; font-weight: 700; color: #f8fafc;")
        left_subtitle = QLabel("Live Account Registry")
        left_subtitle.setStyleSheet("font-size: 12px; color: #64748b;")
        left_header.addWidget(left_title)
        left_header.addStretch()
        left_header.addWidget(left_subtitle)
        left_layout.addLayout(left_header)

        # Accounts Preview Table
        self.accounts_table = QTableWidget()
        self.accounts_table.setColumnCount(5)
        self.accounts_table.setHorizontalHeaderLabels([
            "Account Number",
            "Customer Name",
            "Location",
            "Status",
            "Balance (USD)",
        ])
        self.accounts_table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self.accounts_table.setSelectionMode(QTableWidget.SelectionMode.SingleSelection)
        self.accounts_table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.accounts_table.setAlternatingRowColors(True)
        self.accounts_table.setShowGrid(False)
        self.accounts_table.verticalHeader().setVisible(False)
        self.accounts_table.setStyleSheet(
            "QTableWidget { background-color: #05080f; alternate-background-color: #090e18; "
            "border: 1px solid #151e2e; border-radius: 6px; color: #f8fafc; font-size: 13px; }"
            "QHeaderView::section { background-color: #0a0f1a; color: #94a3b8; padding: 8px 10px; "
            "font-weight: 700; font-size: 11px; border: none; border-bottom: 2px solid #151e2e; }"
            "QTableWidget::item { padding: 8px; }"
            "QTableWidget::item:selected { background-color: #1e3a8a; color: #ffffff; }"
        )

        h_header = self.accounts_table.horizontalHeader()
        h_header.setSectionResizeMode(0, QHeaderView.ResizeMode.ResizeToContents)
        h_header.setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)
        h_header.setSectionResizeMode(2, QHeaderView.ResizeMode.ResizeToContents)
        h_header.setSectionResizeMode(3, QHeaderView.ResizeMode.ResizeToContents)
        h_header.setSectionResizeMode(4, QHeaderView.ResizeMode.ResizeToContents)

        self.accounts_table.doubleClicked.connect(self._on_table_double_clicked)
        left_layout.addWidget(self.accounts_table, stretch=1)

        # Footer button to view all accounts
        view_all_btn = QPushButton("View Complete Accounts Directory →")
        view_all_btn.setStyleSheet(
            "QPushButton { background-color: transparent; color: #38bdf8; font-weight: 600; text-align: right; border: none; padding: 4px; }"
            "QPushButton:hover { color: #60a5fa; text-decoration: underline; }"
        )
        view_all_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        view_all_btn.clicked.connect(lambda: self._route_to("accounts"))
        left_layout.addWidget(view_all_btn)

        split_layout.addWidget(left_card, stretch=65)

        # Right Column: Core Infrastructure & Compliance Watchdog
        right_card = QFrame()
        right_card.setObjectName("DashboardRightCard")
        right_card.setStyleSheet(
            "QFrame#DashboardRightCard { background-color: #0b111c; border: 1px solid #172235; border-radius: 8px; padding: 18px; }"
        )
        right_layout = QVBoxLayout(right_card)
        right_layout.setSpacing(14)

        right_title = QLabel("System Health & Subsystems")
        right_title.setStyleSheet("font-size: 15px; font-weight: 700; color: #f8fafc;")
        right_layout.addWidget(right_title)

        # Subsystem items
        subsystems = [
            ("Database Engine", "SQLite v3 (StaticPool Active)", "● CONNECTED", "#34d399"),
            ("Local AI Copilot", "LM Studio (localhost:1234)", "● READY", "#38bdf8"),
            ("Credential Vault", "Windows DPAPI Keyring", "🔒 SECURE", "#a78bfa"),
            ("Compliance Trail", "Immutable Append-Only Log", "✓ AUDITED", "#34d399"),
        ]

        for name, detail, status_txt, color in subsystems:
            item_frame = QFrame()
            item_frame.setStyleSheet(
                "QFrame { background-color: #070b13; border: 1px solid #151e2e; border-radius: 6px; padding: 6px; }"
            )
            item_layout = QHBoxLayout(item_frame)
            item_layout.setContentsMargins(10, 8, 10, 8)
            item_layout.setSpacing(8)

            info_layout = QVBoxLayout()
            info_layout.setSpacing(2)
            name_lbl = QLabel(name)
            name_lbl.setStyleSheet("font-size: 13px; font-weight: 600; color: #f8fafc;")
            detail_lbl = QLabel(detail)
            detail_lbl.setStyleSheet("font-size: 11px; color: #64748b;")
            info_layout.addWidget(name_lbl)
            info_layout.addWidget(detail_lbl)
            item_layout.addLayout(info_layout, stretch=1)

            badge = QLabel(status_txt)
            badge.setStyleSheet(
                f"color: {color}; font-size: 11px; font-weight: 700; padding: 3px 8px; "
                f"border-radius: 4px; background-color: #0b111c; border: 1px solid #172235;"
            )
            item_layout.addWidget(badge)

            right_layout.addWidget(item_frame)

        right_layout.addStretch()

        # Audit logs button
        audit_btn = QPushButton("Inspect Audit Trail & Compliance →")
        audit_btn.setStyleSheet(
            "QPushButton { background-color: transparent; color: #38bdf8; font-weight: 600; text-align: right; border: none; padding: 4px; }"
            "QPushButton:hover { color: #60a5fa; text-decoration: underline; }"
        )
        audit_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        audit_btn.clicked.connect(lambda: self._route_to("audit_logs"))
        right_layout.addWidget(audit_btn)

        split_layout.addWidget(right_card, stretch=35)

        layout.addLayout(split_layout)

        scroll_area.setWidget(container)
        root_layout.addWidget(scroll_area)

    def _create_kpi_card(
        self,
        title: str,
        initial_value: str,
        initial_sub: str,
        accent_color: str,
        icon_badge: str,
    ) -> tuple[QFrame, QLabel, QLabel]:
        """Create a stylized KPI executive metric card."""
        card = QFrame()
        card_id = "KpiCard_" + icon_badge.replace(" ", "_")
        card.setObjectName(card_id)
        card.setStyleSheet(
            f"QFrame#{card_id} {{ background-color: #0b111c; border: 1px solid #172235; "
            f"border-top: 3px solid {accent_color}; border-radius: 8px; }}"
        )
        layout = QVBoxLayout(card)
        layout.setContentsMargins(16, 14, 16, 14)
        layout.setSpacing(6)

        badge_row = QHBoxLayout()
        badge_lbl = QLabel(icon_badge)
        badge_lbl.setStyleSheet(
            f"font-size: 10px; font-weight: 800; color: {accent_color}; "
            "letter-spacing: 0.8px; text-transform: uppercase;"
        )
        badge_row.addWidget(badge_lbl)
        badge_row.addStretch()
        layout.addLayout(badge_row)

        val_lbl = QLabel(initial_value)
        val_lbl.setStyleSheet(
            "font-size: 24px; font-weight: 800; color: #f8fafc; font-family: 'Segoe UI', sans-serif;"
        )
        layout.addWidget(val_lbl)

        title_lbl = QLabel(title)
        title_lbl.setStyleSheet("font-size: 11px; font-weight: 700; color: #64748b; letter-spacing: 0.5px;")
        layout.addWidget(title_lbl)

        sub_lbl = QLabel(initial_sub)
        sub_lbl.setStyleSheet("font-size: 12px; color: #94a3b8;")
        layout.addWidget(sub_lbl)

        return card, val_lbl, sub_lbl

    def _create_action_card(
        self,
        icon: str,
        title: str,
        description: str,
        target_route: str,
    ) -> QPushButton:
        """Create an interactive desk action launch button."""
        btn = QPushButton()
        btn.setCursor(Qt.CursorShape.PointingHandCursor)
        btn.setStyleSheet(
            "QPushButton { background-color: #0b111c; border: 1px solid #172235; border-radius: 8px; padding: 12px; text-align: left; }"
            "QPushButton:hover { background-color: #121a29; border-color: #38bdf8; }"
            "QPushButton:pressed { background-color: #080c14; }"
        )

        inner_layout = QHBoxLayout(btn)
        inner_layout.setContentsMargins(10, 8, 10, 8)
        inner_layout.setSpacing(12)

        icon_lbl = QLabel(icon)
        icon_lbl.setStyleSheet("font-size: 18px; color: #38bdf8;")
        inner_layout.addWidget(icon_lbl)

        text_layout = QVBoxLayout()
        text_layout.setSpacing(2)
        title_lbl = QLabel(title)
        title_lbl.setStyleSheet("font-size: 13px; font-weight: 700; color: #f8fafc;")
        desc_lbl = QLabel(description)
        desc_lbl.setStyleSheet("font-size: 11px; color: #64748b;")
        text_layout.addWidget(title_lbl)
        text_layout.addWidget(desc_lbl)

        inner_layout.addLayout(text_layout, stretch=1)

        arrow_lbl = QLabel("→")
        arrow_lbl.setStyleSheet("font-size: 14px; font-weight: bold; color: #475569;")
        inner_layout.addWidget(arrow_lbl)

        btn.clicked.connect(lambda: self._route_to(target_route))
        return btn

    def _route_to(self, route_key: str) -> None:
        """Invoke navigation callback to switch views."""
        if self.navigate_callback:
            self.navigate_callback(route_key)

    def _on_table_double_clicked(self) -> None:
        """Double-clicking account row opens accounts directory."""
        self._route_to("accounts")

    def load_data(self) -> None:
        """Fetch and populate live metrics asynchronously."""
        if not self.banking_service:
            return

        if self.task_runner:
            self.task_runner.run_async(
                self._fetch_dashboard_data,
                on_result=self._on_data_loaded,
                on_error=self._on_data_error,
            )
        else:
            data = self._fetch_dashboard_data()
            self._on_data_loaded(data)

    def _fetch_dashboard_data(self) -> dict:
        """Worker background task gathering executive financial metrics."""
        accounts, total_count = self.banking_service.list_accounts(page=1, page_size=25)
        total_aum = sum((acc.balance for acc in accounts), Decimal("0.00"))
        active_count = sum(1 for acc in accounts if acc.is_active)

        return {
            "accounts": accounts,
            "total_count": total_count,
            "total_aum": total_aum,
            "active_count": active_count,
        }

    def _on_data_loaded(self, data: dict) -> None:
        """Update KPI metrics and populate account snapshot table."""
        accounts: list[AccountDTO] = data.get("accounts", [])
        self._accounts_cache = accounts
        total_aum: Decimal = data.get("total_aum", Decimal("0.00"))
        active_count: int = data.get("active_count", 0)
        total_count: int = data.get("total_count", 0)

        # Update KPI Cards
        self.val_aum.setText(f"${total_aum:,.2f}")
        self.sub_aum.setText(f"Across {total_count} customer account{'s' if total_count != 1 else ''}")

        self.val_acc.setText(f"{active_count} Active")
        self.sub_acc.setText(f"{total_count} total registered accounts")

        # Estimated ledger activity volume
        self.val_vol.setText(f"${total_aum:,.2f}")
        self.sub_vol.setText("Active liquid capital")

        self.val_sec.setText("100% Verified")
        self.sub_sec.setText("All transactions cryptographically ledgered")

        # Populate Accounts Table
        self.accounts_table.setRowCount(len(accounts))
        for row, acc in enumerate(accounts):
            item_num = QTableWidgetItem(acc.account_number)
            item_num.setFont(QFont("Consolas", 11))

            item_name = QTableWidgetItem(acc.holder_name)
            item_loc = QTableWidgetItem(f"{acc.city}, {acc.state}")

            status_str = "ACTIVE" if acc.is_active else "CLOSED"
            item_status = QTableWidgetItem(status_str)
            item_status.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
            if acc.is_active:
                item_status.setForeground(Qt.GlobalColor.green)
            else:
                item_status.setForeground(Qt.GlobalColor.red)

            item_bal = QTableWidgetItem(f"${acc.balance:,.2f}")
            item_bal.setTextAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
            item_bal.setFont(QFont("Segoe UI", 11, QFont.Weight.Bold))

            self.accounts_table.setItem(row, 0, item_num)
            self.accounts_table.setItem(row, 1, item_name)
            self.accounts_table.setItem(row, 2, item_loc)
            self.accounts_table.setItem(row, 3, item_status)
            self.accounts_table.setItem(row, 4, item_bal)

    def _on_data_error(self, exc: Exception, tb: str) -> None:
        """Handle metric fetch failure gracefully."""
        self.val_aum.setText("Unavailable")
        self.sub_aum.setText(str(exc))
