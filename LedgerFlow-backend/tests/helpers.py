"""
Shared test helpers — merchant + ledger factory functions.
"""
from apps.merchants.models import Merchant
from apps.ledger.models import LedgerEntry


def create_merchant(name="Test Merchant") -> Merchant:
    return Merchant.objects.create(name=name)


def seed_balance(merchant: Merchant, amount_paise: int) -> LedgerEntry:
    """Create a single CREDIT entry to give a merchant a starting balance."""
    return LedgerEntry.objects.create(
        merchant=merchant,
        type=LedgerEntry.EntryType.CREDIT,
        amount_paise=amount_paise,
        reference_type="SEED",
        reference_id="test-seed",
    )
