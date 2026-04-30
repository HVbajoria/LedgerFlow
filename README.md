# LedgerFlow — Production-Grade Payout Engine

A minimal but production-correct payout engine where merchants accumulate balance from incoming payments and withdraw funds to their bank accounts. Built with correctness-first principles: concurrency safety, idempotency, immutable ledger, and a strict state machine.

---

## Table of Contents

- [High-Level Architecture](#high-level-architecture)
- [Tech Stack](#tech-stack)
- [Project Structure](#project-structure)
- [Core Concepts](#core-concepts)
  - [1. The Append-Only Ledger](#1-the-append-only-ledger)
  - [2. Balance Calculation — No Stored Balance](#2-balance-calculation--no-stored-balance)
  - [3. Payout State Machine](#3-payout-state-machine)
  - [4. Concurrency Control and Row-Level Locking](#4-concurrency-control-and-row-level-locking)
  - [5. Idempotency](#5-idempotency)
  - [6. Payout Processing and Bank Simulation](#6-payout-processing-and-bank-simulation)
  - [7. Refund Atomicity](#7-refund-atomicity)
  - [8. Retry and Stuck Payout Recovery](#8-retry-and-stuck-payout-recovery)
  - [9. Celery Task Architecture](#9-celery-task-architecture)
- [End-to-End Payout Flow](#end-to-end-payout-flow)
- [Frontend Architecture](#frontend-architecture)
- [Data Models](#data-models)
- [API Reference](#api-reference)
- [Testing Strategy](#testing-strategy)
- [Local Setup](#local-setup)
- [System Guarantees](#system-guarantees)

---

## High-Level Architecture

```mermaid
graph TB
    subgraph Frontend["Frontend — React + Vite"]
        UI["Dashboard UI"]
        API_CLIENT["Axios API Client"]
    end

    subgraph Backend["Backend — Django + DRF"]
        VIEWS["REST API Views"]
        SERVICES["Service Layer"]
        MODELS["Django ORM Models"]
    end

    subgraph Workers["Background Processing"]
        CELERY_WORKER["Celery Worker"]
        CELERY_BEAT["Celery Beat Scheduler"]
    end

    subgraph DataStores["Data Stores"]
        PG[("PostgreSQL")]
        REDIS[("Redis")]
    end

    UI --> API_CLIENT
    API_CLIENT -->|"HTTP/JSON"| VIEWS
    VIEWS --> SERVICES
    SERVICES --> MODELS
    MODELS --> PG
    SERVICES -->|"on_commit"| CELERY_WORKER
    CELERY_BEAT -->|"every 30s"| CELERY_WORKER
    CELERY_WORKER --> MODELS
    CELERY_WORKER --> REDIS
    REDIS --> CELERY_WORKER
```

The frontend communicates with the backend exclusively through a RESTful JSON API. The backend is split into a synchronous request-handling layer (Django views and services) and an asynchronous processing layer (Celery workers). PostgreSQL is the single source of truth for all financial data, while Redis serves as the Celery message broker.

---

## Tech Stack

| Layer | Technology | Purpose |
|---|---|---|
| Backend Framework | Django 4.2 + Django REST Framework | API endpoints, ORM, migrations |
| Database | PostgreSQL (Neon) | Persistent storage, row-level locking, ACID transactions |
| Task Queue | Celery 5.6 + Redis (Upstash) | Async payout processing, periodic retries |
| Frontend | React 19 + Vite 8 | Single-page dashboard |
| Styling | Tailwind CSS 4 | Utility-first CSS |
| HTTP Client | Axios | API communication with idempotency headers |

---

## Project Structure

```
LedgerFlow/
├── LedgerFlow-backend/
│   ├── apps/
│   │   ├── core/                  # Health check, base model, seed command
│   │   │   ├── models.py          # TimeStampedModel (abstract base)
│   │   │   ├── views.py           # GET /api/v1/health/
│   │   │   └── management/commands/seed_data.py
│   │   ├── merchants/             # Merchant entity + balance endpoint
│   │   │   ├── models.py          # Merchant (UUID PK, name)
│   │   │   └── views.py           # GET /api/v1/merchants/{id}/balance/
│   │   ├── ledger/                # Immutable financial ledger
│   │   │   ├── models.py          # LedgerEntry (append-only, immutable)
│   │   │   ├── services.py        # Balance computation (total, held, available)
│   │   │   └── views.py           # GET /api/v1/ledger/
│   │   └── payouts/               # Payout lifecycle management
│   │       ├── models.py          # Payout (state machine) + IdempotencyKey
│   │       ├── serializers.py     # Request/response validation
│   │       ├── services.py        # Payout creation (lock, validate, create)
│   │       ├── processing.py      # Bank simulation, refunds, retry logic
│   │       ├── tasks.py           # Celery tasks (process, retry, purge)
│   │       └── views.py           # POST + GET /api/v1/payouts/
│   ├── ledgerflow/                # Django project config
│   │   ├── settings/
│   │   │   ├── base.py            # Shared settings (DB, Celery, CORS, DRF)
│   │   │   ├── development.py     # DEBUG=True, browsable API
│   │   │   └── test.py            # SQLite in-memory, eager Celery
│   │   ├── celery.py              # Celery app initialization
│   │   └── urls.py                # Root URL routing
│   ├── tests/                     # 26 tests across 4 modules
│   │   ├── test_concurrency.py    # Race condition and double-spend prevention
│   │   ├── test_idempotency.py    # Duplicate request handling
│   │   ├── test_state_machine.py  # Valid/invalid transition enforcement
│   │   └── test_refund.py         # Atomic refund correctness
│   └── EXPLAINER.md               # Technical deep-dive document
└── ledgerflow-frontend/
    ├── src/
    │   ├── api/                   # Axios client + endpoint wrappers
    │   │   ├── client.js          # Base Axios instance + idempotency helper
    │   │   ├── balance.js         # getBalance()
    │   │   ├── payouts.js         # getPayouts(), createPayout()
    │   │   └── ledger.js          # getLedgerEntries()
    │   ├── components/
    │   │   ├── BalanceCard.jsx    # Single balance metric display
    │   │   ├── PayoutForm.jsx     # Payout request form with validation
    │   │   ├── PayoutHistory.jsx  # Auto-polling payout table
    │   │   └── LedgerTable.jsx    # Credit/debit entry list
    │   ├── pages/
    │   │   └── Dashboard.jsx      # Main page composing all components
    │   └── utils/
    │       └── currency.js        # formatPaise() — paise to INR string
    ├── package.json
    └── vite.config.js
```

---

## Core Concepts

### 1. The Append-Only Ledger

The ledger is the financial backbone of LedgerFlow. Every money movement — whether an incoming payment, a payout hold, or a refund — is recorded as an immutable row in the `ledger_entries` table. No row is ever updated or deleted.

```mermaid
graph LR
    subgraph Ledger["Append-Only Ledger"]
        direction TB
        E1["CREDIT +₹5,000<br/>ref: PAYMENT TXN-001"]
        E2["CREDIT +₹1,200<br/>ref: PAYMENT TXN-002"]
        E3["DEBIT −₹800<br/>ref: PAYOUT pay-abc"]
        E4["CREDIT +₹800<br/>ref: PAYOUT_REFUND pay-abc"]
    end

    E1 --> E2 --> E3 --> E4
```

**How it works:**

- **CREDIT entries** represent money flowing in (incoming payments, refunds)
- **DEBIT entries** represent money flowing out (payout holds)
- The `LedgerEntry` model overrides both `save()` and `delete()` to enforce immutability:
  - Calling `save()` on an existing entry raises `ValueError`
  - Calling `delete()` always raises `ValueError`
  - `amount_paise` must be a positive integer (validation on creation)

**Why append-only:**

- Eliminates balance drift — the balance is always derivable from the ledger
- Provides a complete, auditable financial history
- Refunds are new CREDIT entries, never mutations of existing rows
- Makes the system replayable — you can reconstruct any point-in-time balance

**Reference tracking:**

Each entry carries a `reference_type` and `reference_id` to trace its origin:

| reference_type | Meaning |
|---|---|
| `PAYMENT` | Incoming merchant payment |
| `PAYOUT` | Funds held for a payout |
| `PAYOUT_REFUND` | Funds returned after a failed payout |
| `SEED` | Initial seed data for development |

---

### 2. Balance Calculation — No Stored Balance

LedgerFlow does **not** store a balance field on the merchant. Instead, balance is computed on-the-fly from the ledger using two efficient SQL queries.

```mermaid
graph TD
    A["All Ledger Entries<br/>for Merchant"] --> B["Query 1: Aggregate"]
    B --> C["total_credits = SUM where type=CREDIT"]
    B --> D["total_debits = SUM where type=DEBIT"]
    C --> E["total_balance = credits − debits"]
    D --> E

    F["Non-Terminal Payouts<br/>PENDING + PROCESSING"] --> G["Query 2: Aggregate"]
    G --> H["held_balance = SUM of DEBIT entries<br/>linked to non-terminal payouts"]

    E --> I["available_balance = total − held"]
    H --> I
```

**Three balance types:**

| Balance | Formula | Meaning |
|---|---|---|
| **Total** | `SUM(CREDITS) - SUM(DEBITS)` | Net funds in the system |
| **Held** | `SUM(DEBITS linked to PENDING/PROCESSING payouts)` | Funds locked by in-flight payouts |
| **Available** | `Total - Held` | Funds the merchant can actually withdraw |

**Why no stored balance:**

A stored balance field creates a second source of truth. If the ledger says one thing and the balance field says another, which is correct? By deriving balance from the ledger every time, there is exactly one source of truth. The tradeoff is a query on every read, but with proper indexes (`idx_ledger_merchant`, `idx_ledger_merchant_created`) this is fast even at scale.

---

### 3. Payout State Machine

Every payout follows a strict, forward-only state machine. The `Payout.transition_to()` method validates transitions **before** any state is persisted to the database, so invalid states can never exist.

```mermaid
stateDiagram-v2
    [*] --> PENDING : Payout created
    PENDING --> PROCESSING : Worker picks up
    PROCESSING --> COMPLETED : Bank confirms success
    PROCESSING --> FAILED : Bank confirms failure / max retries
    COMPLETED --> [*]
    FAILED --> [*]
```

**Transition rules:**

| From | Allowed Targets | Description |
|---|---|---|
| `PENDING` | `PROCESSING` | Worker begins processing |
| `PROCESSING` | `COMPLETED`, `FAILED` | Bank returns final outcome |
| `COMPLETED` | _(none — terminal)_ | Payout settled successfully |
| `FAILED` | _(none — terminal)_ | Payout failed, funds refunded |

**Enforcement mechanism:**

```python
VALID_TRANSITIONS = {
    "PENDING":    {"PROCESSING"},
    "PROCESSING": {"COMPLETED", "FAILED"},
    "COMPLETED":  set(),   # terminal — no outgoing edges
    "FAILED":     set(),   # terminal — no outgoing edges
}

def transition_to(self, new_status):
    allowed = self.VALID_TRANSITIONS.get(self.status, set())
    if new_status not in allowed:
        raise ValueError(f"Invalid transition: {self.status} -> {new_status}")
    self.status = new_status
    self.save(update_fields=["status", "updated_at"])
```

**Key guarantee:** Validation happens before `save()`. If the transition is invalid, a `ValueError` is raised and the database is never touched. This means:
- A `COMPLETED` payout can never go back to `PROCESSING`
- A `FAILED` payout can never be retried
- A `PENDING` payout cannot skip directly to `COMPLETED`

---

### 4. Concurrency Control and Row-Level Locking

The hardest problem in a payout system is preventing double-spending when two requests arrive simultaneously. LedgerFlow solves this with PostgreSQL's `SELECT ... FOR UPDATE` row-level locking.

```mermaid
sequenceDiagram
    participant R1 as Request 1
    participant R2 as Request 2
    participant DB as PostgreSQL

    R1->>DB: BEGIN TRANSACTION
    R1->>DB: SELECT merchant FOR UPDATE (acquires lock)
    R2->>DB: BEGIN TRANSACTION
    R2->>DB: SELECT merchant FOR UPDATE (BLOCKED — waiting)
    R1->>DB: Check balance: 10,000p available
    R1->>DB: Create Payout (6,000p) + DEBIT entry
    R1->>DB: COMMIT (releases lock)
    R2->>DB: Lock acquired
    R2->>DB: Check balance: 4,000p available
    R2->>DB: 4,000p < 6,000p — REJECT
    R2->>DB: ROLLBACK
```

**How it works:**

1. The `create_payout` service wraps everything in `transaction.atomic()`
2. Inside the transaction, `Merchant.objects.select_for_update().get(id=merchant_id)` acquires an exclusive row lock on the merchant
3. The second concurrent request blocks at this line until the first transaction commits
4. After the first commits, the second reads the updated balance and correctly rejects if insufficient

**Why not Python-level locks (threading.Lock, asyncio.Lock)?**

Python locks only work within a single process. In production, you have multiple Django processes (gunicorn workers) and potentially multiple servers. Only database-level locks work across all of them.

**What happens on SQLite (tests)?**

SQLite uses table-level locking, not row-level. Concurrent writes raise `OperationalError`. The test suite handles this gracefully — the core safety assertion (balance never goes negative) holds on both databases.

---

### 5. Idempotency

Network failures, client retries, and user double-clicks can all cause duplicate payout requests. LedgerFlow guarantees that the same `Idempotency-Key` always produces the same result, with no duplicate payouts or ledger entries.

```mermaid
flowchart TD
    A["POST /api/v1/payouts/<br/>Idempotency-Key: abc-123"] --> B{"Payout exists for<br/>merchant + key?"}
    B -->|"Yes"| C["Return existing payout<br/>(same response as original)"]
    B -->|"No"| D["Atomic Transaction"]
    D --> E["Lock merchant row"]
    E --> F["Validate balance"]
    F --> G["Create Payout + DEBIT entry"]
    G --> H{"IntegrityError?"}
    H -->|"No"| I["Return 201 Created"]
    H -->|"Yes — concurrent duplicate"| J["Fetch existing payout"]
    J --> C
```

**Two layers of protection:**

1. **Fast path (pre-check):** Before entering the atomic block, query for an existing payout with the same `(merchant_id, idempotency_key)`. If found, return it immediately.

2. **Slow path (constraint catch):** If two requests pass the pre-check simultaneously, one will succeed at `Payout.objects.create()` and the other will hit the unique constraint `uq_payout_merchant_idempotency_key`, raising an `IntegrityError`. The catch block fetches the already-created payout and returns it.

**Database enforcement:**

```python
class Meta:
    constraints = [
        models.UniqueConstraint(
            fields=["merchant", "idempotency_key"],
            name="uq_payout_merchant_idempotency_key",
        )
    ]
```

**Frontend integration:**

The `PayoutForm` component generates a fresh `uuid` for every form submission using the `uuid` library. This key is sent as the `Idempotency-Key` HTTP header. If the user double-clicks or the network retries, the same key is reused, and the backend returns the same payout.

---

### 6. Payout Processing and Bank Simulation

After a payout is created, it needs to be sent to a bank for settlement. LedgerFlow simulates this with a randomized outcome function that models real-world bank behavior.

```mermaid
flowchart TD
    A["process_payout_logic(payout_id)"] --> B["Lock payout row<br/>SELECT FOR UPDATE"]
    B --> C{"Already terminal?<br/>COMPLETED or FAILED"}
    C -->|"Yes"| D["Skip — idempotent"]
    C -->|"No"| E["Transition PENDING → PROCESSING"]
    E --> F["Increment attempts counter"]
    F --> G["Simulate bank API call"]
    G --> H{"Outcome?"}
    H -->|"70% Success"| I["PROCESSING → COMPLETED"]
    H -->|"20% Failure"| J["PROCESSING → FAILED<br/>+ Issue Refund"]
    H -->|"10% Delayed"| K["Stay PROCESSING<br/>Beat task retries later"]
```

**Bank outcome simulation:**

| Outcome | Probability | Action |
|---|---|---|
| `success` | 70% | Transition to `COMPLETED` |
| `failure` | 20% | Transition to `FAILED` + atomic refund |
| `pending` | 10% | Stay in `PROCESSING` — Celery Beat retries |

**Idempotent processing:**

The processing function is safe to call multiple times. If the payout is already in a terminal state (`COMPLETED` or `FAILED`), it returns immediately without side effects. This is critical for retry safety.

**Row locking during processing:**

```python
payout = Payout.objects.select_for_update().get(id=payout_id)
```

This prevents two Celery workers from processing the same payout simultaneously, which could lead to duplicate refunds or inconsistent state transitions.

---

### 7. Refund Atomicity

When a payout fails, the held funds must be returned to the merchant. This happens atomically — the status change and the refund ledger entry are created in the same database transaction.

```mermaid
flowchart TD
    A["Bank returns FAILURE"] --> B["Inside transaction.atomic()"]
    B --> C["transition_to FAILED"]
    C --> D{"Refund already exists?"}
    D -->|"Yes"| E["Skip — idempotent"]
    D -->|"No"| F["Create CREDIT entry<br/>type=PAYOUT_REFUND<br/>amount=payout.amount_paise"]
    F --> G["Transaction COMMIT"]
    G --> H["Merchant balance restored"]
```

**Guarantees:**

- **Atomic:** If the status change succeeds but the refund entry fails, the entire transaction rolls back. No partial updates.
- **Idempotent:** `_issue_refund()` checks for an existing `PAYOUT_REFUND` entry before creating one. Calling it twice is safe.
- **No lost funds:** The CREDIT entry exactly matches the original DEBIT amount, fully restoring the merchant's balance.

**Refund check:**

```python
def _issue_refund(payout):
    already_refunded = LedgerEntry.objects.filter(
        reference_type="PAYOUT_REFUND",
        reference_id=str(payout.id),
    ).exists()

    if already_refunded:
        return  # no-op

    LedgerEntry.objects.create(
        merchant=payout.merchant,
        type=LedgerEntry.EntryType.CREDIT,
        amount_paise=payout.amount_paise,
        reference_type="PAYOUT_REFUND",
        reference_id=str(payout.id),
    )
```

---

### 8. Retry and Stuck Payout Recovery

Real bank APIs can be slow or unresponsive. LedgerFlow handles this with a periodic sweep task that finds stuck payouts and either retries them or forces them to fail.

```mermaid
flowchart TD
    A["Celery Beat<br/>every 30 seconds"] --> B["retry_stuck_payouts task"]
    B --> C["Find all PROCESSING payouts<br/>SELECT FOR UPDATE SKIP LOCKED"]
    C --> D{"For each payout"}
    D --> E{"Past backoff window?"}
    E -->|"No"| F["Skip — not stuck yet"]
    E -->|"Yes"| G{"attempts < MAX_ATTEMPTS?"}
    G -->|"Yes"| H["Increment attempts<br/>Re-queue for processing"]
    G -->|"No — exceeded 3 attempts"| I["Force FAILED<br/>+ Issue Refund"]
```

**Exponential backoff schedule:**

| Attempt | Backoff Delay | Cumulative Wait |
|---|---|---|
| 1 | 30 seconds | 30s |
| 2 | 60 seconds | 1m 30s |
| 3 | 120 seconds | 3m 30s |
| > 3 | Force FAILED | — |

**Formula:** `delay = 30 * 2^(attempt - 1)` seconds

**`skip_locked=True`:**

The query uses `select_for_update(skip_locked=True)` so that if another worker is already processing a payout, the sweep task skips it instead of blocking. This prevents contention between the periodic sweep and active processing.

---

### 9. Celery Task Architecture

LedgerFlow uses Celery for asynchronous payout processing and periodic maintenance tasks.

```mermaid
graph LR
    subgraph Tasks["Celery Tasks"]
        T1["process_payout<br/>max_retries=3<br/>backoff: 30s, 60s, 120s"]
        T2["retry_stuck_payouts<br/>periodic: every 30s"]
        T3["purge_expired_idempotency_keys<br/>cleanup task"]
    end

    subgraph Triggers["Triggers"]
        TR1["on_commit after<br/>payout creation"]
        TR2["Celery Beat<br/>scheduler"]
    end

    TR1 --> T1
    TR2 --> T2
    TR2 --> T3
    T2 -->|"re-queues stuck payouts"| T1
```

**Task details:**

| Task | Trigger | Purpose |
|---|---|---|
| `process_payout` | `on_commit` after payout creation | Process a single payout through the bank simulation |
| `retry_stuck_payouts` | Celery Beat (every 30s) | Find and retry/fail stuck PROCESSING payouts |
| `purge_expired_idempotency_keys` | Celery Beat | Clean up expired idempotency records (24h TTL) |

**Deployment note:** Currently, payout processing runs synchronously via `on_commit` due to free-tier hosting constraints (no persistent worker). Switching to async requires only changing `process_payout_logic(payout_id)` to `process_payout.delay(payout_id)` — no refactor needed.

---

## End-to-End Payout Flow

This is the complete lifecycle of a payout, from the user clicking "Request Payout" to the funds being settled or refunded.

```mermaid
sequenceDiagram
    actor User
    participant FE as Frontend
    participant API as Django API
    participant SVC as Service Layer
    participant DB as PostgreSQL
    participant WK as Celery Worker

    User->>FE: Enter amount + bank account
    FE->>FE: Generate UUID idempotency key
    FE->>FE: Convert ₹ to paise (× 100)
    FE->>API: POST /api/v1/payouts/<br/>Idempotency-Key: uuid

    API->>API: Validate Idempotency-Key header
    API->>API: Validate request body (serializer)
    API->>SVC: create_payout()

    SVC->>DB: Check existing payout for key (fast path)
    alt Duplicate key found
        DB-->>SVC: Return existing payout
        SVC-->>API: Return cached response
    else New request
        SVC->>DB: BEGIN TRANSACTION
        SVC->>DB: SELECT merchant FOR UPDATE (lock)
        SVC->>DB: Calculate available balance
        alt Insufficient balance
            SVC-->>API: Raise InsufficientBalanceError
            API-->>FE: 400 insufficient_balance
        else Balance OK
            SVC->>DB: INSERT Payout (status=PENDING)
            SVC->>DB: INSERT LedgerEntry (DEBIT)
            SVC->>DB: COMMIT
            SVC->>WK: on_commit → trigger processing
            SVC-->>API: Return payout data
        end
    end

    API-->>FE: 201 Created
    FE-->>User: Show success message

    Note over WK,DB: Background Processing
    WK->>DB: SELECT payout FOR UPDATE
    WK->>WK: PENDING → PROCESSING
    WK->>WK: Simulate bank outcome

    alt Bank: Success (70%)
        WK->>DB: PROCESSING → COMPLETED
    else Bank: Failure (20%)
        WK->>DB: PROCESSING → FAILED
        WK->>DB: INSERT LedgerEntry (CREDIT refund)
    else Bank: Delayed (10%)
        Note over WK: Stay PROCESSING<br/>Beat retries later
    end

    FE->>API: Poll GET /api/v1/payouts/ (every 4s)
    API-->>FE: Updated payout status
    FE-->>User: Status badge updates in real-time
```

---

## Frontend Architecture

The frontend is a single-page React application that provides a merchant dashboard for viewing balances, requesting payouts, and monitoring transaction history.

```mermaid
graph TD
    subgraph App["App.jsx"]
        HEADER["Header — LedgerFlow Dashboard"]
        subgraph Dashboard["Dashboard.jsx"]
            BC["BalanceCard ×3<br/>Total | Held | Available"]
            PF["PayoutForm<br/>Amount + Bank Account"]
            PH["PayoutHistory<br/>Auto-polls every 4s"]
            LT["LedgerTable<br/>Credits and Debits"]
        end
    end

    subgraph API_Layer["API Layer"]
        CLIENT["client.js<br/>Axios instance"]
        BAL_API["balance.js<br/>getBalance()"]
        PAY_API["payouts.js<br/>getPayouts() | createPayout()"]
        LED_API["ledger.js<br/>getLedgerEntries()"]
    end

    subgraph Utils["Utilities"]
        CURR["currency.js<br/>formatPaise()"]
    end

    BC --> BAL_API
    PF --> PAY_API
    PH --> PAY_API
    LT --> LED_API
    BAL_API --> CLIENT
    PAY_API --> CLIENT
    LED_API --> CLIENT
    BC --> CURR
    PH --> CURR
    LT --> CURR
    CLIENT -->|"HTTP"| BACKEND["Django Backend"]
```

### Component Details

**BalanceCard** — Displays a single balance metric (total, held, or available) formatted as INR currency. Uses color-coded accents: default gray for total, amber for held, emerald for available.

**PayoutForm** — A form with amount (in ₹) and bank account ID fields. On submit:
1. Validates that amount > 0 and bank account is not empty
2. Generates a fresh UUID v4 as the idempotency key
3. Converts rupees to paise (`amount × 100`)
4. Sends POST request with `Idempotency-Key` header
5. Shows success/error feedback inline

**PayoutHistory** — Polls `GET /api/v1/payouts/` every 4 seconds and renders a table with payout ID (truncated), amount, status badge, and creation date. Status badges are color-coded:
- `PENDING` — yellow
- `PROCESSING` — blue
- `COMPLETED` — green
- `FAILED` — red

**LedgerTable** — Fetches and displays all ledger entries for the merchant. Each row shows the entry type (CREDIT/DEBIT with color), amount, reference label (Payment, Payout Hold, Payout Refund, Seed Credit), and date.

**API Client** — A configured Axios instance with `baseURL` from `VITE_API_BASE_URL`. The `withIdempotencyKey(key)` helper attaches the `Idempotency-Key` header to payout creation requests.

**Currency Utility** — `formatPaise(paise)` converts an integer paise value to a formatted INR string using `Intl.NumberFormat` (e.g., `100000` → `₹1,000.00`).

---

## Data Models

```mermaid
erDiagram
    MERCHANT {
        uuid id PK
        string name
        datetime created_at
        datetime updated_at
    }

    LEDGER_ENTRY {
        int id PK
        uuid merchant_id FK
        string type "CREDIT | DEBIT"
        bigint amount_paise "always positive"
        string reference_type "PAYMENT | PAYOUT | PAYOUT_REFUND | SEED"
        string reference_id "nullable"
        datetime created_at
    }

    PAYOUT {
        uuid id PK
        uuid merchant_id FK
        bigint amount_paise
        string status "PENDING | PROCESSING | COMPLETED | FAILED"
        string idempotency_key
        int attempts "default 0"
        datetime created_at
        datetime updated_at
    }

    IDEMPOTENCY_KEY {
        int id PK
        uuid merchant_id FK
        string key
        string request_hash "nullable"
        json response_data
        datetime created_at
        datetime expires_at
    }

    MERCHANT ||--o{ LEDGER_ENTRY : "has many"
    MERCHANT ||--o{ PAYOUT : "has many"
    MERCHANT ||--o{ IDEMPOTENCY_KEY : "has many"
    PAYOUT ||--o| LEDGER_ENTRY : "referenced by (DEBIT)"
    PAYOUT ||--o| LEDGER_ENTRY : "referenced by (REFUND CREDIT)"
```

### Model Constraints and Indexes

**Merchant:**
- UUID primary key (auto-generated)
- Inherits `TimeStampedModel` (created_at, updated_at)

**LedgerEntry:**
- **Immutable** — `save()` raises `ValueError` on existing records, `delete()` always raises `ValueError`
- `amount_paise` must be > 0
- Indexes: `idx_ledger_merchant`, `idx_ledger_merchant_created`, `idx_ledger_reference`

**Payout:**
- UUID primary key (auto-generated)
- Unique constraint: `(merchant, idempotency_key)` — prevents duplicate payouts
- Indexes: `idx_payout_merchant_status`, `idx_payout_idempotency_key`
- `on_delete=PROTECT` on merchant FK — cannot delete a merchant with payouts

**IdempotencyKey:**
- Unique constraint: `(merchant, key)`
- Index on `expires_at` for efficient cleanup
- 24-hour TTL, purged by periodic Celery task

---

## API Reference

All endpoints return JSON. Errors follow a consistent structure:

```json
{
  "error": {
    "code": "error_code",
    "message": "Human-readable description"
  }
}
```

### GET /api/v1/health/

Health check endpoint.

**Response 200:**
```json
{
  "status": "ok",
  "service": "LedgerFlow API"
}
```

---

### GET /api/v1/merchants/{merchant_id}/balance/

Returns computed balance for a merchant.

**Response 200:**
```json
{
  "merchant_id": "uuid-string",
  "total_balance": 84500000,
  "held_balance": 8000000,
  "available_balance": 76500000
}
```

**Response 404:**
```json
{
  "error": {
    "code": "merchant_not_found",
    "message": "Merchant <uuid> not found."
  }
}
```

---

### POST /api/v1/payouts/

Create a new payout request. Requires an `Idempotency-Key` header.

**Request Headers:**
```
Content-Type: application/json
Idempotency-Key: <uuid-v4>
```

**Request Body:**
```json
{
  "merchant_id": "uuid-string",
  "amount_paise": 50000,
  "bank_account_id": "HDFC-XXXX-1234"
}
```

**Response 201:**
```json
{
  "payout_id": "uuid-string",
  "status": "PENDING",
  "amount_paise": 50000
}
```

**Error Responses:**

| Status | Code | Cause |
|---|---|---|
| 400 | `missing_idempotency_key` | No `Idempotency-Key` header |
| 400 | `validation_error` | Invalid request body |
| 400 | `insufficient_balance` | Not enough available funds |
| 404 | `merchant_not_found` | Merchant UUID does not exist |

**cURL Example:**
```bash
curl -X POST http://localhost:8000/api/v1/payouts/ \
  -H "Content-Type: application/json" \
  -H "Idempotency-Key: $(uuidgen)" \
  -d '{"merchant_id": "<uuid>", "amount_paise": 50000, "bank_account_id": "HDFC-001"}'
```

---

### GET /api/v1/payouts/?merchant_id={uuid}

List all payouts for a merchant, ordered by most recent first.

**Response 200:**
```json
[
  {
    "payout_id": "uuid-string",
    "amount_paise": 50000,
    "status": "COMPLETED",
    "created_at": "2025-01-15T10:30:00Z",
    "attempts": 1
  }
]
```

---

### GET /api/v1/ledger/?merchant_id={uuid}

List all ledger entries (credits and debits) for a merchant.

**Response 200:**
```json
[
  {
    "id": "1",
    "type": "CREDIT",
    "amount_paise": 50000000,
    "reference_type": "PAYMENT",
    "reference_id": "TXN-001",
    "created_at": "2025-01-15T10:00:00Z"
  }
]
```

---

## Testing Strategy

LedgerFlow has 26 tests across 4 modules, covering the most critical correctness properties of a financial system. Tests run in approximately 2 seconds using SQLite in-memory.

```mermaid
graph TD
    subgraph Tests["Test Suite — 26 Tests"]
        subgraph TC["test_concurrency.py<br/>3 tests"]
            TC1["Two 6,000p requests vs 10,000p balance<br/>only one succeeds"]
            TC2["Five 4,000p requests vs 10,000p balance<br/>at most 2 succeed"]
            TC3["DEBIT entries never exceed<br/>funded payouts"]
        end

        subgraph TI["test_idempotency.py<br/>5 tests"]
            TI1["Same key returns same response"]
            TI2["Same key creates only 1 payout"]
            TI3["Same key creates only 1 DEBIT"]
            TI4["Different keys create separate payouts"]
            TI5["Concurrent same-key handled safely"]
        end

        subgraph TS["test_state_machine.py<br/>12 tests"]
            TS1["3 valid transitions tested"]
            TS2["8 invalid transitions rejected"]
            TS3["Invalid transition does not persist"]
        end

        subgraph TR["test_refund.py<br/>6 tests"]
            TR1["Failed payout creates CREDIT refund"]
            TR2["Balance restored after failure"]
            TR3["Completed payout has no refund"]
            TR4["Refund is idempotent"]
            TR5["Balance never negative after failure"]
            TR6["Payout status is FAILED in DB"]
        end
    end
```

### Concurrency Tests

Uses `TransactionTestCase` (not `TestCase`) because `select_for_update()` requires real committed transactions. Tests spawn multiple threads to simulate concurrent API requests.

**Key scenarios:**
- Two requests each for 6,000p against a 10,000p balance: at most one succeeds
- Five requests each for 4,000p against a 10,000p balance: at most two succeed
- After all concurrent requests, balance is never negative
- Number of DEBIT ledger entries never exceeds the number of funded payouts

### Idempotency Tests

Tests both sequential and concurrent duplicate requests.

**Sequential:** Sending the same idempotency key 5 times creates exactly 1 payout and 1 DEBIT entry. All responses reference the same payout ID.

**Concurrent:** Two threads fire the same key simultaneously. The unique constraint `(merchant, idempotency_key)` ensures only one payout is created. The second request either gets the cached response (fast path) or catches the `IntegrityError` and fetches the existing payout (slow path).

### State Machine Tests

Exhaustively tests every possible transition:
- 3 valid transitions: PENDING to PROCESSING, PROCESSING to COMPLETED, PROCESSING to FAILED
- 8 invalid transitions: all other combinations raise `ValueError`
- Verifies that a rejected transition does not modify the database

### Refund Tests

Uses `unittest.mock.patch` to control the bank simulation outcome.

**Key verifications:**
- A failed payout creates exactly one `PAYOUT_REFUND` CREDIT entry
- The merchant's available balance is fully restored after failure
- A successful payout does NOT create any refund entry
- Calling `_issue_refund()` twice creates only one refund (idempotent)
- Balance never goes negative after any failure scenario

### Running Tests

```bash
cd LedgerFlow-backend
python manage.py test tests --settings=ledgerflow.settings.test
```

The test settings use:
- SQLite in-memory database (fast, isolated, no external dependencies)
- Celery eager mode (tasks run synchronously)
- MD5 password hasher (faster than default for tests)

---

## Local Setup

### Prerequisites

- Python 3.10+
- Node.js 18+
- A PostgreSQL database (free tier: [neon.tech](https://neon.tech))
- A Redis instance (free tier: [upstash.com](https://upstash.com))

### 1. Backend

```bash
cd LedgerFlow-backend

# Create and activate virtual environment
python -m venv venv
source venv/bin/activate     # macOS / Linux
# venv\Scripts\activate      # Windows

# Install dependencies
pip install -r requirements.txt
```

Create a `.env` file:

```env
SECRET_KEY=any-random-string-here
DEBUG=True
ALLOWED_HOSTS=localhost,127.0.0.1

# PostgreSQL (from neon.tech dashboard)
DB_NAME=neondb
DB_USER=neondb_owner
DB_PASSWORD=your-password
DB_HOST=your-host.neon.tech
DB_PORT=5432

# Redis (from upstash.com dashboard)
CELERY_BROKER_URL=rediss://default:password@host.upstash.io:6379?ssl_cert_reqs=CERT_NONE
CELERY_RESULT_BACKEND=rediss://default:password@host.upstash.io:6379?ssl_cert_reqs=CERT_NONE

# CORS
CORS_ALLOWED_ORIGINS=http://localhost:5173
```

Run migrations and seed data:

```bash
python manage.py migrate
python manage.py seed_data
```

The seed script creates 3 merchants with realistic balances:

| Merchant | Total | Held | Available |
|---|---|---|---|
| Acme Payments Ltd | Rs.8,45,000 | Rs.80,000 | Rs.7,65,000 |
| SwiftPay Solutions | Rs.5,70,000 | Rs.50,000 | Rs.5,20,000 |
| NovaMerchant Inc | Rs.50,000 | Rs.0 | Rs.50,000 |

Copy a merchant UUID from the output. You will need it for the frontend.

Start the server:

```bash
python manage.py runserver
```

### 2. Celery Workers (Optional)

Open two additional terminals inside `LedgerFlow-backend/` with the venv activated:

```bash
# Terminal 2: worker that processes payouts
python -m celery -A ledgerflow worker --loglevel=info --pool=solo

# Terminal 3: beat scheduler for periodic retry/cleanup
python -m celery -A ledgerflow beat --loglevel=info
```

> Without Celery running, payouts are processed synchronously within the HTTP request. The system works either way.

### 3. Frontend

```bash
cd ledgerflow-frontend
npm install
```

Create a `.env` file:

```env
VITE_API_BASE_URL=http://localhost:8000
VITE_MERCHANT_ID=paste-merchant-uuid-from-seed-output
```

Start the dev server:

```bash
npm run dev
```

Open `http://localhost:5173`

---

## System Guarantees

LedgerFlow enforces the following invariants under all conditions, including concurrent requests, network retries, and worker failures:

```mermaid
graph TD
    subgraph Guarantees["System Guarantees"]
        G1["No Negative Balances<br/>Balance check inside row lock"]
        G2["No Double Spending<br/>SELECT FOR UPDATE on merchant"]
        G3["No Duplicate Payouts<br/>Unique constraint on idempotency key"]
        G4["No Duplicate Refunds<br/>Existence check before CREDIT"]
        G5["Append-Only Ledger<br/>No updates or deletes allowed"]
        G6["Valid State Transitions Only<br/>Validated before persistence"]
        G7["Atomic Refunds<br/>Status + ledger in one transaction"]
        G8["Retry Safety<br/>Idempotent processing function"]
    end
```

| Guarantee | Mechanism | Tested By |
|---|---|---|
| No negative balances | Balance validated inside `select_for_update` lock | `test_concurrency.py` |
| No double spending | PostgreSQL row-level locking on merchant | `test_concurrency.py` |
| No duplicate payouts | Unique constraint `(merchant, idempotency_key)` | `test_idempotency.py` |
| No duplicate refunds | Existence check in `_issue_refund()` | `test_refund.py` |
| Append-only ledger | `save()` and `delete()` overrides on `LedgerEntry` | Model-level enforcement |
| Valid state transitions | `transition_to()` validates before `save()` | `test_state_machine.py` |
| Atomic refunds | Status change + CREDIT entry in `transaction.atomic()` | `test_refund.py` |
| Retry safety | Terminal state check at start of `process_payout_logic()` | `test_refund.py` |

---

## License

This project was built for the Playto Founding Engineer Challenge.
