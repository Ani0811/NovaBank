"""Application BankingService orchestrating financial workflows and transaction boundaries."""

from __future__ import annotations

import logging
import threading
import uuid
from datetime import date, datetime, time, timezone
from decimal import Decimal
from pathlib import Path
from typing import TYPE_CHECKING, Any, Callable, Optional, Sequence, TextIO, Union

if TYPE_CHECKING:
    from novabank.application.dto.statement_dto import AccountStatementDTO

from sqlalchemy.orm import Session, sessionmaker

from novabank.application.dto.account_dto import AccountDTO, OpenAccountResultDTO
from novabank.application.dto.beneficiary_dto import BeneficiaryDTO
from novabank.application.dto.transaction_dto import TransactionDTO, TransferResultDTO
from novabank.application.events import (
    AccountClosedEvent,
    AccountFrozenEvent,
    AccountOpenedEvent,
    AccountUnfrozenEvent,
    BeneficiaryAddedEvent,
    BeneficiaryRemovedEvent,
    DepositCompletedEvent,
    InterestAccruedEvent,
    ProfileUpdatedEvent,
    TransferCompletedEvent,
    WithdrawalCompletedEvent,
)
from novabank.domain.entities.account import Account
from novabank.domain.entities.beneficiary import Beneficiary
from novabank.domain.exceptions import (
    AccountClosedError,
    AccountFrozenError,
    AccountNotFoundError,
    CurrencyMismatchError,
    InvalidAmountError,
    SelfTransferError,
)
from novabank.domain.services.interest_calculator import InterestCalculator
from novabank.domain.value_objects.account_number import AccountNumber
from novabank.domain.value_objects.money import Money
from novabank.domain.value_objects.transaction_type import TransactionType
from novabank.infrastructure.repositories.sql_account_repository import SQLAccountRepository
from novabank.infrastructure.repositories.sql_beneficiary_repository import SQLBeneficiaryRepository
from novabank.infrastructure.repositories.sql_transaction_repository import SQLTransactionRepository

logger = logging.getLogger(__name__)


class AccountLockManager:
    """Fine-grained per-account re-entrant mutex for in-process thread serialization."""

    def __init__(self) -> None:
        self._global_lock = threading.Lock()
        self._account_locks: dict[str, threading.RLock] = {}

    def get_lock(self, account_number: str) -> threading.RLock:
        with self._global_lock:
            if account_number not in self._account_locks:
                self._account_locks[account_number] = threading.RLock()
            return self._account_locks[account_number]


class BankingService:
    """Application service coordinating financial transactions, row locking, and domain invariants."""

    def __init__(
        self,
        session_factory: sessionmaker[Session],
        event_publisher: Optional[Callable[[Any], None]] = None,
    ) -> None:
        self._session_factory = session_factory
        self._lock_manager = AccountLockManager()
        self._listeners: list[Callable[[Any], None]] = []
        if event_publisher is not None:
            self._listeners.append(event_publisher)

    def subscribe(self, listener: Callable[[Any], None]) -> None:
        """Register an event listener/subscriber callback."""
        self._listeners.append(listener)

    def register_listener(self, listener: Callable[[Any], None]) -> None:
        """Alias for subscribe to register lifecycle event listeners."""
        self.subscribe(listener)

    def _emit(self, event: Any) -> None:
        """Publish event to all registered listeners."""
        for listener in self._listeners:
            try:
                listener(event)
            except Exception as exc:
                # Listener exceptions must not break core business flows
                logger.warning("Event listener %s failed processing event %s: %s", listener, event, exc)

    def open_account(
        self,
        holder_name: str,
        dob: date,
        address_line: str,
        city: str,
        state: str,
        country: str,
        phone_number: str,
        initial_deposit: Optional[Union[Money, Decimal, str, int]] = None,
        currency: str = "USD",
        actor: str = "teller",
    ) -> OpenAccountResultDTO:
        """Register a new customer account with optional initial deposit.

        Steps:
        1. Parse and validate initial deposit amount (>= 0).
        2. Begin database transaction.
        3. Generate cryptographically random 12-digit AccountNumber unique in DB.
        4. Create and validate Account domain entity.
        5. If initial deposit > 0, credit account and create ledger record.
        6. Persist account and transaction.
        7. Commit transaction.
        8. Emit AccountOpenedEvent.
        9. Return OpenAccountResultDTO.
        """
        if initial_deposit is not None:
            if isinstance(initial_deposit, Money):
                deposit_money = initial_deposit
            else:
                try:
                    deposit_money = Money(initial_deposit, currency=currency, allow_negative=True)
                except Exception as exc:
                    raise InvalidAmountError(
                        f"Invalid initial deposit amount: {initial_deposit}"
                    ) from exc
            if deposit_money.is_negative():
                raise InvalidAmountError(
                    f"Initial deposit cannot be negative, got {deposit_money.formatted()}"
                )
        else:
            deposit_money = Money.zero(currency=currency)

        with self._session_factory() as session:
            with session.begin():
                account_repo = SQLAccountRepository(session)
                tx_repo = SQLTransactionRepository(session)

                # Generate unique account number
                while True:
                    candidate = AccountNumber.generate()
                    if account_repo.get_by_number(candidate.value) is None:
                        account_number = candidate
                        break

                account = Account(
                    account_number=account_number,
                    holder_name=holder_name,
                    dob=dob,
                    address_line=address_line,
                    city=city,
                    state=state,
                    country=country,
                    phone_number=phone_number,
                    balance=Money.zero(currency=currency),
                )

                initial_tx_dto: Optional[TransactionDTO] = None
                if deposit_money.is_positive():
                    tx_entity = account.credit(
                        amount=deposit_money,
                        transaction_type=TransactionType.DEPOSIT,
                        description="Initial Deposit",
                        actor=actor,
                    )
                    account_repo.save(account)
                    tx_repo.append(tx_entity)
                    initial_tx_dto = TransactionDTO.from_entity(tx_entity)
                else:
                    account_repo.save(account)

                result_dto = OpenAccountResultDTO(
                    account=AccountDTO.from_entity(account),
                    initial_transaction=initial_tx_dto,
                )

                event = AccountOpenedEvent(
                    account_number=account.account_number.value,
                    holder_name=account.holder_name,
                    phone_number=account.phone_number,
                    initial_deposit=deposit_money.amount,
                    currency=currency,
                    timestamp=datetime.now(timezone.utc),
                    actor=actor,
                )

        self._emit(event)
        return result_dto

    def list_accounts(
        self,
        search: Optional[str] = None,
        active_only: bool = False,
        status_filter: str = "ALL",
        page: int = 1,
        page_size: int = 50,
    ) -> tuple[list[AccountDTO], int]:
        """Query paginated customer accounts with optional search and status filters."""
        is_active: Optional[bool] = None
        if status_filter == "ACTIVE":
            is_active = True
        elif status_filter == "CLOSED":
            is_active = False

        offset = max(0, (page - 1) * page_size)
        with self._session_factory() as session:
            repo = SQLAccountRepository(session)
            total_count = repo.count_accounts(
                search=search,
                active_only=active_only,
                is_active=is_active,
            )
            entities = repo.list_accounts(
                search=search,
                active_only=active_only,
                is_active=is_active,
                limit=page_size,
                offset=offset,
            )
            dtos = [AccountDTO.from_entity(e) for e in entities]
            return dtos, total_count

    def get_account(self, account_number: Union[AccountNumber, str]) -> Optional[AccountDTO]:
        """Fetch account DTO by account number."""
        if isinstance(account_number, AccountNumber):
            acc_str = account_number.value
        else:
            acc_str = str(account_number).strip().replace("-", "").replace(" ", "")

        with self._session_factory() as session:
            repo = SQLAccountRepository(session)
            entity = repo.get_by_number(acc_str)
            return AccountDTO.from_entity(entity) if entity else None

    def update_account_profile(
        self,
        account_number: Union[AccountNumber, str],
        address_line: str,
        city: str,
        state: str,
        country: str,
        phone_number: str,
        actor: str = "teller",
    ) -> AccountDTO:
        """Update mutable customer profile details (address and contact information)."""
        if isinstance(account_number, AccountNumber):
            acc_str = account_number.value
        else:
            acc_str = str(account_number).strip().replace("-", "").replace(" ", "")

        with self._lock_manager.get_lock(acc_str):
            with self._session_factory() as session:
                with session.begin():
                    repo = SQLAccountRepository(session)
                    account = repo.get_by_number_for_update(acc_str)
                    if account is None:
                        raise AccountNotFoundError(acc_str)

                    account.update_profile(
                        address_line=address_line,
                        city=city,
                        state=state,
                        country=country,
                        phone_number=phone_number,
                    )
                    repo.save(account)
                    dto = AccountDTO.from_entity(account)

                    event = ProfileUpdatedEvent(
                        account_number=acc_str,
                        phone_number=phone_number,
                        city=city,
                        state=state,
                        timestamp=datetime.now(timezone.utc),
                        actor=actor,
                    )

            self._emit(event)
            return dto

    def close_account(
        self,
        account_number: Union[AccountNumber, str],
        reason: str = "Customer request",
        actor: str = "teller",
    ) -> AccountDTO:
        """Deactivate/close an account with zero balance invariant."""
        if isinstance(account_number, AccountNumber):
            acc_str = account_number.value
        else:
            acc_str = str(account_number).strip().replace("-", "").replace(" ", "")

        with self._lock_manager.get_lock(acc_str):
            with self._session_factory() as session:
                with session.begin():
                    repo = SQLAccountRepository(session)
                    account = repo.get_by_number_for_update(acc_str)
                    if account is None:
                        raise AccountNotFoundError(acc_str)

                    account.close(reason=reason)
                    repo.save(account)
                    dto = AccountDTO.from_entity(account)

                    event = AccountClosedEvent(
                        account_number=acc_str,
                        reason=reason,
                        timestamp=datetime.now(timezone.utc),
                        actor=actor,
                    )

            self._emit(event)
            return dto

    def freeze_account(
        self,
        account_number: Union[AccountNumber, str],
        reason: str = "Administrative risk hold",
        actor: str = "teller",
    ) -> AccountDTO:
        """Place an administrative freeze on an account, restricting debits and withdrawals."""
        if isinstance(account_number, AccountNumber):
            acc_str = account_number.value
        else:
            acc_str = str(account_number).strip().replace("-", "").replace(" ", "")

        with self._lock_manager.get_lock(acc_str):
            with self._session_factory() as session:
                with session.begin():
                    repo = SQLAccountRepository(session)
                    account = repo.get_by_number_for_update(acc_str)
                    if account is None:
                        raise AccountNotFoundError(acc_str)

                    account.freeze(reason=reason)
                    repo.save(account)
                    dto = AccountDTO.from_entity(account)

                    event = AccountFrozenEvent(
                        account_number=acc_str,
                        reason=reason,
                        timestamp=datetime.now(timezone.utc),
                        actor=actor,
                    )

            self._emit(event)
            return dto

    def unfreeze_account(
        self,
        account_number: Union[AccountNumber, str],
        reason: str = "Administrative hold released",
        actor: str = "teller",
    ) -> AccountDTO:
        """Release administrative freeze on an account, restoring normal debit capabilities."""
        if isinstance(account_number, AccountNumber):
            acc_str = account_number.value
        else:
            acc_str = str(account_number).strip().replace("-", "").replace(" ", "")

        with self._lock_manager.get_lock(acc_str):
            with self._session_factory() as session:
                with session.begin():
                    repo = SQLAccountRepository(session)
                    account = repo.get_by_number_for_update(acc_str)
                    if account is None:
                        raise AccountNotFoundError(acc_str)

                    account.unfreeze(reason=reason)
                    repo.save(account)
                    dto = AccountDTO.from_entity(account)

                    event = AccountUnfrozenEvent(
                        account_number=acc_str,
                        reason=reason,
                        timestamp=datetime.now(timezone.utc),
                        actor=actor,
                    )

            self._emit(event)
            return dto

    def deposit(
        self,
        account_number: Union[AccountNumber, str],
        amount: Union[Money, Decimal, str, int],
        description: str = "Cash Deposit",
        ref: Optional[str] = None,
        actor: str = "system",
    ) -> TransactionDTO:
        """Atomically deposit funds into a customer account.

        Steps:
        1. Parse and validate account number and monetary amount (> 0).
        2. Acquire fine-grained in-process mutex for the account.
        3. Begin atomic database transaction with pessimistic row lock (SELECT ... FOR UPDATE).
        4. Validate account existence and active status.
        5. Apply credit mutation to Account domain entity (updating balance & version).
        6. Persist updated Account and append immutable Transaction record.
        7. Commit database transaction (or rollback entirely on failure).
        8. Emit DepositCompletedEvent and return TransactionDTO.

        Raises:
            AccountNotFoundError: If account does not exist.
            AccountClosedError: If account is deactivated or closed.
            InvalidAmountError: If amount is non-positive or invalid.
            DuplicateTransactionRefError: If reference is duplicate.
        """
        # 1. Normalize account number string
        if isinstance(account_number, AccountNumber):
            acc_str = account_number.value
        else:
            acc_str = str(account_number).strip().replace("-", "").replace(" ", "")

        # 2. Parse and validate amount
        if isinstance(amount, Money):
            deposit_money = amount
        else:
            try:
                deposit_money = Money(amount, allow_negative=True)
            except Exception as exc:
                raise InvalidAmountError(f"Invalid monetary deposit amount: {amount}") from exc

        if not deposit_money.is_positive():
            raise InvalidAmountError(
                f"Deposit amount must be strictly positive, got {deposit_money.formatted()}"
            )

        # 3. Synchronize in-process concurrent workers for this account
        with self._lock_manager.get_lock(acc_str):
            # 4. Atomic database transaction block
            with self._session_factory() as session:
                with session.begin():
                    account_repo = SQLAccountRepository(session)
                    tx_repo = SQLTransactionRepository(session)

                    # Acquire pessimistic row-level lock
                    account = account_repo.get_by_number_for_update(acc_str)
                    if account is None:
                        raise AccountNotFoundError(acc_str)

                    if not account.is_active:
                        raise AccountClosedError(acc_str)

                    if account.is_frozen:
                        raise AccountFrozenError(acc_str)

                    # Domain entity credit execution
                    tx_entity = account.credit(
                        amount=deposit_money,
                        transaction_type=TransactionType.DEPOSIT,
                        description=description,
                        ref=ref,
                        actor=actor,
                    )

                    # Persist changes
                    account_repo.save(account)
                    tx_repo.append(tx_entity)

                    # Prepare DTO and Event before exiting transaction
                    dto = TransactionDTO.from_entity(tx_entity)
                    event = DepositCompletedEvent(
                        account_number=account.account_number.value,
                        amount=deposit_money.amount,
                        balance_after=account.balance.amount,
                        currency=account.balance.currency,
                        transaction_ref=tx_entity.transaction_ref,
                        timestamp=tx_entity.created_at,
                        actor=actor,
                        description=description,
                    )

            # 5. Emit event after transaction commits successfully
            self._emit(event)
            return dto

    def withdraw(
        self,
        account_number: Union[AccountNumber, str],
        amount: Union[Money, Decimal, str, int],
        description: str = "Cash Withdrawal",
        ref: Optional[str] = None,
        actor: str = "system",
    ) -> TransactionDTO:
        """Atomically withdraw funds from a customer account.

        Steps:
        1. Parse and validate account number and monetary amount (> 0).
        2. Acquire fine-grained in-process mutex for the account.
        3. Begin atomic database transaction with pessimistic row lock (SELECT ... FOR UPDATE).
        4. Validate account existence and active status.
        5. Verify sufficient funds (balance >= amount, overdraft protection).
        6. Apply debit mutation to Account domain entity (updating balance & version).
        7. Persist updated Account and append immutable Transaction record.
        8. Commit database transaction (or rollback entirely on failure).
        9. Emit WithdrawalCompletedEvent and return TransactionDTO.

        Raises:
            AccountNotFoundError: If account does not exist.
            AccountClosedError: If account is deactivated or closed.
            InvalidAmountError: If amount is non-positive or invalid.
            InsufficientFundsError: If requested amount exceeds available balance.
            DuplicateTransactionRefError: If reference is duplicate.
        """
        # 1. Normalize account number string
        if isinstance(account_number, AccountNumber):
            acc_str = account_number.value
        else:
            acc_str = str(account_number).strip().replace("-", "").replace(" ", "")

        # 2. Parse and validate amount
        if isinstance(amount, Money):
            withdraw_money = amount
        else:
            try:
                withdraw_money = Money(amount, allow_negative=True)
            except Exception as exc:
                raise InvalidAmountError(f"Invalid monetary withdrawal amount: {amount}") from exc

        if not withdraw_money.is_positive():
            raise InvalidAmountError(
                f"Withdrawal amount must be strictly positive, got {withdraw_money.formatted()}"
            )

        # 3. Synchronize in-process concurrent workers for this account
        with self._lock_manager.get_lock(acc_str):
            # 4. Atomic database transaction block
            with self._session_factory() as session:
                with session.begin():
                    account_repo = SQLAccountRepository(session)
                    tx_repo = SQLTransactionRepository(session)

                    # Acquire pessimistic row-level lock
                    account = account_repo.get_by_number_for_update(acc_str)
                    if account is None:
                        raise AccountNotFoundError(acc_str)

                    if not account.is_active:
                        raise AccountClosedError(acc_str)

                    if account.is_frozen:
                        raise AccountFrozenError(acc_str)

                    # Domain entity debit execution (checks balance >= amount)
                    tx_entity = account.debit(
                        amount=withdraw_money,
                        transaction_type=TransactionType.WITHDRAWAL,
                        description=description,
                        ref=ref,
                        actor=actor,
                    )

                    # Persist changes
                    account_repo.save(account)
                    tx_repo.append(tx_entity)

                    # Prepare DTO and Event before exiting transaction
                    dto = TransactionDTO.from_entity(tx_entity)
                    event = WithdrawalCompletedEvent(
                        account_number=account.account_number.value,
                        amount=withdraw_money.amount,
                        balance_after=account.balance.amount,
                        currency=account.balance.currency,
                        transaction_ref=tx_entity.transaction_ref,
                        timestamp=tx_entity.created_at,
                        actor=actor,
                        description=description,
                    )

            # 5. Emit event after transaction commits successfully
            self._emit(event)
            return dto

    def transfer(
        self,
        source_account_number: Union[AccountNumber, str],
        destination_account_number: Union[AccountNumber, str],
        amount: Union[Money, Decimal, str, int],
        description: str = "Account Transfer",
        correlation_id: Optional[str] = None,
        actor: str = "system",
    ) -> TransferResultDTO:
        """Atomically transfer funds between two accounts with deadlock-free dual locking.

        Steps:
        1. Validate source and destination are different accounts (reject self-transfers).
        2. Normalize account numbers and parse monetary amount (> 0).
        3. Acquire fine-grained in-process mutexes in deterministic ascending order.
        4. Begin atomic database transaction.
        5. Acquire pessimistic DB row locks in deterministic ascending order (SELECT ... FOR UPDATE).
        6. Validate existence, active status, currency compatibility, and sufficient funds.
        7. Apply debit mutation to source and credit mutation to destination.
        8. Write two immutable linked transaction records (TRANSFER_OUT and TRANSFER_IN).
        9. Commit database transaction (or rollback entirely on failure).
        10. Emit TransferCompletedEvent and return TransferResultDTO.

        Raises:
            SelfTransferError: If source and destination accounts are identical.
            AccountNotFoundError: If source or destination account does not exist.
            AccountClosedError: If either account is deactivated or closed.
            InvalidAmountError: If amount is non-positive or invalid.
            InsufficientFundsError: If source balance is less than transfer amount.
            CurrencyMismatchError: If account currencies do not match.
            DuplicateTransactionRefError: If correlation ID or transaction ref exists.
        """
        # 1. Normalize account numbers
        if isinstance(source_account_number, AccountNumber):
            src_str = source_account_number.value
        else:
            src_str = str(source_account_number).strip().replace("-", "").replace(" ", "")

        if isinstance(destination_account_number, AccountNumber):
            dst_str = destination_account_number.value
        else:
            dst_str = str(destination_account_number).strip().replace("-", "").replace(" ", "")

        # 2. Reject self-transfer
        if src_str == dst_str:
            raise SelfTransferError(src_str)

        # 3. Parse and validate amount
        if isinstance(amount, Money):
            transfer_money = amount
        else:
            try:
                transfer_money = Money(amount, allow_negative=True)
            except Exception as exc:
                raise InvalidAmountError(f"Invalid monetary transfer amount: {amount}") from exc

        if not transfer_money.is_positive():
            raise InvalidAmountError(
                f"Transfer amount must be strictly positive, got {transfer_money.formatted()}"
            )

        # 4. Deterministic lock ordering (lexicographical) to prevent deadlocks
        first_acc, second_acc = sorted([src_str, dst_str])
        lock_first = self._lock_manager.get_lock(first_acc)
        lock_second = self._lock_manager.get_lock(second_acc)

        corr_id = correlation_id or str(uuid.uuid4())
        src_ref = f"{corr_id}-out"
        dst_ref = f"{corr_id}-in"

        with lock_first, lock_second:
            with self._session_factory() as session:
                with session.begin():
                    account_repo = SQLAccountRepository(session)
                    tx_repo = SQLTransactionRepository(session)

                    # Acquire pessimistic row-level locks in deterministic order
                    first_model = account_repo.get_by_number_for_update(first_acc)
                    second_model = account_repo.get_by_number_for_update(second_acc)

                    accounts_by_num = {
                        first_acc: first_model,
                        second_acc: second_model,
                    }
                    source_account = accounts_by_num[src_str]
                    destination_account = accounts_by_num[dst_str]

                    if source_account is None:
                        raise AccountNotFoundError(src_str)
                    if destination_account is None:
                        raise AccountNotFoundError(dst_str)

                    if not source_account.is_active:
                        raise AccountClosedError(src_str)
                    if not destination_account.is_active:
                        raise AccountClosedError(dst_str)

                    if source_account.balance.currency != destination_account.balance.currency:
                        raise CurrencyMismatchError(
                            f"Source currency '{source_account.balance.currency}' does not "
                            f"match destination currency '{destination_account.balance.currency}'."
                        )

                    # Execute domain mutations: debit source, credit destination
                    src_tx = source_account.debit(
                        amount=transfer_money,
                        transaction_type=TransactionType.TRANSFER_OUT,
                        description=description or f"Transfer to {dst_str}",
                        ref=src_ref,
                        actor=actor,
                    )
                    dst_tx = destination_account.credit(
                        amount=transfer_money,
                        transaction_type=TransactionType.TRANSFER_IN,
                        description=description or f"Transfer from {src_str}",
                        ref=dst_ref,
                        actor=actor,
                    )

                    # Persist account mutations and transaction records
                    account_repo.save(source_account)
                    account_repo.save(destination_account)
                    tx_repo.append(src_tx)
                    tx_repo.append(dst_tx)

                    src_dto = TransactionDTO.from_entity(src_tx)
                    dst_dto = TransactionDTO.from_entity(dst_tx)
                    result_dto = TransferResultDTO(
                        correlation_id=corr_id,
                        source_transaction=src_dto,
                        destination_transaction=dst_dto,
                        amount=transfer_money.amount,
                        currency=transfer_money.currency,
                        timestamp=src_tx.created_at,
                    )

                    event = TransferCompletedEvent(
                        source_account=src_str,
                        destination_account=dst_str,
                        amount=transfer_money.amount,
                        source_balance_after=source_account.balance.amount,
                        destination_balance_after=destination_account.balance.amount,
                        currency=transfer_money.currency,
                        correlation_id=corr_id,
                        timestamp=src_tx.created_at,
                        actor=actor,
                        description=description,
                    )

            # 5. Emit event after transaction commits successfully
            self._emit(event)
            return result_dto

    def get_statement(
        self,
        account_number: Union[AccountNumber, str],
        start_date: Optional[Union[date, datetime]] = None,
        end_date: Optional[Union[date, datetime]] = None,
    ) -> AccountStatementDTO:
        """Generate historical statement for the specified account with full reconciliation."""
        from novabank.application.services.statement_service import StatementService

        service = StatementService(self._session_factory)
        return service.generate_statement(
            account_number=account_number,
            start_date=start_date,
            end_date=end_date,
        )

    def export_statement_csv(
        self,
        statement: AccountStatementDTO,
        destination: Optional[Union[str, Path, TextIO]] = None,
        *,
        include_summary: bool = True,
        encoding: str = "utf-8",
        sanitize_formulas: bool = True,
    ) -> str:
        """Export an account statement to RFC-4180 compliant CSV."""
        from novabank.application.services.export_service import ExportService

        return ExportService.export_statement_to_csv(
            statement=statement,
            destination=destination,
            include_summary=include_summary,
            encoding=encoding,
            sanitize_formulas=sanitize_formulas,
        )

    def export_statement_pdf(
        self,
        statement: AccountStatementDTO,
        destination_path: Optional[Union[str, Path]] = None,
        *,
        bank_name: str = "NovaBank National Banking & Trust",
    ) -> Union[str, bytes]:
        """Generate official PDF statement using StatementPdfGenerator."""
        from novabank.infrastructure.reporting.pdf_generator import StatementPdfGenerator

        return StatementPdfGenerator.generate_statement_pdf(
            statement=statement,
            destination_path=destination_path,
            bank_name=bank_name,
        )

    def add_beneficiary(
        self,
        source_account: Union[AccountNumber, str],
        destination_account: Union[AccountNumber, str],
        nickname: str,
        bank_name: str = "NovaBank",
        actor: str = "teller",
    ) -> BeneficiaryDTO:
        """Register or update a frequent payee contact in the account address book."""
        src_str = (
            source_account.value
            if isinstance(source_account, AccountNumber)
            else str(source_account).strip().replace("-", "").replace(" ", "")
        )
        dest_str = (
            destination_account.value
            if isinstance(destination_account, AccountNumber)
            else str(destination_account).strip().replace("-", "").replace(" ", "")
        )

        if src_str == dest_str:
            raise SelfTransferError(src_str)

        with self._session_factory() as session:
            with session.begin():
                acc_repo = SQLAccountRepository(session)
                src_acc = acc_repo.get_by_number(src_str)
                if src_acc is None:
                    raise AccountNotFoundError(src_str)
                dest_acc = acc_repo.get_by_number(dest_str)
                if dest_acc is None:
                    raise AccountNotFoundError(dest_str)

                beneficiary = Beneficiary(
                    source_account_number=AccountNumber(src_str),
                    destination_account_number=AccountNumber(dest_str),
                    destination_holder_name=dest_acc.holder_name,
                    nickname=nickname,
                    bank_name=bank_name,
                )
                ben_repo = SQLBeneficiaryRepository(session)
                ben_repo.save(beneficiary)
                dto = BeneficiaryDTO.from_entity(beneficiary)

                event = BeneficiaryAddedEvent(
                    source_account=src_str,
                    destination_account=dest_str,
                    destination_holder_name=dest_acc.holder_name,
                    nickname=beneficiary.nickname,
                    timestamp=datetime.now(timezone.utc),
                    actor=actor,
                )

        self._emit(event)
        return dto

    def list_beneficiaries(
        self, source_account: Union[AccountNumber, str]
    ) -> list[BeneficiaryDTO]:
        """Fetch all verified saved payees for the specified source account."""
        src_str = (
            source_account.value
            if isinstance(source_account, AccountNumber)
            else str(source_account).strip().replace("-", "").replace(" ", "")
        )
        with self._session_factory() as session:
            ben_repo = SQLBeneficiaryRepository(session)
            entities = ben_repo.list_by_source(src_str)
            return [BeneficiaryDTO.from_entity(e) for e in entities]

    def delete_beneficiary(self, beneficiary_id: int, actor: str = "teller") -> bool:
        """Remove a beneficiary record from the account address book."""
        event: Optional[BeneficiaryRemovedEvent] = None
        with self._session_factory() as session:
            with session.begin():
                ben_repo = SQLBeneficiaryRepository(session)
                ben = ben_repo.get_by_id(beneficiary_id)
                if ben is None:
                    return False
                event = BeneficiaryRemovedEvent(
                    beneficiary_id=beneficiary_id,
                    source_account=ben.source_account_number.value,
                    destination_account=ben.destination_account_number.value,
                    timestamp=datetime.now(timezone.utc),
                    actor=actor,
                )
                ben_repo.delete(beneficiary_id)

        if event is not None:
            self._emit(event)
        return True

    def search_transactions(
        self,
        account_number: Optional[Union[AccountNumber, str]] = None,
        start_date: Optional[Union[date, datetime]] = None,
        end_date: Optional[Union[date, datetime]] = None,
        tx_type: Optional[str] = None,
        min_amount: Optional[Decimal] = None,
        max_amount: Optional[Decimal] = None,
        page: int = 1,
        page_size: int = 50,
        descending: bool = True,
    ) -> tuple[list[TransactionDTO], int]:
        """Search transactions matching flexible criteria across all accounts or a specific account."""
        s_dt: Optional[datetime] = None
        if isinstance(start_date, date) and not isinstance(start_date, datetime):
            s_dt = datetime.combine(start_date, time.min).replace(tzinfo=timezone.utc)
        elif isinstance(start_date, datetime):
            s_dt = start_date

        e_dt: Optional[datetime] = None
        if isinstance(end_date, date) and not isinstance(end_date, datetime):
            e_dt = datetime.combine(end_date, time.max).replace(tzinfo=timezone.utc)
        elif isinstance(end_date, datetime):
            e_dt = end_date

        offset = max(0, (page - 1) * page_size)
        with self._session_factory() as session:
            repo = SQLTransactionRepository(session)
            entities, total_count = repo.search_transactions(
                account_number=account_number,
                start_date=s_dt,
                end_date=e_dt,
                tx_type=tx_type,
                min_amount=min_amount,
                max_amount=max_amount,
                limit=page_size,
                offset=offset,
                descending=descending,
            )
            return [TransactionDTO.from_entity(e) for e in entities], total_count

    def export_ledger_csv(
        self,
        transactions: Sequence[TransactionDTO],
        destination: Optional[Union[str, Path, TextIO]] = None,
        *,
        encoding: str = "utf-8",
        sanitize_formulas: bool = True,
    ) -> str:
        """Export ledger transactions directly to RFC-4180 CSV table."""
        from novabank.application.dto.statement_dto import StatementEntryDTO
        from novabank.application.services.export_service import ExportService

        entries = [
            StatementEntryDTO(
                transaction_id=tx.transaction_id,
                transaction_ref=tx.transaction_ref,
                created_at=tx.created_at,
                transaction_type=tx.transaction_type,
                direction=tx.direction,
                description=tx.description,
                amount=tx.amount,
                debit_amount=tx.amount if tx.direction == "DEBIT" else None,
                credit_amount=tx.amount if tx.direction == "CREDIT" else None,
                balance_after=tx.balance_after,
                currency=tx.currency,
                created_by=tx.created_by,
                formatted_amount=f"${tx.amount:,.2f}",
                formatted_balance_after=f"${tx.balance_after:,.2f}",
                formatted_debit=f"${tx.amount:,.2f}" if tx.direction == "DEBIT" else "",
                formatted_credit=f"${tx.amount:,.2f}" if tx.direction == "CREDIT" else "",
            )
            for tx in transactions
        ]
        return ExportService.export_transactions_to_csv(
            entries=entries,
            destination=destination,
            encoding=encoding,
            sanitize_formulas=sanitize_formulas,
        )

    def accrue_interest(
        self,
        annual_rate_percentage: Decimal = Decimal("2.50"),
        min_qualifying_balance: Decimal = Decimal("100.00"),
        actor: str = "system",
    ) -> list[TransactionDTO]:
        """Execute monthly compounding interest accrual across all qualifying active accounts."""
        if annual_rate_percentage < Decimal("0.00"):
            raise InvalidAmountError(f"Interest rate cannot be negative: {annual_rate_percentage}")

        credited_dtos: list[TransactionDTO] = []
        total_credited = Decimal("0.00")

        # 1. Fetch active accounts
        with self._session_factory() as session:
            account_repo = SQLAccountRepository(session)
            accounts = account_repo.list_accounts(active_only=True, limit=1000)

        min_qual = Money(min_qualifying_balance)

        for acc in accounts:
            if not acc.is_active or acc.is_frozen or acc.balance < min_qual:
                continue

            interest = InterestCalculator.calculate_monthly_interest(
                balance=acc.balance,
                annual_rate_percentage=annual_rate_percentage,
                min_qualifying_balance=min_qual,
            )

            if not interest.is_positive():
                continue

            acc_str = acc.account_number.value
            with self._lock_manager.get_lock(acc_str):
                with self._session_factory() as session:
                    with session.begin():
                        account_repo = SQLAccountRepository(session)
                        tx_repo = SQLTransactionRepository(session)
                        account = account_repo.get_by_number_for_update(acc_str)
                        if account is None or not account.is_active or account.is_frozen:
                            continue

                        locked_interest = InterestCalculator.calculate_monthly_interest(
                            balance=account.balance,
                            annual_rate_percentage=annual_rate_percentage,
                            min_qualifying_balance=min_qual,
                        )
                        if not locked_interest.is_positive():
                            continue

                        tx_entity = account.credit(
                            amount=locked_interest,
                            transaction_type=TransactionType.INTEREST,
                            description=f"Monthly Interest Accrual ({annual_rate_percentage:.2f}% APY)",
                            ref=f"INT-{uuid.uuid4().hex[:12].upper()}",
                            actor=actor,
                        )
                        account_repo.save(account)
                        tx_repo.append(tx_entity)
                        dto = TransactionDTO.from_entity(tx_entity)
                        credited_dtos.append(dto)
                        total_credited += locked_interest.amount

        if credited_dtos:
            event = InterestAccruedEvent(
                accounts_credited=len(credited_dtos),
                total_interest_credited=total_credited,
                annual_rate_percentage=annual_rate_percentage,
                timestamp=datetime.now(timezone.utc),
                actor=actor,
            )
            self._emit(event)

        return credited_dtos
