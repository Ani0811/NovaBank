# Modern NovaBank (BMS) - Software Requirements Specification (SRS)

## 1. Introduction & Modernization Scope

This document specifies the complete functional, non-functional, security, and artificial intelligence requirements for the modernized Python NovaBank. All requirements are written to be verifiable, testable, and directly traceable to tasks defined in `TASKS.md`.

---

## 2. Functional Requirements (FR)

### FR-01: Customer Account Opening
- **Description**: The system shall permit tellers to create new customer bank accounts with complete biographical and contact information.
- **Inputs**: Holder Full Name (1-100 characters), Date of Birth (must indicate age between 18 and 120 years), Street Address (1-255 characters), City (1-100 characters), State (1-100 characters), Country (1-100 characters), Phone Number (exactly 10 digits), and Optional Initial Deposit (non-negative decimal).
- **Processing**:
  1. Validates all inputs client-side and at domain boundary.
  2. Generates a unique 12-digit account number.
  3. Inserts account record with status `Active` and initial balance.
  4. If initial deposit > 0, executes an atomic initial deposit transaction.
  5. Emits an audit event `ACCOUNT_CREATED`.
- **Acceptance Criteria**:
  - Valid input creates active account and generates unique 12-digit number.
  - Submitting invalid inputs (e.g., age < 18, alphabetic phone number) displays inline field errors and blocks submission.
  - If initial deposit is supplied, account balance reflects the deposit and a corresponding `DEPOSIT` transaction is recorded.

### FR-02: Customer Profile Inquiry & Modification
- **Description**: The system shall allow tellers to retrieve customer profile details and update mutable contact information.
- **Inputs**: Account Number. Mutable fields: Address, City, State, Country, Phone Number.
- **Processing**:
  1. Retrieves customer details and current calculated balance.
  2. Allows editing mutable contact fields with validation.
  3. Prohibits direct modification of Account Number, Date of Birth, or Account Balance through profile editing.
  4. Records an audit event `ACCOUNT_UPDATED` with before/after diff.
- **Acceptance Criteria**:
  - Searching by account number retrieves accurate customer profile and balance.
  - Updating contact details modifies the record and persists change in database.
  - Audit event logs the prior and new values.

### FR-03: Safe Account Deactivation & Closure
- **Description**: The system shall allow authorized tellers to close an existing bank account with balance safeguards.
- **Inputs**: Account Number, Closure Reason.
- **Processing**:
  1. Checks current account balance.
  2. If `balance > 0`, blocks closure and prompts user to withdraw or transfer remaining funds first.
  3. If `balance == 0`, displays confirmation modal.
  4. Sets `is_active = False` in database.
  5. Records an audit event `ACCOUNT_CLOSED`.
- **Acceptance Criteria**:
  - Closing an account with positive balance is strictly rejected with a clear message: "Account balance must be zero before closure."
  - Closed accounts cannot perform any subsequent deposits, withdrawals, or transfers.
  - Status updates to `Closed` across all UI views.

### FR-04: Cash Deposit Operations
- **Description**: The system shall execute atomic cash deposits into active customer accounts.
- **Inputs**: Account Number, Deposit Amount (Decimal > 0), Optional Description.
- **Processing**:
  1. Locks account row (`SELECT ... FOR UPDATE`).
  2. Verifies account exists and `is_active == True`.
  3. Increments account balance by deposit amount.
  4. Appends transaction record (`direction = 'CREDIT'`, `type = 'DEPOSIT'`).
  5. Commits transaction and generates digital deposit receipt.
- **Acceptance Criteria**:
  - Deposit of $100.00 onto an account with $50.00 results in an exact balance of $150.00.
  - Transaction table shows a new row with timestamp, unique reference, credit amount, and post-transaction balance.
  - Depositing into a closed or non-existent account fails with an explicit error dialog.

### FR-05: Cash Withdrawal Operations & Overdraft Prevention
- **Description**: The system shall execute atomic cash withdrawals from active customer accounts while strictly enforcing balance sufficiency.
- **Inputs**: Account Number, Withdrawal Amount (Decimal > 0), Optional Description.
- **Processing**:
  1. Locks account row (`SELECT ... FOR UPDATE`).
  2. Verifies account is active.
  3. Verifies `current_balance >= withdrawal_amount`.
  4. Decrements account balance.
  5. Appends transaction record (`direction = 'DEBIT'`, `type = 'WITHDRAWAL'`).
  6. Commits transaction and generates digital withdrawal receipt.
- **Acceptance Criteria**:
  - Withdrawal of $50.00 from an account with $150.00 balance succeeds, leaving $100.00.
  - Withdrawal of $150.01 from an account with $150.00 balance is rejected with `InsufficientFundsError`.
  - Under concurrent withdrawal requests, double-spending is physically prevented by row-level locking.

### FR-06: Internal Account-to-Account Fund Transfer
- **Description**: The system shall transfer funds atomically between two active bank accounts.
- **Inputs**: Source Account Number, Destination Account Number, Transfer Amount (Decimal > 0).
- **Processing**:
  1. Validates source and destination accounts are distinct.
  2. Acquires row locks on both accounts in deterministic order (by account number ascending) to prevent deadlocks.
  3. Verifies both accounts are active and source balance >= transfer amount.
  4. Debits source account and credits destination account.
  5. Appends linked transaction records with matching correlation ID.
  6. Commits transaction.
- **Acceptance Criteria**:
  - Source balance decreases by transfer amount, destination balance increases by exact same amount.
  - Transfer between identical accounts is blocked.
  - If destination credit fails, source debit is rolled back completely.

### FR-07: Account Directory Search & Filtering
- **Description**: The system shall provide a responsive, searchable directory of all customer accounts.
- **Inputs**: Search query (Name, Account Number, Phone Number), Status filter (All, Active, Closed).
- **Processing**:
  1. Executes parameterized search with SQL `LIKE` or index lookup.
  2. Debounces user keystrokes (200ms).
  3. Returns paginated results (50 per page).
- **Acceptance Criteria**:
  - Typing an account number or name updates results within 100ms.
  - Filter chips isolate active versus closed accounts accurately.

### FR-08: Account Statement Generation & Historical Reconciliation
- **Description**: The system shall generate comprehensive statements of account transactions over user-specified date ranges.
- **Inputs**: Account Number, Start Date, End Date.
- **Processing**:
  1. Computes opening balance as of `Start Date 00:00:00`.
  2. Fetches all transactions between `Start Date` and `End Date 23:59:59` ordered by timestamp.
  3. Computes total credits, total debits, and closing balance.
  4. Verifies mathematical reconciliation: `Opening Balance + Credits - Debits == Closing Balance`.
- **Acceptance Criteria**:
  - Statement table correctly presents opening balance, period transactions with running balances, and ending balance.
  - Statements with zero transactions correctly show opening balance == closing balance.

### FR-09: Statement Export to CSV & Printable PDF
- **Description**: The system shall export generated account statements into CSV and PDF formats.
- **Inputs**: Generated statement data, Target File Path on Windows filesystem.
- **Processing**:
  1. CSV: Formats data complying with RFC-4180.
  2. PDF: Renders styled document with bank header, customer details, and transaction grid.
  3. Executes asynchronously on worker thread.
- **Acceptance Criteria**:
  - CSV opens cleanly in Microsoft Excel without character encoding corruption.
  - PDF contains all statement metadata, headers, and footer pagination.

### FR-10: Audit Event Logging & Compliance Viewer
- **Description**: The system shall automatically record and display an immutable audit log of administrative and financial operations.
- **Inputs**: Automatically captured on actions (account open, update, close, transfer).
- **Processing**:
  1. Inserts audit record (`timestamp`, `actor`, `event_type`, `entity_id`, `payload`).
  2. Displays read-only viewer for branch managers with category and date filtering.
- **Acceptance Criteria**:
  - Audit records cannot be edited or deleted through the application.
  - Viewer displays before/after JSON state changes clearly.

---

## 3. Non-Functional Requirements (NFR)

### NFR-01: User Interface Responsiveness & 60 FPS Guarantee
- The PySide6 user interface main thread shall never block during database transactions, file I/O, or AI inference.
- All non-trivial operations must execute on `QThreadPool` worker threads.
- UI response to mouse clicks and keystrokes must occur within 50 milliseconds.

### NFR-02: Database Transaction Latency
- Core counter operations (deposit, withdrawal, account lookup) shall complete within 100 milliseconds under normal local network/host conditions.

### NFR-03: Monetary Precision & Zero Rounding Error
- All currency values shall be stored as `DECIMAL(15, 2)` and processed in Python as `decimal.Decimal`.
- Floating-point arithmetic (`float`) is strictly prohibited in monetary code paths.

### NFR-04: Concurrency Safety & Double-Spend Immunity
- The system shall guarantee complete isolation against race conditions.
- Simultaneous withdrawal requests on the same account shall serialize cleanly via InnoDB row-level locking (`SELECT ... FOR UPDATE`), preventing overdrafts or double-spending.

### NFR-05: Windows Platform Native Experience
- The desktop software shall be optimized for Windows 10 and Windows 11 (64-bit).
- Support dynamic high-DPI display scaling (100%, 125%, 150%, 200%) without blurry text or clipped controls.

### NFR-06: Code Quality & Automated Test Coverage
- Automated test coverage shall exceed 90% across the domain and application layers.
- Static analysis with `ruff` and `bandit` must pass with zero High/Medium warnings.

---

## 4. Security & Data Integrity Requirements (SEC)

### SEC-01: Zero SQL Injection Tolerance
- 100% of database interactions shall use SQLAlchemy parameterized queries or typed ORM models.
- String concatenation, formatting, or hand-rolled string sanitization (such as legacy `FormatString`) in SQL execution is strictly forbidden.

### SEC-02: Secure Credential Management
- Plaintext storage of database passwords in CSV files (such as legacy `BMS_MySQL_ConnectionString.csv`) is completely abolished.
- Credentials must be sourced from Windows Credential Manager (`keyring`), environment variables, or gitignored `.env` files.
- Sensitive strings must be protected in memory using `pydantic.SecretStr`.

### SEC-03: Non-Destructive Database Management
- Execution of unconditional `DROP DATABASE` or `DROP TABLE` statements (as seen in legacy `BMS_Tables.Py.310.py`) is prohibited.
- Schema evolution must proceed strictly via reversible Alembic migrations.

### SEC-04: Data Immutability on Financial Ledger
- The `transactions` table is append-only.
- The application shall contain no `UPDATE` or `DELETE` endpoints for transaction ledger records.

---

## 5. Local AI Requirements (AI)

### AI-01: Strictly Local Inference & Data Sovereignty
- All AI features shall communicate exclusively with a locally hosted **LM Studio** server at `http://localhost:1234/v1`.
- Zero external internet or cloud API calls are permitted for AI processing.

### AI-02: Client-Side PII Scrubbing & Privacy Boundary
- Before any domain data is submitted to LM Studio, it must pass through an automated PII sanitizer.
- Customer names, full phone numbers, and street addresses must be redacted.
- Account numbers must be masked to display only the last 4 digits (`****-****-1234`).

### AI-03: Zero Mutation Capability (Read-Only AI)
- The AI assistant shall have ZERO authority or technical access to alter database records, create accounts, or execute financial transactions.
- The AI's role is strictly confined to natural language query translation, statement summarization, and rule explanation.

### AI-04: Structured Output Validation
- Natural-language query translations must conform to strict JSON schemas validated via Pydantic.
- Hallucinated or malformed outputs must be caught and cleanly discarded, falling back to deterministic keyword search.

### AI-05: Graceful Offline Degradation
- If LM Studio is not running, offline, or returns a timeout (> 10 seconds), the desktop application shall:
  1. Display an "AI Assistant: Offline" status indicator.
  2. Maintain 100% full operational capacity for all core banking workflows.
  3. Never crash or raise an unhandled exception.

---

## 6. Traceability Matrix

| Requirement ID | Domain Area | Target Priority | Primary Affected Module | Implementing Task ID |
|---|---|---|---|---|
| **FR-01** | Account Management | P2 | `novabank.application.services.banking_service` | `TASK-P1-08`, `TASK-P2-03` |
| **FR-02** | Account Management | P2 | `novabank.ui.views.account_detail_view` | `TASK-P2-05` |
| **FR-03** | Account Management | P2 | `novabank.ui.views.account_close_dialog` | `TASK-P2-06` |
| **FR-04** | Financial Transactions | P1 / P2 | `novabank.application.services.banking_service` | `TASK-P1-08`, `TASK-P2-07` |
| **FR-05** | Financial Transactions | P1 / P2 | `novabank.application.services.banking_service` | `TASK-P1-09`, `TASK-P2-08` |
| **FR-06** | Financial Transactions | P1 / P2 | `novabank.application.services.banking_service` | `TASK-P1-10`, `TASK-P2-09` |
| **FR-07** | Directory & Search | P2 | `novabank.ui.views.account_list_view` | `TASK-P2-04` |
| **FR-08** | Reporting & Statements | P3 | `novabank.application.services.statement_service` | `TASK-P3-01`, `TASK-P3-02` |
| **FR-09** | Reporting & Statements | P3 | `novabank.application.services.export_service` | `TASK-P3-03`, `TASK-P3-04` |
| **FR-10** | Compliance & Audit | P3 | `novabank.application.services.audit_service` | `TASK-P3-05`, `TASK-P3-06` |
| **NFR-01** | Performance & UI | P2 | `novabank.ui.workers.task_runner` | `TASK-P2-02` |
| **NFR-03** | Domain Math | P1 | `novabank.domain.value_objects.money` | `TASK-P1-01` |
| **NFR-04** | Concurrency Safety | P1 | `novabank.infrastructure.repositories` | `TASK-P1-09`, `TASK-P1-11` |
| **SEC-01** | Security | P1 | `novabank.infrastructure.repositories` | `TASK-P1-06`, `TASK-P5-01` |
| **SEC-02** | Security | P0 | `novabank.infrastructure.config` | `TASK-P0-03` |
| **SEC-03** | Data Integrity | P1 | `migrations/` | `TASK-P1-04`, `TASK-P1-05` |
| **AI-01..05** | Local AI Assistant | P4 | `novabank.infrastructure.ai` | `TASK-P4-01..06` |
