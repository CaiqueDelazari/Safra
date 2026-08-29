from django.urls import path

from apps.conciliacao.views import ConciliacaoView, FluxoView, PendenciasView

urlpatterns = [
    path("", ConciliacaoView.as_view(), name="conciliacao"),
    path("fluxo/", FluxoView.as_view(), name="conciliacao-fluxo"),
    path("pendencias/", PendenciasView.as_view(), name="conciliacao-pendencias"),
]
