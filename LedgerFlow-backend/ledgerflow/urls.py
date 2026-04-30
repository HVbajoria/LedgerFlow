from django.contrib import admin
from django.urls import path, include

urlpatterns = [
    path("admin/", admin.site.urls),
    path("api/v1/", include("apps.core.urls")),
    path("api/v1/merchants/", include("apps.merchants.urls")),
    path("api/v1/payouts/", include("apps.payouts.urls")),
    path("api/v1/ledger/", include("apps.ledger.urls")),
]
