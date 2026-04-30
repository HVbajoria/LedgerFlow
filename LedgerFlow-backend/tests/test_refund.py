"""
PART 6 — Refund correctness tests.

Verifies:
- A failed payout atomically creates a CREDIT refund entry
- Balance is fully restored after failure
- Refund is never issued twice (idempotent)
- A completed payout does NOT trigger a refund
"""
from unittest.mock import patch
from django.test import TestCase

from apps.payouts.models import Payout
from apps.payouts.processing import process_payout_logic, _issue_refund
from apps.ledger.models import LedgerEntry
from apps.ledger.services import get_merchant_balance, get_available_balance
from tests.helpers import create_merchant, seed_balance


def _create_payout_with_debit(merchant, amount_paise=10_000) -> Payout:
    
    payout = Payout.objects.create(
        merchant=merchant,
        amount_paise=amount_paise,
        status=Payout.Status.PENDING,
        idempotency_key=f"refund-test-{id(object())}",
    )
    LedgerEntry.objects.create(
        merchant=merchant,
        type=LedgerEntry.EntryType.DEBIT,
        amount_paise=amount_paise,
        reference_type="PAYOUT",
        reference_id=str(payout.id),
    )
    return payout


class RefundCorrectnessTest(TestCase):

    def setUp(self):
        self.merchant = create_merchant("Refund Merchant")
        seed_balance(self.merchant, 50_000)

    def test_failed_payout_creates_refund_entry(self):
        
        payout = _create_payout_with_debit(self.merchant, 10_000)

        with patch("apps.payouts.processing._simulate_bank_outcome", return_value="failure"):
            final_status = process_payout_logic(str(payout.id))

        self.assertEqual(final_status, Payout.Status.FAILED)

        refund = LedgerEntry.objects.filter(
            merchant=self.merchant,
            type=LedgerEntry.EntryType.CREDIT,
            reference_type="PAYOUT_REFUND",
            reference_id=str(payout.id),
        )
        self.assertEqual(refund.count(), 1)
        self.assertEqual(refund.first().amount_paise, 10_000)

    def test_balance_restored_after_failure(self):
        """After a failed payout, available balance must return to its original value."""
        balance_before = get_available_balance(self.merchant.id)
        payout = _create_payout_with_debit(self.merchant, 10_000)

        with patch("apps.payouts.processing._simulate_bank_outcome", return_value="failure"):
            process_payout_logic(str(payout.id))

        balance_after = get_available_balance(self.merchant.id)
        self.assertEqual(balance_before, balance_after)

    def test_completed_payout_does_not_create_refund(self):
        """A successful payout must NOT generate any refund entry."""
        payout = _create_payout_with_debit(self.merchant, 10_000)

        with patch("apps.payouts.processing._simulate_bank_outcome", return_value="success"):
            process_payout_logic(str(payout.id))

        refund_count = LedgerEntry.objects.filter(
            reference_type="PAYOUT_REFUND",
            reference_id=str(payout.id),
        ).count()
        self.assertEqual(refund_count, 0)

    def test_refund_is_idempotent(self):
        """Calling _issue_refund twice must only create one CREDIT entry."""
        payout = _create_payout_with_debit(self.merchant, 10_000)
        payout.status = Payout.Status.FAILED
        payout.save(update_fields=["status", "updated_at"])

        _issue_refund(payout)
        _issue_refund(payout)  # second call must be a no-op

        refund_count = LedgerEntry.objects.filter(
            reference_type="PAYOUT_REFUND",
            reference_id=str(payout.id),
        ).count()
        self.assertEqual(refund_count, 1)

    def test_balance_never_negative_after_failure(self):
        """Total ledger balance must never go below zero after a failed payout."""
        payout = _create_payout_with_debit(self.merchant, 50_000)

        with patch("apps.payouts.processing._simulate_bank_outcome", return_value="failure"):
            process_payout_logic(str(payout.id))

        self.assertGreaterEqual(get_merchant_balance(self.merchant.id), 0)

    def test_payout_status_is_failed_after_failure(self):
        """Payout record must reflect FAILED status in the DB."""
        payout = _create_payout_with_debit(self.merchant, 10_000)

        with patch("apps.payouts.processing._simulate_bank_outcome", return_value="failure"):
            process_payout_logic(str(payout.id))

        payout.refresh_from_db()
        self.assertEqual(payout.status, Payout.Status.FAILED)
