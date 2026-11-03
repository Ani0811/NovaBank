"""Account statement generation service providing historical reconciliation and ledger reporting."""

from __future__ import annotations

from datetime import date, datetime, timezone
from decimal import Decimal
from typing import Optional, Union

from sqlalchemy.orm import Session, sessionmaker

from novabank.application.dto.statement_dto import AccountStatementDTO, StatementEntryDTO
from novabank.domain.exceptions import AccountNotFoundError
from novabank.domain.value_objects.account_number import AccountNumber
from novabank.domain.value_objects.transaction_type import TransactionDirection
from novabank.infrastructure.repositories.sql_account_repository import SQLAccountRepository
from novabank.infrastructure.repositories.sql_transaction_repository import SQLTransactionRepository


class StatementService:
    """Application service calculating historical statements with guaranteed mathematical reconciliation.

    Invariant guaranteed:
        Opening Balance + Total Credits - Total Debits == Closing Balance
    """

    def __init__(self, session_factory: sessionmaker[Session]) -> None:
        self._session_factory = session_factory

    @staticmethod
    def _normalize_account_number(account_number: Union[AccountNumber, str]) -> str:
        if isinstance(account_number, AccountNumber):
            return account_number.value
        return str(account_number).strip().replace("-", "").replace(" ", "")

    @staticmethod
    def _normalize_start_date(start_date: Optional[Union[date, datetime]]) -> Optional[datetime]:
        if start_date is None:
            return None
        if isinstance(start_date, datetime):
            if start_date.tzinfo is None:
                return start_date.replace(tzinfo=timezone.utc)
            return start_date.astimezone(timezone.utc)
        # Plain date -> start of day UTC
        return datetime.combine(start_date, datetime.min.time(), tzinfo=timezone.utc)

    @staticmethod
    def _normalize_end_date(end_date: Optional[Union[date, datetime]]) -> datetime:
        if end_date is None:
            return datetime.now(timezone.utc)
        if isinstance(end_date, datetime):
            if end_date.tzinfo is None:
                return end_date.replace(tzinfo=timezone.utc)
            return end_date.astimezone(timezone.utc)
        # Plain date -> end of day UTC (23:59:59.999999)
        return datetime.combine(end_date, datetime.max.time(), tzinfo=timezone.utc)

    def generate_statement(
        self,
        account_number: Union[AccountNumber, str],
        start_date: Optional[Union[date, datetime]] = None,
        end_date: Optional[Union[date, datetime]] = None,
    ) -> AccountStatementDTO:
        """Generate a reconciled historical statement for the specified account and date range.

        Args:
            account_number: 12-digit account number (str or AccountNumber VO).
            start_date: Starting boundary (inclusive). If None, starts from inception.
            end_date: Ending boundary (inclusive). If None, defaults to current UTC time.

        Returns:
            AccountStatementDTO containing opening balance, line items, and reconciled closing balance.

        Raises:
            AccountNotFoundError: If account does not exist.
            ValueError: If start_date is strictly after end_date.
        """
        clean_acc = self._normalize_account_number(account_number)
        norm_start = self._normalize_start_date(start_date)
        norm_end = self._normalize_end_date(end_date)

        if norm_start is not None and norm_start > norm_end:
            raise ValueError(
                f"Start date ({norm_start.isoformat()}) cannot be after end date ({norm_end.isoformat()})."
            )

        with self._session_factory() as session:
            account_repo = SQLAccountRepository(session)
            tx_repo = SQLTransactionRepository(session)

            account = account_repo.get_by_number(clean_acc)
            if account is None:
                raise AccountNotFoundError(f"Account '{clean_acc}' not found.")

            # 1. Calculate opening balance strictly prior to start_date
            if norm_start is None:
                opening_balance = Decimal("0.00")
            else:
                prior_tx = tx_repo.get_last_transaction_before(clean_acc, before_date=norm_start)
                opening_balance = (
                    prior_tx.balance_after.amount if prior_tx is not None else Decimal("0.00")
                )

            # 2. Query period transactions chronologically
            tx_list = tx_repo.list_by_account(
                account_number=clean_acc,
                start_date=norm_start,
                end_date=norm_end,
                limit=None,
                offset=0,
                descending=False,
            )

            # 3. Aggregate period totals
            total_credits = Decimal("0.00")
            total_debits = Decimal("0.00")
            entries: list[StatementEntryDTO] = []

            for tx in tx_list:
                if tx.direction == TransactionDirection.CREDIT:
                    total_credits += tx.amount.amount
                elif tx.direction == TransactionDirection.DEBIT:
                    total_debits += tx.amount.amount
                entries.append(StatementEntryDTO.from_entity(tx))

            net_change = total_credits - total_debits
            closing_balance = opening_balance + net_change

            # Ledger reconciliation invariant verification
            if entries:
                expected_last = entries[-1].balance_after
                if closing_balance != expected_last:
                    raise RuntimeError(
                        f"Statement reconciliation mismatch: computed closing balance "
                        f"{closing_balance} != last transaction balance {expected_last}."
                    )
            elif closing_balance != opening_balance:
                raise RuntimeError("Statement reconciliation mismatch on empty period.")

            statement = AccountStatementDTO(
                account_number=account.account_number.value,
                holder_name=account.holder_name,
                account_status="Active" if account.is_active else "Closed",
                currency=account.balance.currency,
                start_date=norm_start,
                end_date=norm_end,
                generated_at=datetime.now(timezone.utc),
                opening_balance=opening_balance,
                total_credits=total_credits,
                total_debits=total_debits,
                net_change=net_change,
                closing_balance=closing_balance,
                transaction_count=len(entries),
                entries=tuple(entries),
            )

            if not statement.is_reconciled():
                raise RuntimeError("Statement must satisfy reconciliation formula: opening + credits - debits == closing")
            return statement
