"""
PART 2 - Concurrency / race condition tests.

Verifies that select_for_update() prevents two simultaneous payout requests
from both succeeding when only one can be funded.

NOTE: These tests require PostgreSQL for full row-locking behavior.
SQLite does not support concurrent writes from multiple threads (table-level
locking). On SQLite, concurrent requests raise OperationalError which we
treat as a rejection. The core safety assertion - balance never goes
negative - holds on both databases.

Scenario:
  Merchant balance = 10,000 paise
  Two concurrent requests each for 6,000 paise
  Only ONE must succeed. Balance must never go negative.
"""
import uuid
import threading
from django.test import TransactionTestCase
from django.db import OperationalError
from rest_framework.test import APIClient

from apps.ledger.services import get_merchant_balance
from tests.helpers import create_merchant, seed_balance


class ConcurrencyTest(TransactionTestCase):
    """
    TransactionTestCase is required (not TestCase) because:
    - select_for_update() only works across real committed DB transactions
    - TestCase wraps everything in one transaction that never commits,
      making row-level locking invisible to other threads
    """

    def setUp(self):
        self.merchant = create_merchant("Concurrency Merchant")
        seed_balance(self.merchant, 10_000)
        self.url = "/api/v1/payouts/"

    def _post_payout(self, amount: int, results: list, index: int):
        client = APIClient()
        try:
            r = client.post(
                self.url,
                data={
                    "merchant_id": str(self.merchant.id),
                    "amount_paise": amount,
                    "bank_account_id": "BANK-001",
                },
                format="json",
                headers={"Idempotency-Key": str(uuid.uuid4())},
            )
            results[index] = r
        except OperationalError:
            # SQLite concurrent write limitation - treat as rejected request
            results[index] = None

    def test_only_one_of_two_overspending_payouts_succeeds(self):
        """
        Two concurrent requests each for 6,000p against a 10,000p balance.
        At most one must succeed. On PostgreSQL: one 201 + one 400.
        On SQLite: one 201 + one None (lock error treated as rejection).
        """
        results = [None, None]
        t1 = threading.Thread(target=self._post_payout, args=(6_000, results, 0))
        t2 = threading.Thread(target=self._post_payout, args=(6_000, results, 1))
        t1.start(); t2.start()
        t1.join(); t2.join()

        successes = [r for r in results if r is not None and r.status_code == 201]
        self.assertLessEqual(len(successes), 1, "More than one payout succeeded - overspend!")

    def test_balance_never_goes_negative(self):
        """
        Fire 5 concurrent payout requests each for 4,000p against 10,000p.
        At most 2 can succeed. Balance must never go below 0.
        """
        n = 5
        results = [None] * n
        threads = [
            threading.Thread(target=self._post_payout, args=(4_000, results, i))
            for i in range(n)
        ]
        for t in threads: t.start()
        for t in threads: t.join()

        final_balance = get_merchant_balance(self.merchant.id)
        self.assertGreaterEqual(final_balance, 0, "Balance went negative - concurrency bug!")

        successes = [r for r in results if r is not None and r.status_code == 201]
        self.assertLessEqual(len(successes), 2, "Too many payouts succeeded - overspend!")

    def test_debit_entries_never_exceed_funded_payouts(self):
        """
        At most one DEBIT entry can exist for two 6,000p requests against 10,000p.
        Balance must never go negative. On PostgreSQL the DEBIT count matches
        successful responses exactly. On SQLite a lock error may drop the HTTP
        response while the DEBIT was already committed, so we assert the upper
        bound only.
        """
        from apps.ledger.models import LedgerEntry

        results = [None, None]
        t1 = threading.Thread(target=self._post_payout, args=(6_000, results, 0))
        t2 = threading.Thread(target=self._post_payout, args=(6_000, results, 1))
        t1.start(); t2.start()
        t1.join(); t2.join()

        debit_count = LedgerEntry.objects.filter(
            merchant=self.merchant,
            type=LedgerEntry.EntryType.DEBIT,
            reference_type="PAYOUT",
        ).count()

        final_balance = get_merchant_balance(self.merchant.id)
        self.assertGreaterEqual(final_balance, 0, "Balance went negative")
        self.assertLessEqual(debit_count, 1, "More DEBIT entries than possible funded payouts")
