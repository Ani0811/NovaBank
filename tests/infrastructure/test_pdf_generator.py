"""Tests for StatementPdfGenerator and enterprise bank statement PDF export."""

from __future__ import annotations

import os
from datetime import datetime
from decimal import Decimal
from pathlib import Path

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from novabank.application.dto.statement_dto import AccountStatementDTO, StatementEntryDTO
from novabank.application.services.banking_service import BankingService
from novabank.infrastructure.db.models import Base
from novabank.infrastructure.reporting.pdf_generator import StatementPdfGenerator

# Ensure offscreen platform for headless Qt PDF generation in CI/tests
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")


@pytest.fixture
def populated_statement() -> AccountStatementDTO:
    """Create a fully reconciled AccountStatementDTO for PDF testing."""
    entry1 = StatementEntryDTO(
        transaction_id=101,
        transaction_ref="TXN-98765432101",
        created_at=datetime(2026, 7, 5, 14, 20, 0),
        transaction_type="DEPOSIT",
        direction="CREDIT",
        description="Client invoice settlement",
        amount=Decimal("4500.00"),
        debit_amount=None,
        credit_amount=Decimal("4500.00"),
        balance_after=Decimal("7000.00"),
        currency="USD",
        created_by="WIRE-GW",
        formatted_amount="$4,500.00",
        formatted_balance_after="$7,000.00",
        formatted_debit="",
        formatted_credit="+$4,500.00",
    )

    entry2 = StatementEntryDTO(
        transaction_id=102,
        transaction_ref="TXN-98765432102",
        created_at=datetime(2026, 7, 18, 9, 45, 0),
        transaction_type="WITHDRAWAL",
        direction="DEBIT",
        description="Office rent electronic payment",
        amount=Decimal("1200.00"),
        debit_amount=Decimal("1200.00"),
        credit_amount=None,
        balance_after=Decimal("5800.00"),
        currency="USD",
        created_by="ACH-SYS",
        formatted_amount="$1,200.00",
        formatted_balance_after="$5,800.00",
        formatted_debit="-$1,200.00",
        formatted_credit="",
    )

    return AccountStatementDTO(
        account_number="123456789012",
        holder_name="Alexander Hamilton",
        account_status="Active",
        currency="USD",
        start_date=datetime(2026, 7, 1),
        end_date=datetime(2026, 7, 31, 23, 59, 59),
        generated_at=datetime(2026, 8, 1, 8, 0, 0),
        opening_balance=Decimal("2500.00"),
        total_credits=Decimal("4500.00"),
        total_debits=Decimal("1200.00"),
        net_change=Decimal("3300.00"),
        closing_balance=Decimal("5800.00"),
        transaction_count=2,
        entries=(entry1, entry2),
    )


def test_pdf_generation_magic_bytes_and_page_count(
    populated_statement: AccountStatementDTO,
) -> None:
    """Verify in-memory PDF generation produces standard %PDF- header and page count >= 1."""
    pdf_bytes = StatementPdfGenerator.generate_statement_pdf(
        populated_statement,
        destination_path=None,
    )

    assert isinstance(pdf_bytes, bytes)
    assert len(pdf_bytes) > 1000

    # PDF standard magic header
    assert pdf_bytes.startswith(b"%PDF-")

    # Verify page count is positive integer
    page_count = StatementPdfGenerator.extract_page_count(pdf_bytes)
    assert page_count >= 1


def test_pdf_generation_to_filesystem_file(
    populated_statement: AccountStatementDTO, tmp_path: Path
) -> None:
    """Verify writing PDF directly to filesystem path."""
    dest_path = tmp_path / "statements" / "july_2026.pdf"
    result_path = StatementPdfGenerator.generate_statement_pdf(
        populated_statement,
        destination_path=dest_path,
        bank_name="NovaBank Trust",
    )

    assert result_path == str(dest_path.resolve())
    assert dest_path.is_file()
    assert dest_path.stat().st_size > 1000

    raw_bytes = dest_path.read_bytes()
    assert raw_bytes.startswith(b"%PDF-")


def test_pdf_html_content_rendering(populated_statement: AccountStatementDTO) -> None:
    """Verify HTML template contains bank header, customer details, and transaction lines."""
    html_text = StatementPdfGenerator.generate_statement_html(
        populated_statement,
        bank_name="NovaBank National Trust",
    )

    assert "NovaBank National Trust" in html_text
    assert "Alexander Hamilton" in html_text
    assert "123456789012" in html_text
    assert "MATHEMATICALLY RECONCILED" in html_text
    assert "$2,500.00" in html_text  # Opening
    assert "$4,500.00" in html_text  # Total Credits
    assert "$1,200.00" in html_text  # Total Debits
    assert "$5,800.00" in html_text  # Closing
    assert "TXN-98765432101" in html_text
    assert "Client invoice settlement" in html_text
    assert "Office rent electronic payment" in html_text


def test_pdf_html_escaping_security() -> None:
    """Verify malicious input strings in customer fields are escaped to prevent HTML injection."""
    xss_entry = StatementEntryDTO(
        transaction_id=1,
        transaction_ref="<script>alert('xss')</script>",
        created_at=datetime(2026, 1, 1),
        transaction_type="<b>DEPOSIT</b>",
        direction="CREDIT",
        description="<img src=x onerror=alert(1)>",
        amount=Decimal("100.00"),
        debit_amount=None,
        credit_amount=Decimal("100.00"),
        balance_after=Decimal("100.00"),
        currency="USD",
        created_by="attacker",
        formatted_amount="$100.00",
        formatted_balance_after="$100.00",
        formatted_debit="",
        formatted_credit="+$100.00",
    )

    stmt = AccountStatementDTO(
        account_number="<script>hack()</script>",
        holder_name="John <b>Doe</b> & Co",
        account_status="Active",
        currency="USD",
        start_date=None,
        end_date=datetime(2026, 1, 1),
        generated_at=datetime(2026, 1, 2),
        opening_balance=Decimal("0.00"),
        total_credits=Decimal("100.00"),
        total_debits=Decimal("0.00"),
        net_change=Decimal("100.00"),
        closing_balance=Decimal("100.00"),
        transaction_count=1,
        entries=(xss_entry,),
    )

    html_text = StatementPdfGenerator.generate_statement_html(stmt)

    # HTML tags should be escaped
    assert "<script>" not in html_text
    assert "&lt;script&gt;" in html_text
    assert "<img" not in html_text
    assert "&lt;img" in html_text
    assert "John &lt;b&gt;Doe&lt;/b&gt; &amp; Co" in html_text


def test_pdf_empty_statement_rendering() -> None:
    """Verify zero transaction statement produces valid PDF with empty message."""
    empty_stmt = AccountStatementDTO(
        account_number="123456789999",
        holder_name="Empty Account Holder",
        account_status="Active",
        currency="USD",
        start_date=datetime(2026, 2, 1),
        end_date=datetime(2026, 2, 28),
        generated_at=datetime(2026, 3, 1),
        opening_balance=Decimal("100.00"),
        total_credits=Decimal("0.00"),
        total_debits=Decimal("0.00"),
        net_change=Decimal("0.00"),
        closing_balance=Decimal("100.00"),
        transaction_count=0,
        entries=(),
    )

    pdf_bytes = StatementPdfGenerator.generate_statement_pdf(empty_stmt)
    assert pdf_bytes.startswith(b"%PDF-")
    assert StatementPdfGenerator.extract_page_count(pdf_bytes) >= 1

    html_text = StatementPdfGenerator.generate_statement_html(empty_stmt)
    assert "No transactions recorded for this period." in html_text


def test_banking_service_export_statement_pdf_delegation(
    populated_statement: AccountStatementDTO,
) -> None:
    """Verify BankingService delegates PDF generation properly."""
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    session_factory = sessionmaker(bind=engine)
    service = BankingService(session_factory=session_factory)

    pdf_bytes = service.export_statement_pdf(populated_statement)
    assert isinstance(pdf_bytes, bytes)
    assert pdf_bytes.startswith(b"%PDF-")
