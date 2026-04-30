
from django.db.models import Q, Sum, OuterRef, Subquery
from django.db.models.functions import Cast, Coalesce
from django.db.models import CharField, IntegerField

from apps.ledger.models import LedgerEntry
from apps.payouts.models import Payout


def get_merchant_balance(merchant_id) -> int:
    """
    Total balance = SUM(CREDITS) - SUM(DEBITS). Single query.
    """
    result = LedgerEntry.objects.filter(merchant_id=merchant_id).aggregate(
        total_credits=Sum(
            "amount_paise",
            filter=Q(type=LedgerEntry.EntryType.CREDIT),
            default=0,
        ),
        total_debits=Sum(
            "amount_paise",
            filter=Q(type=LedgerEntry.EntryType.DEBIT),
            default=0,
        ),
    )
    return result["total_credits"] - result["total_debits"]


def get_merchant_held_balance(merchant_id) -> int:
    """
    Held balance = DEBIT entries linked to non-terminal payouts. Single query.
    """
    non_terminal = [Payout.Status.PENDING, Payout.Status.PROCESSING]

    pending_ids = (
        Payout.objects.filter(merchant_id=merchant_id, status__in=non_terminal)
        .annotate(id_str=Cast("id", output_field=CharField()))
        .values_list("id_str", flat=True)
    )

    result = LedgerEntry.objects.filter(
        merchant_id=merchant_id,
        type=LedgerEntry.EntryType.DEBIT,
        reference_type="PAYOUT",
        reference_id__in=pending_ids,
    ).aggregate(held=Sum("amount_paise", default=0))

    return result["held"]


def get_all_balances(merchant_id) -> dict:
    """
    Compute total, held, and available balance in TWO queries instead of three.

    Query 1: aggregate all CREDIT and DEBIT entries for the merchant.
    Query 2: aggregate only DEBIT entries linked to non-terminal payouts.

    Returns:
        {
            "total_balance": int,
            "held_balance": int,
            "available_balance": int,
        }
    """

    # Query 1 — total credits and total debits in one aggregation
    totals = LedgerEntry.objects.filter(merchant_id=merchant_id).aggregate(
        total_credits=Sum(
            "amount_paise",
            filter=Q(type=LedgerEntry.EntryType.CREDIT),
            default=0,
        ),
        total_debits=Sum(
            "amount_paise",
            filter=Q(type=LedgerEntry.EntryType.DEBIT),
            default=0,
        ),
    )
    total_balance = totals["total_credits"] - totals["total_debits"]
    

    # Query 2 — held funds (debits for pending/processing payouts)
    non_terminal = [Payout.Status.PENDING, Payout.Status.PROCESSING]
    pending_ids = (
        Payout.objects.filter(merchant_id=merchant_id, status__in=non_terminal)
        .annotate(id_str=Cast("id", output_field=CharField()))
        .values_list("id_str", flat=True)
    )
    held_result = LedgerEntry.objects.filter(
        merchant_id=merchant_id,
        type=LedgerEntry.EntryType.DEBIT,
        reference_type="PAYOUT",
        reference_id__in=pending_ids,
    ).aggregate(held=Sum("amount_paise", default=0))
    held_balance = held_result["held"]

    return {
        "total_balance": total_balance,
        "held_balance": held_balance,
        "available_balance": total_balance - held_balance,
    }


def get_available_balance(merchant_id) -> int:
    """Available balance = total - held."""
    return get_all_balances(merchant_id)["available_balance"]
