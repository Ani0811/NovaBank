"""Enterprise Status Bar component for NovaBank desktop platform."""

from __future__ import annotations

from typing import Optional

from PySide6.QtWidgets import (
    QLabel,
    QStatusBar,
    QWidget,
)


class NovaStatusBar(QStatusBar):
    """Institutional application status bar displaying DB health, session info, and AI availability."""

    def __init__(self, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self.setObjectName("NovaStatusBar")
        self.setSizeGripEnabled(False)

        # Left-hand operational telemetry
        self._system_indicator = QLabel("NovaBank Core Engine • TLS 1.3 Verified")
        self._system_indicator.setObjectName("SystemTelemetryLabel")
        self._system_indicator.setStyleSheet("color: #94A3B8; font-size: 11px; padding-left: 4px;")
        self.addWidget(self._system_indicator)

        # Session indicator
        self._session_indicator = QLabel("Session: Default Session (Main Branch)")
        self._session_indicator.setObjectName("SessionIndicator")
        self._session_indicator.setProperty("class", "StatusIndicatorPill")
        self._session_indicator.setProperty("status", "neutral")

        # AI Assistant indicator
        self._ai_indicator = QLabel("AI Assistant: Ready")
        self._ai_indicator.setObjectName("AiStatusIndicator")
        self._ai_indicator.setProperty("class", "StatusIndicatorPill")
        self._ai_indicator.setProperty("status", "success")

        # Database indicator
        self._db_indicator = QLabel("Database: Initializing")
        self._db_indicator.setObjectName("DbStatusIndicator")
        self._db_indicator.setProperty("class", "StatusIndicatorPill")
        self._db_indicator.setProperty("status", "warning")

        # Add indicators as permanent widgets to right side of status bar
        self.addPermanentWidget(self._session_indicator)
        self.addPermanentWidget(self._ai_indicator)
        self.addPermanentWidget(self._db_indicator)

    def set_db_status(self, connected: bool, details: str = "") -> None:
        """Update database connectivity status."""
        if connected:
            text = f"● Database: Connected {details}".strip()
            status = "success"
        else:
            text = f"▲ Database: Offline {details}".strip()
            status = "danger"

        self._db_indicator.setText(text)
        self._db_indicator.setProperty("status", status)
        self._db_indicator.style().unpolish(self._db_indicator)
        self._db_indicator.style().polish(self._db_indicator)

    def set_session_info(self, username: str, branch: str = "Main Branch") -> None:
        """Update user session info."""
        self._session_indicator.setText(f"Session: {username} ({branch})")

    def set_ai_status(self, ready: bool, details: str = "") -> None:
        """Update local AI assistant availability."""
        if ready:
            text = f"● AI Assistant: Ready {details}".strip()
            status = "success"
        else:
            text = f"▲ AI Assistant: Offline {details}".strip()
            status = "warning"

        self._ai_indicator.setText(text)
        self._ai_indicator.setProperty("status", status)
        self._ai_indicator.style().unpolish(self._ai_indicator)
        self._ai_indicator.style().polish(self._ai_indicator)
