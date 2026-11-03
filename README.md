# NovaBank Enterprise Banking System

[![Python](https://img.shields.io/badge/Python-3.11%2B%20%7C%203.14-blue?logo=python&logoColor=white)](https://python.org)
[![PySide6](https://img.shields.io/badge/UI-PySide6%20%28Qt%206%29-41cd52?logo=qt&logoColor=white)](https://doc.qt.io/qtforpython/)
[![SQLAlchemy](https://img.shields.io/badge/ORM-SQLAlchemy%202.0-d71f00)](https://www.sqlalchemy.org/)
[![Database](https://img.shields.io/badge/Database-MySQL%208.0-4479a1?logo=mysql&logoColor=white)](https://mysql.com)
[![Coverage](https://img.shields.io/badge/Coverage-95%25-brightgreen)](tests/)
[![Security](https://img.shields.io/badge/Bandit-Passed%20%280%20Issues%29-success)](tests/test_security_audit.py)
[![Local AI](https://img.shields.io/badge/Local%20AI-LM%20Studio%20%28Loopback%20Only%29-8a2be2)](src/novabank/infrastructure/ai/)

**NovaBank** is a modern, enterprise-grade desktop banking application built from the ground up to modernize legacy console banking software (`BMS_CONSOLE-main`) into a robust, secure, and intuitive desktop platform for retail bank branches.

Built on **Clean Architecture** and **Domain-Driven Design (DDD)** principles, NovaBank combines strict financial precision, thread-safe atomic transactions, certified regulatory reporting, transactional backup procedures, and privacy-preserving local AI assistance.

---

## 🏛️ System Architecture

NovaBank is structured into 4 isolated architectural layers with strictly unidirectional inward dependencies:

```
+-------------------------------------------------------------------------+
|                              PRESENTATION                               |
|   PySide6 (Qt 6) Views  •  MVVM ViewModels  •  TaskRunner ThreadPool    |
+------------------------------------+------------------------------------+
                                     |
                                     v
+-------------------------------------------------------------------------+
|                              APPLICATION                                |
|   BankingService  •  StatementService  •  AuditService  •  AISearch     |
|   ExportService   •  ActivityMonitoringService  •  DTOs & Events        |
+------------------------------------+------------------------------------+
                                     |
                                     v
+------------------------------------+------------------------------------+
|               DOMAIN               |           INFRASTRUCTURE           |
|  Account & Transaction Entities    |  SQLAlchemy 2.0 Repositories       |
|  Immutable Money Value Object      |  MySQL 8.0 & Alembic Migrations    |
|  AccountNumber & Domain Exceptions |  LM Studio Local AI Client & PII   |
|  Repository Interfaces             |  BackupManager & RestoreManager    |
+------------------------------------+------------------------------------+
```

---

## ✨ Key Enterprise Capabilities

### 1. Financial Precision & Domain Invariants
* **Immutable `Money` Value Object**: Uses Python `Decimal` with strict 2-decimal-place rounding (`ROUND_HALF_UP`) across all monetary calculations. Zero floating-point arithmetic.
* **Deterministic Account Numbers**: Enforces 12-digit format (`\d{12}`) with Luhn check-digit verification.
* **Atomic State Validation**: Accounts cannot transition to negative balances; closed accounts reject all incoming debits and credits.

### 2. High-Concurrency Transaction Engine
* **In-Process Thread Serialization**: Fine-grained per-account re-entrant mutexes (`AccountLockManager`) combined with database `SELECT ... FOR UPDATE` row locks.
* **Deadlock-Free Transfers**: Circular transfer deadlock freedom guaranteed by strict global account number sorting (`min(acc1, acc2)` acquired before `max(acc1, acc2)`).
* **Stress-Tested**: 100% verified under multi-threaded concurrency stress workloads with zero data race or balance drift.

### 3. Certified Regulatory Reporting & Safe Exports
* **RFC-4180 Compliant CSV Export**: Streaming CSV generation with automated formula injection defense (sanitizing `=`, `+`, `-`, `@`, `\t`, `\r`).
* **Official Bank PDF Statements**: Built using PySide6 `QTextDocument` and `QPdfWriter` with certified FDIC branding, customer summary strips, and mathematical balance reconciliation:
  $$\text{Closing Balance} = \text{Opening Balance} + \text{Total Credits} - \text{Total Debits}$$

### 4. Immutable Compliance Audit Trail
* **Automated Event Capture**: Listens to core lifecycle events (`AccountOpenedEvent`, `ProfileUpdatedEvent`, `AccountClosedEvent`, `DepositCompletedEvent`, `WithdrawalCompletedEvent`, `TransferCompletedEvent`).
* **Deep State Diff Inspector**: Records structured before/after JSON state snapshots. Audit records are strictly append-only with zero update or delete APIs.

### 5. Safe Transactional Backup & Restore
* **Non-Blocking Hot Backups**: Uses `mysqldump` with `--single-transaction --quick --routines --triggers`, streaming GZIP compression, and SHA-256 integrity verification.
* **Safeguarded Restore Wizard**: Inspects file headers and schema markers, requiring explicit target database name typing before proceeding.

### 6. Privacy-Preserving Local AI Assistant
* **Strict Loopback Boundary**: Connects exclusively to local LM Studio instances (`localhost` / `127.0.0.1`); all external egress is hard-blocked.
* **Client-Side PII Scrubbing**: Redacts names, phone numbers, addresses, and masks account numbers (`****-****-1234`) *before* prompt generation.
* **Natural Language Queries**: Translates questions like *"show deposits over 5,000 from last month"* into validated `StructuredQueryDTO` filters without raw SQL generation.
* **Deterministic Fallback**: Provides reliable template fallbacks if the local AI model is offline or returns invalid schema.

---

## 🚀 Quick Start Guide

### Prerequisites
* Windows 10 / 11 (64-bit)
* Python 3.11+ (Python 3.14 recommended)
* MySQL Server 8.0 (Optional for demo mode; runs SQLite in-memory if MySQL is offline)
* LM Studio (Optional, for local conversational AI features)

### 1. Clone & Setup Environment
```powershell
git clone https://github.com/NovaBank/NovaBank.git
cd NovaBank

# Create and activate virtual environment
python -m venv .venv
.\.venv\Scripts\Activate.ps1

# Install package with development dependencies
pip install -e .[dev]
```

### 2. Configure Credentials
```powershell
# Copy environment template
Copy-Item .env.example .env

# Edit .env or store database credentials securely in Windows Credential Manager:
python -c "from novabank.infrastructure.config import save_db_password_to_keyring; save_db_password_to_keyring('root', 'your_password')"
```

### 3. Launch NovaBank
```powershell
# Normal launch (connects to configured database)
python -m novabank.main

# Demo mode (instant standalone launch with in-memory database)
python -m novabank.main --demo

# Run system & database diagnostics
python -m novabank.main --diagnostics
```

---

## 🧪 Testing & Verification

NovaBank features an exhaustive automated test suite with **270 test items** and **95% code coverage** across domain and application layers:

```powershell
# Run complete test suite
pytest -v

# Run with coverage report
pytest --cov=novabank.domain --cov=novabank.application --cov-report=term-missing

# Run static security audit
pytest tests/test_security_audit.py -v
```

---

## 📦 Standalone Packaging & Distribution

### Build Standalone Executable
```powershell
python packaging/build_exe.py
# Outputs standalone portable bundle to dist\NovaBank\NovaBank.exe
```

### Build Windows Installer
```powershell
python packaging/build_installer.py
# Uses Inno Setup 6 (packaging/installer.iss) to generate NovaBank_Setup_v1.0.0.exe
```

---

## 📚 Documentation Index

* [**Developer Guide**](docs/DEVELOPER_GUIDE.md): Architecture walkthrough, contribution setup, and testing guides.
* [**User Manual**](docs/USER_MANUAL.md): Branch teller workflows, cash desk operations, statements, and AI assistant.
* [**Migration Guide**](docs/MIGRATION_GUIDE.md): Migrating data and workflows from legacy console `narDB`.
* [**Engineering Task Backlog**](TASKS.md): Detailed 43-task ledger across all 5 project phases.

