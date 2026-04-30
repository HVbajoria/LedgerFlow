"""
Payout processing service.

Handles the full lifecycle of a payout after creation:
- state transitions (strict, via Payout.transition_to())
- simulated bank outcome
- atomic ledger refund on failure
- retry/timeout logic
"""

import logging
import random
from django.db import transaction
from django.utils import timezone

from apps.ledger.models import LedgerEntry
from apps.payouts.models import Payout

logger = logging.getLogger(__name__)

OUTCOME_SUCCESS = "success"
OUTCOME_FAILURE = "failure"
OUTCOME_PENDING = "pending"   # bank delayed — stay in PROCESSING

MAX_ATTEMPTS = 3
STUCK_THRESHOLD_SECONDS = 30


def _backoff_delay(attempts: int) -> int:
    """Exponential backoff: 30s, 60s, 120s for attempts 1, 2, 3."""
    return STUCK_THRESHOLD_SECONDS * (2 ** (attempts - 1))


def _simulate_bank_outcome() -> str:
    """70% success / 20% failure / 10% delayed."""
    roll = random.random()
    if roll < 0.70:
        return OUTCOME_SUCCESS
    elif roll < 0.90:
        return OUTCOME_FAILURE
    return OUTCOME_PENDING


def _issue_refund(payout: Payout) -> None:
    
    already_refunded = LedgerEntry.objects.filter(
        reference_type="PAYOUT_REFUND",
        reference_id=str(payout.id),
    ).exists()

    if already_refunded:
        logger.warning("Refund already exists for payout %s — skipping.", payout.id)
        return

    LedgerEntry.objects.create(
        merchant=payout.merchant,
        type=LedgerEntry.EntryType.CREDIT,
        amount_paise=payout.amount_paise,
        reference_type="PAYOUT_REFUND",
        reference_id=str(payout.id),
    )
    logger.info("Refund issued for payout %s — %sp returned.", payout.id, payout.amount_paise)


def process_payout_logic(payout_id: str) -> str:
   
    with transaction.atomic():
        # Row lock — prevents two workers processing the same payout concurrently
        try:
            payout = Payout.objects.select_for_update().get(id=payout_id)
        except Payout.DoesNotExist:
            logger.error("Payout %s not found.", payout_id)
            return "NOT_FOUND"


        # Idempotent: terminal state — nothing to do
        if payout.status in (Payout.Status.COMPLETED, Payout.Status.FAILED):
            logger.info(
                "Payout %s already terminal (%s) — skipping.", payout_id, payout.status
            )
            return payout.status


        # PENDING → PROCESSING (validated by transition_to)
        if payout.status == Payout.Status.PENDING:
            payout.transition_to(Payout.Status.PROCESSING)
            payout.attempts += 1
            payout.save(update_fields=["attempts", "updated_at"])
            logger.info("Payout %s → PROCESSING (attempt %s)", payout_id, payout.attempts)


        # Simulate bank API call
        outcome = _simulate_bank_outcome()
        logger.info("Payout %s bank outcome: %s", payout_id, outcome)

        if outcome == OUTCOME_SUCCESS:
       
            payout.transition_to(Payout.Status.COMPLETED)
            logger.info("Payout %s COMPLETED.", payout_id)
            return Payout.Status.COMPLETED

        elif outcome == OUTCOME_FAILURE:
            # transition_to validates PROCESSING → FAILED before writing
            payout.transition_to(Payout.Status.FAILED)
            
            _issue_refund(payout)
            logger.info("Payout %s FAILED — funds refunded.", payout_id)
            return Payout.Status.FAILED

        else:
            # Bank delayed — stay in PROCESSING, beat task will retry
            logger.info("Payout %s still PROCESSING — bank delayed.", payout_id)
            return Payout.Status.PROCESSING


def handle_stuck_payouts() -> None:
    """
    Periodic task: find PROCESSING payouts stuck past their backoff window.
    Backoff: attempt 1 → 30s, attempt 2 → 60s, attempt 3 → 120s.
    After MAX_ATTEMPTS, force FAILED + refund.
    """
    from apps.payouts.tasks import process_payout

    now = timezone.now()

    with transaction.atomic():
        # Fetch all stuck PROCESSING payouts and lock them
        candidates = Payout.objects.filter(
            status=Payout.Status.PROCESSING,
        ).select_for_update(skip_locked=True)

        for payout in candidates:
            threshold = timezone.timedelta(seconds=_backoff_delay(max(payout.attempts, 1)))
            if now - payout.updated_at < threshold:
                continue  # not stuck yet for this attempt

            if payout.attempts < MAX_ATTEMPTS:
                logger.info(
                    "Retrying stuck payout %s (attempt %s/%s, backoff %ss)",
                    payout.id, payout.attempts + 1, MAX_ATTEMPTS,
                    _backoff_delay(payout.attempts + 1),
                )
                payout.attempts += 1
                payout.save(update_fields=["attempts", "updated_at"])
                process_payout.delay(str(payout.id))
            else:
                logger.warning(
                    "Payout %s exceeded max attempts — forcing FAILED + refund.",
                    payout.id,
                )
                payout.transition_to(Payout.Status.FAILED)
                _issue_refund(payout)
