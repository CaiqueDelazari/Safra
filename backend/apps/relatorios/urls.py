from django.urls import path

from apps.relatorios.views import (
    RelatorioCobrancasView,
    RelatorioConciliacaoView,
    RelatorioInadimplenciaView,
    RelatorioPagamentosView,
    RelatorioRejeicoesView,
    RelatorioRemessasView,
    RelatorioRetornosView,
)

urlpatterns = [
    path("cobrancas/", RelatorioCobrancasView.as_view(), name="rel-cobrancas"),
    path("pagamentos/", RelatorioPagamentosView.as_view(), name="rel-pagamentos"),
    path("inadimplencia/", RelatorioInadimplenciaView.as_view(), name="rel-inadimplencia"),
    path("remessas/", RelatorioRemessasView.as_view(), name="rel-remessas"),
    path("retornos/", RelatorioRetornosView.as_view(), name="rel-retornos"),
    path("rejeicoes/", RelatorioRejeicoesView.as_view(), name="rel-rejeicoes"),
    path("conciliacao/", RelatorioConciliacaoView.as_view(), name="rel-conciliacao"),
]
