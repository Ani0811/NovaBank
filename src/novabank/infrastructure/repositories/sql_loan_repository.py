"""SQLAlchemy implementation of LoanRepositoryInterface."""

from __future__ import annotations

from typing import Optional, Union

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from novabank.domain.entities.loan import LoanContract
from novabank.domain.repositories.loan_repository import LoanRepositoryInterface
from novabank.domain.value_objects.account_number import AccountNumber
from novabank.infrastructure.db.models import LoanContractModel


class SQLLoanRepository(LoanRepositoryInterface):
    """SQL repository for persistent commercial loan contracts and amortization tracking."""

    def __init__(self, session: Session) -> None:
        self._session = session

    def _normalize(self, account_number: Union[AccountNumber, str]) -> str:
        if isinstance(account_number, AccountNumber):
            return account_number.value
        return str(account_number).strip().replace("-", "").replace(" ", "")

    def save(self, loan: LoanContract) -> None:
        """Persist a new or modified commercial loan contract."""
        model = self._session.get(LoanContractModel, loan.loan_id)
        if model is None:
            model = LoanContractModel.from_entity(loan)
            self._session.add(model)
        else:
            model.status = loan.status.value
            model.outstanding_balance = loan.outstanding_balance.amount
            model.next_due_date = loan.next_due_date
            # Update serialized schedule
            model.schedule_json = [
                {
                    "installment_number": item.installment_number,
                    "due_date": item.due_date.isoformat(),
                    "payment_amount": str(item.payment_amount.amount),
                    "principal_amount": str(item.principal_amount.amount),
                    "interest_amount": str(item.interest_amount.amount),
                    "remaining_balance": str(item.remaining_balance.amount),
                    "is_paid": item.is_paid,
                    "paid_date": item.paid_date.isoformat() if item.paid_date else None,
                }
                for item in loan.schedule
            ]
        self._session.flush()

    def get_by_id(self, loan_id: str) -> Optional[LoanContract]:
        """Fetch loan contract by unique facility identifier."""
        clean_id = loan_id.strip()
        model = self._session.get(LoanContractModel, clean_id)
        return model.to_entity() if model is not None else None

    def list_loans(
        self,
        account_number: Optional[Union[AccountNumber, str]] = None,
        status: Optional[str] = None,
        limit: int = 50,
        offset: int = 0,
    ) -> tuple[list[LoanContract], int]:
        """Retrieve paginated loan facilities matching optional filter criteria."""
        conditions = []

        if account_number is not None:
            acc_num = self._normalize(account_number)
            if acc_num:
                conditions.append(LoanContractModel.account_number == acc_num)

        if status is not None and status.strip() and status.strip().upper() != "ALL":
            conditions.append(LoanContractModel.status == status.strip().upper())

        # Total count query
        count_stmt = select(func.count(LoanContractModel.loan_id))
        if conditions:
            count_stmt = count_stmt.where(*conditions)
        total_count = int(self._session.execute(count_stmt).scalar() or 0)

        # Paginated data query
        data_stmt = (
            select(LoanContractModel)
            .order_by(LoanContractModel.originated_at.desc())
            .offset(offset)
            .limit(max(1, limit))
        )
        if conditions:
            data_stmt = data_stmt.where(*conditions)

        models = self._session.execute(data_stmt).scalars().all()
        return [m.to_entity() for m in models], total_count
