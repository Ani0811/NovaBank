"""SQLAlchemy implementation of TransactionRepositoryInterface."""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal
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
        limit: Optional[int] = 50,
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

        if offset > 0:
            stmt = stmt.offset(offset)
        if limit is not None:
            stmt = stmt.limit(max(1, limit))

        models = self._session.execute(stmt).scalars().all()
        return [m.to_entity() for m in models]

    def get_last_transaction_before(
        self,
        account_number: Union[AccountNumber, str],
        before_date: datetime,
    ) -> Optional[Transaction]:
        """Fetch the most recent transaction strictly before the given date."""
        acc_num = self._normalize_account_number(account_number)
        stmt = (
            select(TransactionModel)
            .where(
                TransactionModel.account_number == acc_num,
                TransactionModel.created_at < before_date,
            )
            .order_by(
                TransactionModel.created_at.desc(),
                TransactionModel.transaction_id.desc(),
            )
            .limit(1)
        )
        model = self._session.execute(stmt).scalar_one_or_none()
        return model.to_entity() if model is not None else None

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

    def search_transactions(
        self,
        account_number: Optional[Union[AccountNumber, str]] = None,
        start_date: Optional[datetime] = None,
        end_date: Optional[datetime] = None,
        tx_type: Optional[str] = None,
        min_amount: Optional[Decimal] = None,
        max_amount: Optional[Decimal] = None,
        limit: int = 50,
        offset: int = 0,
        descending: bool = True,
    ) -> tuple[list[Transaction], int]:
        """Search transactions with multi-criteria filters across the entire ledger or specific account."""
        conditions = []

        if account_number is not None:
            acc_num = self._normalize_account_number(account_number)
            if acc_num:
                conditions.append(TransactionModel.account_number == acc_num)

        if start_date is not None:
            conditions.append(TransactionModel.created_at >= start_date)

        if end_date is not None:
            conditions.append(TransactionModel.created_at <= end_date)

        if tx_type is not None and tx_type.strip() and tx_type.strip().upper() != "ALL":
            conditions.append(TransactionModel.transaction_type == tx_type.strip().upper())

        if min_amount is not None:
            conditions.append(TransactionModel.amount >= min_amount)

        if max_amount is not None:
            conditions.append(TransactionModel.amount <= max_amount)

        # Count total matches
        count_stmt = select(func.count(TransactionModel.transaction_id))
        if conditions:
            count_stmt = count_stmt.where(*conditions)
        total_count = int(self._session.execute(count_stmt).scalar() or 0)

        # Query paginated rows
        data_stmt = select(TransactionModel)
        if conditions:
            data_stmt = data_stmt.where(*conditions)

        if descending:
            data_stmt = data_stmt.order_by(
                TransactionModel.created_at.desc(), TransactionModel.transaction_id.desc()
            )
        else:
            data_stmt = data_stmt.order_by(
                TransactionModel.created_at.asc(), TransactionModel.transaction_id.asc()
            )

        if offset > 0:
            data_stmt = data_stmt.offset(offset)
        if limit is not None:
            data_stmt = data_stmt.limit(max(1, limit))

        models = self._session.execute(data_stmt).scalars().all()
        return [m.to_entity() for m in models], total_count
