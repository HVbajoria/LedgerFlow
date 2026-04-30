import uuid
from django.db import models
from apps.core.models import TimeStampedModel


class Payout(TimeStampedModel):
   

    class Status(models.TextChoices):
        PENDING = "PENDING", "Pending"
        PROCESSING = "PROCESSING", "Processing"
        COMPLETED = "COMPLETED", "Completed"
        FAILED = "FAILED", "Failed"

    # Valid forward-only transitions
    VALID_TRANSITIONS = {
        Status.PENDING: {Status.PROCESSING},
        Status.PROCESSING: {Status.COMPLETED, Status.FAILED},
        Status.COMPLETED: set(),
        Status.FAILED: set(),
    }

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    merchant = models.ForeignKey(
        "merchants.Merchant",
        on_delete=models.PROTECT,
        related_name="payouts",
    )
    amount_paise = models.BigIntegerField()
    status = models.CharField(
        max_length=10,
        choices=Status.choices,
        default=Status.PENDING,
        db_index=True,
    )
    idempotency_key = models.CharField(max_length=255)
    attempts = models.PositiveIntegerField(default=0)

    class Meta:
        db_table = "payouts"
        ordering = ["-created_at"]
        constraints = [
            models.UniqueConstraint(
                fields=["merchant", "idempotency_key"],
                name="uq_payout_merchant_idempotency_key",
            )
        ]
        indexes = [
            models.Index(fields=["merchant", "status"], name="idx_payout_merchant_status"),
            models.Index(fields=["idempotency_key"], name="idx_payout_idempotency_key"),
        ]

    def __str__(self):
        return f"Payout {self.id} [{self.status}] {self.amount_paise}p"

    def transition_to(self, new_status: str):
        """Enforce state machine transitions. Raises ValueError on invalid move."""
        allowed = self.VALID_TRANSITIONS.get(self.status, set())
        if new_status not in allowed:
            raise ValueError(
                f"Invalid transition: {self.status} → {new_status}. "
                f"Allowed: {allowed or 'none (terminal state)'}"
            )
        self.status = new_status
        self.save(update_fields=["status", "updated_at"])


class IdempotencyKey(models.Model):
    """
    Stores idempotency records scoped per merchant.
    Same key returns the same response within TTL (24h).
    """

    merchant = models.ForeignKey(
        "merchants.Merchant",
        on_delete=models.CASCADE,
        related_name="idempotency_keys",
    )
    key = models.CharField(max_length=255)
    request_hash = models.CharField(max_length=64, null=True, blank=True)
    response_data = models.JSONField(default=dict)
    created_at = models.DateTimeField(auto_now_add=True)
    expires_at = models.DateTimeField()

    class Meta:
        db_table = "idempotency_keys"
        constraints = [
            models.UniqueConstraint(
                fields=["merchant", "key"],
                name="uq_idempotency_merchant_key",
            )
        ]
        indexes = [
            models.Index(fields=["merchant", "key"], name="idx_idempotency_merchant_key"),
            models.Index(fields=["expires_at"], name="idx_idempotency_expires_at"),
        ]

    def __str__(self):
        return f"IdempotencyKey {self.key} (merchant={self.merchant_id})"
