"""
PART 5 — State machine validation tests.

Verifies that invalid payout status transitions are always rejected,
and valid transitions always succeed.
"""
from django.test import TestCase

from apps.payouts.models import Payout
from tests.helpers import create_merchant, seed_balance


def _make_payout(merchant, status=Payout.Status.PENDING) -> Payout:
    p = Payout.objects.create(
        merchant=merchant,
        amount_paise=5_000,
        status=status,
        idempotency_key=f"sm-test-{status}-{id(object())}",
    )
    return p


class StateMachineTest(TestCase):

    def setUp(self):
        self.merchant = create_merchant("State Machine Merchant")
        seed_balance(self.merchant, 50_000)

    #  Valid transitions 

    def test_pending_to_processing(self):
        p = _make_payout(self.merchant, Payout.Status.PENDING)
        p.transition_to(Payout.Status.PROCESSING)
        p.refresh_from_db()
        self.assertEqual(p.status, Payout.Status.PROCESSING)

    def test_processing_to_completed(self):
        p = _make_payout(self.merchant, Payout.Status.PROCESSING)
        p.transition_to(Payout.Status.COMPLETED)
        p.refresh_from_db()
        self.assertEqual(p.status, Payout.Status.COMPLETED)

    def test_processing_to_failed(self):
        p = _make_payout(self.merchant, Payout.Status.PROCESSING)
        p.transition_to(Payout.Status.FAILED)
        p.refresh_from_db()
        self.assertEqual(p.status, Payout.Status.FAILED)

    # Invalid transitions 

    def test_completed_to_pending_rejected(self):
        p = _make_payout(self.merchant, Payout.Status.COMPLETED)
        with self.assertRaises(ValueError):
            p.transition_to(Payout.Status.PENDING)

    def test_completed_to_processing_rejected(self):
        p = _make_payout(self.merchant, Payout.Status.COMPLETED)
        with self.assertRaises(ValueError):
            p.transition_to(Payout.Status.PROCESSING)

    def test_completed_to_failed_rejected(self):
        p = _make_payout(self.merchant, Payout.Status.COMPLETED)
        with self.assertRaises(ValueError):
            p.transition_to(Payout.Status.FAILED)

    def test_failed_to_pending_rejected(self):
        p = _make_payout(self.merchant, Payout.Status.FAILED)
        with self.assertRaises(ValueError):
            p.transition_to(Payout.Status.PENDING)

    def test_failed_to_processing_rejected(self):
        p = _make_payout(self.merchant, Payout.Status.FAILED)
        with self.assertRaises(ValueError):
            p.transition_to(Payout.Status.PROCESSING)

    def test_failed_to_completed_rejected(self):
        p = _make_payout(self.merchant, Payout.Status.FAILED)
        with self.assertRaises(ValueError):
            p.transition_to(Payout.Status.COMPLETED)

    def test_processing_to_pending_rejected(self):
        p = _make_payout(self.merchant, Payout.Status.PROCESSING)
        with self.assertRaises(ValueError):
            p.transition_to(Payout.Status.PENDING)

    def test_pending_to_completed_rejected(self):
        
        p = _make_payout(self.merchant, Payout.Status.PENDING)
        with self.assertRaises(ValueError):
            p.transition_to(Payout.Status.COMPLETED)

    def test_invalid_transition_does_not_persist(self):
        
        p = _make_payout(self.merchant, Payout.Status.COMPLETED)
        try:
            p.transition_to(Payout.Status.PENDING)
        except ValueError:
            pass
        p.refresh_from_db()
        self.assertEqual(p.status, Payout.Status.COMPLETED)
