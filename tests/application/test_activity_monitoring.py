"""Unit tests for ActivityMonitoringService rules engine and AI explanation generation."""

from __future__ import annotations

from datetime import datetime, timedelta
from decimal import Decimal
from unittest.mock import MagicMock

from novabank.application.dto.activity_flag_dto import ActivityFlagDTO
from novabank.application.services.activity_monitoring_service import (
    ActivityMonitoringService,
)
from novabank.domain.entities.transaction import Transaction
from novabank.domain.value_objects.account_number import AccountNumber
from novabank.domain.value_objects.money import Money
from novabank.domain.value_objects.transaction_type import TransactionDirection, TransactionType
from novabank.infrastructure.ai.exceptions import AIConnectionError
from novabank.infrastructure.ai.lm_studio_client import LMStudioClient


def make_tx(
    tx_id: int,
    tx_type: TransactionType,
    direction: TransactionDirection,
    amount: Decimal,
    created_at: datetime,
) -> Transaction:
    return Transaction(
        transaction_id=tx_id,
        account_number=AccountNumber("100000001234"),
        transaction_type=tx_type,
        direction=direction,
        amount=Money(amount),
        balance_after=Money(Decimal("10000.00")),
        created_at=created_at,
        created_by="teller",
        transaction_ref=f"TXN-{tx_id:04d}",
        description=f"Transaction {tx_id}",
    )


def test_large_transaction_rule_trigger() -> None:
    """Transactions >= $10,000 must trigger LARGE_TRANSACTION flag."""
    t1 = make_tx(
        1,
        TransactionType.DEPOSIT,
        TransactionDirection.CREDIT,
        Decimal("15000.00"),
        datetime(2026, 3, 1, 10, 0),
    )
    service = ActivityMonitoringService()
    flags = service.evaluate_transactions("100000001234", [t1])

    assert len(flags) == 1
    assert flags[0].flag_code == "LARGE_TRANSACTION"
    assert flags[0].severity == "HIGH"
    assert flags[0].account_number_masked == "****-****-1234"
    assert flags[0].metrics["amount"] == "15000.00"


def test_rapid_withdrawals_rule_trigger() -> None:
    """Three withdrawals within 24 hours must trigger RAPID_WITHDRAWALS flag."""
    base_time = datetime(2026, 3, 5, 8, 0)
    txs = [
        make_tx(1, TransactionType.WITHDRAWAL, TransactionDirection.DEBIT, Decimal("200.00"), base_time),
        make_tx(2, TransactionType.WITHDRAWAL, TransactionDirection.DEBIT, Decimal("300.00"), base_time + timedelta(hours=2)),
        make_tx(3, TransactionType.WITHDRAWAL, TransactionDirection.DEBIT, Decimal("500.00"), base_time + timedelta(hours=5)),
    ]

    service = ActivityMonitoringService()
    flags = service.evaluate_transactions("100000001234", txs)

    assert len(flags) == 1
    assert flags[0].flag_code == "RAPID_WITHDRAWALS"
    assert flags[0].severity == "MEDIUM"
    assert flags[0].metrics["withdrawal_count"] == 3
    assert flags[0].metrics["total_withdrawn"] == "1000.00"


def test_dormant_account_spike_trigger() -> None:
    """Burst of 3 transactions after >= 90 days gap triggers DORMANT_ACCOUNT_SPIKE."""
    t1 = make_tx(1, TransactionType.DEPOSIT, TransactionDirection.CREDIT, Decimal("100.00"), datetime(2025, 10, 1, 12, 0))
    # 100 days gap
    burst_time = datetime(2026, 1, 10, 12, 0)
    t2 = make_tx(2, TransactionType.DEPOSIT, TransactionDirection.CREDIT, Decimal("50.00"), burst_time)
    t3 = make_tx(3, TransactionType.WITHDRAWAL, TransactionDirection.DEBIT, Decimal("40.00"), burst_time + timedelta(hours=1))
    t4 = make_tx(4, TransactionType.DEPOSIT, TransactionDirection.CREDIT, Decimal("60.00"), burst_time + timedelta(hours=3))

    service = ActivityMonitoringService()
    flags = service.evaluate_transactions("100000001234", [t1, t2, t3, t4])

    spike_flags = [f for f in flags if f.flag_code == "DORMANT_ACCOUNT_SPIKE"]
    assert len(spike_flags) == 1
    assert spike_flags[0].severity == "MEDIUM"
    assert spike_flags[0].metrics["burst_count"] == 3
    assert spike_flags[0].metrics["dormancy_days"] >= 90


def test_normal_activity_triggers_zero_flags() -> None:
    """Normal modest transactions spread over days trigger no flags."""
    txs = [
        make_tx(1, TransactionType.DEPOSIT, TransactionDirection.CREDIT, Decimal("500.00"), datetime(2026, 3, 1, 10, 0)),
        make_tx(2, TransactionType.WITHDRAWAL, TransactionDirection.DEBIT, Decimal("100.00"), datetime(2026, 3, 5, 12, 0)),
    ]

    service = ActivityMonitoringService()
    flags = service.evaluate_transactions("100000001234", txs)
    assert len(flags) == 0


def test_deterministic_explanation_generation() -> None:
    """Verify deterministic fallback explanations for all flag types."""
    service = ActivityMonitoringService()

    flag_large = ActivityFlagDTO(
        flag_code="LARGE_TRANSACTION",
        severity="HIGH",
        rule_name="Large Transaction BSA/CTR Threshold",
        triggered_at=datetime(2026, 3, 1),
        description="Over 10k",
        metrics={"amount": "12500.00", "type": "DEPOSIT"},
        account_number_masked="****-****-1234",
    )
    exp = service.generate_deterministic_explanation(flag_large)
    assert "$12,500.00" in exp
    assert "Currency Transaction Report (CTR)" in exp

    flag_rapid = ActivityFlagDTO(
        flag_code="RAPID_WITHDRAWALS",
        severity="MEDIUM",
        rule_name="Rapid Consecutive Withdrawals",
        triggered_at=datetime(2026, 3, 1),
        description="3 withdrawals",
        metrics={"withdrawal_count": 3, "total_withdrawn": "1500.00"},
        account_number_masked="****-****-1234",
    )
    exp_rapid = service.generate_deterministic_explanation(flag_rapid)
    assert "3 consecutive cash withdrawals" in exp_rapid
    assert "$1,500.00" in exp_rapid


def test_explain_flag_with_lm_studio() -> None:
    """Valid 2-sentence explanation from LM Studio is returned."""
    mock_client = MagicMock(spec=LMStudioClient)
    mock_client.chat_completion.return_value = (
        "A deposit of $15,000 exceeds the $10,000 regulatory reporting threshold. "
        "Staff should verify customer identification and file a standard Currency Transaction Report."
    )

    service = ActivityMonitoringService(lm_client=mock_client)
    flag = ActivityFlagDTO(
        flag_code="LARGE_TRANSACTION",
        severity="HIGH",
        rule_name="Large Transaction BSA/CTR Threshold",
        triggered_at=datetime(2026, 3, 1),
        description="Over 10k",
        metrics={"amount": "15000.00", "type": "DEPOSIT"},
        account_number_masked="****-****-1234",
    )

    result = service.explain_flag(flag)
    assert "$15,000" in result
    assert "Currency Transaction Report" in result


def test_explain_flag_rejects_autonomous_freeze() -> None:
    """If AI claims to freeze the account, the explanation is rejected in favor of fallback."""
    mock_client = MagicMock(spec=LMStudioClient)
    mock_client.chat_completion.return_value = (
        "This activity is suspicious so the AI has chosen to freeze the account. Contact supervisor."
    )

    service = ActivityMonitoringService(lm_client=mock_client)
    flag = ActivityFlagDTO(
        flag_code="RAPID_WITHDRAWALS",
        severity="MEDIUM",
        rule_name="Rapid Consecutive Withdrawals",
        triggered_at=datetime(2026, 3, 1),
        description="3 debits",
        metrics={"withdrawal_count": 3, "total_withdrawn": "900.00"},
        account_number_masked="****-****-1234",
    )

    result = service.explain_flag(flag)
    # Must use deterministic explanation
    assert "consecutive cash withdrawals" in result
    assert "freeze" not in result.lower()


def test_explain_flag_offline_fallback() -> None:
    """When LM Studio raises connection error, service gracefully falls back."""
    mock_client = MagicMock(spec=LMStudioClient)
    mock_client.chat_completion.side_effect = AIConnectionError("Connection refused on 127.0.0.1:1234")

    service = ActivityMonitoringService(lm_client=mock_client)
    flag = ActivityFlagDTO(
        flag_code="LARGE_TRANSACTION",
        severity="HIGH",
        rule_name="Large Transaction BSA/CTR Threshold",
        triggered_at=datetime(2026, 3, 1),
        description="Over 10k",
        metrics={"amount": "25000.00", "type": "DEPOSIT"},
        account_number_masked="****-****-1234",
    )

    result = service.explain_flag(flag)
    assert "$25,000.00" in result
    assert "Currency Transaction Report (CTR)" in result

