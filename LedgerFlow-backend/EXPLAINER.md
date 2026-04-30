# LedgerFlow – Payout Engine Explainer

This document explains the core architectural decisions behind LedgerFlow, focusing on correctness, concurrency safety, and real-world payment system constraints.

---

## 1. The Ledger

**Balance calculation query:**

```python
from django.db.models import Sum, Case, When, F, BigIntegerField

balance = LedgerEntry.objects.filter(merchant_id=merchant_id).aggregate(
    total=Sum(
        Case(
            When(type="CREDIT", then=F("amount_paise")),
            When(type="DEBIT", then=-F("amount_paise")),
            output_field=BigIntegerField(),
        )
    )
)["total"] or 0
```

**Invariant:**

At all times:

balance = sum(CREDITS) - sum(DEBITS)

**Why this design:**

* The ledger is append-only: every financial event creates a new row
* Credits = incoming funds
* Debits = payouts (or holds)
* Refunds are new CREDIT entries — never mutations

This ensures:

* No balance drift
* Full auditability
* Replayable financial history

There is **no stored balance field**, eliminating inconsistencies between derived and stored values.

---

## 2. The Lock

**Exact code:**

```python
from django.db import transaction

with transaction.atomic():
    merchant = Merchant.objects.select_for_update().get(id=merchant_id)

    available = get_available_balance(merchant.id)

    if available < amount_paise:
        raise InsufficientBalanceError()

    payout = Payout.objects.create(...)
    LedgerEntry.objects.create(
        merchant=merchant,
        type="DEBIT",
        amount_paise=amount_paise,
    )
```

**What it relies on:**

PostgreSQL’s `SELECT ... FOR UPDATE` row-level locking.

**Why this works:**

* The first transaction locks the merchant row
* The second transaction blocks until the first commits
* The second then reads updated balance and fails if insufficient

**Result:**

* No double spending
* No race conditions

Python-level locks were rejected because they don’t work across multiple processes or servers.

---

## 3. The Idempotency

**How the system detects repeated requests:**

A unique constraint exists on:

```python
(merchant, idempotency_key)
```

**Flow:**

```python
existing = Payout.objects.filter(
    merchant_id=merchant_id,
    idempotency_key=idempotency_key,
).first()

if existing:
    return build_response(existing)
```

If not found:

```python
try:
    payout = Payout.objects.create(...)
except IntegrityError:
    payout = Payout.objects.get(
        merchant_id=merchant_id,
        idempotency_key=idempotency_key,
    )
```

**When first request is in-flight:**

* Both requests pass pre-check
* One succeeds
* Second hits DB constraint → fetches existing

**Guarantee:**

* Same key → same payout
* No duplicates
* Safe under retries

The response returned is **identical to the original**, ensuring safe client retries.

---

## 4. The State Machine

**Allowed transitions:**

PENDING → PROCESSING → COMPLETED
→ FAILED

COMPLETED and FAILED are terminal.

**Enforcement:**

```python
VALID_TRANSITIONS = {
    "PENDING": {"PROCESSING"},
    "PROCESSING": {"COMPLETED", "FAILED"},
    "COMPLETED": set(),
    "FAILED": set(),
}

def transition_to(self, new_status):
    if new_status not in VALID_TRANSITIONS[self.status]:
        raise ValueError("Invalid transition")
    self.status = new_status
    self.save()
```

**Where FAILED → COMPLETED is blocked:**

* `VALID_TRANSITIONS["FAILED"] = set()`
* Any transition from FAILED raises error before DB write

**Key guarantee:**

Validation happens **before any state is persisted**, so invalid states never exist in the database.

---

## 5. The AI Audit

**AI-generated bug:**

```python
# WRONG
stuck = Payout.objects.filter(...).select_for_update(skip_locked=True)

with transaction.atomic():
    for payout in stuck:
        ...
```

**Problem:**

* Queryset defined outside transaction
* Lock not guaranteed to be held properly
* Multiple workers can process same payout
* Leads to duplicate refunds

**Fix:**

```python
# CORRECT
with transaction.atomic():
    stuck = Payout.objects.filter(
        status="PROCESSING",
        updated_at__lt=cutoff,
    ).select_for_update(skip_locked=True)

    for payout in stuck:
        ...
```

**Result:**

* Lock acquired inside transaction
* `skip_locked=True` prevents contention
* No duplicate processing

---

## 6. Refund Atomicity

On payout failure:

```python
with transaction.atomic():
    payout.transition_to("FAILED")

    LedgerEntry.objects.create(
        merchant=merchant,
        type="CREDIT",
        amount_paise=payout.amount_paise,
    )
```

**Guarantees:**

* No partial updates
* No lost funds
* Refund happens exactly once

---

## 7. Async Design vs Deployment Reality

**Original design:**

* Celery worker processes payouts asynchronously
* Handles:

  * status transitions
  * retries
  * failure simulation

```python
process_payout.delay(payout.id)
```

**Problem:**

Free-tier platforms (like Render/Railway) do not reliably support background workers.

**Adjustment made:**

```python
process_payout(payout.id)
```

**Why this is acceptable:**

* Business logic unchanged
* Only execution mode changed
* System remains async-ready

**Switching back to async:**

```python
process_payout.delay(payout.id)
```

No refactor required.

---

## 8. System Guarantees

The system enforces:

* No negative balances
* No double spending under concurrency
* No duplicate payouts (idempotency)
* No duplicate refunds
* Ledger is append-only and auditable
* All state transitions are valid

These guarantees hold under concurrent requests and retry scenarios.

---

## Final Note

This system prioritizes **correctness over convenience**.

The hardest problem in payments is not APIs — it is ensuring money remains consistent under concurrency, retries, and failure conditions.

LedgerFlow is designed to solve exactly that.
