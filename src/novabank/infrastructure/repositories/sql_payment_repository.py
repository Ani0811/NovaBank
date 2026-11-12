"""SQLAlchemy implementation of PaymentRepositoryInterface."""

from __future__ import annotations

from typing import Optional, Union

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from novabank.domain.entities.payment import PaymentTransaction
from novabank.domain.repositories.payment_repository import PaymentRepositoryInterface
from novabank.domain.value_objects.account_number import AccountNumber
from novabank.infrastructure.db.models import PaymentTransactionModel


class SQLPaymentRepository(PaymentRepositoryInterface):
    """SQL repository for persistent payment gateway authorizations and settlements."""

    def __init__(self, session: Session) -> None:
        self._session = session

    def _normalize(self, account_number: Union[AccountNumber, str]) -> str:
        if isinstance(account_number, AccountNumber):
            return account_number.value
        return str(account_number).strip().replace("-", "").replace(" ", "")

    def save(self, payment: PaymentTransaction) -> None:
        """Persist a new or modified payment transaction record."""
        model = self._session.get(PaymentTransactionModel, payment.payment_id)
        if model is None:
            model = PaymentTransactionModel.from_entity(payment)
            self._session.add(model)
        else:
            model.status = payment.status.value
            model.settled_at = payment.settled_at
            model.failure_reason = payment.failure_reason
            model.refund_reason = payment.refund_reason
        self._session.flush()

    def get_by_id(self, payment_id: str) -> Optional[PaymentTransaction]:
        """Fetch payment transaction by unique payment_id."""
        clean_id = payment_id.strip()
        model = self._session.get(PaymentTransactionModel, clean_id)
        return model.to_entity() if model is not None else None

    def get_by_idempotency_key(self, key: str) -> Optional[PaymentTransaction]:
        """Fetch payment transaction by unique idempotency key."""
        clean_key = key.strip()
        stmt = select(PaymentTransactionModel).where(
            PaymentTransactionModel.idempotency_key == clean_key
        )
        model = self._session.execute(stmt).scalar_one_or_none()
        return model.to_entity() if model is not None else None

    def list_payments(
        self,
        account_number: Optional[Union[AccountNumber, str]] = None,
        channel: Optional[str] = None,
        status: Optional[str] = None,
        limit: int = 50,
        offset: int = 0,
    ) -> tuple[list[PaymentTransaction], int]:
        """Retrieve paginated payment transactions with optional filters."""
        conditions = []

        if account_number is not None:
            acc_num = self._normalize(account_number)
            if acc_num:
                conditions.append(PaymentTransactionModel.account_number == acc_num)

        if channel is not None and channel.strip() and channel.strip().upper() != "ALL":
            conditions.append(PaymentTransactionModel.channel == channel.strip().upper())

        if status is not None and status.strip() and status.strip().upper() != "ALL":
            conditions.append(PaymentTransactionModel.status == status.strip().upper())

        # Total count
        count_stmt = select(func.count(PaymentTransactionModel.payment_id))
        if conditions:
            count_stmt = count_stmt.where(*conditions)
        total_count = int(self._session.execute(count_stmt).scalar() or 0)

        # Paginated data
        data_stmt = (
            select(PaymentTransactionModel)
            .order_by(PaymentTransactionModel.created_at.desc())
            .offset(offset)
            .limit(max(1, limit))
        )
        if conditions:
            data_stmt = data_stmt.where(*conditions)

        models = self._session.execute(data_stmt).scalars().all()
        return [m.to_entity() for m in models], total_count

