from django.urls import path
from .views import MerchantBalanceView

urlpatterns = [
    path("<uuid:merchant_id>/balance/", MerchantBalanceView.as_view(), name="merchant-balance"),
]
