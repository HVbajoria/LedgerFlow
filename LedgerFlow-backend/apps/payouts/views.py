import logging
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status
from rest_framework.permissions import AllowAny

from apps.payouts.serializers import PayoutRequestSerializer, PayoutResponseSerializer
from apps.payouts.models import Payout
from apps.payouts.services import (
    create_payout,
    InsufficientBalanceError,
    MerchantNotFoundError,
)

logger = logging.getLogger(__name__)


def _error(message: str, code: str = "error") -> dict:
    return {"error": {"code": code, "message": message}}


class PayoutListCreateView(APIView):
    permission_classes = [AllowAny]

    def get(self, request):
        """List payouts for a merchant. GET /api/v1/payouts/?merchant_id=..."""
        merchant_id = request.query_params.get("merchant_id")
        if not merchant_id:
            return Response(
                _error("merchant_id query parameter is required.", "missing_param"),
                status=status.HTTP_400_BAD_REQUEST,
            )

        payouts = (
            Payout.objects
            .filter(merchant_id=merchant_id)
            .order_by("-created_at")
            .values("id", "amount_paise", "status", "created_at", "attempts")
        )

        results = [
            {
                "payout_id": str(p["id"]),
                "amount_paise": p["amount_paise"],
                "status": p["status"],
                "created_at": p["created_at"],
                "attempts": p["attempts"],
            }
            for p in payouts
        ]
        return Response(results)

    def post(self, request):
        """Create a payout. POST /api/v1/payouts/"""
        idempotency_key = request.headers.get("Idempotency-Key")
        if not idempotency_key:
            return Response(
                _error("Idempotency-Key header is required.", "missing_idempotency_key"),
                status=status.HTTP_400_BAD_REQUEST,
            )

        serializer = PayoutRequestSerializer(data=request.data)
        if not serializer.is_valid():
            return Response(
                {"error": {"code": "validation_error", "details": serializer.errors}},
                status=status.HTTP_400_BAD_REQUEST,
            )

        data = serializer.validated_data

        try:
            result = create_payout(
                merchant_id=data["merchant_id"],
                amount_paise=data["amount_paise"],
                bank_account_id=data["bank_account_id"],
                idempotency_key=idempotency_key,
            )
        except MerchantNotFoundError as e:
            logger.warning("Payout rejected — merchant not found: %s", e)
            return Response(_error(str(e), "merchant_not_found"), status=status.HTTP_404_NOT_FOUND)
        except InsufficientBalanceError as e:
            logger.warning("Payout rejected — insufficient balance: %s", e)
            return Response(_error(str(e), "insufficient_balance"), status=status.HTTP_400_BAD_REQUEST)

        logger.info(
            "Payout accepted: id=%s amount=%sp key=%s",
            result["payout_id"], result["amount_paise"], idempotency_key,
        )
        return Response(PayoutResponseSerializer(result).data, status=status.HTTP_201_CREATED)
