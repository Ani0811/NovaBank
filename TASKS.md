# NovaBank Modernization Project - Engineering Task Backlog

## Task Ledger & Status Overview

| Phase | Priority | Total Tasks | Planned | In Progress | Blocked | Done |
|---|---|---|---|---|---|---|
| **Phase 0: Baseline & Preservation** | P0 | 4 | 1 | 0 | 0 | 3 |
| **Phase 1: Domain, Database & Transactions** | P1 | 11 | 7 | 0 | 0 | 4 |
| **Phase 2: PySide6 Desktop Application** | P2 | 9 | 9 | 0 | 0 | 0 |
| **Phase 3: Statements, Audit & Operations** | P3 | 8 | 8 | 0 | 0 | 0 |
| **Phase 4: Local LM Studio AI Integration** | P4 | 6 | 6 | 0 | 0 | 0 |
| **Phase 5: Hardening, Packaging & Release** | P5 | 5 | 5 | 0 | 0 | 0 |
| **Total** | | **43** | **36** | **0** | **0** | **7** |

---

## Phase 0: Baseline & Safe Configuration (P0)

### TASK-P0-01: Initialize Modern Repository Workspace & Package Architecture
- **Objective**: Establish the isolated modern repository at `C:\Github\NovaBank`, directory structure, virtual environment, and dependency configuration (`pyproject.toml`) while ensuring legacy source in `C:\Github\BMS_CONSOLE-main` is completely untouched.
- **Priority**: P0
- **Dependencies**: None
- **Affected Files/Modules**:
  - `pyproject.toml`
  - `.gitignore`
  - `src/novabank/__init__.py`
  - `tests/__init__.py`
- **Acceptance Criteria**:
  - Legacy files in `C:\Github\BMS_CONSOLE-main` remain 100% unaltered.
  - Modern project directory contains standard `src/` layout: `novabank.domain`, `novabank.application`, `novabank.infrastructure`, `novabank.ui`.
  - Virtual environment installs dependencies successfully (`pydantic>=2.0`, `SQLAlchemy>=2.0`, `PyMySQL>=1.1`, `alembic>=1.13`, `PySide6>=6.6`, `keyring>=24.0`, `pytest>=8.0`).
- **Required Tests**: `tests/test_workspace_sanity.py` (verifies package imports and legacy path isolation).
- **Status**: Done
- **Notes**: Package structure (`src/novabank/{domain,application,infrastructure,ui}`), virtual environment (`.venv`), `pyproject.toml`, `.gitignore`, `.env.example`, and baseline test suite created. 4/4 sanity tests verified passing with pytest 9.1.1 on Python 3.14.7.

---

### TASK-P0-02: Establish Code Quality, Type Checking & Testing Infrastructure
- **Objective**: Configure automated linting, formatting, static analysis, and pytest configuration.
- **Priority**: P0
- **Dependencies**: `TASK-P0-01`
- **Affected Files/Modules**:
  - `pyproject.toml` (tool configurations for ruff, pytest, mypy)
  - `tests/conftest.py`
- **Acceptance Criteria**:
  - `ruff check .` runs without configuration errors.
  - `pytest` executes and discovers tests in `tests/`.
  - Type checking configuration is established with strict optional checking.
- **Required Tests**: Baseline smoke test asserting pytest runs and passes.
- **Status**: Planned
- **Notes**: None.

---

### TASK-P0-03: Implement Secure Configuration & Credential Store
- **Objective**: Implement application settings and database credential management supporting environment variables and Windows Credential Manager (`keyring`), completely deprecating plaintext CSV storage (`BMS_MySQL_ConnectionString.csv`).
- **Priority**: P0
- **Dependencies**: `TASK-P0-01`
- **Affected Files/Modules**:
  - `src/novabank/infrastructure/config.py`
  - `tests/infrastructure/test_config.py`
  - `.env.example`
- **Acceptance Criteria**:
  - Configuration reads from environment variables, `.env` file (strictly gitignored), or Windows Credential Manager.
  - Plaintext CSV files are rejected; if a user provides a legacy CSV, the system offers a one-way secure import into Windows Credential Manager and immediately prompts for CSV deletion.
  - Default database connection string connects securely to MySQL without hardcoded passwords.
- **Required Tests**: Unit tests verifying environment loading, default overrides, and secret masking in string representations (`SecretStr`).
- **Status**: Done
- **Notes**: Implemented `AppConfig` with `pydantic-settings`, SecretStr password masking, Windows Credential Manager (`keyring`) storage/retrieval helpers, and secure one-way legacy CSV import/deletion. 9/9 config tests passing (13/13 total tests passing).

---

### TASK-P0-04: Implement Safe Read-Only Database Connectivity & Environment Checker
- **Objective**: Create a diagnostic utility that tests connection to MySQL 8.0, verifies server variables, and inspects legacy `narDB` tables in read-only mode without issuing DDL.
- **Priority**: P0
- **Dependencies**: `TASK-P0-03`
- **Affected Files/Modules**:
  - `src/novabank/infrastructure/db/diagnostics.py`
  - `tests/infrastructure/test_diagnostics.py`
- **Acceptance Criteria**:
  - Connects to MySQL using configured credentials.
  - Verifies database server version is >= 8.0.
  - Checks existence of `narDB.BMS_MASTER` and `narDB.BMS_ACCOUNTS` without issuing any `DROP`, `ALTER`, or `INSERT` statements.
  - Returns clear diagnostics if MySQL service is stopped or unreachable.
- **Required Tests**: Mock tests for successful connection, connection refused, authentication failure, and read-only schema inspection.
- **Status**: Done
- **Notes**: Implemented `check_database_connectivity` and `DatabaseDiagnostics` with safe read-only inspection of MySQL version and legacy narDB tables via information_schema (zero DDL). Tested live on local stopped MySQL80 service and verified with 8 comprehensive unit tests (21/21 total tests passing).

---

## Phase 1: Core Domain, Database Schema & Atomic Transactions (P1)

### TASK-P1-01: Implement Monetary Value Object & Precision Arithmetic
- **Objective**: Create an immutable `Money` value object encapsulating exact decimal arithmetic to prevent floating-point errors and integer truncation.
- **Priority**: P1
- **Dependencies**: `TASK-P0-01`
- **Affected Files/Modules**:
  - `src/novabank/domain/value_objects/money.py`
  - `tests/domain/test_money.py`
- **Acceptance Criteria**:
  - Backed by Python `decimal.Decimal` with fixed 2 decimal places and `ROUND_HALF_UP` rounding.
  - Rejects negative amounts unless explicitly constructed as signed deltas.
  - Supports addition, subtraction, multiplication with non-negative scalars, and exact comparison.
  - Disallows direct operations with float types (`TypeError`).
- **Required Tests**: Extensive unit tests covering boundary values, precision preservation, division rounding, and type safety.
- **Status**: Done
- **Notes**: Implemented immutable `Money` value object with exact decimal quantization (ROUND_HALF_UP to 2 decimal places), float rejection, currency safety, integer cents conversion, formatting, and domain exceptions. 21/21 unit tests passing with 98% code coverage (42/42 total suite tests passing).

---

### TASK-P1-02: Implement Domain Entities & Account Validation Rules
- **Objective**: Create `Account`, `AccountNumber`, `Transaction`, and domain invariants.
- **Priority**: P1
- **Dependencies**: `TASK-P1-01`
- **Affected Files/Modules**:
  - `src/novabank/domain/entities/account.py`
  - `src/novabank/domain/entities/transaction.py`
  - `src/novabank/domain/value_objects/account_number.py`
  - `src/novabank/domain/exceptions.py`
  - `tests/domain/test_account.py`
- **Acceptance Criteria**:
  - `AccountNumber`: 12-digit string format; generator includes collision detection and validation.
  - `Account`: Enforces non-empty name (max 100 chars), valid DOB (age >= 18 and <= 120 years), valid 10-digit phone number, address fields.
  - Active status invariants: Deactivated accounts reject all deposits, withdrawals, and transfers.
  - Non-negative balance invariant: `balance >= Money.zero()` at all times.
- **Required Tests**: Unit tests for age validation, phone regex, name formatting, and state transitions (active -> closed).
- **Status**: Done
- **Notes**: Implemented `Account` entity, `Transaction` entity, `AccountNumber` 12-digit value object, and `TransactionType` / `TransactionDirection` enums. Replaces legacy console recursive input loops with deterministic domain validation and overdraft prevention invariants. 14/14 unit tests passing (56/56 total suite tests passing with 90% overall coverage).

---

### TASK-P1-03: Implement SQLAlchemy Declarative ORM & Table Schemas
- **Objective**: Define relational database models with proper primary keys, foreign keys, indexes, and constraints.
- **Priority**: P1
- **Dependencies**: `TASK-P1-02`
- **Affected Files/Modules**:
  - `src/novabank/infrastructure/db/models.py`
  - `tests/infrastructure/test_models.py`
- **Acceptance Criteria**:
  - `accounts`: `account_number` VARCHAR(12) PRIMARY KEY, `holder_name` VARCHAR(100) NOT NULL, `dob` DATE NOT NULL, `address_line` VARCHAR(255) NOT NULL, `city` VARCHAR(100) NOT NULL, `state` VARCHAR(100) NOT NULL, `country` VARCHAR(100) NOT NULL, `phone_number` VARCHAR(15) NOT NULL, `is_active` BOOLEAN NOT NULL DEFAULT TRUE, `balance` DECIMAL(15, 2) NOT NULL DEFAULT 0.00, `version` INT NOT NULL DEFAULT 1, `created_at` DATETIME NOT NULL, `updated_at` DATETIME NOT NULL.
  - `transactions`: `transaction_id` BIGINT AUTO_INCREMENT PRIMARY KEY, `transaction_ref` VARCHAR(36) NOT NULL UNIQUE (UUIDv4), `account_number` VARCHAR(12) NOT NULL FK, `transaction_type` VARCHAR(20) NOT NULL, `direction` VARCHAR(10) NOT NULL, `amount` DECIMAL(15, 2) NOT NULL, `balance_after` DECIMAL(15, 2) NOT NULL, `description` VARCHAR(255), `created_at` DATETIME NOT NULL, `created_by` VARCHAR(50) NOT NULL.
  - `audit_events`: `event_id` BIGINT AUTO_INCREMENT PRIMARY KEY, `event_type` VARCHAR(50) NOT NULL, `entity_id` VARCHAR(50) NOT NULL, `actor` VARCHAR(50) NOT NULL, `payload` JSON, `timestamp` DATETIME NOT NULL.
  - Indices on `transactions.account_number`, `transactions.created_at`, `accounts.holder_name`.
- **Required Tests**: Schema verification tests using SQLite in-memory and MySQL container.
- **Status**: Done
- **Notes**: Implemented SQLAlchemy 2.0 declarative models (`AccountModel`, `TransactionModel`, `AuditEventModel`), session management (`session.py`), and bi-directional entity mappers. Fixes legacy unkeyed `BMS_ACCOUNTS` table with proper PKs, unique UUIDv4 transaction references, decimal fields, and check constraints. 6/6 tests passing with 100% model coverage (62/62 total suite tests passing with 91% overall coverage).

---

### TASK-P1-04: Configure Alembic Migrations & Initial Schema Revision
- **Objective**: Set up Alembic version-controlled database migrations to replace destructive table-creation scripts.
- **Priority**: P1
- **Dependencies**: `TASK-P1-03`
- **Affected Files/Modules**:
  - `alembic.ini`
  - `migrations/env.py`
  - `migrations/versions/001_initial_schema.py`
  - `tests/infrastructure/test_migrations.py`
- **Acceptance Criteria**:
  - Migration script creates all tables, indices, and constraints without dropping existing unrelated schemas.
  - Downgrade script cleanly reverts the migration.
  - Safe check prevents migration from executing if destructive drops are detected.
- **Required Tests**: Test running `alembic upgrade head` followed by `alembic downgrade base` on a test database.
- **Status**: Done
- **Notes**: Configured Alembic (`alembic.ini`, `migrations/env.py`, `migrations/script.py.mako`), initial schema revision (`001_initial_schema.py`), and programmatic migration runner (`migrator.py`). Verified clean upgrade/downgrade cycle and idempotent re-upgrade without data corruption. 2/2 migration tests passing with 97% coverage (64/64 total suite tests passing with 92% overall coverage).

---

### TASK-P1-05: Implement Safe Non-Destructive Legacy Data Importer (ETL)
- **Objective**: Create a data migration utility that reads existing records from legacy `narDB.BMS_MASTER` and `narDB.BMS_ACCOUNTS` and migrates them safely into the modern schema without altering original tables.
- **Priority**: P1
- **Dependencies**: `TASK-P1-04`
- **Affected Files/Modules**:
  - `src/novabank/infrastructure/db/legacy_migrator.py`
  - `tests/infrastructure/test_legacy_migrator.py`
- **Acceptance Criteria**:
  - Opens legacy database in read-only mode (`READ ONLY` transaction).
  - Imports all accounts from `BMS_MASTER`, converting dates and active flags.
  - Imports transactions from `BMS_ACCOUNTS`, synthesizing deterministic UUIDs and calculating running balances.
  - Validates total sum of legacy credits minus debits equals final calculated account balance.
  - Generates detailed reconciliation report showing migrated accounts, transactions, and any validation discrepancies.
- **Required Tests**: Migration test on mock legacy dataset with edge cases (zero balance, multiple deposits, closed accounts).
- **Status**: Obsolete / Not Needed
- **Notes**: Deprecated by user decision: No historical data exists in MySQL/narDB. All accounts and transactions will be created fresh via NovaBank modern schema.

---

### TASK-P1-06: Implement AccountRepository with Parameterized Queries
- **Objective**: Implement data access repository for `Account` entities using SQLAlchemy Core/ORM with zero string concatenation.
- **Priority**: P1
- **Dependencies**: `TASK-P1-03`
- **Affected Files/Modules**:
  - `src/novabank/domain/repositories/account_repository.py` (interface)
  - `src/novabank/infrastructure/repositories/sql_account_repository.py`
  - `tests/infrastructure/test_account_repository.py`
- **Acceptance Criteria**:
  - Methods: `save(account)`, `get_by_number(account_number)`, `get_by_number_for_update(account_number)`, `list_accounts(search, active_only, limit, offset)`, `count_accounts(search, active_only)`.
  - Row locking: `get_by_number_for_update` issues `SELECT ... FOR UPDATE` within the active transaction.
  - 100% parameterized SQL; zero SQL injection vulnerability.
- **Required Tests**: Repository unit tests and integration tests verifying query generation and parameter binding.
- **Status**: Completed
- **Notes**: Replaces raw SQL string concatenation in `getData()` and `getInsertUpdateSQL()`.

---

### TASK-P1-07: Implement TransactionRepository & Ledger Recording
- **Objective**: Implement repository for recording and querying immutable financial transactions.
- **Priority**: P1
- **Dependencies**: `TASK-P1-03`
- **Affected Files/Modules**:
  - `src/novabank/domain/repositories/transaction_repository.py` (interface)
  - `src/novabank/infrastructure/repositories/sql_transaction_repository.py`
  - `tests/infrastructure/test_transaction_repository.py`
- **Acceptance Criteria**:
  - Methods: `append(transaction)`, `get_by_ref(ref)`, `list_by_account(account_number, start_date, end_date, limit, offset)`.
  - Transactions are strictly append-only; update and delete operations are prohibited.
  - Duplicate `transaction_ref` raises `DuplicateTransactionRefError` (idempotency support).
- **Required Tests**: Unit tests verifying append-only enforcement and query filtering by date range.
- **Status**: Completed
- **Notes**: Provides complete ledger history missing in legacy implementation.

---

### TASK-P1-08: Implement BankingService Core Cash Deposit Workflow
- **Objective**: Implement atomic deposit service with explicit success, failure, rollback, and concurrency criteria.
- **Priority**: P1
- **Dependencies**: `TASK-P1-06`, `TASK-P1-07`
- **Affected Files/Modules**:
  - `src/novabank/application/services/banking_service.py`
  - `src/novabank/application/dto/transaction_dto.py`
  - `tests/application/test_deposit_service.py`
- **Acceptance Criteria**:
  - **Success**: Starts transaction; acquires row lock on account; validates account exists and `is_active == True`; validates `amount > 0`; calculates `new_balance = current_balance + amount`; writes `Transaction` record (`direction='CREDIT'`, `type='DEPOSIT'`); updates account balance; commits transaction; emits `DepositCompletedEvent`; returns DTO.
  - **Failure**: If account not found -> raises `AccountNotFoundError`; if account closed -> raises `AccountClosedError`; if amount <= 0 -> raises `InvalidAmountError`.
  - **Rollback**: On any exception or database failure, entire transaction rolls back; no balance change or orphan transaction record persists.
  - **Concurrency**: Multiple concurrent deposits on the same account serialize cleanly; final balance equals initial balance plus sum of all deposits.
- **Required Tests**: Success path, inactive account rejection, zero amount rejection, simulated DB failure rollback, multi-threaded concurrent deposits.
- **Status**: Completed
- **Notes**: Fixes legacy lack of transaction boundary.

---

### TASK-P1-09: Implement BankingService Core Cash Withdrawal Workflow
- **Objective**: Implement atomic withdrawal service with explicit success, failure, rollback, and concurrency criteria.
- **Priority**: P1
- **Dependencies**: `TASK-P1-06`, `TASK-P1-07`
- **Affected Files/Modules**:
  - `src/novabank/application/services/banking_service.py`
  - `tests/application/test_withdrawal_service.py`
- **Acceptance Criteria**:
  - **Success**: Starts transaction; locks account row with `SELECT ... FOR UPDATE`; verifies account is active; verifies `current_balance >= amount`; calculates `new_balance = current_balance - amount`; writes `Transaction` record (`direction='DEBIT'`, `type='WITHDRAWAL'`); updates account balance; commits transaction; returns DTO.
  - **Failure**: If `current_balance < amount` -> raises `InsufficientFundsError`; if account inactive -> raises `AccountClosedError`; if amount <= 0 -> raises `InvalidAmountError`.
  - **Rollback**: If any error occurs after lock acquisition, transaction is immediately rolled back; balance remains unaltered.
  - **Concurrency**: When two concurrent withdrawals of $100 are executed against an account with $150 balance, exactly one succeeds ($50 remaining) and one fails with `InsufficientFundsError`. Overdraft is mathematically prevented.
- **Required Tests**: Normal withdrawal test, overdraft rejection test, inactive account rejection, rollback test, concurrency double-spend test.
- **Status**: Completed
- **Notes**: Completely resolves the race condition in legacy `getWithdrawAmt()`.

---

### TASK-P1-10: Implement BankingService Account-to-Account Transfer Workflow
- **Objective**: Implement atomic fund transfer between two accounts with dual-lock acquisition ordering to prevent deadlocks.
- **Priority**: P1
- **Dependencies**: `TASK-P1-08`, `TASK-P1-09`
- **Affected Files/Modules**:
  - `src/novabank/application/services/banking_service.py`
  - `tests/application/test_transfer_service.py`
- **Acceptance Criteria**:
  - **Success**: Locks source and destination accounts in deterministic order (by account number ascending) to avoid deadlocks; verifies source has sufficient funds and both accounts are active; debits source account; credits destination account; records two linked transaction records with matching correlation ID; commits transaction.
  - **Failure**: Fails if source == destination (`SelfTransferError`), if either account is closed, or if source has insufficient funds.
  - **Rollback**: If destination credit fails, source debit is rolled back completely. Total system money remains constant.
  - **Concurrency**: Opposite simultaneous transfers between Account A and Account B serialize without deadlocks.
- **Required Tests**: Transfer success, insufficient funds rollback, reverse concurrent transfers deadlock test.
- **Status**: Completed
- **Notes**: New capability modernizing the legacy application.

---

### TASK-P1-11: Automated Concurrency & Stress Testing Suite
- **Objective**: Stress-test the transaction engine with high concurrency to verify financial invariants under load.
- **Priority**: P1
- **Dependencies**: `TASK-P1-08`, `TASK-P1-09`, `TASK-P1-10`
- **Affected Files/Modules**:
  - `tests/integration/test_concurrency.py`
- **Acceptance Criteria**:
  - Spawns 20 parallel threads performing random deposits, withdrawals, and transfers across 5 accounts.
  - Verifies that:
    1. Sum of all account balances + total net external cash in/out is perfectly balanced.
    2. No account ever experienced a negative balance.
    3. Every transaction record has an exact corresponding balance transition.
- **Required Tests**: Multi-threaded stress test executing >= 100 concurrent operations.
- **Status**: Completed
- **Notes**: Financial integrity sign-off benchmark.

---

## Phase 2: PySide6 Desktop Application Shell & Core Banking UI (P2)

### TASK-P2-01: PySide6 Application Shell & Navigation Framework
- **Objective**: Build the main desktop application window with responsive navigation sidebar, header, dynamic content stack, and status bar.
- **Priority**: P2
- **Dependencies**: `TASK-P1-02`
- **Affected Files/Modules**:
  - `src/novabank/ui/main_window.py`
  - `src/novabank/ui/components/sidebar.py`
  - `src/novabank/ui/components/status_bar.py`
  - `src/novabank/ui/resources/styles.qss`
  - `tests/ui/test_main_window.py`
- **Acceptance Criteria**:
  - Fluent modern design adhering to Windows 10/11 desktop guidelines with polished typography and dark/light mode support.
  - Navigation switches views via `QStackedWidget` smoothly without lag.
  - Status bar displays database connection health indicator and session info.
  - Application handles high-DPI scaling gracefully.
- **Required Tests**: `pytest-qt` test verifying window creation, sidebar navigation, and status bar updates.
- **Status**: Completed
- **Notes**: Replaces console text menus.

---

### TASK-P2-02: Asynchronous Qt Worker Framework (QThreadPool & QRunnable)
- **Objective**: Build a robust background task execution manager so all database queries, file exports, and AI calls run off the UI thread.
- **Priority**: P2
- **Dependencies**: `TASK-P2-01`
- **Affected Files/Modules**:
  - `src/novabank/ui/workers/task_runner.py`
  - `tests/ui/test_task_runner.py`
- **Acceptance Criteria**:
  - Background tasks execute on worker threads; results and errors emit to the main thread via Qt signals.
  - UI remains responsive (60 FPS) with loading spinners or progress bars during slow operations.
  - Worker captures exceptions and presents user-friendly error dialogs on the main thread.
- **Required Tests**: Pytest-qt test verifying background execution and signal delivery without blocking GUI thread.
- **Status**: Completed
- **Notes**: Guarantees zero GUI freezing.

---

### TASK-P2-03: Customer Account Creation View & Form Validation
- **Objective**: Build `OpenAccountView` with interactive input validation and account opening workflow.
- **Priority**: P2
- **Dependencies**: `TASK-P1-08`, `TASK-P2-02`
- **Affected Files/Modules**:
  - `src/novabank/ui/views/open_account_view.py`
  - `src/novabank/ui/viewmodels/open_account_viewmodel.py`
  - `tests/ui/test_open_account_view.py`
- **Acceptance Criteria**:
  - Form fields: Full Name, Date of Birth (calendar widget), Address, City, State, Country, Phone Number, Optional Initial Deposit.
  - Real-time client-side validation displays inline hints (e.g. phone must be exactly 10 digits; customer must be >= 18 years old).
  - Submit button is disabled until all required fields are valid.
  - On submission: Opens account via `BankingService`, presents success confirmation modal displaying new 12-digit account number, and offers receipt printing.
- **Required Tests**: Form validation tests, submission trigger test, error display test.
- **Status**: Completed
- **Notes**: Replaces legacy `getOpenAccount()` console input loops.

---

### TASK-P2-04: Account Directory View with Live Search & Filtering
- **Objective**: Build `AccountListView` displaying a paginated table of customer accounts with instant debounce search and status filters.
- **Priority**: P2
- **Dependencies**: `TASK-P1-06`, `TASK-P2-02`
- **Affected Files/Modules**:
  - `src/novabank/ui/views/account_list_view.py`
  - `src/novabank/ui/viewmodels/account_list_viewmodel.py`
  - `tests/ui/test_account_list_view.py`
- **Acceptance Criteria**:
  - Displays table columns: Account No, Holder Name, Phone, City, State, Status (Active/Closed badge), Current Balance.
  - Search bar filters accounts by name, account number, or phone with a 200ms debounce.
  - Filter chips allow viewing All, Active Only, or Closed Only.
  - Double-clicking a row navigates to the Account Detail View.
- **Required Tests**: Table population test, search filter debounce test, navigation signal test.
- **Status**: Completed
- **Notes**: Modernizes legacy `getAccountsList()`.

---

### TASK-P2-05: Customer Profile Detail & Modification View
- **Objective**: Build `AccountDetailView` allowing tellers to inspect complete customer information and update contact details.
- **Priority**: P2
- **Dependencies**: `TASK-P2-04`
- **Affected Files/Modules**:
  - `src/novabank/ui/views/account_detail_view.py`
  - `src/novabank/ui/viewmodels/account_detail_viewmodel.py`
  - `tests/ui/test_account_detail_view.py`
- **Acceptance Criteria**:
  - Displays customer personal details, account status, creation date, and balance summary.
  - Allows editing address, city, state, country, and phone number with field-level validation.
  - Prohibits editing account number, holder name (without manager override), or balance directly through this view.
  - Saves updates via `BankingService`, records an audit event, and refreshes view.
- **Required Tests**: Profile load test, edit validation test, update submission test.
- **Status**: Completed
- **Notes**: Replaces legacy `getModifyAccount()` and `getAccountDetails()`.

---

### TASK-P2-06: Account Deactivation / Closure Workflow
- **Objective**: Build safe account closure dialog with prerequisite checks and confirmation guardrails.
- **Priority**: P2
- **Dependencies**: `TASK-P2-05`
- **Affected Files/Modules**:
  - `src/novabank/ui/views/account_close_dialog.py`
  - `tests/ui/test_account_close.py`
- **Acceptance Criteria**:
  - Verifies account balance is exactly zero before allowing closure. If balance > 0, prompts user to withdraw or transfer remaining funds first.
  - Requires explicit confirmation dialog with warning.
  - On confirmation: Marks `is_active = False`, records audit log entry, updates UI status badges.
- **Required Tests**: Non-zero balance rejection test, closure confirmation test, status update test.
- **Status**: Completed
- **Notes**: Replaces legacy `getCloseAccount()` which allowed closing accounts without checking balance.

---

### TASK-P2-07: Cash Deposit Transaction UI
- **Objective**: Build dedicated `DepositView` for cash deposit counter operations.
- **Priority**: P2
- **Dependencies**: `TASK-P1-08`, `TASK-P2-02`
- **Affected Files/Modules**:
  - `src/novabank/ui/views/deposit_view.py`
  - `src/novabank/ui/viewmodels/transaction_viewmodel.py`
  - `tests/ui/test_deposit_view.py`
- **Acceptance Criteria**:
  - Entering an account number immediately looks up account details (holder name, active status, current balance) in the background.
  - Amount input field validates numeric format with 2 decimals, enforces minimum deposit ($1.00) and maximum counter limit ($1,000,000.00).
  - Displays transaction preview (Previous Balance, Deposit Amount, New Balance).
  - Submits asynchronously; displays digital deposit receipt upon completion with print option.
- **Required Tests**: Account lookup trigger test, amount validation test, submission test.
- **Status**: Completed
- **Notes**: Modernizes legacy `getDepositAmt()`.

---

### TASK-P2-08: Cash Withdrawal Transaction UI
- **Objective**: Build dedicated `WithdrawalView` for cash withdrawal counter operations.
- **Priority**: P2
- **Dependencies**: `TASK-P1-09`, `TASK-P2-02`
- **Affected Files/Modules**:
  - `src/novabank/ui/views/withdrawal_view.py`
  - `src/novabank/ui/viewmodels/transaction_viewmodel.py`
  - `tests/ui/test_withdrawal_view.py`
- **Acceptance Criteria**:
  - Real-time balance check: If entered withdrawal amount exceeds available balance, field displays an error banner and disables submit button.
  - Enforces active account requirement; inactive accounts show a prominent closure notice.
  - Submits asynchronously via `BankingService`; displays digital withdrawal slip upon completion.
- **Required Tests**: Overdraft prevention UI test, inactive account block test, successful withdrawal test.
- **Status**: Completed
- **Notes**: Modernizes legacy `getWithdrawAmt()`.

---

### TASK-P2-09: Account-to-Account Fund Transfer UI
- **Objective**: Build `TransferView` for internal account transfers.
- **Priority**: P2
- **Dependencies**: `TASK-P1-10`, `TASK-P2-02`
- **Affected Files/Modules**:
  - `src/novabank/ui/views/transfer_view.py`
  - `src/novabank/ui/viewmodels/transaction_viewmodel.py`
  - `tests/ui/test_transfer_view.py`
- **Acceptance Criteria**:
  - Validates source and destination accounts independently; displays both account holder names.
  - Prohibits selecting identical source and destination accounts.
  - Validates available balance on source account.
  - Submits atomic transfer and presents dual-receipt summary.
- **Required Tests**: Dual account validation test, same-account block test, transfer execution test.
- **Status**: Planned
- **Notes**: New feature.

---

## Phase 3: Statements, Reports, Audit & Backup Procedures (P3)

### TASK-P3-01: Account Statement Generation Engine
- **Objective**: Implement service to generate detailed historical transaction statements with opening, period, and closing balance reconciliations.
- **Priority**: P3
- **Dependencies**: `TASK-P1-07`
- **Affected Files/Modules**:
  - `src/novabank/application/services/statement_service.py`
  - `src/novabank/application/dto/statement_dto.py`
  - `tests/application/test_statement_service.py`
- **Acceptance Criteria**:
  - Takes account number, start date, and end date.
  - Calculates opening balance prior to start date, lists all transactions in period, calculates total credits, total debits, and closing balance.
  - Opening Balance + Credits - Debits == Closing Balance mathematically guaranteed.
- **Required Tests**: Statement generation test with zero transactions, multiple transactions, boundary dates.
- **Status**: Planned
- **Notes**: Modernizes legacy `getAccBalance()`.

---

### TASK-P3-02: Interactive Statement & Transaction History View
- **Objective**: Build `StatementView` with date range selectors, filter presets, and interactive transaction data table.
- **Priority**: P3
- **Dependencies**: `TASK-P3-01`, `TASK-P2-02`
- **Affected Files/Modules**:
  - `src/novabank/ui/views/statement_view.py`
  - `src/novabank/ui/viewmodels/statement_viewmodel.py`
  - `tests/ui/test_statement_view.py`
- **Acceptance Criteria**:
  - Preset filters: Today, Last 7 Days, Current Month, Year to Date, Custom Date Range.
  - Table columns: Date & Time, Reference ID, Type, Description, Debit, Credit, Running Balance.
  - Summary cards at the top show Opening Balance, Total Inflow, Total Outflow, and Ending Balance.
- **Required Tests**: Date filter change test, summary card update test.
- **Status**: Planned
- **Notes**: Replaces console statement printout.

---

### TASK-P3-03: RFC-4180 Compliant CSV Statement Export
- **Objective**: Implement export of account statements and transaction histories to formatted CSV files.
- **Priority**: P3
- **Dependencies**: `TASK-P3-01`
- **Affected Files/Modules**:
  - `src/novabank/application/services/export_service.py`
  - `tests/application/test_csv_export.py`
- **Acceptance Criteria**:
  - Generates RFC-4180 compliant CSV with proper quoting, headers, and UTF-8 encoding.
  - File save dialog allows user to select destination file on Windows filesystem.
  - Export runs asynchronously on worker thread without GUI lag.
- **Required Tests**: CSV formatting test, special characters escaping test, empty statement export test.
- **Status**: Planned
- **Notes**: New capability.

---

### TASK-P3-04: Professional PDF Statement Generator
- **Objective**: Create printable PDF account statement generator with formal bank branding, customer details, and transaction table.
- **Priority**: P3
- **Dependencies**: `TASK-P3-01`
- **Affected Files/Modules**:
  - `src/novabank/infrastructure/reporting/pdf_generator.py`
  - `tests/infrastructure/test_pdf_generator.py`
- **Acceptance Criteria**:
  - Generates clean PDF using ReportLab or Qt `QPrinter`/`QTextDocument`.
  - Includes bank header, statement period, customer summary, transaction table, and closing reconciliation.
  - Runs asynchronously on worker thread.
- **Required Tests**: PDF generation test asserting valid PDF byte header and page count > 0.
- **Status**: Planned
- **Notes**: New capability.

---

### TASK-P3-05: Audit Event Logging Engine
- **Objective**: Implement automatic audit logging for all account modifications, closures, and large transactions.
- **Priority**: P3
- **Dependencies**: `TASK-P1-03`
- **Affected Files/Modules**:
  - `src/novabank/application/services/audit_service.py`
  - `src/novabank/infrastructure/repositories/sql_audit_repository.py`
  - `tests/application/test_audit_service.py`
- **Acceptance Criteria**:
  - Records: Timestamp, Actor, Event Type (`ACCOUNT_CREATED`, `ACCOUNT_UPDATED`, `ACCOUNT_CLOSED`, `DEPOSIT`, `WITHDRAWAL`, `TRANSFER`), Entity ID, and JSON payload containing before/after state diff.
  - Audit records are immutable; no update/delete methods exist.
- **Required Tests**: Audit event recording test, payload serialization test.
- **Status**: Planned
- **Notes**: Vital security requirement for portfolio bank system.

---

### TASK-P3-06: Administrative Audit Trail Viewer UI
- **Objective**: Build `AuditLogView` allowing branch administrators to review the audit trail.
- **Priority**: P3
- **Dependencies**: `TASK-P3-05`, `TASK-P2-02`
- **Affected Files/Modules**:
  - `src/novabank/ui/views/audit_log_view.py`
  - `src/novabank/ui/viewmodels/audit_log_viewmodel.py`
  - `tests/ui/test_audit_log_view.py`
- **Acceptance Criteria**:
  - Searchable table displaying event timestamp, category, actor, and entity ID.
  - Selecting an event displays JSON diff inspector showing changed fields.
  - Filterable by date range and event category.
- **Required Tests**: Audit table loading test, diff inspector display test.
- **Status**: Planned
- **Notes**: Compliance feature.

---

### TASK-P3-07: Safe Transactional Database Backup Utility
- **Objective**: Implement automated backup utility using `mysqldump` with safe transactional consistency flags.
- **Priority**: P3
- **Dependencies**: `TASK-P0-03`
- **Affected Files/Modules**:
  - `src/novabank/infrastructure/backup/backup_manager.py`
  - `tests/infrastructure/test_backup_manager.py`
- **Acceptance Criteria**:
  - Invokes `mysqldump` with `--single-transaction --quick --routines --triggers`.
  - Saves compressed, timestamped `.sql.gz` file into configured backup folder.
  - Verifies exit code and generated file integrity.
- **Required Tests**: Mocked mysqldump execution test and backup file validation test.
- **Status**: Planned
- **Notes**: Operational safety procedure.

---

### TASK-P3-08: Safe Database Restore Wizard with Safeguards
- **Objective**: Implement database restore utility with explicit safety checks preventing accidental overwrite of active databases.
- **Priority**: P3
- **Dependencies**: `TASK-P3-07`
- **Affected Files/Modules**:
  - `src/novabank/infrastructure/backup/restore_manager.py`
  - `tests/infrastructure/test_restore_manager.py`
- **Acceptance Criteria**:
  - Inspects backup file header and schema compatibility before execution.
  - Requires user to explicitly type the target database name as confirmation before proceeding.
  - Never executes automatically.
- **Required Tests**: Restore dry-run test and confirmation validation test.
- **Status**: Planned
- **Notes**: Prevents accidental data wipe.

---

## Phase 4: Local LM Studio AI Integration (P4)

### TASK-P4-01: LM Studio Client & Health Check Service
- **Objective**: Implement HTTP client connecting to local LM Studio endpoint (`http://localhost:1234/v1`) with timeouts, health checks, and graceful offline fallback.
- **Priority**: P4
- **Dependencies**: `TASK-P1-02`
- **Affected Files/Modules**:
  - `src/novabank/infrastructure/ai/lm_studio_client.py`
  - `src/novabank/infrastructure/ai/exceptions.py`
  - `tests/infrastructure/test_lm_studio_client.py`
- **Acceptance Criteria**:
  - **Permitted Inputs**: Base URL (default `http://localhost:1234/v1`), model identifier, timeout (10s default), sanitized prompt payloads.
  - **Output Validation**: Validates HTTP status 200 and standard OpenAI JSON response structure (`choices[0].message.content`).
  - **Fallback Behavior**: If LM Studio is offline or connection fails, immediately catches `AIConnectionError`, sets system state to `AI_OFFLINE`, and returns graceful offline response without throwing unhandled exceptions.
  - **Prohibited Actions**: Network calls outside `127.0.0.1` / `localhost` are strictly blocked.
- **Required Tests**: Health check test, successful completion mock, connection timeout mock, server error fallback test.
- **Status**: Planned
- **Notes**: Core local AI integration layer.

---

### TASK-P4-02: Client-Side PII Sanitizer & AI Trust Boundary Enforcement
- **Objective**: Build data privacy filter that scrubs customer Personally Identifiable Information (PII) before constructing prompts for LM Studio.
- **Priority**: P4
- **Dependencies**: `TASK-P4-01`
- **Affected Files/Modules**:
  - `src/novabank/infrastructure/ai/sanitizer.py`
  - `tests/infrastructure/test_sanitizer.py`
- **Acceptance Criteria**:
  - **Privacy Boundary**: Masks customer full name (`[Customer-Redacted]`), phone number (`[Phone-Redacted]`), street address (`[Address-Redacted]`), and masks account numbers to last 4 digits (`****-****-1234`).
  - **Permitted Inputs**: Raw domain entity or statement data.
  - **Prohibited Actions**: Passing unmasked customer names, phone numbers, or addresses to the AI client is blocked by automated assertion.
- **Required Tests**: Unit tests asserting complete removal of PII tokens from prompt contexts.
- **Status**: Planned
- **Notes**: Guarantees customer privacy compliance.

---

### TASK-P4-03: Natural Language Transaction Query Translator
- **Objective**: Translate natural-language queries (e.g. "show deposits over 5,000 from last month") into validated structured filter parameters.
- **Priority**: P4
- **Dependencies**: `TASK-P4-01`, `TASK-P4-02`
- **Affected Files/Modules**:
  - `src/novabank/application/services/ai_search_service.py`
  - `src/novabank/application/dto/ai_query_dto.py`
  - `tests/application/test_ai_search.py`
- **Acceptance Criteria**:
  - **Permitted Inputs**: Natural language user search string.
  - **Output Validation**: Model output is constrained to JSON and parsed into `StructuredQueryDTO` (fields: `min_amount`, `max_amount`, `start_date`, `end_date`, `transaction_type`).
  - **Fallback Behavior**: If JSON parsing fails or model hallucinates invalid fields, falls back to standard keyword text search.
  - **Prohibited Actions**: AI is NEVER allowed to generate raw SQL strings or execute database queries directly.
- **Required Tests**: Schema parsing tests, hallucinated JSON fallback test, valid filter translation test.
- **Status**: Planned
- **Notes**: Intelligent query translation with strict safety envelope.

---

### TASK-P4-04: Smart Account Statement Summarizer
- **Objective**: Generate concise financial narrative summaries of account statements for customers.
- **Priority**: P4
- **Dependencies**: `TASK-P4-01`, `TASK-P4-02`, `TASK-P3-01`
- **Affected Files/Modules**:
  - `src/novabank/application/services/ai_summary_service.py`
  - `tests/application/test_ai_summary.py`
- **Acceptance Criteria**:
  - **Permitted Inputs**: Sanitized statement aggregates (opening balance, total credits, total debits, closing balance, top 3 transaction categories).
  - **Output Validation**: Validates summary text length (< 300 words), tone (professional banking advisory), and checks that numbers in summary match the input statement figures.
  - **Fallback Behavior**: If AI is offline, provides deterministic template summary ("For the period X to Y, total deposits were $A and total withdrawals were $B.").
  - **Prohibited Actions**: AI cannot offer investment advice or speculate on financial health.
- **Required Tests**: Narrative generation test, offline template fallback test, numerical consistency verification.
- **Status**: Planned
- **Notes**: Enhances customer statements.

---

### TASK-P4-05: Rule-Based Activity Flag Explainer
- **Objective**: Generate explainable summaries for tellers when deterministic business rules flag unusual account activity.
- **Priority**: P4
- **Dependencies**: `TASK-P4-01`, `TASK-P4-02`
- **Affected Files/Modules**:
  - `src/novabank/application/services/activity_monitoring_service.py`
  - `tests/application/test_activity_monitoring.py`
- **Acceptance Criteria**:
  - Rules Engine: Deterministically detects flags: rapid consecutive withdrawals, single transaction > $10,000, high frequency on previously dormant accounts.
  - **Permitted Inputs**: Deterministic flag code, trigger metrics, sanitized transaction timestamps.
  - **Output Validation**: Concise 2-sentence explanation of why the rule was triggered for teller review.
  - **Prohibited Actions**: AI cannot freeze accounts, block transactions, or alter rules. All control remains with the human teller/manager.
- **Required Tests**: Rule trigger tests, explanation prompt formatting test, offline fallback message test.
- **Status**: Planned
- **Notes**: Practical, explainable AI use case for banking operations.

---

### TASK-P4-06: PySide6 AI Assistant Panel UI
- **Objective**: Build integrated conversational AI assistant sidebar in PySide6 with status indicators and quick-action chips.
- **Priority**: P4
- **Dependencies**: `TASK-P4-01`, `TASK-P4-03`, `TASK-P4-04`, `TASK-P2-02`
- **Affected Files/Modules**:
  - `src/novabank/ui/views/ai_assistant_panel.py`
  - `src/novabank/ui/viewmodels/ai_assistant_viewmodel.py`
  - `tests/ui/test_ai_assistant_panel.py`
- **Acceptance Criteria**:
  - Live status badge: "AI Assistant: Connected (Local LM Studio)" vs "AI Assistant: Offline (Local Mode Only)".
  - Quick actions: "Summarize Current Statement", "Find Recent Large Expenses", "Explain Active Flags".
  - Runs queries asynchronously via `QThreadPool`; streaming response updates text smoothly without UI stutter.
- **Required Tests**: UI connection indicator test, quick action dispatch test, async response handling test.
- **Status**: Planned
- **Notes**: Clean UI integration of Phase 4 AI.

---

## Phase 5: Hardening, Packaging & Release (P5)

### TASK-P5-01: Static Security Analysis & Vulnerability Remediation
- **Objective**: Execute static security tools (`bandit`, `safety`, `ruff`) and perform comprehensive code review.
- **Priority**: P5
- **Dependencies**: All Phase 1, 2, 3, 4 tasks
- **Affected Files/Modules**: Entire codebase
- **Acceptance Criteria**:
  - Bandit reports zero High or Medium severity vulnerabilities.
  - No plaintext credentials, hardcoded secrets, or SQL injection vectors exist.
  - All external input is validated by Pydantic domain models or Qt validators.
- **Required Tests**: Automated bandit scan in CI/pytest test suite.
- **Status**: Planned
- **Notes**: Ensures enterprise-grade security posture.

---

### TASK-P5-02: Full End-to-End Regression & Concurrency Verification
- **Objective**: Run complete automated test suite covering unit, repository, service, UI, and concurrency scenarios.
- **Priority**: P5
- **Dependencies**: `TASK-P5-01`
- **Affected Files/Modules**: `tests/`
- **Acceptance Criteria**:
  - 100% of automated tests pass without flaky failures.
  - Code coverage >= 90% across domain and application layers.
  - Multi-threaded financial concurrency tests execute cleanly without data race or deadlock.
- **Required Tests**: Full pytest suite execution with coverage report generation.
- **Status**: Planned
- **Notes**: Sign-off gate before binary packaging.

---

### TASK-P5-03: Windows Standalone Binary Packaging (PyInstaller)
- **Objective**: Configure PyInstaller specification to build a standalone, self-contained Windows executable.
- **Priority**: P5
- **Dependencies**: `TASK-P5-02`
- **Affected Files/Modules**:
  - `packaging/novabank.spec`
  - `packaging/build_exe.py`
- **Acceptance Criteria**:
  - Generates standalone executable bundle including all PySide6 binaries, icons, and dependencies.
  - Application launches cleanly on a clean Windows machine without requiring Python installation.
  - Executable size is optimized and launch time is under 3 seconds.
- **Required Tests**: Binary smoke test executing help/version command and launching application window.
- **Status**: Planned
- **Notes**: Packaging modern Windows desktop application.

---

### TASK-P5-04: Inno Setup Windows Installer Script
- **Objective**: Create professional Windows installer with desktop shortcut, Start Menu entry, prerequisites notice, and uninstaller.
- **Priority**: P5
- **Dependencies**: `TASK-P5-03`
- **Affected Files/Modules**:
  - `packaging/installer.iss`
- **Acceptance Criteria**:
  - Inno Setup compiles installer (`NovaBank_Setup_v1.0.exe`).
  - Installs cleanly into `Program Files\NovaBank` or user directory.
  - Creates Start Menu and Desktop shortcuts with proper application icon.
  - Uninstaller removes all installed files cleanly.
- **Required Tests**: Installation and uninstallation test in a Windows sandbox environment.
- **Status**: Planned
- **Notes**: Standard Windows distribution standard.

---

### TASK-P5-05: Documentation, User Manual & Case Study Portfolio Guide
- **Objective**: Author complete technical and user documentation showcasing the modernization engineering journey.
- **Priority**: P5
- **Dependencies**: `TASK-P5-04`
- **Affected Files/Modules**:
  - `README.md`
  - `docs/DEVELOPER_GUIDE.md`
  - `docs/USER_MANUAL.md`
  - `docs/MIGRATION_GUIDE.md`
- **Acceptance Criteria**:
  - `README.md` features architecture diagrams, tech stack summary, screenshot mockups, and quick start guide.
  - `DEVELOPER_GUIDE.md` details local development setup, testing, and architecture.
  - `MIGRATION_GUIDE.md` provides step-by-step instructions for safely migrating from legacy console `narDB`.
- **Required Tests**: Documentation review and markdown linting.
- **Status**: Planned
- **Notes**: Portfolio presentation artifact.
