"""SQLAlchemy implementation of TransactionRepositoryInterface."""

from __future__ import annotations

from datetime import datetime
from typing import Optional, Union

from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from novabank.domain.entities.transaction import Transaction
from novabank.domain.exceptions import DuplicateTransactionRefError
from novabank.domain.repositories.transaction_repository import TransactionRepositoryInterface
from novabank.domain.value_objects.account_number import AccountNumber
from novabank.infrastructure.db.models import TransactionModel


class SQLTransactionRepository(TransactionRepositoryInterface):
    """SQL repository for immutable Transaction ledger entries using SQLAlchemy 2.0.

    Guarantees:
    - Transactions are strictly append-only (no update or delete operations).
    - Idempotency via transaction_ref uniqueness constraint.
    - Zero string interpolation; 100% parameterized queries.
    """

    def __init__(self, session: Session) -> None:
        self._session = session

    def _normalize_account_number(self, account_number: Union[AccountNumber, str]) -> str:
        if isinstance(account_number, AccountNumber):
            return account_number.value
        return str(account_number).strip().replace("-", "").replace(" ", "")

    def append(self, transaction: Transaction) -> None:
        """Append an immutable transaction to the ledger.

        Raises:
            DuplicateTransactionRefError: If transaction_ref already exists in ledger.
        """
        ref_check_stmt = select(func.count(TransactionModel.transaction_id)).where(
            TransactionModel.transaction_ref == transaction.transaction_ref
        )
        existing_count = self._session.execute(ref_check_stmt).scalar()
        if existing_count and existing_count > 0:
            raise DuplicateTransactionRefError(
                f"Transaction with reference '{transaction.transaction_ref}' already exists."
            )

        model = TransactionModel.from_entity(transaction)
        self._session.add(model)
        try:
            self._session.flush()
        except IntegrityError as exc:
            self._session.rollback()
            raise DuplicateTransactionRefError(
                f"Transaction with reference '{transaction.transaction_ref}' already exists."
            ) from exc

    def get_by_ref(self, transaction_ref: str) -> Optional[Transaction]:
        """Fetch a transaction by its unique reference string with parameterized query."""
        clean_ref = str(transaction_ref).strip()
        stmt = select(TransactionModel).where(TransactionModel.transaction_ref == clean_ref)
        model = self._session.execute(stmt).scalar_one_or_none()
        return model.to_entity() if model is not None else None

    def list_by_account(
        self,
        account_number: Union[AccountNumber, str],
        start_date: Optional[datetime] = None,
        end_date: Optional[datetime] = None,
        limit: int = 50,
        offset: int = 0,
        descending: bool = True,
    ) -> list[Transaction]:
        """Fetch paginated transactions for an account with parameterized filtering."""
        acc_num = self._normalize_account_number(account_number)
        stmt = select(TransactionModel).where(TransactionModel.account_number == acc_num)

        if start_date is not None:
            stmt = stmt.where(TransactionModel.created_at >= start_date)

        if end_date is not None:
            stmt = stmt.where(TransactionModel.created_at <= end_date)

        if descending:
            stmt = stmt.order_by(
                TransactionModel.created_at.desc(), TransactionModel.transaction_id.desc()
            )
        else:
            stmt = stmt.order_by(
                TransactionModel.created_at.asc(), TransactionModel.transaction_id.asc()
            )

        stmt = stmt.offset(max(0, offset)).limit(max(1, limit))
        models = self._session.execute(stmt).scalars().all()
        return [m.to_entity() for m in models]

    def count_by_account(
        self,
        account_number: Union[AccountNumber, str],
        start_date: Optional[datetime] = None,
        end_date: Optional[datetime] = None,
    ) -> int:
        """Count total transactions for an account with parameterized filtering."""
        acc_num = self._normalize_account_number(account_number)
        stmt = select(func.count(TransactionModel.transaction_id)).where(
            TransactionModel.account_number == acc_num
        )

        if start_date is not None:
            stmt = stmt.where(TransactionModel.created_at >= start_date)

        if end_date is not None:
            stmt = stmt.where(TransactionModel.created_at <= end_date)

        count = self._session.execute(stmt).scalar()
        return int(count or 0)
