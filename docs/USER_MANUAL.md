# NovaBank Teller Operations Manual

Welcome to the **NovaBank Enterprise Banking System**. This operational guide details daily workflows for branch tellers, operations staff, and branch managers.

---

## 🖥️ Navigation & Interface Overview

NovaBank features a dark desktop user interface designed for readability during long banking shifts:

- **Navigation Sidebar (Left)**: Quick access to core banking modules:
  - 📊 **Dashboard**: System overview and daily branch activity.
  - 👥 **Accounts**: Search, inspect, and manage customer accounts.
  - ➕ **Open Account**: Register new customers with instant validation.
  - 💳 **Transactions**: Cash desk for deposits, withdrawals, and transfers.
  - 📄 **Statements**: Account statements, ledger exploration, and exports.
  - 🛡️ **Audit Trail**: Compliance log and before/after change inspection.
  - 🤖 **AI Assistant**: Conversational financial intelligence and smart queries.
  - ⚙️ **Settings**: Database status and configuration.
- **Top Header Bar**: Displays the active section title and context description.
- **Status Bar (Bottom)**: Real-time database connectivity badge, active teller session, and background task progress.

---

## 📋 Core Teller Workflows

### 1. Opening a New Customer Account
1. Click **Open Account** in the sidebar.
2. Fill out customer profile details:
   - **Full Legal Name**
   - **Date of Birth** (Customer must be at least 18 years of age)
   - **Address Line, City, State, Country**
   - **10-Digit Phone Number**
   - **Initial Deposit Amount** (Optional; minimum $0.00)
3. Click **Open Account**.
4. The system validates all inputs, generates an immutable 12-digit account number with Luhn check-digits, and displays a success confirmation dialog with the customer's account credentials.

### 2. Cash Desk Operations

#### A. Making a Cash Deposit
1. Navigate to **Transactions** > **Deposit**.
2. Enter the 12-digit customer account number. The system automatically fetches and displays the current balance and account status.
3. Enter the deposit amount and optional description/teller reference.
4. Review the computed new balance preview.
5. Click **Submit Deposit**. An atomic transaction record is appended to the ledger.

#### B. Cash Withdrawal (Overdraft Protected)
1. Navigate to **Transactions** > **Withdrawal**.
2. Enter the account number.
3. Enter the withdrawal amount.
4. **Overdraft Prevention**: If the withdrawal amount exceeds the active balance, the submission button is automatically blocked, and an explicit overdraft warning displays.
5. Click **Submit Withdrawal**.

#### C. Inter-Account Transfers
1. Navigate to **Transactions** > **Transfer**.
2. Enter the **Source Account** and **Destination Account**. (Transferring to the same account is strictly blocked).
3. Enter the transfer amount.
4. Click **Execute Transfer**. The system executes an atomic, dual-entry debit and credit.
5. A **Transfer Receipt Dialog** appears with transaction reference UUIDs, timestamp, and printable confirmation.

---

### 3. Account Statements & Reports

1. Navigate to **Statements**.
2. Enter the account number in the search bar.
3. Choose a filter preset:
   - `Today`
   - `Last 7 Days`
   - `This Month`
   - `Year to Date (YTD)`
   - `All Time`
   - `Custom Date Range`
4. Review the interactive ledger explorer and KPI financial summary strip:
   - Opening Balance
   - Total Inflow (Credits)
   - Total Outflow (Debits)
   - Net Cash Flow
   - Closing Balance & Mathematical Reconciliation Badge
5. **Exporting**:
   - Click **Export CSV** to generate an RFC-4180 compliant CSV file protected against formula injection attacks.
   - Click **Export PDF** to generate an official certified bank statement featuring FDIC branding, summary strips, and detailed ledger tables.

---

### 4. Audit Trail & Compliance

1. Navigate to **Audit Trail**.
2. Filter events by category (`ACCOUNT_OPENED`, `PROFILE_UPDATED`, `DEPOSIT`, `WITHDRAWAL`, `TRANSFER`, `ACCOUNT_CLOSED`).
3. Search by Entity ID or Actor.
4. Select any row to open the **Deep State Diff Inspector**, which visually displays the JSON snapshot of changes made during that transaction.

---

### 5. Local AI Assistant

NovaBank features an integrated AI Assistant connected exclusively to a private local LM Studio instance:

- **Connection Status Badge**:
  - Green `● AI Assistant: Connected (Local LM Studio)`
  - Amber `○ AI Assistant: Offline (Local Mode Only)`
- **Target Account Context**: Enter an account number in the top context bar to focus AI insights on a specific customer.
- **Quick Actions**:
  - 📋 **Summarize Statement**: Generates a concise, verified financial narrative of recent statement activity with strict numerical consistency checks.
  - 💸 **Find Large Expenses**: Filters notable debits and withdrawals exceeding $100.
  - 🛡️ **Explain Active Flags**: Analyzes ledger patterns for security flags (large transactions $\ge \$10,000$, rapid consecutive withdrawals, or dormant account reactivations) and produces explainable teller guidance without autonomous freezing.
- **Conversational Search**: Type queries such as *"Show deposits over 5,000 from last month"* to automatically translate natural language into structured ledger filters.

