"""
Celery tasks for payout processing.
"""

import logging
from celery import shared_task
from django.utils import timezone

from apps.payouts.processing import process_payout_logic, handle_stuck_payouts

logger = logging.getLogger(__name__)


@shared_task(bind=True, max_retries=3, default_retry_delay=30)
def process_payout(self, payout_id: str):
    try:
        final_status = process_payout_logic(payout_id)
        logger.info("process_payout task done: id=%s status=%s", payout_id, final_status)
        return final_status
    except Exception as exc:
        logger.exception("process_payout task failed for %s", payout_id)
        # Exponential backoff: 30s, 60s, 120s
        raise self.retry(exc=exc, countdown=30 * (2 ** self.request.retries))


@shared_task
def retry_stuck_payouts():
    logger.info("retry_stuck_payouts: starting sweep at %s", timezone.now())
    handle_stuck_payouts()
    logger.info("retry_stuck_payouts: sweep complete.")


@shared_task
def purge_expired_idempotency_keys():
    from apps.payouts.models import IdempotencyKey

    cutoff = timezone.now()
    deleted, _ = IdempotencyKey.objects.filter(expires_at__lt=cutoff).delete()
    logger.info("purge_expired_idempotency_keys: deleted %d expired keys.", deleted)
