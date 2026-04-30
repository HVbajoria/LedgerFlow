from django.urls import path
from .views import PayoutListCreateView

urlpatterns = [
    path("", PayoutListCreateView.as_view(), name="payout-list-create"),
]
