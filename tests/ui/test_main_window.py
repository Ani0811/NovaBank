"""Tests for MainWindow, Sidebar, and NovaStatusBar using pytest-qt."""

import pytest
from PySide6.QtCore import Qt

from novabank.ui.components.status_bar import NovaStatusBar
from novabank.ui.main_window import MainWindow


@pytest.fixture(autouse=True)
def setup_offscreen_qt(monkeypatch):
    """Ensure offscreen platform for headless test execution."""
    monkeypatch.setenv("QT_QPA_PLATFORM", "offscreen")


def test_main_window_initialization(qtbot):
    """Verify MainWindow initializes with correct title, dimensions, and default view."""
    window = MainWindow()
    qtbot.addWidget(window)

    assert "NovaBank" in window.windowTitle()
    assert window.minimumWidth() == 1024
    assert window.minimumHeight() == 680
    assert window.current_view_key == "dashboard"
    assert window.header_title.text() == "Dashboard"
    assert window.sidebar is not None
    assert window.status_bar is not None


def test_sidebar_navigation_switch(qtbot):
    """Verify clicking sidebar buttons switches view stack and updates header."""
    window = MainWindow()
    qtbot.addWidget(window)

    # Click on 'Accounts' button
    accounts_btn = window.sidebar._buttons["accounts"]
    qtbot.mouseClick(accounts_btn, Qt.MouseButton.LeftButton)

    assert window.current_view_key == "accounts"
    assert window.header_title.text() == "Accounts Management"
    assert window.sidebar.current_view == "accounts"

    # Click on 'Transactions' button
    tx_btn = window.sidebar._buttons["transactions"]
    qtbot.mouseClick(tx_btn, Qt.MouseButton.LeftButton)

    assert window.current_view_key == "transactions"
    assert window.header_title.text() == "Transactions & Cash Desk"
    assert window.sidebar.current_view == "transactions"

    # Click on 'AI Assistant' button
    ai_btn = window.sidebar._buttons["ai_assistant"]
    qtbot.mouseClick(ai_btn, Qt.MouseButton.LeftButton)

    assert window.current_view_key == "ai_assistant"
    assert window.header_title.text() == "AI Banking Assistant"


def test_programmatic_navigation(qtbot):
    """Verify navigate_to method programmatic routing."""
    window = MainWindow()
    qtbot.addWidget(window)

    window.navigate_to("statements")
    assert window.current_view_key == "statements"
    assert window.header_title.text() == "Account Statements"
    assert window.sidebar.current_view == "statements"

    window.navigate_to("settings")
    assert window.current_view_key == "settings"
    assert window.header_title.text() == "System Settings"


def test_status_bar_updates(qtbot):
    """Verify status bar indicator text and property updates."""
    status_bar = NovaStatusBar()
    qtbot.addWidget(status_bar)

    # Database status update
    status_bar.set_db_status(connected=True, details="(MySQL 8.0)")
    assert "Connected (MySQL 8.0)" in status_bar._db_indicator.text()
    assert status_bar._db_indicator.property("status") == "success"

    status_bar.set_db_status(connected=False, details="(Connection Refused)")
    assert "Offline (Connection Refused)" in status_bar._db_indicator.text()
    assert status_bar._db_indicator.property("status") == "danger"

    # Session info update
    status_bar.set_session_info(username="teller_john", branch="North Branch")
    assert "teller_john (North Branch)" in status_bar._session_indicator.text()

    # AI status update
    status_bar.set_ai_status(ready=True, details="[llama-3.2-3b]")
    assert "Ready [llama-3.2-3b]" in status_bar._ai_indicator.text()
    assert status_bar._ai_indicator.property("status") == "success"

    status_bar.set_ai_status(ready=False, details="[LM Studio Stopped]")
    assert "Offline [LM Studio Stopped]" in status_bar._ai_indicator.text()
    assert status_bar._ai_indicator.property("status") == "warning"


def test_stylesheet_loaded(qtbot):
    """Verify stylesheet is loaded and applied to MainWindow."""
    window = MainWindow()
    qtbot.addWidget(window)

    stylesheet = window.styleSheet()
    assert "SidebarFrame" in stylesheet
    assert "HeaderBar" in stylesheet
    assert "NovaStatusBar" in stylesheet
