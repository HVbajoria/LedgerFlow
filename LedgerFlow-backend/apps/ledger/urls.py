from django.urls import path
from .views import LedgerEntryListView

urlpatterns = [
    path("", LedgerEntryListView.as_view(), name="ledger-list"),
]
