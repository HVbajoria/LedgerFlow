# LedgerFlow — Payout Engine

A minimal but production-correct payout engine. Merchants accumulate balance from incoming payments and withdraw to their bank account. Built for the Playto Founding Engineer Challenge.

**Live demo:** _add your deployed URL here_

---

## Stack

| Layer | Tech |
|---|---|
| Backend | Django 4.2, Django REST Framework |
| Database | PostgreSQL (Neon) |
| Background jobs | Celery + Redis (Upstash) |
| Frontend | React 19, Vite, Tailwind CSS 4, Axios |

---

## Local Setup

### Prerequisites

- Python 3.10+
- Node.js 18+
- A PostgreSQL database (free: [neon.tech](https://neon.tech))
- A Redis instance (free: [upstash.com](https://upstash.com))

---

### 1. Backend

```bash
cd LedgerFlow-backend

# Create and activate virtual environment
python -m venv venv
venv\Scripts\activate        # Windows
source venv/bin/activate     # macOS / Linux

# Install dependencies
pip install -r requirements.txt
```

Copy the example env file and fill in your credentials:

```bash
cp .env.example .env
```

`.env` variables you must set:

```env
SECRET_KEY=any-random-string-here
DEBUG=True
ALLOWED_HOSTS=localhost,127.0.0.1

# PostgreSQL — get from neon.tech dashboard
DB_NAME=neondb
DB_USER=neondb_owner
DB_PASSWORD=your-password
DB_HOST=your-host.neon.tech
DB_PORT=5432

# Redis — get from upstash.com dashboard (use rediss:// with ?ssl_cert_reqs=CERT_NONE)
CELERY_BROKER_URL=rediss://default:password@your-host.upstash.io:6379?ssl_cert_reqs=CERT_NONE
CELERY_RESULT_BACKEND=rediss://default:password@your-host.upstash.io:6379?ssl_cert_reqs=CERT_NONE

# CORS
CORS_ALLOWED_ORIGINS=http://localhost:5173
```

Run migrations and seed data:

```bash
python manage.py migrate
python manage.py seed_data
```

The seed script creates 3 merchants and prints their UUIDs and balances:

```
Merchant: Acme Payments Ltd (created)
Merchant: SwiftPay Solutions (created)
Merchant: NovaMerchant Inc (created)

=== Balance Summary ===
Merchant                  Total            Held       Available
------------------------------------------------------------------------
Acme Payments Ltd    Rs.765,000.00   Rs.80,000.00  Rs.685,000.00
...
```

Copy one of the merchant UUIDs — you'll need it for the frontend.

Start the server:

```bash
python manage.py runserver
```

---

### 2. Celery Workers

Open two additional terminals (both inside `LedgerFlow-backend/` with venv activated):

```bash
# Terminal 2 — processes payouts in the background
python -m celery -A ledgerflow worker --loglevel=info --pool=solo

# Terminal 3 — runs periodic retry/cleanup tasks
python -m celery -A ledgerflow beat --loglevel=info
```

The worker must stay running for payouts to be processed.

---

### 3. Frontend

```bash
cd ledgerflow-frontend
npm install
```

Copy the example env file:

```bash
cp .env.example .env
```

Set these values:

```env
VITE_API_BASE_URL=http://localhost:8000
VITE_MERCHANT_ID=paste-merchant-uuid-from-seed_data-output
```

Start the dev server:

```bash
npm run dev
```

Open `http://localhost:5173`

---

## API Reference

All endpoints return JSON. Errors follow `{"error": {"code": "...", "message": "..."}}`.

| Method | Endpoint | Description |
|---|---|---|
| GET | `/api/v1/merchants/{id}/balance/` | Total, held, available balance |
| POST | `/api/v1/payouts/` | Create payout — requires `Idempotency-Key` header |
| GET | `/api/v1/payouts/?merchant_id=` | List payouts for a merchant |
| GET | `/api/v1/ledger/?merchant_id=` | Ledger entries (credits + debits) |
| GET | `/api/v1/health/` | Health check |

**POST /api/v1/payouts/ example:**

```bash
curl -X POST http://localhost:8000/api/v1/payouts/ \
  -H "Content-Type: application/json" \
  -H "Idempotency-Key: $(uuidgen)" \
  -d '{"merchant_id": "<uuid>", "amount_paise": 50000, "bank_account_id": "HDFC-001"}'
```

---

## Tests

```bash
cd LedgerFlow-backend
python manage.py test tests --settings=ledgerflow.settings.test
```

26 tests, runs in ~2 seconds using SQLite in-memory:

- **Concurrency** — two simultaneous 60-rupee requests against a 100-rupee balance; exactly one succeeds
- **Idempotency** — same key returns same response, no duplicate payouts or ledger entries
- **State machine** — all invalid transitions rejected, terminal states are final
- **Refunds** — atomic with status change, never issued twice

---

## Project Structure

```
LedgerFlow-backend/
├── apps/
│   ├── core/          # health check, seed command, base model
│   ├── merchants/     # Merchant model, balance endpoint
│   ├── ledger/        # LedgerEntry model, ledger endpoint
│   └── payouts/       # Payout model, API, Celery tasks, processing logic
├── ledgerflow/        # Django settings, Celery config, URLs
├── tests/             # Concurrency, idempotency, state machine, refund tests
└── EXPLAINER.md       # Technical deep-dive (required reading)

ledgerflow-frontend/
├── src/
│   ├── api/           # Axios client, balance/payouts/ledger API functions
│   ├── components/    # BalanceCard, PayoutForm, PayoutHistory, LedgerTable
│   ├── pages/         # Dashboard
│   └── utils/         # formatPaise currency formatter
```

---

See `EXPLAINER.md` for the technical decisions behind concurrency, idempotency, the state machine, and the AI audit.
