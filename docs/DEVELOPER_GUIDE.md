# NovaBank Developer & Contributor Guide

Welcome to the **NovaBank** engineering codebase. This guide details our development standards, environment setup, testing practices, and architecture rules.

---

## 🛠️ Development Environment Setup

### 1. Prerequisites
- **OS**: Windows 10 or 11 (64-bit)
- **Python**: 3.11 or newer (Python 3.14 recommended)
- **Database**: MySQL Server 8.0 (Optional: SQLite in-memory engine supported for development/tests)
- **Git**: 2.30+

### 2. Initial Setup
```powershell
git clone https://github.com/NovaBank/NovaBank.git
cd NovaBank

# Create virtual environment
python -m venv .venv
.\.venv\Scripts\Activate.ps1

# Upgrade pip and install editable package with all dev dependencies
python -m pip install --upgrade pip
pip install -e .[dev]
```

### 3. Environment Configuration
Copy the template `.env.example` to `.env`:
```powershell
Copy-Item .env.example .env
```
Key configuration parameters:
| Parameter | Default | Description |
|---|---|---|
| `NOVABANK_DB_HOST` | `127.0.0.1` | MySQL Host |
| `NOVABANK_DB_PORT` | `3306` | MySQL Port |
| `NOVABANK_DB_NAME` | `novabank` | Application database schema |
| `NOVABANK_DB_USER` | `root` | Database username |
| `NOVABANK_LM_STUDIO_URL` | `http://localhost:1234/v1` | Local LM Studio endpoint |
| `NOVABANK_AI_MODEL` | `local-model` | Target local model identifier |

---

## 🏛️ Architecture & Coding Standards

### Clean Architecture Layers
1. **`novabank.domain`**: Pure business models (`Account`, `Transaction`, `Money`, `AccountNumber`).
   - Zero dependencies on frameworks, databases, or Qt.
   - All monetary figures **MUST** use the immutable `Money` value object (`Decimal`). Never use Python `float`.
2. **`novabank.application`**: Use case orchestrators (`BankingService`, `StatementService`, `AuditService`, `AISearchService`).
   - Accepts and returns Data Transfer Objects (DTOs).
   - Coordinates transactions, events, and domain entities.
3. **`novabank.infrastructure`**: External technology adapters.
   - SQLAlchemy 2.0 ORM mappings, PyMySQL database connections.
   - `mysqldump` hot backup and restore utilities.
   - Local LM Studio AI HTTP client and PII sanitizer.
4. **`novabank.ui`**: Presentation layer built with PySide6 (Qt 6).
   - MVVM architecture: Views connect directly to ViewModels via Qt Signals.
   - Asynchronous operations dispatch to background threads using `TaskRunner` (`QThreadPool`). The GUI thread must never block.

---

## 🧪 Testing Guidelines

NovaBank enforces high testing standards with automated gates:

```powershell
# Run complete test suite
pytest -v

# Run with coverage report across core domain & application layers
pytest --cov=novabank.domain --cov=novabank.application --cov-report=term-missing

# Run concurrency stress tests
pytest tests/integration/test_concurrency.py -v

# Run UI tests
pytest tests/ui/ -v

# Run static security audit
pytest tests/test_security_audit.py -v
```

### Writing Tests
- **Unit Tests**: Place in `tests/domain/` or `tests/application/`. Use in-memory data or mock interfaces.
- **UI Tests**: Use `pytest-qt` and the `qtbot` fixture. Always set appropriate signal wait timeouts (`timeout=10000`).
- **Financial Concurrency**: When testing multi-threaded balance transfers, verify net zero balance drift:
  $$\sum \Delta \text{Balance}_i = 0$$

---

## 🛡️ Security & Static Analysis

We run strict automated static checks before every commit:

```powershell
# Ruff linter and import formatter
ruff check .

# Bandit security scan (must report 0 High and 0 Medium issues)
bandit -r src/ -ll
```

---

## 📦 Binary Packaging Workflow

### Compiling Standalone Executable
```powershell
python packaging/build_exe.py
```
This produces `dist/NovaBank/NovaBank.exe` bundled with all PySide6 DLLs, styles, and dependencies.

### Generating Windows Setup Wizard
```powershell
python packaging/build_installer.py
```
Compiles `packaging/installer.iss` using Inno Setup 6 into `dist/installer/NovaBank_Setup_v1.0.0.exe`.

