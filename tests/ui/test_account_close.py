"""Tests for AccountCloseDialog and account deactivation workflows."""

from __future__ import annotations

from datetime import date, datetime, timezone
from decimal import Decimal

from PySide6.QtWidgets import QLabel

from novabank.application.dto.account_dto import AccountDTO
from novabank.ui.views.account_close_dialog import AccountCloseDialog


def make_dto(balance: str = "0.00", is_active: bool = True) -> AccountDTO:
    """Helper creating mock AccountDTO for dialog testing."""
    return AccountDTO(
        account_number="123456789012",
        holder_name="Jane Doe",
        dob=date(1990, 1, 1),
        address_line="100 Main St",
        city="Denver",
        state="CO",
        country="USA",
        phone_number="5551234567",
        balance=Decimal(balance),
        currency="USD",
        is_active=is_active,
        version=1,
        created_at=datetime.now(timezone.utc),
        updated_at=datetime.now(timezone.utc),
    )


def test_close_dialog_blocks_non_zero_balance(qtbot) -> None:
    """Verify dialog with active balance displays blocked notice and no confirm button."""
    dto = make_dto(balance="150.75")
    dialog = AccountCloseDialog(dto)
    qtbot.addWidget(dialog)

    assert not hasattr(dialog, "confirm_btn")
    assert not hasattr(dialog, "reason_combo")

    # Verify blocked warning title is present
    labels = dialog.findChildren(QLabel)
    assert any("Action Blocked" in label.text() for label in labels)


def test_close_dialog_zero_balance_allows_closure(qtbot) -> None:
    """Verify dialog with zero balance enables confirmation checkbox and closure workflow."""
    dto = make_dto(balance="0.00")
    dialog = AccountCloseDialog(dto)
    qtbot.addWidget(dialog)

    assert hasattr(dialog, "confirm_btn")
    assert hasattr(dialog, "confirm_check")
    assert hasattr(dialog, "reason_combo")

    # Confirm button is initially disabled
    assert dialog.confirm_btn.isEnabled() is False

    # Check confirmation checkbox
    dialog.confirm_check.setChecked(True)
    assert dialog.confirm_btn.isEnabled() is True

    # Check reason selection
    dialog.reason_combo.setCurrentText("Customer Relocation")
    dialog.notes_edit.setText("Moving overseas")

    reason = dialog.get_closure_reason()
    assert "Customer Relocation" in reason
    assert "Moving overseas" in reason


def test_close_dialog_uncheck_disables_button(qtbot) -> None:
    """Verify unchecking confirmation checkbox disables confirm button."""
    dto = make_dto(balance="0.00")
    dialog = AccountCloseDialog(dto)
    qtbot.addWidget(dialog)

    dialog.confirm_check.setChecked(True)
    assert dialog.confirm_btn.isEnabled() is True

    dialog.confirm_check.setChecked(False)
    assert dialog.confirm_btn.isEnabled() is False
