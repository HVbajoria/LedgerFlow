from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework.permissions import AllowAny
from rest_framework import status

from apps.ledger.models import LedgerEntry


class LedgerEntryListView(APIView):
    permission_classes = [AllowAny]

    def get(self, request):
        """
        GET /api/v1/ledger/?merchant_id=...
        Returns recent ledger entries (credits + debits) for a merchant.
        """
        merchant_id = request.query_params.get("merchant_id")
        if not merchant_id:
            return Response(
                {"error": {"code": "missing_param", "message": "merchant_id is required."}},
                status=status.HTTP_400_BAD_REQUEST,
            )

        entries = (
            LedgerEntry.objects
            .filter(merchant_id=merchant_id)
            .order_by("-created_at")
            .values("id", "type", "amount_paise", "reference_type", "reference_id", "created_at")
        )

        return Response([
            {
                "id": str(e["id"]),
                "type": e["type"],
                "amount_paise": e["amount_paise"],
                "reference_type": e["reference_type"],
                "reference_id": e["reference_id"],
                "created_at": e["created_at"],
            }
            for e in entries
        ])
