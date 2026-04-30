from rest_framework import serializers


class PayoutRequestSerializer(serializers.Serializer):
    merchant_id = serializers.UUIDField()
    amount_paise = serializers.IntegerField(min_value=1)
    bank_account_id = serializers.CharField(max_length=100)


class PayoutResponseSerializer(serializers.Serializer):
    payout_id = serializers.UUIDField()
    status = serializers.CharField()
    amount_paise = serializers.IntegerField()
