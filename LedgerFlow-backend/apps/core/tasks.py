from celery import shared_task
import logging

logger = logging.getLogger(__name__)


@shared_task
def sample_task(message: str) -> str:
    """Test task to verify Celery is wired up correctly."""
    logger.info("sample_task received: %s", message)
    return f"processed: {message}"
