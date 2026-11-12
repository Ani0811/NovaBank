"""UI tests for SettingsView and Automated Interest Accrual engine."""

from datetime import date
from decimal import Decimal
import pytest
from PySide6.QtWidgets import QMessageBox

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from novabank.application.services.banking_service import BankingService
from novabank.infrastructure.db.models import Base
from novabank.ui.views.settings_view import SettingsView
from novabank.ui.workers.task_runner import TaskRunner


@pytest.fixture
def banking_service():
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    session_factory = sessionmaker(bind=engine)
    return BankingService(session_factory=session_factory)


@pytest.fixture
def task_runner():
    return TaskRunner()


def test_settings_view_initialization(qtbot, banking_service, task_runner):
    """Verify SettingsView components and default interest parameters."""
    view = SettingsView(banking_service, task_runner)
    qtbot.addWidget(view)
    view.show()

    assert view.apy_rate_edit.text() == "2.50"
    assert view.min_bal_edit.text() == "100.00"
    assert view.interest_status_pill.text() == "Engine Ready"


def test_settings_view_post_interest_flow(qtbot, banking_service, task_runner, monkeypatch):
    """Verify interest accrual execution triggered from SettingsView."""
    acc = banking_service.open_account(
        holder_name="Interest Test Client",
        dob=date(1980, 2, 20),
        address_line="888 Yield Blvd",
        city="Miami",
        state="FL",
        country="USA",
        phone_number="5552224444",
        initial_deposit=Decimal("12000.00"),
    ).account

    view = SettingsView(banking_service, task_runner)
    qtbot.addWidget(view)
    view.show()

    # Automatically answer Yes to confirmation and OK to information
    monkeypatch.setattr(QMessageBox, "question", lambda *args, **kwargs: QMessageBox.StandardButton.Yes)
    monkeypatch.setattr(QMessageBox, "information", lambda *args, **kwargs: None)

    view._on_post_interest_clicked()

    # Wait for execution completion
    qtbot.waitUntil(lambda: "Successfully posted interest" in view.interest_result_lbl.text(), timeout=4000)
    assert view.interest_status_pill.text() == "Interest Posted"

    # Verify interest was credited to the account:
    # 12,000 * 0.025 / 12 = $25.00
    updated_acc = banking_service.get_account(acc.account_number)
    assert updated_acc.balance == Decimal("12025.00")
