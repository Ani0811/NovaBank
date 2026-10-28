"""Status bar component for NovaBank desktop application."""

from __future__ import annotations

from typing import Optional

from PySide6.QtWidgets import (
    QLabel,
    QStatusBar,
    QWidget,
)


class NovaStatusBar(QStatusBar):
    """Application status bar displaying DB health, session info, and AI availability."""

    def __init__(self, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self.setObjectName("NovaStatusBar")

        # Database indicator pill
        self._db_indicator = QLabel("● Database: Initializing")
        self._db_indicator.setObjectName("DbStatusIndicator")
        self._db_indicator.setProperty("class", "StatusIndicatorPill")
        self._db_indicator.setProperty("status", "warning")

        # Session indicator pill
        self._session_indicator = QLabel("👤 Teller: Default Session")
        self._session_indicator.setObjectName("SessionIndicator")
        self._session_indicator.setProperty("class", "StatusIndicatorPill")
        self._session_indicator.setProperty("status", "success")

        # AI Assistant indicator pill
        self._ai_indicator = QLabel("🤖 AI: Ready")
        self._ai_indicator.setObjectName("AiStatusIndicator")
        self._ai_indicator.setProperty("class", "StatusIndicatorPill")
        self._ai_indicator.setProperty("status", "success")

        # Add indicators as permanent widgets to right side of status bar
        self.addPermanentWidget(self._session_indicator)
        self.addPermanentWidget(self._ai_indicator)
        self.addPermanentWidget(self._db_indicator)

    def set_db_status(self, connected: bool, details: str = "") -> None:
        """Update database connectivity status pill."""
        if connected:
            text = f"● Database: Connected {details}".strip()
            status = "success"
        else:
            text = f"● Database: Offline {details}".strip()
            status = "danger"

        self._db_indicator.setText(text)
        self._db_indicator.setProperty("status", status)
        self._db_indicator.style().unpolish(self._db_indicator)
        self._db_indicator.style().polish(self._db_indicator)

    def set_session_info(self, username: str, branch: str = "Main Branch") -> None:
        """Update user session pill."""
        self._session_indicator.setText(f"👤 {username} ({branch})")

    def set_ai_status(self, ready: bool, details: str = "") -> None:
        """Update local AI assistant availability pill."""
        if ready:
            text = f"🤖 AI: Ready {details}".strip()
            status = "success"
        else:
            text = f"🤖 AI: Offline {details}".strip()
            status = "warning"

        self._ai_indicator.setText(text)
        self._ai_indicator.setProperty("status", status)
        self._ai_indicator.style().unpolish(self._ai_indicator)
        self._ai_indicator.style().polish(self._ai_indicator)
