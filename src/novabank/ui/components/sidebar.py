"""Navigation sidebar component for NovaBank desktop application."""

from __future__ import annotations

from typing import Optional

from PySide6.QtCore import Signal
from PySide6.QtWidgets import (
    QFrame,
    QLabel,
    QPushButton,
    QVBoxLayout,
    QWidget,
)


class Sidebar(QFrame):
    """Collapsible navigation sidebar emitting view navigation events."""

    # Signal emitting destination view identifier (e.g. "dashboard", "accounts")
    navigation_changed = Signal(str)

    NAV_ITEMS: list[tuple[str, str, str]] = [
        ("dashboard", "Dashboard", "📊"),
        ("accounts", "Accounts", "👥"),
        ("open_account", "Open Account", "➕"),
        ("transactions", "Transactions", "💳"),
        ("statements", "Statements", "📄"),
        ("ai_assistant", "AI Assistant", "🤖"),
        ("settings", "Settings", "⚙️"),
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
        layout.setSpacing(4)

        # Branding Header
        brand_container = QWidget()
        brand_layout = QVBoxLayout(brand_container)
        brand_layout.setContentsMargins(20, 4, 20, 20)
        brand_layout.setSpacing(2)

        title_lbl = QLabel("NovaBank")
        title_lbl.setObjectName("BrandTitle")
        subtitle_lbl = QLabel("Core Banking System")
        subtitle_lbl.setObjectName("BrandSubtitle")

        brand_layout.addWidget(title_lbl)
        brand_layout.addWidget(subtitle_lbl)
        layout.addWidget(brand_container)

        # Navigation Buttons
        for view_key, label_text, icon_symbol in self.NAV_ITEMS:
            btn = QPushButton(f"  {icon_symbol}   {label_text}")
            btn.setObjectName(f"NavBtn_{view_key}")
            btn.setProperty("class", "NavButton")
            btn.setCheckable(True)
            btn.setAutoExclusive(True)
            btn.clicked.connect(lambda checked=False, vk=view_key: self._on_btn_clicked(vk))

            layout.addWidget(btn)
            self._buttons[view_key] = btn

        layout.addStretch()

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
