from django.core.management.base import BaseCommand
from django.db import transaction

from apps.merchants.models import Merchant
from apps.ledger.models import LedgerEntry
from apps.payouts.models import Payout
from apps.ledger.services import (
    get_merchant_balance,
    get_merchant_held_balance,
    get_available_balance,
)


SEED_MERCHANTS = [
    {
        "name": "Acme Payments Ltd",
        "credits": [
            {"amount_paise": 500_000_00, "ref": "TXN-001"},  # ₹5,00,000
            {"amount_paise": 120_000_00, "ref": "TXN-002"},  # ₹1,20,000
            {"amount_paise": 75_000_00,  "ref": "TXN-003"},  # ₹75,000
            {"amount_paise": 200_000_00, "ref": "TXN-004"},  # ₹2,00,000
            {"amount_paise": 50_000_00,  "ref": "TXN-005"},  # ₹50,000
        ],
        "debits": [
            {"amount_paise": 100_000_00, "ref": "PAY-001", "status": Payout.Status.COMPLETED},
        ],
        "pending_payouts": [
            {"amount_paise": 80_000_00, "ref": "PAY-002", "status": Payout.Status.PROCESSING},
        ],
    },
    {
        "name": "SwiftPay Solutions",
        "credits": [
            {"amount_paise": 300_000_00, "ref": "TXN-101"},  # ₹3,00,000
            {"amount_paise": 180_000_00, "ref": "TXN-102"},  # ₹1,80,000
            {"amount_paise": 90_000_00,  "ref": "TXN-103"},  # ₹90,000
        ],
        "debits": [],
        "pending_payouts": [
            {"amount_paise": 50_000_00, "ref": "PAY-101", "status": Payout.Status.PENDING},
        ],
    },
    {
        "name": "NovaMerchant Inc",
        "credits": [
            {"amount_paise": 25_000_00,  "ref": "TXN-201"},  # ₹25,000
            {"amount_paise": 40_000_00,  "ref": "TXN-202"},  # ₹40,000
        ],
        "debits": [
            {"amount_paise": 10_000_00, "ref": "PAY-201", "status": Payout.Status.COMPLETED},
            {"amount_paise": 5_000_00,  "ref": "PAY-202", "status": Payout.Status.COMPLETED},
        ],
        "pending_payouts": [],
    },
]


class Command(BaseCommand):
    help = "Seed realistic merchant and ledger data for development/testing."

    @transaction.atomic
    def handle(self, *args, **kwargs):
        self.stdout.write(self.style.MIGRATE_HEADING("\n=== LedgerFlow Seed Data ===\n"))

        for data in SEED_MERCHANTS:
            merchant, created = Merchant.objects.get_or_create(name=data["name"])
            status = "created" if created else "already exists"
            self.stdout.write(f"Merchant: {merchant.name} ({status})")

            if not created:
                self.stdout.write(self.style.WARNING("  → Skipping entries (already seeded)\n"))
                continue


            # CREDIT entries — incoming payments
            for credit in data["credits"]:
                LedgerEntry.objects.create(
                    merchant=merchant,
                    type=LedgerEntry.EntryType.CREDIT,
                    amount_paise=credit["amount_paise"],
                    reference_type="PAYMENT",
                    reference_id=credit["ref"],
                )


            # Completed DEBIT entries — past settled payouts
            for debit in data["debits"]:
                payout = Payout.objects.create(
                    merchant=merchant,
                    amount_paise=debit["amount_paise"],
                    status=debit["status"],
                    idempotency_key=f"seed-{debit['ref']}",
                )
                LedgerEntry.objects.create(
                    merchant=merchant,
                    type=LedgerEntry.EntryType.DEBIT,
                    amount_paise=debit["amount_paise"],
                    reference_type="PAYOUT",
                    reference_id=str(payout.id),
                )


            # Pending/processing payouts — funds are held
            for pending in data["pending_payouts"]:
                payout = Payout.objects.create(
                    merchant=merchant,
                    amount_paise=pending["amount_paise"],
                    status=pending["status"],
                    idempotency_key=f"seed-{pending['ref']}",
                )
                LedgerEntry.objects.create(
                    merchant=merchant,
                    type=LedgerEntry.EntryType.DEBIT,
                    amount_paise=pending["amount_paise"],
                    reference_type="PAYOUT",
                    reference_id=str(payout.id),
                )

            self.stdout.write(self.style.SUCCESS("  → Entries created"))
            

        # Print balance summary for all seeded merchants
        self.stdout.write(self.style.MIGRATE_HEADING("\n=== Balance Summary ===\n"))
        self.stdout.write(f"{'Merchant':<25} {'Total':>15} {'Held':>15} {'Available':>15}")
        self.stdout.write("-" * 72)

        def fmt(paise: int) -> str:
            return f"Rs.{paise / 100:,.2f}"

        for data in SEED_MERCHANTS:
            merchant = Merchant.objects.get(name=data["name"])
            total     = get_merchant_balance(merchant.id)
            held      = get_merchant_held_balance(merchant.id)
            available = get_available_balance(merchant.id)

            self.stdout.write(
                f"{merchant.name:<25} {fmt(total):>15} {fmt(held):>15} {fmt(available):>15}"
            )

        self.stdout.write("")
