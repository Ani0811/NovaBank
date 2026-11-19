"""Application BankingService orchestrating financial workflows and transaction boundaries."""

from __future__ import annotations

import csv
import io
import logging
import re
import threading
import uuid
from datetime import date, datetime, time, timezone
from decimal import Decimal, ROUND_HALF_UP
from pathlib import Path
from typing import TYPE_CHECKING, Any, Callable, Optional, Sequence, TextIO, Union

if TYPE_CHECKING:
    from novabank.application.dto.statement_dto import AccountStatementDTO

from sqlalchemy.orm import Session, sessionmaker

from novabank.application.dto.account_dto import AccountDTO, OpenAccountResultDTO
from novabank.application.dto.beneficiary_dto import BeneficiaryDTO
from novabank.application.dto.fx_dto import (
    ExecuteFXTradeRequestDTO,
    FXQuoteRequestDTO,
    FXQuoteResponseDTO,
    FXRateTableEntryDTO,
    FXTradeDTO,
    TreasuryPositionDTO,
)
from novabank.application.dto.loan_dto import (
    AmortizationScheduleEntryDTO,
    LoanContractDTO,
    LoanOriginationRequestDTO,
    LoanQuoteRequestDTO,
    LoanQuoteResponseDTO,
    LoanRepaymentResultDTO,
)
from novabank.application.dto.payment_dto import (
    PaymentRefundResultDTO,
    PaymentRequestDTO,
    PaymentTransactionDTO,
)
from novabank.application.dto.term_deposit_dto import (
    CDAccrualMilestoneDTO,
    CDSimulationRequestDTO,
    CDSimulationResponseDTO,
    CertificateOfDepositDTO,
    EarlyRedemptionPreviewDTO,
    OpenCDRequestDTO,
    RedemptionResultDTO,
)
from novabank.application.dto.transaction_dto import TransactionDTO, TransferResultDTO
from novabank.application.events import (
    AccountClosedEvent,
    AccountFrozenEvent,
    AccountOpenedEvent,
    AccountUnfrozenEvent,
    BeneficiaryAddedEvent,
    BeneficiaryRemovedEvent,
    DepositCompletedEvent,
    FXTradeExecutedEvent,
    InterestAccruedEvent,
    LoanOriginatedEvent,
    LoanPaidOffEvent,
    LoanRepaymentProcessedEvent,
    PaymentDeclinedEvent,
    PaymentProcessedEvent,
    PaymentRefundedEvent,
    ProfileUpdatedEvent,
    TermDepositEarlyRedeemedEvent,
    TermDepositMaturedEvent,
    TermDepositOpenedEvent,
    TermDepositRolledOverEvent,
    TransferCompletedEvent,
    TreasuryPositionUpdatedEvent,
    WithdrawalCompletedEvent,
)
from novabank.domain.entities.account import Account
from novabank.domain.entities.beneficiary import Beneficiary
from novabank.domain.entities.fx_trade import (
    ExchangeRate,
    FXTrade,
    FXTradeStatus,
    TreasuryPosition,
)
from novabank.domain.entities.loan import LoanContract, LoanStatus, LoanType
from novabank.domain.entities.payment import (
    PaymentChannel,
    PaymentDirection,
    PaymentStatus,
    PaymentTransaction,
)
from novabank.domain.entities.term_deposit import (
    CDAccrualMilestone,
    CertificateOfDeposit,
    TermDepositPayoutFrequency,
    TermDepositRolloverOption,
    TermDepositStatus,
)
from novabank.domain.entities.transaction import Transaction
from novabank.domain.exceptions import (
    AccountClosedError,
    AccountFrozenError,
    AccountNotFoundError,
    CurrencyMismatchError,
    DuplicateIdempotencyKeyError,
    FXError,
    FXTradeNotFoundError,
    InsufficientFundsError,
    InsufficientTreasuryReserveError,
    InvalidAmountError,
    InvalidFXAmountError,
    InvalidLoanTermsError,
    InvalidTermDepositTermsError,
    LoanAlreadyPaidOffError,
    LoanDisbursementError,
    LoanError,
    LoanNotFoundError,
    PaymentDeclinedError,
    PaymentRefundError,
    PrematureRedemptionNotAllowedError,
    SelfTransferError,
    TermDepositAlreadyClosedError,
    TermDepositError,
    TermDepositNotFoundError,
    UnsupportedCurrencyError,
)
from novabank.domain.services.amortization_calculator import AmortizationCalculator
from novabank.domain.services.fx_calculator import FXCalculator, SUPPORTED_CURRENCIES
from novabank.domain.services.interest_calculator import InterestCalculator
from novabank.domain.services.term_deposit_calculator import TermDepositCalculator
from novabank.domain.value_objects.account_number import AccountNumber
from novabank.domain.value_objects.money import Money
from novabank.domain.value_objects.transaction_type import TransactionType
from novabank.infrastructure.gateways.payment_rails_simulator import PaymentRailsSimulator
from novabank.infrastructure.repositories.sql_account_repository import SQLAccountRepository
from novabank.infrastructure.repositories.sql_beneficiary_repository import SQLBeneficiaryRepository
from novabank.infrastructure.repositories.sql_fx_repository import SQLFXRepository
from novabank.infrastructure.repositories.sql_loan_repository import SQLLoanRepository
from novabank.infrastructure.repositories.sql_payment_repository import SQLPaymentRepository
from novabank.infrastructure.repositories.sql_term_deposit_repository import (
    SQLTermDepositRepository,
)
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

    def process_gateway_payment(
        self,
        request: PaymentRequestDTO,
        actor: str = "gateway",
    ) -> PaymentTransactionDTO:
        """Process external payment ingestion (Card, ACH, FedNow, Wire) with atomic ledger settlement."""
        acc_str = str(request.account_number).strip().replace("-", "").replace(" ", "")

        # 1. Parse amount & channel
        if not isinstance(request.amount, Decimal) or request.amount <= Decimal("0.00"):
            raise InvalidAmountError(f"Payment amount must be positive, got: {request.amount}")

        try:
            channel_enum = PaymentChannel(request.channel.strip().upper())
        except ValueError:
            raise DomainError(f"Unsupported payment channel: '{request.channel}'")

        gross_money = Money(request.amount)
        idemp_key = request.idempotency_key or f"IDEMP-{uuid.uuid4().hex[:16]}"

        # 2. Check Idempotency
        with self._session_factory() as session:
            pay_repo = SQLPaymentRepository(session)
            existing = pay_repo.get_by_idempotency_key(idemp_key)
            if existing is not None:
                if existing.status == PaymentStatus.SETTLED:
                    return PaymentTransactionDTO.from_entity(existing)
                raise DuplicateIdempotencyKeyError(idemp_key)

        # 3. Verify Account Exists & Active
        with self._session_factory() as session:
            acc_repo = SQLAccountRepository(session)
            account_preview = acc_repo.get_by_number(acc_str)
            if account_preview is None:
                raise AccountNotFoundError(acc_str)
            if not account_preview.is_active:
                raise AccountClosedError(acc_str)
            if account_preview.is_frozen:
                raise AccountFrozenError(acc_str, "Account risk hold in effect")

        # 4. Calculate Fee and Identify Card Details
        fee_money = PaymentRailsSimulator.calculate_interchange_fee(channel_enum, gross_money)
        card_brand: Optional[str] = None
        last4: Optional[str] = None

        if channel_enum == PaymentChannel.CARD and request.card_number:
            clean_card = re.sub(r"\D", "", request.card_number)
            card_brand = PaymentRailsSimulator.detect_card_brand(clean_card)
            last4 = clean_card[-4:] if len(clean_card) >= 4 else "0000"

        # 5. Process Network Clearance
        approved, auth_code, decline_reason = PaymentRailsSimulator.process_authorization(
            channel=channel_enum,
            amount=gross_money,
            card_number=request.card_number,
            card_exp=request.card_exp,
            card_cvv=request.card_cvv,
            routing_number=request.routing_number,
        )

        payment_id = f"PAY-{uuid.uuid4().hex[:12].upper()}"

        if not approved:
            # Record decline
            declined_payment = PaymentTransaction(
                payment_id=payment_id,
                account_number=AccountNumber(acc_str),
                channel=channel_enum,
                direction=PaymentDirection.INBOUND,
                amount=gross_money,
                fee=fee_money,
                status=PaymentStatus.DECLINED,
                merchant_name=request.merchant_name,
                customer_name=request.customer_name,
                idempotency_key=idemp_key,
                card_brand=card_brand,
                last4=last4,
                description=request.description or f"{channel_enum.value} Payment Attempt",
                failure_reason=decline_reason,
            )
            with self._session_factory() as session:
                with session.begin():
                    SQLPaymentRepository(session).save(declined_payment)

            self._emit(
                PaymentDeclinedEvent(
                    payment_id=payment_id,
                    account_number=acc_str,
                    amount=gross_money.amount,
                    reason=decline_reason or "Card issuer declined payment",
                    timestamp=declined_payment.created_at,
                    actor=actor,
                )
            )
            raise PaymentDeclinedError(decline_reason or "Card issuer declined payment")

        # 6. Atomic Core Ledger Settlement
        with self._lock_manager.get_lock(acc_str):
            with self._session_factory() as session:
                with session.begin():
                    acc_repo = SQLAccountRepository(session)
                    tx_repo = SQLTransactionRepository(session)
                    pay_repo = SQLPaymentRepository(session)

                    account = acc_repo.get_by_number_for_update(acc_str)
                    if account is None:
                        raise AccountNotFoundError(acc_str)
                    if not account.is_active:
                        raise AccountClosedError(acc_str)
                    if account.is_frozen:
                        raise AccountFrozenError(acc_str)

                    # Inbound merchant settlement: Net settlement = Gross - Interchange Fee
                    net_settlement = gross_money - fee_money

                    tx_entity = account.credit(
                        amount=net_settlement,
                        transaction_type=TransactionType.DEPOSIT,
                        description=(
                            f"Gateway Settlement ({channel_enum.value}): {request.merchant_name} "
                            f"(Gross: ${gross_money.amount:,.2f}, Fee: ${fee_money.amount:,.2f})"
                        ),
                        ref=f"GW-{uuid.uuid4().hex[:12].upper()}",
                        actor=actor,
                    )
                    acc_repo.save(account)
                    tx_repo.append(tx_entity)

                    payment = PaymentTransaction(
                        payment_id=payment_id,
                        account_number=AccountNumber(acc_str),
                        channel=channel_enum,
                        direction=PaymentDirection.INBOUND,
                        amount=gross_money,
                        fee=fee_money,
                        status=PaymentStatus.SETTLED,
                        merchant_name=request.merchant_name,
                        customer_name=request.customer_name,
                        idempotency_key=idemp_key,
                        card_brand=card_brand,
                        last4=last4,
                        description=request.description or f"{channel_enum.value} Gateway Settlement",
                        settled_at=datetime.now(timezone.utc),
                    )
                    pay_repo.save(payment)
                    dto = PaymentTransactionDTO.from_entity(payment)

                    event = PaymentProcessedEvent(
                        payment_id=payment.payment_id,
                        account_number=acc_str,
                        channel=channel_enum.value,
                        amount=gross_money.amount,
                        fee=fee_money.amount,
                        net_amount=net_settlement.amount,
                        merchant_name=request.merchant_name,
                        timestamp=payment.created_at,
                        actor=actor,
                    )

        self._emit(event)
        return dto

    def refund_gateway_payment(
        self,
        payment_id: str,
        reason: str = "Customer requested refund",
        actor: str = "teller",
    ) -> PaymentRefundResultDTO:
        """Issue full reversal and refund against an established settled gateway transaction."""
        clean_id = payment_id.strip()

        with self._session_factory() as session:
            pay_repo = SQLPaymentRepository(session)
            payment = pay_repo.get_by_id(clean_id)
            if payment is None:
                raise PaymentRefundError(f"Payment transaction '{clean_id}' does not exist.")
            if payment.status != PaymentStatus.SETTLED:
                raise PaymentRefundError(
                    f"Only settled payments can be refunded. Current status is {payment.status.value}."
                )
            acc_str = payment.account_number.value
            net_amt = payment.net_amount

        # Atomic debit reversal from account
        with self._lock_manager.get_lock(acc_str):
            with self._session_factory() as session:
                with session.begin():
                    acc_repo = SQLAccountRepository(session)
                    tx_repo = SQLTransactionRepository(session)
                    pay_repo = SQLPaymentRepository(session)

                    account = acc_repo.get_by_number_for_update(acc_str)
                    if account is None:
                        raise AccountNotFoundError(acc_str)
                    if not account.is_active:
                        raise AccountClosedError(acc_str)
                    if account.is_frozen:
                        raise AccountFrozenError(acc_str)

                    if account.balance < net_amt:
                        raise InsufficientFundsError(
                            current_balance=str(account.balance),
                            requested_amount=str(net_amt),
                        )

                    tx_entity = account.debit(
                        amount=net_amt,
                        transaction_type=TransactionType.WITHDRAWAL,
                        description=f"Gateway Refund ({payment.payment_id}): {reason}",
                        ref=f"REF-{uuid.uuid4().hex[:12].upper()}",
                        actor=actor,
                    )
                    acc_repo.save(account)
                    tx_repo.append(tx_entity)

                    payment.refund(reason=reason)
                    pay_repo.save(payment)

                    now = datetime.now(timezone.utc)
                    result_dto = PaymentRefundResultDTO(
                        payment_id=payment.payment_id,
                        account_number=acc_str,
                        refunded_amount=net_amt.amount,
                        refund_reason=reason,
                        status="REFUNDED",
                        timestamp=now,
                    )

                    event = PaymentRefundedEvent(
                        payment_id=payment.payment_id,
                        account_number=acc_str,
                        refund_amount=net_amt.amount,
                        reason=reason,
                        timestamp=now,
                        actor=actor,
                    )

        self._emit(event)
        return result_dto

    def list_gateway_payments(
        self,
        account_number: Optional[Union[AccountNumber, str]] = None,
        channel: Optional[str] = None,
        status: Optional[str] = None,
        page: int = 1,
        page_size: int = 50,
    ) -> tuple[list[PaymentTransactionDTO], int]:
        """Query paginated payment transactions with optional filters."""
        offset = max(0, (page - 1) * page_size)
        with self._session_factory() as session:
            pay_repo = SQLPaymentRepository(session)
            entities, total_count = pay_repo.list_payments(
                account_number=account_number,
                channel=channel,
                status=status,
                limit=page_size,
                offset=offset,
            )
            return [PaymentTransactionDTO.from_entity(e) for e in entities], total_count

    def get_gateway_payment(self, payment_id: str) -> Optional[PaymentTransactionDTO]:
        """Fetch a specific payment transaction record by payment_id."""
        with self._session_factory() as session:
            pay_repo = SQLPaymentRepository(session)
            entity = pay_repo.get_by_id(payment_id)
            return PaymentTransactionDTO.from_entity(entity) if entity is not None else None

    def export_payments_csv(
        self,
        payments: Sequence[PaymentTransactionDTO],
        destination: Optional[Union[str, Path, TextIO]] = None,
        *,
        encoding: str = "utf-8",
        sanitize_formulas: bool = True,
    ) -> str:
        """Export gateway payment records directly to RFC-4180 CSV."""
        import csv
        import io
        from novabank.application.services.export_service import ExportService

        string_buffer = io.StringIO()
        writer = csv.writer(string_buffer, lineterminator="\r\n", quoting=csv.QUOTE_MINIMAL)

        headers = [
            "Payment ID",
            "Date",
            "Account",
            "Channel",
            "Merchant",
            "Customer",
            "Gross Amount",
            "Fee",
            "Net Settled",
            "Status",
            "Card/Routing",
            "Description",
        ]
        writer.writerow(headers)

        for p in payments:
            card_info = f"{p.card_brand or 'Card'} ...{p.last4}" if p.last4 else p.channel
            row = [
                ExportService.sanitize_field(p.payment_id, sanitize_formulas),
                p.created_at.strftime("%Y-%m-%d %H:%M:%S"),
                p.account_number,
                p.channel,
                ExportService.sanitize_field(p.merchant_name, sanitize_formulas),
                ExportService.sanitize_field(p.customer_name, sanitize_formulas),
                f"{p.amount:.2f}",
                f"{p.fee:.2f}",
                f"{p.net_amount:.2f}",
                p.status,
                card_info,
                ExportService.sanitize_field(p.description, sanitize_formulas),
            ]
            writer.writerow(row)

        csv_content = string_buffer.getvalue()
        return ExportService._deliver_output(csv_content, destination, encoding)

    # -------------------------------------------------------------------------
    # Commercial Loan Hub & Amortization Engine
    # -------------------------------------------------------------------------

    def calculate_loan_quote(
        self,
        principal: Decimal,
        apr_percentage: Decimal,
        term_months: int,
    ) -> LoanQuoteResponseDTO:
        """Simulate Equal Monthly Installment (EMI) and interest figures without persistence."""
        principal_money = Money(principal)
        emi = AmortizationCalculator.calculate_monthly_installment(
            principal=principal_money,
            apr_percentage=apr_percentage,
            term_months=term_months,
        )
        schedule = AmortizationCalculator.generate_amortization_schedule(
            principal=principal_money,
            apr_percentage=apr_percentage,
            term_months=term_months,
        )
        total_interest = sum((entry.interest_amount.amount for entry in schedule), Decimal("0.00"))
        total_payable = principal + total_interest

        return LoanQuoteResponseDTO(
            principal=principal,
            apr_percentage=apr_percentage,
            term_months=term_months,
            monthly_installment=emi.amount,
            total_interest=total_interest,
            total_payable=total_payable,
        )

    def originate_loan(
        self,
        request: LoanOriginationRequestDTO,
        actor: str = "lending_officer",
    ) -> LoanContractDTO:
        """Originate, underwrite, disburse, and persist a commercial loan facility."""
        acc_str = str(request.account_number).strip().replace("-", "").replace(" ", "")
        principal_money = Money(request.principal)

        if not principal_money.is_positive():
            raise InvalidLoanTermsError("Principal amount must be positive.")
        if request.term_months <= 0 or request.term_months > 360:
            raise InvalidLoanTermsError(f"Loan term must be between 1 and 360 months, got {request.term_months}.")
        if request.apr_percentage <= Decimal("0.00") or request.apr_percentage > Decimal("100.00"):
            raise InvalidLoanTermsError(f"APR rate must be between 0.01% and 100.00%, got {request.apr_percentage}%.")

        loan_id = f"LN-{uuid.uuid4().hex[:8].upper()}"
        schedule = AmortizationCalculator.generate_amortization_schedule(
            principal=principal_money,
            apr_percentage=request.apr_percentage,
            term_months=request.term_months,
        )
        emi = AmortizationCalculator.calculate_monthly_installment(
            principal=principal_money,
            apr_percentage=request.apr_percentage,
            term_months=request.term_months,
        )
        total_interest = Money(sum(item.interest_amount.amount for item in schedule))

        loan = LoanContract(
            loan_id=loan_id,
            account_number=AccountNumber(acc_str),
            loan_type=LoanType(request.loan_type),
            principal_amount=principal_money,
            interest_rate_apr=request.apr_percentage,
            term_months=request.term_months,
            monthly_installment=emi,
            outstanding_balance=principal_money,
            total_interest=total_interest,
            status=LoanStatus.SUBMITTED,
            schedule=schedule,
            purpose=request.purpose,
        )
        loan.disburse(actor)

        # Atomic disbursement into borrower account
        with self._lock_manager.get_lock(acc_str):
            with self._session_factory() as session:
                with session.begin():
                    account_repo = SQLAccountRepository(session)
                    tx_repo = SQLTransactionRepository(session)
                    loan_repo = SQLLoanRepository(session)

                    account = account_repo.get_by_number_for_update(acc_str)
                    if account is None:
                        raise AccountNotFoundError(acc_str)
                    if not account.is_active:
                        raise AccountClosedError(acc_str)
                    if account.is_frozen:
                        raise AccountFrozenError(acc_str)

                    # Credit borrower checking account
                    tx_entity = account.credit(
                        amount=principal_money,
                        transaction_type=TransactionType.DEPOSIT,
                        description=f"Loan Disbursement: {loan.loan_id} ({request.loan_type})",
                        ref=f"TXN-DISB-{uuid.uuid4().hex[:8].upper()}",
                        actor=actor,
                    )

                    account_repo.save(account)
                    tx_repo.append(tx_entity)
                    loan_repo.save(loan)

                    deposit_event = DepositCompletedEvent(
                        account_number=account.account_number.value,
                        amount=principal_money.amount,
                        balance_after=account.balance.amount,
                        currency=account.balance.currency,
                        transaction_ref=tx_entity.transaction_ref,
                        timestamp=tx_entity.created_at,
                        actor=actor,
                        description=tx_entity.description,
                    )

                    origination_event = LoanOriginatedEvent(
                        loan_id=loan.loan_id,
                        account_number=loan.account_number.value,
                        principal=loan.principal_amount.amount,
                        interest_rate_apr=loan.interest_rate_apr,
                        term_months=loan.term_months,
                        monthly_installment=loan.monthly_installment.amount,
                        timestamp=loan.originated_at,
                        actor=actor,
                    )

        self._emit(deposit_event)
        self._emit(origination_event)
        return LoanContractDTO.from_entity(loan)

    def repay_loan_installment(
        self,
        loan_id: str,
        amount: Optional[Decimal] = None,
        actor: str = "teller",
    ) -> LoanRepaymentResultDTO:
        """Atomically debit borrower account and settle scheduled amortization installment."""
        with self._session_factory() as session:
            loan_repo = SQLLoanRepository(session)
            loan = loan_repo.get_by_id(loan_id)
            if loan is None:
                raise LoanNotFoundError(f"Loan facility '{loan_id}' not found.")

        if loan.status == LoanStatus.PAID_OFF:
            raise LoanAlreadyPaidOffError(f"Loan '{loan_id}' is already paid off in full.")

        target_entry = next((e for e in loan.schedule if not e.is_paid), None)
        if target_entry is None:
            raise LoanAlreadyPaidOffError(f"Loan '{loan_id}' has no remaining unpaid installments.")

        repayment_money = Money(amount) if amount is not None else target_entry.payment_amount
        acc_str = loan.account_number.value

        with self._lock_manager.get_lock(acc_str):
            with self._session_factory() as session:
                with session.begin():
                    account_repo = SQLAccountRepository(session)
                    tx_repo = SQLTransactionRepository(session)
                    loan_repo = SQLLoanRepository(session)

                    account = account_repo.get_by_number_for_update(acc_str)
                    if account is None:
                        raise AccountNotFoundError(acc_str)
                    if not account.is_active:
                        raise AccountClosedError(acc_str)
                    if account.is_frozen:
                        raise AccountFrozenError(acc_str)

                    if account.balance < repayment_money:
                        raise InsufficientFundsError(
                            f"Account {acc_str} has insufficient funds for loan repayment: {account.balance.formatted()} available vs {repayment_money.formatted()} required."
                        )

                    # Reload loan within transaction for concurrency safety
                    locked_loan = loan_repo.get_by_id(loan_id)
                    if locked_loan is None:
                        raise LoanNotFoundError(f"Loan facility '{loan_id}' not found.")

                    principal_paid, interest_paid = locked_loan.process_repayment(
                        amount=repayment_money,
                        actor=actor,
                    )

                    # Debit borrower account
                    tx_entity = account.debit(
                        amount=repayment_money,
                        transaction_type=TransactionType.WITHDRAWAL,
                        description=f"Loan Repayment: {loan_id} - Inst #{target_entry.installment_number}",
                        ref=f"TXN-REPAY-{uuid.uuid4().hex[:8].upper()}",
                        actor=actor,
                    )

                    account_repo.save(account)
                    tx_repo.append(tx_entity)
                    loan_repo.save(locked_loan)

                    now = datetime.now(timezone.utc)
                    withdrawal_event = WithdrawalCompletedEvent(
                        account_number=account.account_number.value,
                        amount=repayment_money.amount,
                        balance_after=account.balance.amount,
                        currency=account.balance.currency,
                        transaction_ref=tx_entity.transaction_ref,
                        timestamp=tx_entity.created_at,
                        actor=actor,
                        description=tx_entity.description,
                    )

                    repayment_event = LoanRepaymentProcessedEvent(
                        loan_id=locked_loan.loan_id,
                        account_number=locked_loan.account_number.value,
                        amount=repayment_money.amount,
                        principal_portion=principal_paid.amount,
                        interest_portion=interest_paid.amount,
                        remaining_balance=locked_loan.outstanding_balance.amount,
                        timestamp=now,
                        actor=actor,
                    )

                    paid_off_event = None
                    if locked_loan.status == LoanStatus.PAID_OFF:
                        paid_off_event = LoanPaidOffEvent(
                            loan_id=locked_loan.loan_id,
                            account_number=locked_loan.account_number.value,
                            total_principal_paid=locked_loan.principal_amount.amount,
                            timestamp=now,
                            actor=actor,
                        )

                    result_dto = LoanRepaymentResultDTO(
                        loan_id=locked_loan.loan_id,
                        account_number=locked_loan.account_number.value,
                        installment_number=target_entry.installment_number,
                        repayment_amount=repayment_money.amount,
                        principal_portion=principal_paid.amount,
                        interest_portion=interest_paid.amount,
                        remaining_balance=locked_loan.outstanding_balance.amount,
                        new_status=locked_loan.status.value,
                        next_due_date=locked_loan.next_due_date.isoformat() if locked_loan.next_due_date else None,
                        timestamp=now,
                    )

        self._emit(withdrawal_event)
        self._emit(repayment_event)
        if paid_off_event:
            self._emit(paid_off_event)

        return result_dto

    def get_loan(self, loan_id: str) -> Optional[LoanContractDTO]:
        """Fetch a specific loan facility by facility identifier."""
        with self._session_factory() as session:
            loan_repo = SQLLoanRepository(session)
            loan = loan_repo.get_by_id(loan_id)
            return LoanContractDTO.from_entity(loan) if loan is not None else None

    def list_loans(
        self,
        account_number: Optional[str] = None,
        status: Optional[str] = None,
        page: int = 1,
        page_size: int = 50,
    ) -> tuple[list[LoanContractDTO], int]:
        """List paginated loan contracts with optional account and status filters."""
        limit = max(1, page_size)
        offset = max(0, (page - 1) * limit)
        with self._session_factory() as session:
            loan_repo = SQLLoanRepository(session)
            loans, total = loan_repo.list_loans(
                account_number=account_number,
                status=status,
                limit=limit,
                offset=offset,
            )
            return [LoanContractDTO.from_entity(ln) for ln in loans], total

    def export_loan_schedule_csv(
        self,
        loan_id: str,
        destination: Optional[Union[str, Path, TextIO]] = None,
        *,
        encoding: str = "utf-8",
        sanitize_formulas: bool = True,
    ) -> str:
        """Export loan amortization schedule directly to RFC-4180 CSV."""
        import csv
        import io
        from novabank.application.services.export_service import ExportService

        loan = self.get_loan(loan_id)
        if loan is None:
            raise LoanNotFoundError(f"Loan facility '{loan_id}' not found.")

        string_buffer = io.StringIO()
        writer = csv.writer(string_buffer, lineterminator="\r\n", quoting=csv.QUOTE_MINIMAL)

        # File header with metadata
        writer.writerow(["# NovaBank Commercial Loan Amortization Schedule"])
        writer.writerow(["# Facility ID", loan.loan_id])
        writer.writerow(["# Borrower Account", loan.account_number])
        writer.writerow(["# Principal", f"{loan.principal_amount:.2f}"])
        writer.writerow(["# APR Rate", f"{loan.interest_rate_apr}%"])
        writer.writerow(["# Term (Months)", str(loan.term_months)])
        writer.writerow(["# Monthly Installment", f"{loan.monthly_installment:.2f}"])
        writer.writerow([])

        headers = [
            "Installment #",
            "Due Date",
            "Monthly Payment",
            "Principal Paid",
            "Interest Paid",
            "Remaining Balance",
            "Status",
            "Settled Date",
        ]
        writer.writerow(headers)

        for entry in loan.schedule:
            status_label = "SETTLED" if entry.is_paid else "SCHEDULED"
            row = [
                entry.installment_number,
                entry.due_date,
                f"{entry.payment_amount:.2f}",
                f"{entry.principal_amount:.2f}",
                f"{entry.interest_amount:.2f}",
                f"{entry.remaining_balance:.2f}",
                status_label,
                entry.paid_date or "—",
            ]
            writer.writerow(row)

        csv_content = string_buffer.getvalue()
        return ExportService._deliver_output(csv_content, destination, encoding)

    # -------------------------------------------------------------------------
    # Term Deposits & Certificate of Deposit (CD) Vault Engine
    # -------------------------------------------------------------------------

    def simulate_term_deposit(
        self,
        principal: Decimal,
        tenor_months: int,
        apy_percentage: Decimal,
        payout_frequency: str = "AT_MATURITY",
    ) -> CDSimulationResponseDTO:
        """Simulate compound interest returns and maturity payout without persistence."""
        principal_money = Money(principal)
        if not principal_money.is_positive():
            raise InvalidTermDepositTermsError("Deposit principal must be strictly positive.")
        if principal < Decimal("500.00"):
            raise InvalidTermDepositTermsError("Minimum principal for CD vault issuance is $500.00.")
        if tenor_months <= 0 or tenor_months > 120:
            raise InvalidTermDepositTermsError(f"Tenor must be between 1 and 120 months, got {tenor_months}.")
        if apy_percentage <= Decimal("0.00") or apy_percentage > Decimal("30.00"):
            raise InvalidTermDepositTermsError(f"APY must be between 0.01% and 30.00%, got {apy_percentage}%.")

        projected_int = TermDepositCalculator.calculate_projected_interest(
            principal=principal_money,
            apy_percentage=apy_percentage,
            tenor_months=tenor_months,
        )
        total_payout = principal + projected_int.amount
        today = date.today()
        maturity_date = TermDepositCalculator.add_months(today, tenor_months)

        temp_cd = CertificateOfDeposit(
            cd_id="SIM",
            account_number=AccountNumber("100000000001"),
            principal_amount=principal_money,
            interest_rate_apy=apy_percentage,
            tenor_months=tenor_months,
            issue_date=today,
            maturity_date=maturity_date,
            payout_frequency=TermDepositPayoutFrequency(payout_frequency),
            rollover_option=TermDepositRolloverOption.PAYOUT_AND_CLOSE,
        )
        accrual_dtos = [CDAccrualMilestoneDTO.from_entity(m) for m in temp_cd.accruals]

        return CDSimulationResponseDTO(
            principal=principal,
            apy_percentage=apy_percentage,
            tenor_months=tenor_months,
            projected_interest=projected_int.amount,
            total_payout_at_maturity=total_payout,
            issue_date=today.isoformat(),
            maturity_date=maturity_date.isoformat(),
            accrual_milestones=accrual_dtos,
        )

    def open_term_deposit(
        self,
        request: OpenCDRequestDTO,
        actor: str = "teller",
    ) -> CertificateOfDepositDTO:
        """Atomically lock funding account balances and issue an institutional Certificate of Deposit."""
        acc_str = str(request.account_number).strip().replace("-", "").replace(" ", "")
        principal_money = Money(request.principal)

        if not principal_money.is_positive():
            raise InvalidTermDepositTermsError("Deposit principal must be strictly positive.")
        if request.principal < Decimal("500.00"):
            raise InvalidTermDepositTermsError("Minimum principal for CD vault issuance is $500.00.")
        if request.tenor_months <= 0 or request.tenor_months > 120:
            raise InvalidTermDepositTermsError(f"Tenor must be between 1 and 120 months, got {request.tenor_months}.")
        if request.apy_percentage <= Decimal("0.00") or request.apy_percentage > Decimal("30.00"):
            raise InvalidTermDepositTermsError(f"APY must be between 0.01% and 30.00%, got {request.apy_percentage}%.")

        cd_id = f"CD-{uuid.uuid4().hex[:8].upper()}"
        issue_d = date.today()
        mat_d = TermDepositCalculator.add_months(issue_d, request.tenor_months)

        # Standard regulatory penalty: 3 months of simple interest for tenors <= 12m, 6 months for tenors > 12m
        penalty_months = 3 if request.tenor_months <= 12 else 6

        cd = CertificateOfDeposit(
            cd_id=cd_id,
            account_number=AccountNumber(acc_str),
            principal_amount=principal_money,
            interest_rate_apy=request.apy_percentage,
            tenor_months=request.tenor_months,
            issue_date=issue_d,
            maturity_date=mat_d,
            payout_frequency=TermDepositPayoutFrequency(request.payout_frequency),
            rollover_option=TermDepositRolloverOption(request.rollover_option),
            early_withdrawal_penalty_months=penalty_months,
            status=TermDepositStatus.ACTIVE,
        )

        with self._lock_manager.get_lock(acc_str):
            with self._session_factory() as session:
                with session.begin():
                    account_repo = SQLAccountRepository(session)
                    tx_repo = SQLTransactionRepository(session)
                    cd_repo = SQLTermDepositRepository(session)

                    account = account_repo.get_by_number_for_update(acc_str)
                    if account is None:
                        raise AccountNotFoundError(acc_str)
                    if not account.is_active:
                        raise AccountClosedError(acc_str)
                    if account.is_frozen:
                        raise AccountFrozenError(acc_str)

                    if account.balance < principal_money:
                        raise InsufficientFundsError(
                            current_balance=account.balance.formatted(),
                            requested_amount=principal_money.formatted(),
                        )

                    # Debit funding account
                    tx_entity = account.debit(
                        amount=principal_money,
                        transaction_type=TransactionType.WITHDRAWAL,
                        description=f"CD Vault Funding: {cd.cd_id} ({request.tenor_months}M @ {request.apy_percentage}% APY)",
                        ref=f"TXN-CDLOCK-{uuid.uuid4().hex[:8].upper()}",
                        actor=actor,
                    )

                    account_repo.save(account)
                    tx_repo.append(tx_entity)
                    cd_repo.save(cd)

                    now = datetime.now(timezone.utc)
                    withdrawal_event = WithdrawalCompletedEvent(
                        account_number=account.account_number.value,
                        amount=principal_money.amount,
                        balance_after=account.balance.amount,
                        currency=account.balance.currency,
                        transaction_ref=tx_entity.transaction_ref,
                        timestamp=tx_entity.created_at,
                        actor=actor,
                        description=tx_entity.description,
                    )

                    cd_opened_event = TermDepositOpenedEvent(
                        cd_id=cd.cd_id,
                        certificate_number=cd.certificate_number,
                        account_number=cd.account_number.value,
                        principal=cd.principal_amount.amount,
                        interest_rate_apy=cd.interest_rate_apy,
                        tenor_months=cd.tenor_months,
                        maturity_date=cd.maturity_date.isoformat(),
                        timestamp=now,
                        actor=actor,
                    )

        self._emit(withdrawal_event)
        self._emit(cd_opened_event)
        return CertificateOfDepositDTO.from_entity(cd)

    def preview_early_redemption(
        self,
        cd_id: str,
        as_of_date: Optional[date] = None,
    ) -> EarlyRedemptionPreviewDTO:
        """Preview early liquidation penalty and net payout without modifying state."""
        with self._session_factory() as session:
            cd_repo = SQLTermDepositRepository(session)
            cd = cd_repo.get_by_id(cd_id)
            if cd is None:
                raise TermDepositNotFoundError(cd_id)

        target_date = as_of_date or date.today()
        principal, accrued, penalty, net_payout = cd.calculate_early_redemption_preview(target_date)

        return EarlyRedemptionPreviewDTO(
            cd_id=cd.cd_id,
            certificate_number=cd.certificate_number,
            account_number=cd.account_number.value,
            principal=principal.amount,
            accrued_interest=accrued.amount,
            penalty=penalty.amount,
            net_payout=net_payout.amount,
            days_held=max(0, (target_date - cd.issue_date).days),
            penalty_months=cd.early_withdrawal_penalty_months,
        )

    def redeem_term_deposit(
        self,
        cd_id: str,
        is_premature: bool = False,
        as_of_date: Optional[date] = None,
        destination_account: Optional[str] = None,
        actor: str = "teller",
    ) -> RedemptionResultDTO:
        """Redeem a Certificate of Deposit at maturity or liquidating prematurely with penalties."""
        with self._session_factory() as session:
            cd_repo = SQLTermDepositRepository(session)
            cd = cd_repo.get_by_id(cd_id)
            if cd is None:
                raise TermDepositNotFoundError(cd_id)

        if cd.status != TermDepositStatus.ACTIVE:
            raise TermDepositAlreadyClosedError(f"CD vault contract '{cd_id}' is already {cd.status.value}.")

        target_date = as_of_date or date.today()
        dest_acc_str = (
            destination_account.strip().replace("-", "").replace(" ", "")
            if destination_account
            else cd.account_number.value
        )

        with self._lock_manager.get_lock(dest_acc_str):
            with self._session_factory() as session:
                with session.begin():
                    account_repo = SQLAccountRepository(session)
                    tx_repo = SQLTransactionRepository(session)
                    cd_repo = SQLTermDepositRepository(session)

                    account = account_repo.get_by_number_for_update(dest_acc_str)
                    if account is None:
                        raise AccountNotFoundError(dest_acc_str)
                    if not account.is_active:
                        raise AccountClosedError(dest_acc_str)
                    if account.is_frozen:
                        raise AccountFrozenError(dest_acc_str)

                    # Reload locked CD
                    locked_cd = cd_repo.get_by_id(cd_id)
                    if locked_cd is None:
                        raise TermDepositNotFoundError(cd_id)

                    now = datetime.now(timezone.utc)

                    if is_premature:
                        principal, net_interest, penalty = locked_cd.close_prematurely(target_date, actor=actor)
                        total_payout_amount = principal.amount + net_interest.amount
                        if total_payout_amount < Decimal("0.00"):
                            total_payout_amount = Decimal("0.00")
                        payout_money = Money(total_payout_amount)

                        desc = (
                            f"CD Early Liquidation: {cd_id} "
                            f"(Net Payout after ${penalty.amount:,.2f} penalty)"
                        )
                        redemption_event = TermDepositEarlyRedeemedEvent(
                            cd_id=locked_cd.cd_id,
                            certificate_number=locked_cd.certificate_number,
                            account_number=dest_acc_str,
                            principal=principal.amount,
                            accrued_interest=locked_cd.accrued_interest.amount,
                            penalty_deducted=penalty.amount,
                            net_payout=payout_money.amount,
                            timestamp=now,
                            actor=actor,
                        )
                        interest_portion = net_interest.amount
                        penalty_portion = penalty.amount
                    else:
                        payout_money = locked_cd.mature(target_date, actor=actor)
                        desc = (
                            f"CD Maturity Settlement: {cd_id} "
                            f"(Principal + ${locked_cd.projected_interest_at_maturity.amount:,.2f} Interest)"
                        )
                        redemption_event = TermDepositMaturedEvent(
                            cd_id=locked_cd.cd_id,
                            certificate_number=locked_cd.certificate_number,
                            account_number=dest_acc_str,
                            principal=locked_cd.principal_amount.amount,
                            interest_paid=locked_cd.projected_interest_at_maturity.amount,
                            total_payout=payout_money.amount,
                            timestamp=now,
                            actor=actor,
                        )
                        interest_portion = locked_cd.projected_interest_at_maturity.amount
                        penalty_portion = Decimal("0.00")

                    # Credit payout to destination checking/savings account
                    tx_entity = account.credit(
                        amount=payout_money,
                        transaction_type=TransactionType.DEPOSIT,
                        description=desc,
                        ref=f"TXN-CDPAY-{uuid.uuid4().hex[:8].upper()}",
                        actor=actor,
                    )

                    account_repo.save(account)
                    tx_repo.append(tx_entity)
                    cd_repo.save(locked_cd)

                    deposit_event = DepositCompletedEvent(
                        account_number=account.account_number.value,
                        amount=payout_money.amount,
                        balance_after=account.balance.amount,
                        currency=account.balance.currency,
                        transaction_ref=tx_entity.transaction_ref,
                        timestamp=tx_entity.created_at,
                        actor=actor,
                        description=tx_entity.description,
                    )

                    result_dto = RedemptionResultDTO(
                        cd_id=locked_cd.cd_id,
                        certificate_number=locked_cd.certificate_number,
                        account_number=dest_acc_str,
                        principal=locked_cd.principal_amount.amount,
                        interest_paid=interest_portion,
                        penalty_deducted=penalty_portion,
                        net_payout=payout_money.amount,
                        status=locked_cd.status.value,
                        timestamp=now,
                        new_account_balance=account.balance.amount,
                    )

        self._emit(deposit_event)
        self._emit(redemption_event)
        return result_dto

    def get_term_deposit(self, cd_id: str) -> Optional[CertificateOfDepositDTO]:
        """Fetch Certificate of Deposit by unique facility identifier."""
        with self._session_factory() as session:
            cd_repo = SQLTermDepositRepository(session)
            cd = cd_repo.get_by_id(cd_id)
            return CertificateOfDepositDTO.from_entity(cd) if cd is not None else None

    def list_term_deposits(
        self,
        account_number: Optional[str] = None,
        status: Optional[str] = None,
        page: int = 1,
        page_size: int = 50,
    ) -> tuple[list[CertificateOfDepositDTO], int]:
        """List paginated Certificate of Deposit records with optional account and status filters."""
        limit = max(1, page_size)
        offset = max(0, (page - 1) * limit)
        with self._session_factory() as session:
            cd_repo = SQLTermDepositRepository(session)
            cds, total = cd_repo.list_term_deposits(
                account_number=account_number,
                status=status,
                limit=limit,
                offset=offset,
            )
            return [CertificateOfDepositDTO.from_entity(c) for c in cds], total

    def export_term_deposits_csv(
        self,
        cds: Sequence[CertificateOfDepositDTO],
        destination: Optional[Union[str, Path, TextIO]] = None,
        *,
        encoding: str = "utf-8",
        sanitize_formulas: bool = True,
    ) -> str:
        """Export Certificate of Deposit records directly to RFC-4180 CSV."""
        import csv
        import io
        from novabank.application.services.export_service import ExportService

        string_buffer = io.StringIO()
        writer = csv.writer(string_buffer, lineterminator="\r\n", quoting=csv.QUOTE_MINIMAL)

        headers = [
            "Certificate ID",
            "Certificate Number",
            "Account Number",
            "Principal",
            "APY %",
            "Tenor (Months)",
            "Issue Date",
            "Maturity Date",
            "Payout Frequency",
            "Accrued Interest",
            "Projected Interest",
            "Total Matured Payout",
            "Status",
        ]
        writer.writerow(headers)

        for c in cds:
            row = [
                ExportService.sanitize_field(c.cd_id, sanitize_formulas),
                ExportService.sanitize_field(c.certificate_number, sanitize_formulas),
                c.account_number,
                f"{c.principal_amount:.2f}",
                f"{c.interest_rate_apy}%",
                c.tenor_months,
                c.issue_date,
                c.maturity_date,
                c.payout_frequency,
                f"{c.accrued_interest:.2f}",
                f"{c.projected_interest_at_maturity:.2f}",
                f"{c.total_payout_at_maturity:.2f}",
                c.status,
            ]
            writer.writerow(row)

        csv_content = string_buffer.getvalue()
        return ExportService._deliver_output(csv_content, destination, encoding)

    # -------------------------------------------------------------------------
    # Foreign Exchange (FX) & Treasury Desk Operations
    # -------------------------------------------------------------------------

    def quote_fx_exchange(
        self,
        source_currency: Union[str, FXQuoteRequestDTO],
        target_currency: Optional[str] = None,
        source_amount: Optional[Decimal] = None,
        spread_bps: int = 20,
    ) -> FXQuoteResponseDTO:
        """Calculate guaranteed spot conversion quote with fee and spread breakdown."""
        if isinstance(source_currency, FXQuoteRequestDTO):
            src = source_currency.source_currency.strip().upper()
            tgt = source_currency.target_currency.strip().upper()
            amount = source_currency.source_amount
        else:
            src = str(source_currency).strip().upper()
            tgt = str(target_currency).strip().upper() if target_currency else ""
            amount = source_amount if source_amount is not None else Decimal("0.00")

        if src not in SUPPORTED_CURRENCIES:
            raise UnsupportedCurrencyError(src)
        if tgt not in SUPPORTED_CURRENCIES:
            raise UnsupportedCurrencyError(tgt)
        if src == tgt:
            raise InvalidFXAmountError("Source and target currencies must differ for FX exchange.")
        if amount <= Decimal("0.00"):
            raise InvalidFXAmountError("Exchange amount must be strictly positive.")

        with self._session_factory() as session:
            fx_repo = SQLFXRepository(session)
            rates_dict = {pair: r.spot_rate for pair, r in fx_repo.get_rates().items()}

        (
            spot_rate,
            effective_rate,
            target_amount,
            fee,
            spread_revenue_usd,
        ) = FXCalculator.compute_conversion(
            source_currency=src,
            target_currency=tgt,
            source_amount=amount,
            spread_bps=spread_bps,
            rates_map=rates_dict,
        )

        return FXQuoteResponseDTO(
            source_currency=src,
            target_currency=tgt,
            source_amount=amount,
            target_amount=target_amount,
            spot_rate=spot_rate,
            effective_rate=effective_rate,
            spread_bps=spread_bps,
            fee_amount=fee,
            spread_revenue_usd=spread_revenue_usd,
            guaranteed_seconds=60,
        )

    def execute_fx_conversion(
        self,
        request: ExecuteFXTradeRequestDTO,
    ) -> FXTradeDTO:
        """Execute atomic spot Foreign Exchange conversion, debit customer balance, and update treasury positions."""
        acc_str = str(request.account_number).strip().replace("-", "").replace(" ", "")
        src = request.source_currency.strip().upper()
        tgt = request.target_currency.strip().upper()

        if src not in SUPPORTED_CURRENCIES:
            raise UnsupportedCurrencyError(src)
        if tgt not in SUPPORTED_CURRENCIES:
            raise UnsupportedCurrencyError(tgt)
        if src == tgt:
            raise InvalidFXAmountError("Source and target currencies must differ for FX exchange.")
        if request.source_amount <= Decimal("0.00"):
            raise InvalidFXAmountError("Exchange amount must be strictly positive.")

        trade_id = f"FX-{uuid.uuid4().hex[:8].upper()}"
        now = datetime.now(timezone.utc)

        with self._lock_manager.get_lock(acc_str):
            with self._session_factory() as session:
                with session.begin():
                    account_repo = SQLAccountRepository(session)
                    tx_repo = SQLTransactionRepository(session)
                    fx_repo = SQLFXRepository(session)

                    account = account_repo.get_by_number_for_update(acc_str)
                    if account is None:
                        raise AccountNotFoundError(acc_str)
                    if not account.is_active:
                        raise AccountClosedError(acc_str)
                    if account.is_frozen:
                        raise AccountFrozenError(acc_str)

                    rates_dict = {pair: r.spot_rate for pair, r in fx_repo.get_rates().items()}

                    (
                        spot_rate,
                        effective_rate,
                        target_amount,
                        fee,
                        spread_revenue_usd,
                    ) = FXCalculator.compute_conversion(
                        source_currency=src,
                        target_currency=tgt,
                        source_amount=request.source_amount,
                        spread_bps=20,
                        rates_map=rates_dict,
                    )

                    # Determine required account debit amount in customer account currency
                    if account.balance.currency == src:
                        debit_amount = request.source_amount
                    else:
                        # Convert source currency to account currency (usually USD)
                        src_to_acc_rate = FXCalculator.resolve_spot_rate(src, account.balance.currency, rates_dict)
                        debit_amount = (request.source_amount * src_to_acc_rate).quantize(
                            Decimal("0.01"), rounding=ROUND_HALF_UP
                        )

                    debit_money = Money(debit_amount, currency=account.balance.currency)
                    if account.balance < debit_money:
                        raise InsufficientFundsError(
                            current_balance=account.balance.formatted(),
                            requested_amount=debit_money.formatted(),
                        )

                    # Debit customer account
                    desc_text = (
                        f"FX Spot Exchange: Sold {request.source_amount:,.2f} {src} "
                        f"for {target_amount:,.2f} {tgt} @ {effective_rate} (Ref: {trade_id})"
                    )
                    tx_entity = account.debit(
                        amount=debit_money,
                        transaction_type=TransactionType.WITHDRAWAL,
                        description=desc_text,
                        ref=trade_id,
                        actor=request.actor,
                    )

                    # Check and update Treasury Positions
                    pos_tgt = fx_repo.get_treasury_position(tgt)
                    if pos_tgt is None or pos_tgt.reserve_balance < target_amount:
                        avail = f"{pos_tgt.reserve_balance if pos_tgt else Decimal('0.00')} {tgt}"
                        raise InsufficientTreasuryReserveError(tgt, f"{target_amount} {tgt}", avail)

                    pos_tgt.withdraw(target_amount)
                    fx_repo.save_treasury_position(pos_tgt)

                    pos_src = fx_repo.get_treasury_position(src)
                    if pos_src is None:
                        pos_src = TreasuryPosition(src, Decimal("0.00"))
                    pos_src.deposit(request.source_amount)
                    fx_repo.save_treasury_position(pos_src)

                    fx_trade = FXTrade(
                        trade_id=trade_id,
                        account_number=account.account_number,
                        source_currency=src,
                        source_amount=request.source_amount,
                        target_currency=tgt,
                        target_amount=target_amount,
                        spot_rate=spot_rate,
                        effective_rate=effective_rate,
                        spread_bps=20,
                        spread_revenue_usd=spread_revenue_usd,
                        fee_amount=fee,
                        status=FXTradeStatus.EXECUTED,
                        settlement_reference=f"SWIFT-CLS-{uuid.uuid4().hex[:8].upper()}",
                        actor=request.actor,
                        executed_at=now,
                    )

                    account_repo.save(account)
                    tx_repo.append(tx_entity)
                    fx_repo.save_trade(fx_trade)

                    withdrawal_event = WithdrawalCompletedEvent(
                        account_number=account.account_number.value,
                        amount=debit_money.amount,
                        balance_after=account.balance.amount,
                        currency=account.balance.currency,
                        transaction_ref=tx_entity.transaction_ref,
                        timestamp=now,
                        actor=request.actor,
                        description=desc_text,
                    )

                    trade_event = FXTradeExecutedEvent(
                        trade_id=trade_id,
                        account_number=account.account_number.value,
                        source_currency=src,
                        source_amount=request.source_amount,
                        target_currency=tgt,
                        target_amount=target_amount,
                        effective_rate=effective_rate,
                        spread_revenue_usd=spread_revenue_usd,
                        fee_amount=fee,
                        settlement_reference=fx_trade.settlement_reference,
                        timestamp=now,
                        actor=request.actor,
                    )

                    pos_event = TreasuryPositionUpdatedEvent(
                        currency=tgt,
                        delta_amount=-target_amount,
                        new_balance=pos_tgt.reserve_balance,
                        timestamp=now,
                        actor=request.actor,
                    )

        self._emit(withdrawal_event)
        self._emit(trade_event)
        self._emit(pos_event)

        return FXTradeDTO.from_entity(fx_trade)

    def list_fx_trades(
        self,
        account_number: Optional[str] = None,
        currency_pair: Optional[str] = None,
        status: Optional[str] = None,
        pair: Optional[str] = None,
        page: int = 1,
        page_size: int = 50,
        limit: Optional[int] = None,
        offset: Optional[int] = None,
    ) -> tuple[list[FXTradeDTO], int]:
        """Query historical FX trade blotter with optional criteria and pagination."""
        resolved_pair = currency_pair or pair
        resolved_page_size = limit or page_size
        resolved_page = (offset // resolved_page_size + 1) if offset is not None else page
        with self._session_factory() as session:
            fx_repo = SQLFXRepository(session)
            trades, total = fx_repo.list_trades(
                account_number=account_number,
                currency_pair=resolved_pair,
                status=status,
                page=resolved_page,
                page_size=resolved_page_size,
            )
            return [FXTradeDTO.from_entity(t) for t in trades], total

    def get_treasury_overview(
        self,
    ) -> tuple[list[TreasuryPositionDTO], Decimal, Decimal, Decimal]:
        """Aggregate bank sovereign currency vault reserves, USD valuation, and 24h metrics."""
        with self._session_factory() as session:
            fx_repo = SQLFXRepository(session)
            positions = fx_repo.get_treasury_positions()
            rates_dict = {pair: r.spot_rate for pair, r in fx_repo.get_rates().items()}
            trades, _ = fx_repo.list_trades(page=1, page_size=500)

        # Compute total USD equivalent value across all reserves
        pos_dtos: list[TreasuryPositionDTO] = []
        total_usd_value = Decimal("0.00")

        # First pass: calculate USD equivalents
        interim: list[tuple[TreasuryPosition, Decimal, Decimal]] = []
        for p in positions:
            spot_to_usd = FXCalculator.resolve_spot_rate(p.currency, "USD", rates_dict)
            usd_val = (p.reserve_balance * spot_to_usd).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
            total_usd_value += usd_val
            interim.append((p, usd_val, spot_to_usd))

        # Second pass: calculate allocations
        for p, usd_val, spot_to_usd in interim:
            alloc_pct = Decimal("0.00")
            if total_usd_value > Decimal("0.00"):
                alloc_pct = ((usd_val / total_usd_value) * Decimal("100.00")).quantize(
                    Decimal("0.10"), rounding=ROUND_HALF_UP
                )

            pos_dtos.append(
                TreasuryPositionDTO(
                    currency=p.currency,
                    reserve_balance=p.reserve_balance,
                    usd_equivalent=usd_val,
                    spot_to_usd=spot_to_usd,
                    target_allocation_pct=p.target_allocation_pct,
                    current_allocation_pct=alloc_pct,
                    last_revalued_at=p.last_revalued_at.strftime("%Y-%m-%d %H:%M:%S"),
                )
            )

        # 24h volume and spread revenue
        volume_24h = Decimal("0.00")
        spread_revenue_24h = Decimal("0.00")
        for t in trades:
            if t.status == FXTradeStatus.EXECUTED:
                src_usd_rate = FXCalculator.resolve_spot_rate(t.source_currency, "USD", rates_dict)
                vol_usd = t.source_amount * src_usd_rate
                volume_24h += vol_usd
                spread_revenue_24h += t.spread_revenue_usd

        return (
            pos_dtos,
            total_usd_value,
            volume_24h.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP),
            spread_revenue_24h.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP),
        )

    def get_live_fx_rates(self) -> list[FXRateTableEntryDTO]:
        """Fetch live benchmark exchange rate table."""
        with self._session_factory() as session:
            fx_repo = SQLFXRepository(session)
            rates = fx_repo.get_rates()
            return [FXRateTableEntryDTO.from_entity(r) for r in rates.values()]

    def export_fx_blotter_csv(
        self,
        trades: Optional[list[FXTradeDTO]] = None,
        destination: Optional[str] = None,
        encoding: str = "utf-8",
        sanitize_formulas: bool = True,
    ) -> str:
        """Export Foreign Exchange trade blotter records into an RFC-4180 CSV document."""
        from novabank.application.services.export_service import ExportService

        if trades is None:
            trades_list, _ = self.list_fx_trades(page=1, page_size=5000)
        else:
            trades_list = trades

        string_buffer = io.StringIO()
        writer = csv.writer(string_buffer, lineterminator="\r\n", quoting=csv.QUOTE_MINIMAL)

        headers = [
            "Trade ID",
            "Timestamp",
            "Account Number",
            "Sold Currency",
            "Sold Amount",
            "Bought Currency",
            "Bought Amount",
            "Spot Rate",
            "Effective Rate",
            "Spread (Bps)",
            "Spread Revenue (USD)",
            "Fee Amount",
            "Status",
            "Settlement Reference",
            "Actor",
        ]
        writer.writerow(headers)

        for t in trades_list:
            row = [
                ExportService.sanitize_field(t.trade_id, sanitize_formulas),
                t.executed_at,
                t.account_number,
                t.source_currency,
                f"{t.source_amount:.2f}",
                t.target_currency,
                f"{t.target_amount:.2f}",
                f"{t.spot_rate:.5f}",
                f"{t.effective_rate:.5f}",
                t.spread_bps,
                f"{t.spread_revenue_usd:.2f}",
                f"{t.fee_amount:.2f}",
                t.status,
                ExportService.sanitize_field(t.settlement_reference, sanitize_formulas),
                t.actor,
            ]
            writer.writerow(row)

        csv_content = string_buffer.getvalue()
        return ExportService._deliver_output(csv_content, destination, encoding)



