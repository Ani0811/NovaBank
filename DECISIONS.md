# Modern NovaBank (BMS) - Architecture Decision Records (ADRs)

## Overview of Architecture Decisions

This document records the critical architectural and engineering decisions made during the modernization of the Python NovaBank. Each record outlines the context, decision, considered alternatives, and consequences.

| ADR ID | Decision Title | Status | Date |
|---|---|---|---|
| **ADR-001** | Dedicated Modern Project Directory with Legacy Preservation | Accepted | 2026-10-24 |
| **ADR-002** | Desktop Framework Selection: PySide6 (Qt 6) | Accepted | 2026-10-24 |
| **ADR-003** | Database Driver: PyMySQL with SQLAlchemy 2.0 | Accepted | 2026-10-24 |
| **ADR-004** | Monetary Precision: `decimal.Decimal` and SQL `DECIMAL(15, 2)` | Accepted | 2026-10-24 |
| **ADR-005** | Concurrency Control: Pessimistic Row Locking (`SELECT ... FOR UPDATE`) | Accepted | 2026-10-24 |
| **ADR-006** | Credential Management: Windows Credential Manager (`keyring`) & `.env` | Accepted | 2026-10-24 |
| **ADR-007** | Database Migrations: Alembic with Read-Only Legacy ETL | Accepted | 2026-10-24 |
| **ADR-008** | Local AI Integration: LM Studio via Localhost OpenAI-Compatible REST | Accepted | 2026-10-24 |
| **ADR-009** | UI Threading: `QThreadPool` / `QRunnable` Worker Architecture | Accepted | 2026-10-24 |
| **ADR-010** | Packaging: PyInstaller Standalone Bundle with Inno Setup Installer | Accepted | 2026-10-24 |

---

## Architecture Decision Records

### ADR-001: Dedicated Modern Project Directory with Legacy Preservation
- **Status**: Accepted
- **Context**: The existing legacy codebase resides in `C:\Github\BMS_CONSOLE-main\BMS_CONSOLE-main` with two monolithic scripts (`BMS.Py310.py` and `BMS_Tables.Py.310.py`). The user requested that the modern project be saved in `C:\Github` while preserving legacy source code and data untouched.
- **Decision**: Establish the modernized project in `C:\Github\NovaBank` as an independent repository with standard clean architecture layout. Mark the legacy directory `C:\Github\BMS_CONSOLE-main` as strictly read-only reference material.
- **Alternatives Considered**:
  - *In-place modification of `BMS_CONSOLE-main`*: Rejected because it risks overwriting working legacy code, obscures the modernization comparison, and risks running legacy destructive scripts.
- **Consequences**:
  - *Positive*: Preserves historical project artifacts in an uncorrupted state; enables side-by-side comparison for portfolio review.
  - *Negative*: Requires creating a new directory structure and managing separate git tracking.

---

### ADR-002: Desktop Framework Selection: PySide6 (Qt 6 for Python)
- **Status**: Accepted
- **Context**: The target application is modern Windows desktop software. The user requires rich aesthetics, modern controls, responsive performance, and high reliability.
- **Decision**: Adopt **PySide6 (Qt 6 for Python)** as the sole desktop UI framework.
- **Alternatives Considered**:
  - *Tkinter*: Standard library, but severely outdated visual aesthetics, poor high-DPI scaling on Windows 11, and limited widget capability.
  - *PyQt5 / PyQt6*: Robust, but PySide6 is the official, actively supported project from the Qt Company with cleaner LGPL licensing.
  - *Electron / Webview*: High memory footprint, bundled Chromium overhead, complex inter-process communication for desktop banking.
- **Consequences**:
  - *Positive*: Enterprise-grade widget library, native Windows 10/11 styling, rock-solid Model-View-ViewModel (MVVM) support, high-DPI display awareness, and native QThread worker concurrency.
  - *Negative*: Larger binary size (~60MB) when bundled; requires familiarity with Qt signals/slots.

---

### ADR-003: Database Driver & ORM: PyMySQL with SQLAlchemy 2.0
- **Status**: Accepted
- **Context**: The target database is MySQL 8.0. The legacy script used `MySQLdb` (from `mysqlclient`), which requires compiled C-extensions and Microsoft Visual C++ Build Tools on Windows. On modern Python (3.12–3.14), compiling `mysqlclient` on Windows frequently fails without specialized developer build environments.
- **Decision**: Adopt **SQLAlchemy 2.0** as the data persistence and query layer, paired with **PyMySQL** as the default pure-Python MySQL driver (`mysql+pymysql://`). Support SQLite in-memory dialect (`sqlite://`) for ultra-fast automated unit and repository testing.
- **Alternatives Considered**:
  - *mysqlclient (MySQLdb)*: Fast, but requires MSVC compilation tools on Windows; brittle dependency.
  - *mysql-connector-python*: Official Oracle driver, but heavier and less performant than PyMySQL under SQLAlchemy.
  - *Raw SQL via DB-API*: Rejected due to high risk of SQL injection, lack of type safety, and boilerplate data mapping.
- **Consequences**:
  - *Positive*: Pure-Python driver installs cleanly on any Windows machine; SQLAlchemy 2.0 provides type-safe query expressions, parameterized execution, and effortless migration between MySQL and test SQLite databases.
  - *Negative*: Slight overhead compared to native C extensions, negligible for counter-banking transaction volumes (< 1,000 TPS).

---

### ADR-004: Monetary Precision: `decimal.Decimal` and SQL `DECIMAL(15, 2)`
- **Status**: Accepted
- **Context**: The legacy database defined `AMOUNT_CR` and `AMOUNT_DR` as `bigint`, completely disallowing cents or paise. Common banking software must support two decimal places with absolute mathematical precision. Using standard IEEE 754 floating-point numbers (`float`) introduces insidious rounding bugs (e.g., `0.1 + 0.2 != 0.3`).
- **Decision**: Represent all monetary quantities using Python's `decimal.Decimal` standard library encapsulated in an immutable `Money` value object with `ROUND_HALF_UP` rounding. In MySQL, store all amounts as `DECIMAL(15, 2)`.
- **Alternatives Considered**:
  - *Integer cents (e.g., $100.00 = 10000)*: Clean in integer math, but error-prone when interfacing with external reports, CSV exports, and UI inputs.
  - *Floating point (`float` / `DOUBLE`)*: Strictly prohibited in financial engineering due to precision loss.
- **Consequences**:
  - *Positive*: Absolute decimal precision; immunity to rounding errors; transparent monetary formatting for UI and statements.
  - *Negative*: Requires explicit conversion at serialization boundaries.

---

### ADR-005: Concurrency Control: Pessimistic Row Locking (`SELECT ... FOR UPDATE`)
- **Status**: Accepted
- **Context**: In the legacy application, withdrawals were vulnerable to double-spending: `getWithdrawAmt()` read balance in one query and executed `INSERT INTO BMS_ACCOUNTS` in a subsequent query with no lock. Two concurrent withdrawals on the same account would both succeed, causing unrecorded overdrafts.
- **Decision**: Implement pessimistic row-level locking via `SELECT ... FOR UPDATE` inside atomic MySQL InnoDB transactions. When transferring funds between two accounts, enforce deterministic lock acquisition ordering (alphabetical by `account_number`) to prevent deadlocks. Additionally, maintain an account `version` column for optimistic conflict detection.
- **Alternatives Considered**:
  - *Pure optimistic locking (version column only)*: High collision rates under rapid consecutive transactions, causing frequent user-facing transaction retry failures.
  - *Table-level locking*: Destroys application throughput; unacceptable in multi-account scenarios.
- **Consequences**:
  - *Positive*: Guarantees zero double-spending, prevents negative balances, and eliminates transfer deadlocks.
  - *Negative*: Requires holding database connection open during the transaction lifecycle (mitigated by fast, tight transaction blocks).

---

### ADR-006: Credential Management: Windows Credential Manager (`keyring`) & `.env`
- **Status**: Accepted
- **Context**: The legacy system stored database host, username, database name, and password in plaintext in `BMS_MySQL_ConnectionString.csv`. This is a critical security vulnerability.
- **Decision**: Completely deprecate plaintext CSV files. Implement `novabank.infrastructure.config` using `pydantic-settings` to load configuration from:
  1. Environment variables (`BMS_DB_HOST`, `BMS_DB_USER`, etc.).
  2. Windows Credential Manager via the Python `keyring` library for desktop password storage.
  3. Gitignored local configuration files (`.env.local`).
- **Alternatives Considered**:
  - *Hardcoded default credentials*: Catastrophic security practice.
  - *Encrypted local file with hardcoded key*: False security (obfuscation).
- **Consequences**:
  - *Positive*: Enterprise-grade security posture; credentials protected by Windows OS DPAPI / Credential Manager.
  - *Negative*: Requires user to configure credentials on initial setup via a setup dialog if environment variables are not set.

---

### ADR-007: Database Migrations: Alembic with Read-Only Legacy ETL
- **Status**: Accepted
- **Context**: Legacy setup script `BMS_Tables.Py.310.py` contained destructive `DROP DATABASE IF EXISTS NARDB` and `DROP TABLE IF EXISTS ...` statements. If executed in production, all data would be permanently destroyed.
- **Decision**: Adopt **Alembic** for structured, reversible, version-controlled migrations. The initial migration creates modern normalized tables (`accounts`, `transactions`, `audit_events`). To import historical data, implement a separate read-only ETL script that transfers data from legacy `narDB` into the new schema without modifying or dropping legacy tables.
- **Alternatives Considered**:
  - *Custom raw SQL migration scripts*: Lack version tracking, rollback management, and automated diffing.
- **Consequences**:
  - *Positive*: Safe, auditable schema evolution; eliminates destructive script execution risks.
  - *Negative*: Adds Alembic configuration overhead to the project.

---

### ADR-008: Local AI Integration: LM Studio via Localhost OpenAI-Compatible REST
- **Status**: Accepted
- **Context**: The modernization project incorporates optional local AI inference for natural-language querying, statement summarization, and explainable activity monitoring. The user specified local inference through LM Studio using open-weight models.
- **Decision**: Connect to LM Studio's local HTTP REST server (`http://localhost:1234/v1`) using an OpenAI-compatible client. The AI layer is strictly **read-only and advisory**, with zero database mutation credentials. Customer PII (name, phone, address, full account number) is scrubbed client-side before sending prompts. If LM Studio is offline, all banking operations continue uninterrupted.
- **Alternatives Considered**:
  - *Embedded in-process inference (llama-cpp-python)*: High build complexity on Windows, heavy GPU library dependencies, and potential memory crashes affecting the main application process.
  - *Cloud AI APIs (OpenAI, Anthropic)*: Violates banking privacy, exposes customer data to third parties, requires recurring API subscriptions, and fails when offline.
- **Consequences**:
  - *Positive*: Zero privacy leak; local sovereignty; process isolation (if LM Studio crashes, the desktop app remains intact); optional and graceful offline degradation.
  - *Negative*: Requires the user to have LM Studio installed and running if they wish to utilize AI features.

---

### ADR-009: UI Threading: `QThreadPool` / `QRunnable` Worker Architecture
- **Status**: Accepted
- **Context**: PySide6 runs on a single main event loop. Executing blocking operations (database queries, network calls to LM Studio, or PDF rendering) directly on the GUI thread causes the Windows desktop window to freeze, display "(Not Responding)", and degrade user experience.
- **Decision**: Implement a reusable `TaskRunner` architecture utilizing Qt's `QThreadPool` and `QRunnable`. All database operations, file exports, and AI calls are dispatched to background worker threads, emitting results and errors back to the main thread via Qt Signals and Slots.
- **Alternatives Considered**:
  - *Python `threading.Thread`*: Lacks deep integration with Qt event loop; direct UI manipulation from standard threads causes memory corruption in Qt.
  - *Asyncio with `qasync`*: Introduces async/await complexity across the entire desktop codebase and ORM layer.
- **Consequences**:
  - *Positive*: Guaranteed responsive UI (60 FPS); smooth loading indicators; robust error capture and main-thread dialog presentation.
  - *Negative*: Requires thread-safe design (passing immutable DTOs rather than shared mutable objects).

---

### ADR-010: Packaging: PyInstaller Standalone Bundle with Inno Setup Installer
- **Status**: Accepted
- **Context**: The target application must be delivered as a professional Windows desktop software product suitable for non-technical users and portfolio demonstration.
- **Decision**: Use **PyInstaller** to compile the application into a standalone Windows binary bundle, and use **Inno Setup** to generate a standard Windows installer (`Setup.exe`) with Start Menu shortcuts and uninstaller.
- **Alternatives Considered**:
  - *Distributing raw Python script*: Requires end-users to install Python, create virtual environments, and install dependencies via terminal; unacceptable for portfolio desktop software.
  - *Nuitka*: Produces highly optimized binaries but has longer compilation times and complex MSVC compiler dependencies.
- **Consequences**:
  - *Positive*: One-click Windows installation; runs on machines without Python installed.
  - *Negative*: Build process must be maintained and verified on Windows.

---

## 3. Unverified Assumptions & Decisions Awaiting User Approval

The following architectural choices are based on engineering analysis of the repository. They are explicitly marked for user review and approval:

1. **MySQL Service Availability & Port Configuration**:
   - *Observation*: Local machine inspection revealed the Windows service `MySQL80` is currently `Stopped`.
   - *Assumption*: The user will start the service or provide connection details (host, port, user, password) when ready to run database migrations.
   - *Status*: **Awaiting User Confirmation**.

2. **Recommended LM Studio Model**:
   - *Proposal*: Recommend **Llama 3.2 3B Instruct** (lightweight, rapid inference on CPU/integrated GPU) or **Qwen 2.5 7B Instruct** (for higher reasoning quality on dedicated GPUs).
   - *Assumption*: The user has at least 8GB of RAM for 3B/7B quantized GGUF models.
   - *Status*: **Awaiting User Confirmation**.

3. **User Authentication & Role-Based Access Control (RBAC)**:
   - *Observation*: The legacy application had zero authentication (anyone opening the script had unrestricted access).
   - *Proposal*: In Phase 2, implement a lightweight local authentication system (Teller PIN / Manager Login) with session context to record `created_by` and `actor` fields in transactions and audit logs.
   - *Status*: **Awaiting User Confirmation**.

4. **Account Number Format**:
   - *Observation*: Legacy code generated random 12-digit integers (`random.SystemRandom().randint(100000000000, 999999999999)`).
   - *Proposal*: Retain the 12-digit account number concept, but introduce an algorithmic Luhn check digit or sequential prefix (e.g. `1001-XXXX-XXXX`) to detect typos and prevent collision loops.
   - *Status*: **Awaiting User Confirmation**.
