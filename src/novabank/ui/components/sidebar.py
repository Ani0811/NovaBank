"""Enterprise Navigation Sidebar for NovaBank Desktop Platform."""

from __future__ import annotations

from typing import Optional

from PySide6.QtCore import QSize, Signal
from PySide6.QtWidgets import (
    QFrame,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from novabank.ui.resources.icons import get_icon


class Sidebar(QFrame):
    """Sophisticated institutional navigation sidebar emitting view navigation events."""

    # Signal emitting destination view identifier (e.g. "dashboard", "accounts")
    navigation_changed = Signal(str)

    NAV_SECTIONS: list[tuple[str, list[tuple[str, str, str]]]] = [
        (
            "CORE BANKING",
            [
                ("dashboard", "Dashboard", "dashboard"),
                ("accounts", "Accounts", "accounts"),
                ("open_account", "Open Account", "open_account"),
            ],
        ),
        (
            "TELLER OPERATIONS",
            [
                ("transactions", "Transactions", "transactions"),
                ("deposits", "Deposits", "deposits"),
                ("withdrawals", "Withdrawals", "withdrawals"),
                ("transfers", "Fund Transfers", "transfers"),
                ("payment_gateway", "Payment Gateway", "credit_card"),
                ("statements", "Statements", "statements"),
            ],
        ),
        (
            "SECURITY & MANAGEMENT",
            [
                ("audit_logs", "Audit Trail", "audit_logs"),
                ("ai_assistant", "AI Assistant", "ai_assistant"),
                ("settings", "Settings", "settings"),
            ],
        ),
    ]

    def __init__(self, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self.setObjectName("SidebarFrame")
        self._buttons: dict[str, QPushButton] = {}
        self._icon_names: dict[str, str] = {}
        self._current_view: str = "dashboard"

        self._build_ui()

    def _build_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 20, 0, 16)
        layout.setSpacing(0)

        # 1. Branding Header
        brand_container = QWidget()
        brand_layout = QHBoxLayout(brand_container)
        brand_layout.setContentsMargins(18, 0, 18, 20)
        brand_layout.setSpacing(12)

        # Institutional Monogram Icon
        logo_lbl = QLabel("NB")
        logo_lbl.setStyleSheet(
            "background-color: #2563EB; color: #FFFFFF; font-weight: 800; font-size: 13px; "
            "border-radius: 6px; min-width: 32px; max-width: 32px; min-height: 32px; max-height: 32px; "
            "qproperty-alignment: AlignCenter;"
        )
        brand_layout.addWidget(logo_lbl)

        brand_text_layout = QVBoxLayout()
        brand_text_layout.setSpacing(1)
        title_lbl = QLabel("NovaBank")
        title_lbl.setObjectName("BrandTitle")
        subtitle_lbl = QLabel("Enterprise Banking")
        subtitle_lbl.setObjectName("BrandSubtitle")

        brand_text_layout.addWidget(title_lbl)
        brand_text_layout.addWidget(subtitle_lbl)
        brand_layout.addLayout(brand_text_layout, stretch=1)

        layout.addWidget(brand_container)

        # 2. Navigation Sections
        for section_title, items in self.NAV_SECTIONS:
            sec_lbl = QLabel(section_title)
            sec_lbl.setProperty("class", "NavSectionTitle")
            layout.addWidget(sec_lbl)

            for view_key, label_text, icon_name in items:
                btn = QPushButton(f"  {label_text}")
                btn.setObjectName(f"NavBtn_{view_key}")
                btn.setProperty("class", "NavButton")
                btn.setIcon(get_icon(icon_name, color="#64748B", size=16))
                btn.setIconSize(QSize(16, 16))
                btn.setCheckable(True)
                btn.setAutoExclusive(True)
                btn.clicked.connect(lambda checked=False, vk=view_key: self._on_btn_clicked(vk))

                layout.addWidget(btn)
                self._buttons[view_key] = btn
                self._icon_names[view_key] = icon_name

        layout.addStretch()

        # 3. Institutional Operator Session Card
        operator_card = QFrame()
        operator_card.setObjectName("SidebarOperatorCard")
        op_layout = QHBoxLayout(operator_card)
        op_layout.setContentsMargins(8, 6, 8, 6)
        op_layout.setSpacing(10)

        avatar_lbl = QLabel("TS")
        avatar_lbl.setStyleSheet(
            "background-color: #EFF6FF; color: #2563EB; font-weight: 700; font-size: 11px; "
            "border-radius: 4px; min-width: 28px; max-width: 28px; min-height: 28px; max-height: 28px; "
            "qproperty-alignment: AlignCenter;"
        )
        op_layout.addWidget(avatar_lbl)

        op_text = QVBoxLayout()
        op_text.setSpacing(1)
        teller_lbl = QLabel("Teller Station #01")
        teller_lbl.setStyleSheet("font-size: 12px; font-weight: 600; color: #172033;")
        status_lbl = QLabel("Operational • Secure")
        status_lbl.setStyleSheet("font-size: 10px; color: #15803D; font-weight: 500;")
        op_text.addWidget(teller_lbl)
        op_text.addWidget(status_lbl)
        op_layout.addLayout(op_text, stretch=1)

        layout.addWidget(operator_card)

        # Set default active item
        self.set_active("dashboard")

    def _on_btn_clicked(self, view_key: str) -> None:
        """Handle button click and emit navigation change."""
        self.set_active(view_key)
        self.navigation_changed.emit(view_key)

    def set_active(self, view_key: str) -> None:
        """Highlight active navigation button and refresh icon states."""
        # Map sub-routes if needed
        target_key = view_key
        if target_key not in self._buttons:
            # Check if it maps to transactions or something else
            if view_key in ("deposits", "withdrawals", "transfers", "fund_transfers"):
                target_key = view_key
            else:
                return

        self._current_view = view_key
        for k, btn in self._buttons.items():
            is_active = (k == target_key) or (k == view_key)
            btn.setChecked(is_active)
            btn.setProperty("active", "true" if is_active else "false")

            # Update icon color: Blue for active, Slate for inactive
            icon_name = self._icon_names.get(k, "dashboard")
            icon_color = "#2563EB" if is_active else "#64748B"
            btn.setIcon(get_icon(icon_name, color=icon_color, size=16))

            btn.style().unpolish(btn)
            btn.style().polish(btn)

    def set_active_route(self, view_key: str) -> None:
        """Alias for set_active."""
        self.set_active(view_key)

    @property
    def current_view(self) -> str:
        """Return currently selected view identifier."""
        return self._current_view
