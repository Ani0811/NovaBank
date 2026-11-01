"""Service for exporting financial account statements and transaction ledgers to CSV and other formats."""

from __future__ import annotations

import csv
import io
from pathlib import Path
from typing import Optional, Sequence, TextIO, Union

from novabank.application.dto.statement_dto import AccountStatementDTO, StatementEntryDTO


class ExportService:
    """Service providing RFC-4180 compliant exports with formula injection defense."""

    FORMULA_PREFIXES = ("=", "+", "-", "@", "\t", "\r")

    LEDGER_HEADERS = (
        "Date",
        "Reference",
        "Type",
        "Description",
        "Debit",
        "Credit",
        "Balance",
        "Currency",
    )

    @classmethod
    def sanitize_field(cls, value: str, sanitize: bool = True) -> str:
        """Prevent CSV formula injection by neutralizing dangerous leading characters.

        Characters =, +, -, @, \\t, and \\r in spreadsheet applications can trigger formula
        execution or dynamic data exchange (DDE) if opened in Microsoft Excel or LibreOffice Calc.
        Prefixing with an apostrophe neutralizes execution while keeping the text visible.
        """
        if not sanitize or not value:
            return value
        if value[0] in cls.FORMULA_PREFIXES:
            return f"'{value}"
        return value

    @classmethod
    def export_statement_to_csv(
        cls,
        statement: AccountStatementDTO,
        destination: Optional[Union[str, Path, TextIO]] = None,
        *,
        include_summary: bool = True,
        encoding: str = "utf-8",
        sanitize_formulas: bool = True,
    ) -> str:
        """Export an AccountStatementDTO to an RFC-4180 compliant CSV.

        Args:
            statement: The AccountStatementDTO containing account metadata and transaction entries.
            destination: File path (str, Path), TextIO buffer, or None (to return CSV as string).
            include_summary: Whether to include metadata header cards before the ledger table.
            encoding: Text encoding when writing to file (default 'utf-8').
            sanitize_formulas: Whether to sanitize text fields against formula injection.

        Returns:
            The CSV text string if destination is None or a StringIO, or the file path string.
        """
        string_buffer = io.StringIO()
        writer = csv.writer(
            string_buffer,
            lineterminator="\r\n",
            quoting=csv.QUOTE_MINIMAL,
        )

        if include_summary:
            cls._write_summary_block(writer, statement, sanitize=sanitize_formulas)
            writer.writerow([])  # Blank row separating summary and ledger table

        # Write table headers
        writer.writerow(cls.LEDGER_HEADERS)

        # Write transaction records
        for entry in statement.entries:
            row = cls._format_entry_row(entry, sanitize=sanitize_formulas)
            writer.writerow(row)

        csv_content = string_buffer.getvalue()

        return cls._deliver_output(
            content=csv_content,
            destination=destination,
            encoding=encoding,
        )

    @classmethod
    def export_transactions_to_csv(
        cls,
        entries: Sequence[StatementEntryDTO],
        destination: Optional[Union[str, Path, TextIO]] = None,
        *,
        encoding: str = "utf-8",
        sanitize_formulas: bool = True,
    ) -> str:
        """Export arbitrary transaction entries directly to an RFC-4180 CSV table."""
        string_buffer = io.StringIO()
        writer = csv.writer(
            string_buffer,
            lineterminator="\r\n",
            quoting=csv.QUOTE_MINIMAL,
        )

        writer.writerow(cls.LEDGER_HEADERS)

        for entry in entries:
            row = cls._format_entry_row(entry, sanitize=sanitize_formulas)
            writer.writerow(row)

        csv_content = string_buffer.getvalue()

        return cls._deliver_output(
            content=csv_content,
            destination=destination,
            encoding=encoding,
        )

    @classmethod
    def _write_summary_block(
        cls,
        writer: csv._writer,
        statement: AccountStatementDTO,
        sanitize: bool,
    ) -> None:
        """Write statement metadata section."""
        period_str = (
            f"{statement.start_date.strftime('%Y-%m-%d')} to {statement.end_date.strftime('%Y-%m-%d')}"
            if statement.start_date
            else f"Inception to {statement.end_date.strftime('%Y-%m-%d')}"
        )
        gen_time = statement.generated_at.strftime("%Y-%m-%d %H:%M:%S")

        reconciled_str = "TRUE" if statement.is_reconciled() else "FALSE"

        writer.writerow(["NovaBank Official Account Statement", ""])
        writer.writerow(["Account Number", cls.sanitize_field(statement.account_number, sanitize)])
        writer.writerow(["Account Holder", cls.sanitize_field(statement.holder_name, sanitize)])
        writer.writerow(["Account Status", cls.sanitize_field(statement.account_status, sanitize)])
        writer.writerow(["Currency", statement.currency])
        writer.writerow(["Statement Period", period_str])
        writer.writerow(["Generated At", gen_time])
        writer.writerow(["Opening Balance", f"{statement.opening_balance:.2f}"])
        writer.writerow(["Total Inflow (Credits)", f"{statement.total_credits:.2f}"])
        writer.writerow(["Total Outflow (Debits)", f"{statement.total_debits:.2f}"])
        writer.writerow(["Closing Balance", f"{statement.closing_balance:.2f}"])
        writer.writerow(["Transaction Count", str(statement.transaction_count)])
        writer.writerow(["Mathematically Reconciled", reconciled_str])

    @classmethod
    def _format_entry_row(
        cls,
        entry: StatementEntryDTO,
        sanitize: bool,
    ) -> list[str]:
        """Convert a StatementEntryDTO into a clean, RFC-4180 CSV row."""
        date_str = entry.created_at.strftime("%Y-%m-%d %H:%M:%S")
        ref_str = cls.sanitize_field(entry.transaction_ref, sanitize)
        type_str = entry.transaction_type
        desc_str = cls.sanitize_field(entry.description, sanitize)

        debit_str = f"{entry.debit_amount:.2f}" if entry.debit_amount is not None else ""
        credit_str = f"{entry.credit_amount:.2f}" if entry.credit_amount is not None else ""
        balance_str = f"{entry.balance_after:.2f}"
        currency_str = entry.currency

        return [
            date_str,
            ref_str,
            type_str,
            desc_str,
            debit_str,
            credit_str,
            balance_str,
            currency_str,
        ]

    @classmethod
    def _deliver_output(
        cls,
        content: str,
        destination: Optional[Union[str, Path, TextIO]],
        encoding: str,
    ) -> str:
        """Write content to destination or return as string."""
        if destination is None:
            return content

        if isinstance(destination, (str, Path)):
            path = Path(destination).resolve()
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(content, encoding=encoding)
            return str(path)

        # File-like object (TextIO)
        destination.write(content)
        return content
