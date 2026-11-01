"""Professional PDF Statement Generator for NovaBank account statements."""

from __future__ import annotations

import html
import re
from pathlib import Path
from typing import Optional, Union

from PySide6.QtCore import QBuffer, QIODevice
from PySide6.QtGui import QPageLayout, QPageSize, QPdfWriter, QTextDocument
from PySide6.QtWidgets import QApplication

from novabank.application.dto.statement_dto import AccountStatementDTO


class StatementPdfGenerator:
    """Generates enterprise-grade, certified PDF bank statements using PySide6 QTextDocument and QPdfWriter."""

    @classmethod
    def generate_statement_pdf(
        cls,
        statement: AccountStatementDTO,
        destination_path: Optional[Union[str, Path]] = None,
        *,
        bank_name: str = "NovaBank National Banking & Trust",
    ) -> Union[str, bytes]:
        """Generate an official account statement PDF.

        Args:
            statement: Reconciled AccountStatementDTO.
            destination_path: Optional file path. If None, returns PDF bytes directly.
            bank_name: Bank brand name.

        Returns:
            Resolved file path string if destination_path provided, or raw PDF bytes if None.
        """
        # Ensure a QApplication exists for font, document, and widget rendering
        _ = QApplication.instance() or QApplication([])

        html_content = cls.generate_statement_html(statement, bank_name=bank_name)

        doc = QTextDocument()
        doc.setHtml(html_content)

        if destination_path is not None:
            resolved_path = Path(destination_path).resolve()
            resolved_path.parent.mkdir(parents=True, exist_ok=True)

            writer = QPdfWriter(str(resolved_path))
            writer.setPageSize(QPageSize(QPageSize.PageSizeId.A4))
            writer.setPageOrientation(QPageLayout.Orientation.Portrait)
            doc.print_(writer)
            del writer
            return str(resolved_path)

        # In-memory byte generation via QBuffer
        buffer = QBuffer()
        buffer.open(QIODevice.OpenModeFlag.WriteOnly)

        writer = QPdfWriter(buffer)
        writer.setPageSize(QPageSize(QPageSize.PageSizeId.A4))
        writer.setPageOrientation(QPageLayout.Orientation.Portrait)
        doc.print_(writer)
        del writer

        pdf_bytes = bytes(buffer.data().data())
        buffer.close()
        return pdf_bytes

    @classmethod
    def extract_page_count(cls, pdf_bytes: bytes) -> int:
        """Extract the number of pages from raw PDF bytes."""
        matches = re.findall(rb"/Type\s*/Page\b", pdf_bytes)
        return len(matches)

    @classmethod
    def generate_statement_html(
        cls,
        statement: AccountStatementDTO,
        bank_name: str = "NovaBank National Banking & Trust",
    ) -> str:
        """Generate clean, certified statement HTML formatted for QTextDocument pagination."""
        period_str = (
            f"{statement.start_date.strftime('%B %d, %Y')} to {statement.end_date.strftime('%B %d, %Y')}"
            if statement.start_date
            else f"Inception to {statement.end_date.strftime('%B %d, %Y')}"
        )
        gen_str = statement.generated_at.strftime("%B %d, %Y %H:%M:%S UTC")

        reconciled_badge = (
            "<span style='color: #059669; font-weight: bold;'>✓ MATHEMATICALLY RECONCILED</span>"
            if statement.is_reconciled()
            else "<span style='color: #dc2626; font-weight: bold;'>⚠ UNRECONCILED DISCREPANCY DETECTED</span>"
        )

        # Build ledger rows
        ledger_rows_html = []
        if not statement.entries:
            ledger_rows_html.append(
                "<tr><td colspan='7' style='padding: 16px; text-align: center; color: #64748b; font-style: italic; border-bottom: 1px solid #e2e8f0;'>"
                "No transactions recorded for this period."
                "</td></tr>"
            )
        else:
            for idx, entry in enumerate(statement.entries):
                bg_color = "#ffffff" if idx % 2 == 0 else "#f8fafc"
                dt_str = entry.created_at.strftime("%Y-%m-%d %H:%M")
                ref_str = html.escape(entry.transaction_ref)
                type_str = html.escape(entry.transaction_type)
                desc_str = html.escape(entry.description)

                debit_cell = (
                    f"<span style='color: #dc2626; font-weight: bold;'>-${entry.debit_amount:,.2f}</span>"
                    if entry.debit_amount is not None
                    else ""
                )
                credit_cell = (
                    f"<span style='color: #059669; font-weight: bold;'>+${entry.credit_amount:,.2f}</span>"
                    if entry.credit_amount is not None
                    else ""
                )
                bal_cell = f"${entry.balance_after:,.2f}"

                row_html = f"""
                <tr style='background-color: {bg_color};'>
                    <td style='padding: 6px 8px; border-bottom: 1px solid #e2e8f0; font-size: 10pt;'>{dt_str}</td>
                    <td style='padding: 6px 8px; border-bottom: 1px solid #e2e8f0; font-family: monospace; font-size: 9pt;'>{ref_str}</td>
                    <td style='padding: 6px 8px; border-bottom: 1px solid #e2e8f0; font-size: 9pt;'>{type_str}</td>
                    <td style='padding: 6px 8px; border-bottom: 1px solid #e2e8f0; font-size: 10pt;'>{desc_str}</td>
                    <td style='padding: 6px 8px; border-bottom: 1px solid #e2e8f0; text-align: right; font-size: 10pt;'>{debit_cell}</td>
                    <td style='padding: 6px 8px; border-bottom: 1px solid #e2e8f0; text-align: right; font-size: 10pt;'>{credit_cell}</td>
                    <td style='padding: 6px 8px; border-bottom: 1px solid #e2e8f0; text-align: right; font-weight: bold; font-size: 10pt;'>{bal_cell}</td>
                </tr>
                """
                ledger_rows_html.append(row_html)

        rows_joined = "\n".join(ledger_rows_html)

        return f"""<!DOCTYPE html>
<html>
<head>
<meta charset="utf-8">
<style>
  body {{
    font-family: Arial, Helvetica, sans-serif;
    color: #1e293b;
    margin: 20px;
    font-size: 10pt;
  }}
  h1 {{
    color: #1e3a8a;
    margin: 0;
    font-size: 22pt;
    font-weight: bold;
  }}
  h2 {{
    color: #0f172a;
    font-size: 14pt;
    margin-top: 15px;
    margin-bottom: 8px;
    border-bottom: 2px solid #2563eb;
    padding-bottom: 4px;
  }}
  table {{
    width: 100%;
    border-collapse: collapse;
  }}
</style>
</head>
<body>

  <!-- Bank Header -->
  <table width="100%" style="border-bottom: 3px solid #1e3a8a; padding-bottom: 12px; margin-bottom: 15px;">
    <tr>
      <td width="60%" valign="top">
        <h1>{html.escape(bank_name)}</h1>
        <p style="color: #64748b; margin: 4px 0 0 0; font-size: 9pt;">
          Member FDIC  •  Equal Housing Lender  •  Official Electronic Banking Record
        </p>
      </td>
      <td width="40%" align="right" valign="top">
        <h3 style="color: #1e3a8a; margin: 0; font-size: 14pt;">ACCOUNT STATEMENT</h3>
        <p style="color: #64748b; margin: 4px 0 0 0; font-size: 9pt;">Statement Period: <b>{period_str}</b></p>
        <p style="color: #64748b; margin: 2px 0 0 0; font-size: 8pt;">Issued: {gen_str}</p>
      </td>
    </tr>
  </table>

  <!-- Customer & Account Summary Box -->
  <table width="100%" style="background-color: #f1f5f9; border: 1px solid #cbd5e1; border-radius: 6px; margin-bottom: 15px; padding: 10px;">
    <tr>
      <td width="50%" valign="top">
        <table width="100%">
          <tr>
            <td width="35%" style="color: #64748b; font-size: 9pt; padding: 2px 0;">Account Holder:</td>
            <td style="font-weight: bold; font-size: 11pt; padding: 2px 0;">{html.escape(statement.holder_name)}</td>
          </tr>
          <tr>
            <td style="color: #64748b; font-size: 9pt; padding: 2px 0;">Account Number:</td>
            <td style="font-family: monospace; font-weight: bold; font-size: 11pt; padding: 2px 0;">{html.escape(statement.account_number)}</td>
          </tr>
          <tr>
            <td style="color: #64748b; font-size: 9pt; padding: 2px 0;">Account Status:</td>
            <td style="font-weight: bold; font-size: 9pt; padding: 2px 0;">{html.escape(statement.account_status)}</td>
          </tr>
        </table>
      </td>
      <td width="50%" valign="top">
        <table width="100%">
          <tr>
            <td width="40%" style="color: #64748b; font-size: 9pt; padding: 2px 0;">Currency:</td>
            <td style="font-weight: bold; font-size: 9pt; padding: 2px 0;">{html.escape(statement.currency)}</td>
          </tr>
          <tr>
            <td style="color: #64748b; font-size: 9pt; padding: 2px 0;">Audit Integrity:</td>
            <td style="padding: 2px 0; font-size: 9pt;">{reconciled_badge}</td>
          </tr>
          <tr>
            <td style="color: #64748b; font-size: 9pt; padding: 2px 0;">Transactions:</td>
            <td style="font-weight: bold; font-size: 9pt; padding: 2px 0;">{statement.transaction_count} recorded</td>
          </tr>
        </table>
      </td>
    </tr>
  </table>

  <!-- Balance Summary Financial Strip -->
  <table width="100%" style="margin-bottom: 20px; text-align: center; border-collapse: separate; border-spacing: 6px;">
    <tr>
      <td width="25%" style="background-color: #f8fafc; border: 1px solid #cbd5e1; padding: 8px; border-radius: 4px;">
        <div style="color: #64748b; font-size: 8pt; text-transform: uppercase;">Opening Balance</div>
        <div style="color: #0f172a; font-size: 13pt; font-weight: bold; margin-top: 3px;">${statement.opening_balance:,.2f}</div>
      </td>
      <td width="25%" style="background-color: #ecfdf5; border: 1px solid #a7f3d0; padding: 8px; border-radius: 4px;">
        <div style="color: #065f46; font-size: 8pt; text-transform: uppercase;">Total Credits (+)</div>
        <div style="color: #059669; font-size: 13pt; font-weight: bold; margin-top: 3px;">+${statement.total_credits:,.2f}</div>
      </td>
      <td width="25%" style="background-color: #fef2f2; border: 1px solid #fecaca; padding: 8px; border-radius: 4px;">
        <div style="color: #991b1b; font-size: 8pt; text-transform: uppercase;">Total Debits (-)</div>
        <div style="color: #dc2626; font-size: 13pt; font-weight: bold; margin-top: 3px;">-${statement.total_debits:,.2f}</div>
      </td>
      <td width="25%" style="background-color: #f0f9ff; border: 1px solid #bae6fd; padding: 8px; border-radius: 4px;">
        <div style="color: #0369a1; font-size: 8pt; text-transform: uppercase;">Closing Balance</div>
        <div style="color: #0284c7; font-size: 13pt; font-weight: bold; margin-top: 3px;">${statement.closing_balance:,.2f}</div>
      </td>
    </tr>
  </table>

  <!-- Transaction Ledger Table -->
  <h2>Transaction Ledger History</h2>
  <table width="100%" style="border: 1px solid #cbd5e1; margin-bottom: 25px;">
    <thead>
      <tr style="background-color: #0f172a; color: #ffffff;">
        <th style="padding: 8px; text-align: left; font-size: 9pt; width: 15%;">Date & Time</th>
        <th style="padding: 8px; text-align: left; font-size: 9pt; width: 14%;">Reference ID</th>
        <th style="padding: 8px; text-align: left; font-size: 9pt; width: 12%;">Type</th>
        <th style="padding: 8px; text-align: left; font-size: 9pt; width: 27%;">Description</th>
        <th style="padding: 8px; text-align: right; font-size: 9pt; width: 10%;">Debit (-)</th>
        <th style="padding: 8px; text-align: right; font-size: 9pt; width: 10%;">Credit (+)</th>
        <th style="padding: 8px; text-align: right; font-size: 9pt; width: 12%;">Balance</th>
      </tr>
    </thead>
    <tbody>
      {rows_joined}
    </tbody>
  </table>

  <!-- Footer Certification -->
  <table width="100%" style="border-top: 1px solid #cbd5e1; padding-top: 10px; margin-top: 20px;">
    <tr>
      <td style="color: #64748b; font-size: 8pt;">
        NovaBank National Banking & Trust • Customer Support: 1-800-555-NOVA • support@novabank.com<br>
        <i>Please examine this statement immediately upon receipt. Report any discrepancies within 30 days.</i>
      </td>
      <td align="right" valign="top" style="color: #94a3b8; font-size: 8pt;">
        Document ID: NB-STMT-{html.escape(statement.account_number)}
      </td>
    </tr>
  </table>

</body>
</html>
"""
