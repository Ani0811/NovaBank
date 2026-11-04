"""Navigation sidebar component for NovaBank desktop application."""

from __future__ import annotations

from typing import Optional

from PySide6.QtCore import Signal
from PySide6.QtWidgets import (
    QFrame,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QVBoxLayout,
    QWidget,
)


class Sidebar(QFrame):
    """Collapsible navigation sidebar emitting view navigation events."""

    # Signal emitting destination view identifier (e.g. "dashboard", "accounts")
    navigation_changed = Signal(str)

    NAV_SECTIONS: list[tuple[str, list[tuple[str, str, str]]]] = [
        (
            "CORE BANKING",
            [
                ("dashboard", "Dashboard", "✦"),
                ("accounts", "Accounts", "◈"),
                ("open_account", "Open Account", "+"),
            ],
        ),
        (
            "TELLER OPERATIONS",
            [
                ("transactions", "Transactions", "⇄"),
                ("statements", "Statements", "≡"),
            ],
        ),
        (
            "SECURITY & AI",
            [
                ("ai_assistant", "AI Assistant", "✦"),
                ("audit_logs", "Audit Trail", "🛡"),
                ("settings", "Settings", "⚙"),
            ],
        ),
    ]

    def __init__(self, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self.setObjectName("SidebarFrame")
        self._buttons: dict[str, QPushButton] = {}
        self._current_view: str = "dashboard"

        self._build_ui()

    def _build_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 16, 0, 16)
        layout.setSpacing(2)

        # Branding Header
        brand_container = QWidget()
        brand_layout = QVBoxLayout(brand_container)
        brand_layout.setContentsMargins(20, 4, 20, 18)
        brand_layout.setSpacing(2)

        title_lbl = QLabel("NovaBank")
        title_lbl.setObjectName("BrandTitle")
        subtitle_lbl = QLabel("Enterprise Terminal")
        subtitle_lbl.setObjectName("BrandSubtitle")

        brand_layout.addWidget(title_lbl)
        brand_layout.addWidget(subtitle_lbl)
        layout.addWidget(brand_container)

        # Navigation Sections
        for section_title, items in self.NAV_SECTIONS:
            sec_lbl = QLabel(section_title)
            sec_lbl.setProperty("class", "NavSectionTitle")
            sec_lbl.setStyleSheet(
                "font-size: 10px; font-weight: 700; color: #475569; letter-spacing: 1.2px; "
                "padding: 14px 20px 4px 20px; text-transform: uppercase;"
            )
            layout.addWidget(sec_lbl)

            for view_key, label_text, icon_symbol in items:
                btn = QPushButton(f"  {icon_symbol}   {label_text}")
                btn.setObjectName(f"NavBtn_{view_key}")
                btn.setProperty("class", "NavButton")
                btn.setCheckable(True)
                btn.setAutoExclusive(True)
                btn.clicked.connect(lambda checked=False, vk=view_key: self._on_btn_clicked(vk))

                layout.addWidget(btn)
                self._buttons[view_key] = btn

        layout.addStretch()

        # Operator Session Card at bottom
        operator_card = QFrame()
        operator_card.setObjectName("SidebarOperatorCard")
        operator_card.setStyleSheet(
            "QFrame#SidebarOperatorCard { background-color: #0c121e; border: 1px solid #1a2436; "
            "border-radius: 8px; margin: 10px 14px; padding: 10px; }"
        )
        op_layout = QHBoxLayout(operator_card)
        op_layout.setContentsMargins(6, 4, 6, 4)
        op_layout.setSpacing(8)

        avatar_lbl = QLabel("NB")
        avatar_lbl.setStyleSheet(
            "background-color: #1e3a8a; color: #38bdf8; font-weight: 800; font-size: 11px; "
            "border-radius: 12px; min-width: 24px; max-width: 24px; min-height: 24px; max-height: 24px; qproperty-alignment: AlignCenter;"
        )
        op_layout.addWidget(avatar_lbl)

        op_text = QVBoxLayout()
        op_text.setSpacing(1)
        teller_lbl = QLabel("Teller Terminal #1")
        teller_lbl.setStyleSheet("font-size: 12px; font-weight: 600; color: #f8fafc;")
        status_lbl = QLabel("● Active Session")
        status_lbl.setStyleSheet("font-size: 10px; color: #34d399; font-weight: 600;")
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
        """Highlight active navigation button."""
        if view_key in self._buttons:
            self._current_view = view_key
            for k, btn in self._buttons.items():
                is_active = k == view_key
                btn.setChecked(is_active)
                btn.setProperty("active", "true" if is_active else "false")
                btn.style().unpolish(btn)
                btn.style().polish(btn)

    def set_active_route(self, view_key: str) -> None:
        """Alias for set_active."""
        self.set_active(view_key)

    @property
    def current_view(self) -> str:
        """Return currently selected view identifier."""
        return self._current_view
