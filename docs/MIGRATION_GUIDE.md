# NovaBank Legacy Migration & Modernization Guide

This document details the architectural modernization journey from the legacy console banking system (`BMS_CONSOLE-main`) to **NovaBank**, providing technical rationale, schema translation maps, and operational migration procedures.

---

## 🏛️ Modernization Comparison Matrix

| Architectural Dimension | Legacy Console (`BMS_CONSOLE-main`) | Modern NovaBank System |
|---|---|---|
| **User Interface** | Text-based CLI console with raw `input()` loops | Modern desktop GUI built on PySide6 (Qt 6) with MVVM architecture |
| **Monetary Arithmetic** | Python `float` and raw database strings subject to floating-point truncation | Immutable `Money` Value Object using `Decimal` with strict rounding (`ROUND_HALF_UP`) |
| **Database Access** | Direct string interpolation (`f"SELECT * ... WHERE acc = '{acc}'"`) vulnerable to SQL injection | SQLAlchemy 2.0 ORM with 100% parameterized queries; zero SQL string formatting |
| **Credential Storage** | Plaintext CSV file (`BMS_MySQL_ConnectionString.csv`) stored on disk | Windows Credential Manager (`keyring`) and encrypted environment variables |
| **Concurrency & Locks** | No locking mechanism; simultaneous transactions cause race conditions and balance corruption | In-process per-account re-entrant mutexes (`AccountLockManager`) and DB `FOR UPDATE` row locks |
| **Transfer Deadlock Safety**| Unordered lock acquisition causing deadlocks | Strict global lock ordering (`min(acc1, acc2)` before `max(acc1, acc2)`) guaranteeing zero deadlocks |
| **Audit Trail** | None; zero state change history or compliance tracking | Comprehensive, immutable audit trail recording before/after JSON state diffs |
| **Reporting & Statements** | Console table printouts | Certified FDIC PDF bank statements and RFC-4180 formula-injection-safe CSV exports |
| **Database Disaster Recovery**| Manual SQL exports | Non-blocking hot backup manager (`mysqldump`) and preflight-checked restore wizard |
| **Artificial Intelligence** | None | Private local LM Studio assistant with client-side PII scrubbing and loopback enforcement |

---

## 🗄️ Database Schema Translation Map

The legacy database `narDB` utilized two unstructured tables: `BMS_MASTER` (customer profiles) and `BMS_ACCOUNTS` (account balances and basic logs). NovaBank maps these into modern relational entities with foreign keys and strict constraints:

### 1. Account Entity Mapping (`narDB.BMS_MASTER` -> `novabank.accounts`)

| Legacy Field (`BMS_MASTER`) | NovaBank Column (`accounts`) | Type | Transformation / Invariants |
|---|---|---|---|
| `Account_No` | `account_number` | `VARCHAR(12)` | Normalizes to 12 digits (`\d{12}`) with Luhn check-digit verification |
| `Name` | `holder_name` | `VARCHAR(100)` | Stripped and sanitized |
| `DOB` | `dob` | `DATE` | Validated; must represent age $\ge 18$ |
| `Address` | `address_line` | `VARCHAR(255)` | Trimmed string |
| `City` | `city` | `VARCHAR(50)` | Trimmed string |
| `State` | `state` | `VARCHAR(50)` | Trimmed string |
| `Country` | `country` | `VARCHAR(50)` | Trimmed string |
| `Phone_No` | `phone_number` | `VARCHAR(20)` | Validated 10-digit format |
| *(implicit)* | `is_active` | `BOOLEAN` | Account status flag (Active vs Closed) |
| *(implicit)* | `version` | `INT` | Optimistic locking concurrency token |
| *(implicit)* | `created_at` / `updated_at`| `DATETIME` | Automatic UTC timestamps |

---

### 2. Transaction Entity Mapping (`narDB.BMS_ACCOUNTS` -> `novabank.transactions`)

| Legacy Field (`BMS_ACCOUNTS`) | NovaBank Column (`transactions`) | Type | Transformation / Invariants |
|---|---|---|---|
| *(auto id)* | `transaction_id` | `BIGINT AUTO_INCREMENT`| Primary Key |
| `Account_No` | `account_number` | `VARCHAR(12)` | Foreign Key -> `accounts.account_number` |
| `Type` | `transaction_type` | `VARCHAR(20)` | Enum: `DEPOSIT`, `WITHDRAWAL`, `TRANSFER` |
| *(implicit)* | `direction` | `VARCHAR(10)` | Enum: `CREDIT` (inflow) or `DEBIT` (outflow) |
| `Amount` | `amount` | `NUMERIC(15, 2)` | Strict `Decimal` monetary amount |
| `Balance` | `balance_after` | `NUMERIC(15, 2)` | Reconciled running balance after transaction |
| *(implicit)* | `currency` | `VARCHAR(3)` | Default: `USD` |
| *(implicit)* | `transaction_ref` | `VARCHAR(36)` | Unique UUID reference string (idempotency key) |
| `Date` | `created_at` | `DATETIME` | Transaction execution timestamp |
| *(implicit)* | `created_by` | `VARCHAR(50)` | Teller actor identifier |

---

## 🔐 Legacy Credential Migration & Shredding

In `BMS_CONSOLE-main`, database passwords were stored insecurely in plaintext CSV:
```
Server,Port,Database,User,Password
localhost,3306,narDB,root,PlainTextPass123
```

NovaBank provides automated one-way migration:
```python
from novabank.infrastructure.config import import_and_shred_legacy_csv

# Imports credentials into Windows Credential Manager and securely deletes the CSV file
success = import_and_shred_legacy_csv("BMS_MySQL_ConnectionString.csv")
```
Once imported, the password is encrypted natively by the Windows Data Protection API (DPAPI) and the plaintext file is shredded from disk.

---

## 🔄 Step-by-Step Data Migration Procedure

1. **Preflight Backup**: Execute full hot backup of legacy `narDB`:
   ```powershell
   mysqldump -u root -p --single-transaction --routines --triggers narDB > legacy_backup.sql
   ```
2. **Execute Alembic Schema Migrations**:
   ```powershell
   alembic upgrade head
   ```
3. **Verify Integrity**: Run system diagnostics to verify database readiness:
   ```powershell
   python -m novabank.main --diagnostics
   ```
4. **Launch Modern NovaBank**:
   ```powershell
   python -m novabank.main
   ```

