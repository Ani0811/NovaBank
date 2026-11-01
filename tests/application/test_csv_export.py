"""Tests for RFC-4180 compliant CSV statement export and formula injection defense."""

from __future__ import annotations

import csv
import io
from datetime import datetime
from decimal import Decimal
from pathlib import Path

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from novabank.application.dto.statement_dto import AccountStatementDTO, StatementEntryDTO
from novabank.application.services.banking_service import BankingService
from novabank.application.services.export_service import ExportService
from novabank.infrastructure.db.models import Base


@pytest.fixture
def sample_statement() -> AccountStatementDTO:
    """Create a fully reconciled sample AccountStatementDTO with realistic entries."""
    entry1 = StatementEntryDTO(
        transaction_id=1,
        transaction_ref="TXN-2026-001",
        created_at=datetime(2026, 1, 5, 10, 30, 0),
        transaction_type="DEPOSIT",
        direction="CREDIT",
        description="Payroll direct deposit",
        amount=Decimal("2500.00"),
        debit_amount=None,
        credit_amount=Decimal("2500.00"),
        balance_after=Decimal("3500.00"),
        currency="USD",
        created_by="SYSTEM",
        formatted_amount="$2,500.00",
        formatted_balance_after="$3,500.00",
        formatted_debit="",
        formatted_credit="+$2,500.00",
    )

    entry2 = StatementEntryDTO(
        transaction_id=2,
        transaction_ref="TXN-2026-002",
        created_at=datetime(2026, 1, 12, 14, 15, 0),
        transaction_type="WITHDRAWAL",
        direction="DEBIT",
        description="ATM Cash Withdrawal",
        amount=Decimal("200.00"),
        debit_amount=Decimal("200.00"),
        credit_amount=None,
        balance_after=Decimal("3300.00"),
        currency="USD",
        created_by="ATM-04",
        formatted_amount="$200.00",
        formatted_balance_after="$3,300.00",
        formatted_debit="-$200.00",
        formatted_credit="",
    )

    return AccountStatementDTO(
        account_number="100000000001",
        holder_name="Alice Anderson",
        account_status="Active",
        currency="USD",
        start_date=datetime(2026, 1, 1, 0, 0, 0),
        end_date=datetime(2026, 1, 31, 23, 59, 59),
        generated_at=datetime(2026, 2, 1, 9, 0, 0),
        opening_balance=Decimal("1000.00"),
        total_credits=Decimal("2500.00"),
        total_debits=Decimal("200.00"),
        net_change=Decimal("2300.00"),
        closing_balance=Decimal("3300.00"),
        transaction_count=2,
        entries=(entry1, entry2),
    )


def test_csv_export_rfc4180_line_endings_and_headers(sample_statement: AccountStatementDTO) -> None:
    """Verify generated CSV conforms strictly to RFC-4180 CRLF line terminators and headers."""
    csv_text = ExportService.export_statement_to_csv(sample_statement, include_summary=True)

    # RFC-4180 requires CRLF \r\n line terminators
    assert "\r\n" in csv_text

    # Parse with standard Python csv reader
    reader = list(csv.reader(io.StringIO(csv_text, newline="")))
    assert len(reader) > 10

    # Verify statement header fields
    header_dict = dict(reader[:13])
    assert header_dict["Account Number"] == "100000000001"
    assert header_dict["Account Holder"] == "Alice Anderson"
    assert header_dict["Account Status"] == "Active"
    assert header_dict["Currency"] == "USD"
    assert header_dict["Opening Balance"] == "1000.00"
    assert header_dict["Total Inflow (Credits)"] == "2500.00"
    assert header_dict["Total Outflow (Debits)"] == "200.00"
    assert header_dict["Closing Balance"] == "3300.00"
    assert header_dict["Mathematically Reconciled"] == "TRUE"

    # Find the table header row
    table_header_idx = [i for i, row in enumerate(reader) if row and row[0] == "Date"][0]
    assert reader[table_header_idx] == [
        "Date",
        "Reference",
        "Type",
        "Description",
        "Debit",
        "Credit",
        "Balance",
        "Currency",
    ]

    # Verify data rows
    row1 = reader[table_header_idx + 1]
    assert row1[0] == "2026-01-05 10:30:00"
    assert row1[1] == "TXN-2026-001"
    assert row1[2] == "DEPOSIT"
    assert row1[3] == "Payroll direct deposit"
    assert row1[4] == ""  # Debit is empty for credit
    assert row1[5] == "2500.00"
    assert row1[6] == "3500.00"
    assert row1[7] == "USD"

    row2 = reader[table_header_idx + 2]
    assert row2[0] == "2026-01-12 14:15:00"
    assert row2[1] == "TXN-2026-002"
    assert row2[2] == "WITHDRAWAL"
    assert row2[3] == "ATM Cash Withdrawal"
    assert row2[4] == "200.00"  # Debit is populated
    assert row2[5] == ""
    assert row2[6] == "3300.00"
    assert row2[7] == "USD"


def test_csv_export_without_summary_table_only(sample_statement: AccountStatementDTO) -> None:
    """Verify include_summary=False produces strictly the table headers and data rows."""
    csv_text = ExportService.export_statement_to_csv(sample_statement, include_summary=False)

    reader = list(csv.reader(io.StringIO(csv_text, newline="")))
    assert len(reader) == 3  # 1 header + 2 transactions

    assert reader[0] == [
        "Date",
        "Reference",
        "Type",
        "Description",
        "Debit",
        "Credit",
        "Balance",
        "Currency",
    ]
    assert reader[1][1] == "TXN-2026-001"
    assert reader[2][1] == "TXN-2026-002"


def test_csv_export_special_characters_escaping() -> None:
    """Verify robust quoting for commas, quotes, line breaks, and international characters."""
    special_entry = StatementEntryDTO(
        transaction_id=99,
        transaction_ref='REF-"SPECIAL",01',
        created_at=datetime(2026, 3, 15, 12, 0, 0),
        transaction_type="TRANSFER_OUT",
        direction="DEBIT",
        description='Payment for "Art, Wine & Cheese"\nInvoice #999',
        amount=Decimal("150.75"),
        debit_amount=Decimal("150.75"),
        credit_amount=None,
        balance_after=Decimal("849.25"),
        currency="EUR",
        created_by="Café München",
        formatted_amount="€150.75",
        formatted_balance_after="€849.25",
        formatted_debit="-€150.75",
        formatted_credit="",
    )

    stmt = AccountStatementDTO(
        account_number="200000000002",
        holder_name='René "The Artist" O\'Connor, Jr.',
        account_status="Active",
        currency="EUR",
        start_date=None,
        end_date=datetime(2026, 3, 31),
        generated_at=datetime(2026, 4, 1),
        opening_balance=Decimal("1000.00"),
        total_credits=Decimal("0.00"),
        total_debits=Decimal("150.75"),
        net_change=Decimal("-150.75"),
        closing_balance=Decimal("849.25"),
        transaction_count=1,
        entries=(special_entry,),
    )

    csv_text = ExportService.export_statement_to_csv(stmt, include_summary=True)

    # Parse back with standard CSV reader to verify round-trip fidelity
    reader = list(csv.reader(io.StringIO(csv_text, newline="")))

    # Verify holder name with quotes and commas
    header_dict = dict(reader[:11])
    assert header_dict["Account Holder"] == 'René "The Artist" O\'Connor, Jr.'

    # Find row
    table_header_idx = [i for i, row in enumerate(reader) if row and row[0] == "Date"][0]
    data_row = reader[table_header_idx + 1]

    # Verify reference and description containing quotes, commas, and newlines survived round-trip
    assert data_row[1] == 'REF-"SPECIAL",01'
    assert data_row[3] == 'Payment for "Art, Wine & Cheese"\nInvoice #999'
    assert data_row[7] == "EUR"


def test_csv_export_formula_injection_defense() -> None:
    """Verify formula injection triggers (=, +, -, @, \\t) are safely neutralized."""
    malicious_entry = StatementEntryDTO(
        transaction_id=1,
        transaction_ref="=cmd|'/C calc'!A0",
        created_at=datetime(2026, 1, 1),
        transaction_type="DEPOSIT",
        direction="CREDIT",
        description="@SUM(1+1)",
        amount=Decimal("10.00"),
        debit_amount=None,
        credit_amount=Decimal("10.00"),
        balance_after=Decimal("10.00"),
        currency="USD",
        created_by="hacker",
        formatted_amount="$10.00",
        formatted_balance_after="$10.00",
        formatted_debit="",
        formatted_credit="+$10.00",
    )

    stmt = AccountStatementDTO(
        account_number="+100000000003",
        holder_name="=HYPERLINK('http://malicious.com','Click')",
        account_status="Active",
        currency="USD",
        start_date=None,
        end_date=datetime(2026, 1, 1),
        generated_at=datetime(2026, 1, 2),
        opening_balance=Decimal("0.00"),
        total_credits=Decimal("10.00"),
        total_debits=Decimal("0.00"),
        net_change=Decimal("10.00"),
        closing_balance=Decimal("10.00"),
        transaction_count=1,
        entries=(malicious_entry,),
    )

    # 1. With formula sanitization enabled (default)
    csv_sanitized = ExportService.export_statement_to_csv(stmt, sanitize_formulas=True)
    reader_sanitized = list(csv.reader(io.StringIO(csv_sanitized, newline="")))
    header_dict = dict(reader_sanitized[:11])

    # Leading +, =, @ are prefixed with single quote '
    assert header_dict["Account Number"] == "'+100000000003"
    assert header_dict["Account Holder"] == "'=HYPERLINK('http://malicious.com','Click')"

    table_header_idx = [i for i, row in enumerate(reader_sanitized) if row and row[0] == "Date"][0]
    data_row = reader_sanitized[table_header_idx + 1]
    assert data_row[1] == "'=cmd|'/C calc'!A0"
    assert data_row[3] == "'@SUM(1+1)"

    # 2. With formula sanitization disabled
    csv_raw = ExportService.export_statement_to_csv(stmt, sanitize_formulas=False)
    reader_raw = list(csv.reader(io.StringIO(csv_raw, newline="")))
    raw_header = dict(reader_raw[:11])
    assert raw_header["Account Number"] == "+100000000003"
    assert raw_header["Account Holder"] == "=HYPERLINK('http://malicious.com','Click')"


def test_csv_export_empty_statement() -> None:
    """Verify empty statement produces valid CSV with 0 transaction rows."""
    empty_stmt = AccountStatementDTO(
        account_number="100000000004",
        holder_name="Bob Builder",
        account_status="Active",
        currency="USD",
        start_date=datetime(2026, 5, 1),
        end_date=datetime(2026, 5, 31),
        generated_at=datetime(2026, 6, 1),
        opening_balance=Decimal("500.00"),
        total_credits=Decimal("0.00"),
        total_debits=Decimal("0.00"),
        net_change=Decimal("0.00"),
        closing_balance=Decimal("500.00"),
        transaction_count=0,
        entries=(),
    )

    csv_text = ExportService.export_statement_to_csv(empty_stmt, include_summary=True)
    reader = list(csv.reader(io.StringIO(csv_text, newline="")))

    table_header_idx = [i for i, row in enumerate(reader) if row and row[0] == "Date"][0]
    # No rows after table header
    assert len(reader) == table_header_idx + 1


def test_csv_export_to_filesystem_file(
    sample_statement: AccountStatementDTO, tmp_path: Path
) -> None:
    """Verify writing directly to a filesystem path."""
    dest_file = tmp_path / "subfolder" / "statement_test.csv"
    result_path = ExportService.export_statement_to_csv(
        sample_statement,
        destination=dest_file,
    )

    assert result_path == str(dest_file.resolve())
    assert dest_file.exists()
    content = dest_file.read_text(encoding="utf-8")
    assert "NovaBank Official Account Statement" in content
    assert "TXN-2026-001" in content


def test_csv_export_transactions_direct_helper(
    sample_statement: AccountStatementDTO,
) -> None:
    """Verify standalone transaction sequence export."""
    csv_text = ExportService.export_transactions_to_csv(sample_statement.entries)
    reader = list(csv.reader(io.StringIO(csv_text, newline="")))

    assert len(reader) == 3
    assert reader[0][0] == "Date"
    assert reader[1][1] == "TXN-2026-001"
    assert reader[2][1] == "TXN-2026-002"


def test_banking_service_export_statement_csv_delegation(
    sample_statement: AccountStatementDTO,
) -> None:
    """Verify BankingService delegates CSV export cleanly."""
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    session_factory = sessionmaker(bind=engine)
    service = BankingService(session_factory=session_factory)

    csv_text = service.export_statement_csv(sample_statement)
    assert "NovaBank Official Account Statement" in csv_text
    assert "Alice Anderson" in csv_text
