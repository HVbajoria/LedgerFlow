import uuid
from django.db import models
from apps.core.models import TimeStampedModel


class Merchant(TimeStampedModel):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    name = models.CharField(max_length=255)

    class Meta:
        db_table = "merchants"
        ordering = ["-created_at"]

    def __str__(self):
        return f"{self.name} ({self.id})"
