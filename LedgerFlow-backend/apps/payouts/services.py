"""
Payout service layer.

All payout creation logic lives here:
- idempotency check
- select_for_update row lock on merchant
- balance validation inside atomic transaction
- payout + ledger debit creation
"""

import logging
from django.db import transaction, IntegrityError
from django.db.transaction import on_commit

from apps.merchants.models import Merchant
from apps.ledger.models import LedgerEntry
from apps.ledger.services import get_available_balance
from apps.payouts.models import Payout

logger = logging.getLogger(__name__)


class InsufficientBalanceError(Exception):
    pass


class MerchantNotFoundError(Exception):
    pass


def _build_payout_response(payout: Payout) -> dict:
    return {
        "payout_id": payout.id,
        "status": payout.status,
        "amount_paise": payout.amount_paise,
    }


def create_payout(merchant_id, amount_paise: int, bank_account_id: str, idempotency_key: str) -> dict:
   

    #  Step 1: Fast idempotency check 
    existing = Payout.objects.filter(
        merchant_id=merchant_id,
        idempotency_key=idempotency_key,
    ).first()

    if existing:
        logger.info("Idempotent hit for key=%s merchant=%s", idempotency_key, merchant_id)
        return _build_payout_response(existing)

    #  Step 2: Atomic block — lock → validate → create 
    try:
        with transaction.atomic():
    
            try:
                merchant = Merchant.objects.select_for_update().get(id=merchant_id)
            except Merchant.DoesNotExist:
                raise MerchantNotFoundError(f"Merchant {merchant_id} not found.")

            # Balance check MUST happen inside the lock
            available = get_available_balance(merchant.id)
            if available < amount_paise:
                raise InsufficientBalanceError(
                    f"Insufficient balance. Available: {available}p, Requested: {amount_paise}p"
                )

            # Create the payout record
            payout = Payout.objects.create(
                merchant=merchant,
                amount_paise=amount_paise,
                status=Payout.Status.PENDING,
                idempotency_key=idempotency_key,
                attempts=0,
            )

            # Immediately hold funds via a DEBIT ledger entry
            LedgerEntry.objects.create(
                merchant=merchant,
                type=LedgerEntry.EntryType.DEBIT,
                amount_paise=amount_paise,
                reference_type="PAYOUT",
                reference_id=str(payout.id),
            )

            logger.info(
                "Payout created: id=%s merchant=%s amount=%sp",
                payout.id, merchant_id, amount_paise,
            )

            # Trigger background processing after transaction commits
            payout_id_str = str(payout.id)
            on_commit(lambda: _trigger_processing(payout_id_str))

            return _build_payout_response(payout)

    except IntegrityError:
        
        logger.warning(
            "IntegrityError on idempotency_key=%s — concurrent duplicate, fetching existing.",
            idempotency_key,
        )
        payout = Payout.objects.get(
            merchant_id=merchant_id,
            idempotency_key=idempotency_key,
        )
        return _build_payout_response(payout)


def _trigger_processing(payout_id: str) -> None:
    from apps.payouts.processing import process_payout_logic

    # NOTE:
    # Running synchronously due to deployment constraints (no worker support).
    # Replace with process_payout.delay(payout_id) in production with Celery.
    try:
        final_status = process_payout_logic(payout_id)
        logger.info("process_payout ran synchronously: id=%s status=%s", payout_id, final_status)
    except Exception:
        logger.exception("Synchronous process_payout failed for %s", payout_id)
