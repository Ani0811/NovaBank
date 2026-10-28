"""Main application window for NovaBank desktop banking system."""

from __future__ import annotations

from pathlib import Path
from typing import Optional

from PySide6.QtWidgets import (
    QFrame,
    QHBoxLayout,
    QLabel,
    QMainWindow,
    QStackedWidget,
    QVBoxLayout,
    QWidget,
)

from novabank.ui.components.sidebar import Sidebar
from novabank.ui.components.status_bar import NovaStatusBar


class MainWindow(QMainWindow):
    """Primary desktop application shell with navigation, content views, and status bar."""

    PAGE_TITLES: dict[str, tuple[str, str]] = {
        "dashboard": ("Dashboard", "Financial overview and key performance metrics"),
        "accounts": ("Accounts Management", "Customer account administration and profile updates"),
        "transactions": (
            "Transactions & Cash Desk",
            "Execute atomic deposits, withdrawals, and transfers",
        ),
        "statements": (
            "Account Statements",
            "Generate and export digital statements and summaries",
        ),
        "ai_assistant": (
            "AI Banking Assistant",
            "Local private AI financial intelligence and natural language queries",
        ),
        "settings": (
            "System Settings",
            "Database connectivity, keyring credentials, and diagnostics",
        ),
    }

    def __init__(self, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self.setWindowTitle("NovaBank - Enterprise Banking System")
        self.setMinimumSize(1024, 680)
        self.resize(1280, 800)

        self._view_indices: dict[str, int] = {}

        self._build_ui()
        self._apply_stylesheet()

    def _build_ui(self) -> None:
        central_widget = QWidget(self)
        central_widget.setObjectName("CentralWidget")
        self.setCentralWidget(central_widget)

        root_layout = QHBoxLayout(central_widget)
        root_layout.setContentsMargins(0, 0, 0, 0)
        root_layout.setSpacing(0)

        # 1. Navigation Sidebar
        self.sidebar = Sidebar(self)
        self.sidebar.navigation_changed.connect(self.navigate_to)
        root_layout.addWidget(self.sidebar)

        # 2. Main Content Container
        content_container = QWidget()
        content_layout = QVBoxLayout(content_container)
        content_layout.setContentsMargins(0, 0, 0, 0)
        content_layout.setSpacing(0)

        # Header Bar
        self.header_bar = QFrame()
        self.header_bar.setObjectName("HeaderBar")
        header_layout = QVBoxLayout(self.header_bar)
        header_layout.setContentsMargins(24, 8, 24, 8)
        header_layout.setSpacing(2)

        self.header_title = QLabel("Dashboard")
        self.header_title.setObjectName("HeaderTitle")
        self.header_subtitle = QLabel("Financial overview and key performance metrics")
        self.header_subtitle.setObjectName("HeaderSubtitle")

        header_layout.addWidget(self.header_title)
        header_layout.addWidget(self.header_subtitle)
        content_layout.addWidget(self.header_bar)

        # Dynamic Stacked Views
        self.view_stack = QStackedWidget()
        self.view_stack.setObjectName("MainViewStack")

        # Initialize placeholder pages for each navigation route
        for view_key, (title, desc) in self.PAGE_TITLES.items():
            page = self._create_placeholder_page(view_key, title, desc)
            idx = self.view_stack.addWidget(page)
            self._view_indices[view_key] = idx

        content_layout.addWidget(self.view_stack)
        root_layout.addWidget(content_container, stretch=1)

        # 3. Status Bar
        self.status_bar = NovaStatusBar(self)
        self.setStatusBar(self.status_bar)

        # Set default view
        self.navigate_to("dashboard")

    def _create_placeholder_page(self, view_key: str, title: str, description: str) -> QWidget:
        """Create a placeholder card page for the given view."""
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setContentsMargins(24, 24, 24, 24)
        layout.setSpacing(16)

        card = QFrame()
        card.setObjectName(f"PageCard_{view_key}")
        card.setProperty("class", "CardFrame")
        card_layout = QVBoxLayout(card)
        card_layout.setContentsMargins(24, 24, 24, 24)
        card_layout.setSpacing(8)

        card_title = QLabel(title)
        card_title.setProperty("class", "CardTitle")
        card_desc = QLabel(description)
        card_desc.setProperty("class", "CardMuted")

        card_layout.addWidget(card_title)
        card_layout.addWidget(card_desc)
        card_layout.addStretch()

        layout.addWidget(card)
        layout.addStretch()
        return page

    def _apply_stylesheet(self) -> None:
        """Load and apply QSS stylesheet."""
        qss_path = Path(__file__).parent / "resources" / "styles.qss"
        if qss_path.is_file():
            stylesheet = qss_path.read_text(encoding="utf-8")
            self.setStyleSheet(stylesheet)

    def navigate_to(self, view_key: str) -> None:
        """Switch view stack and update sidebar and header."""
        if view_key in self._view_indices:
            idx = self._view_indices[view_key]
            self.view_stack.setCurrentIndex(idx)
            self.sidebar.set_active(view_key)

            if view_key in self.PAGE_TITLES:
                title, desc = self.PAGE_TITLES[view_key]
                self.header_title.setText(title)
                self.header_subtitle.setText(desc)

    @property
    def current_view_key(self) -> str:
        """Return currently visible view key."""
        current_idx = self.view_stack.currentIndex()
        for k, idx in self._view_indices.items():
            if idx == current_idx:
                return k
        return "dashboard"
