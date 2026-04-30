from django.db import models
from apps.core.models import TimeStampedModel


class LedgerEntry(models.Model):
    
    class EntryType(models.TextChoices):
        CREDIT = "CREDIT", "Credit"
        DEBIT = "DEBIT", "Debit"

    merchant = models.ForeignKey(
        "merchants.Merchant",
        on_delete=models.PROTECT,
        related_name="ledger_entries",
    )
    type = models.CharField(max_length=6, choices=EntryType.choices)
    amount_paise = models.BigIntegerField()  # always positive
    reference_type = models.CharField(max_length=50)  # e.g. 'PAYOUT', 'SEED'
    reference_id = models.CharField(max_length=100, null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "ledger_entries"
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["merchant"], name="idx_ledger_merchant"),
            models.Index(fields=["merchant", "created_at"], name="idx_ledger_merchant_created"),
            models.Index(fields=["reference_type", "reference_id"], name="idx_ledger_reference"),
        ]

    def __str__(self):
        return f"{self.type} {self.amount_paise}p — {self.merchant_id}"

    def save(self, *args, **kwargs):
        
        if self.pk:
            raise ValueError("LedgerEntry is immutable and cannot be modified after creation.")
        if self.amount_paise <= 0:
            raise ValueError("amount_paise must be a positive integer.")
        super().save(*args, **kwargs)

    def delete(self, *args, **kwargs):
        raise ValueError("LedgerEntry is immutable and cannot be deleted.")
