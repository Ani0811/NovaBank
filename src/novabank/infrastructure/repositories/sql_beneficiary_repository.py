"""SQLAlchemy implementation of BeneficiaryRepositoryInterface."""

from __future__ import annotations

from typing import Optional, Union

from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from novabank.domain.entities.beneficiary import Beneficiary
from novabank.domain.repositories.beneficiary_repository import BeneficiaryRepositoryInterface
from novabank.domain.value_objects.account_number import AccountNumber
from novabank.infrastructure.db.models import BeneficiaryModel


class SQLBeneficiaryRepository(BeneficiaryRepositoryInterface):
    """SQL repository for managing saved payees and beneficiaries."""

    def __init__(self, session: Session) -> None:
        self._session = session

    def _normalize(self, account_number: Union[AccountNumber, str]) -> str:
        if isinstance(account_number, AccountNumber):
            return account_number.value
        return str(account_number).strip().replace("-", "").replace(" ", "")

    def save(self, beneficiary: Beneficiary) -> None:
        """Persist a new or updated Beneficiary record."""
        src = beneficiary.source_account_number.value
        dest = beneficiary.destination_account_number.value

        stmt = select(BeneficiaryModel).where(
            BeneficiaryModel.source_account_number == src,
            BeneficiaryModel.destination_account_number == dest,
        )
        model = self._session.execute(stmt).scalar_one_or_none()

        if model is None:
            model = BeneficiaryModel.from_entity(beneficiary)
            self._session.add(model)
            self._session.flush()
            beneficiary.beneficiary_id = model.beneficiary_id
        else:
            model.destination_holder_name = beneficiary.destination_holder_name
            model.nickname = beneficiary.nickname
            model.bank_name = beneficiary.bank_name
            self._session.flush()
            beneficiary.beneficiary_id = model.beneficiary_id

    def get_by_id(self, beneficiary_id: int) -> Optional[Beneficiary]:
        """Fetch beneficiary by primary key id."""
        stmt = select(BeneficiaryModel).where(BeneficiaryModel.beneficiary_id == beneficiary_id)
        model = self._session.execute(stmt).scalar_one_or_none()
        return model.to_entity() if model else None

    def get_by_source_and_dest(
        self,
        source_account_number: Union[AccountNumber, str],
        destination_account_number: Union[AccountNumber, str],
    ) -> Optional[Beneficiary]:
        """Fetch beneficiary for a specific source and destination pair."""
        src = self._normalize(source_account_number)
        dest = self._normalize(destination_account_number)
        stmt = select(BeneficiaryModel).where(
            BeneficiaryModel.source_account_number == src,
            BeneficiaryModel.destination_account_number == dest,
        )
        model = self._session.execute(stmt).scalar_one_or_none()
        return model.to_entity() if model else None

    def list_by_source(
        self, source_account_number: Union[AccountNumber, str]
    ) -> list[Beneficiary]:
        """List all saved payees for a given source account ordered by nickname."""
        src = self._normalize(source_account_number)
        stmt = (
            select(BeneficiaryModel)
            .where(BeneficiaryModel.source_account_number == src)
            .order_by(BeneficiaryModel.nickname.asc())
        )
        models = self._session.execute(stmt).scalars().all()
        return [m.to_entity() for m in models]

    def delete(self, beneficiary_id: int) -> bool:
        """Remove a beneficiary record by id. Returns True if deleted, False if not found."""
        stmt = select(BeneficiaryModel).where(BeneficiaryModel.beneficiary_id == beneficiary_id)
        model = self._session.execute(stmt).scalar_one_or_none()
        if model is None:
            return False
        self._session.delete(model)
        self._session.flush()
        return True

