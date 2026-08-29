from django.conf import settings
from django.conf.urls.static import static
from django.contrib import admin
from django.urls import include, path
from drf_spectacular.views import SpectacularAPIView, SpectacularSwaggerView

from apps.bancos.urls import urlpatterns_banco, urlpatterns_lotes

# A v1 é montada como uma lista própria. Uma v2 futura é outra lista e outra
# linha em `urlpatterns` — a v1 continua servida sem alteração, que é o
# ponto do versionamento (regra 17).
#
# Os caminhos seguem os nomes fixados no enunciado (/clients, /charges,
# /batches, /payments, /bank/..., /reconciliation). O código é em português e
# a API é em inglês de propósito: quem escreve o sistema fala português com o
# domínio, e quem integra por HTTP encontra os nomes que já esperava.
api_v1 = [
    path("auth/", include("apps.accounts.urls")),
    path("companies/", include("apps.empresas.urls")),
    path("clients/", include("apps.clientes.urls")),
    path("charges/", include("apps.cobrancas.urls")),
    path("batches/", include((urlpatterns_lotes, "batches"))),
    path("payments/", include("apps.pagamentos.urls")),
    path("bank/", include((urlpatterns_banco, "bank"))),
    path("reconciliation/", include("apps.conciliacao.urls")),
    path("reports/", include("apps.relatorios.urls")),
    path("audit/", include("apps.auditoria.urls")),
    path("", include("core.urls")),  # saúde, dashboard, busca, tarefas, mídia
]

urlpatterns = [
    path("api/v1/", include((api_v1, "v1"), namespace="v1")),
    path("api/schema/", SpectacularAPIView.as_view(), name="schema"),
    path("api/docs/", SpectacularSwaggerView.as_view(url_name="schema"), name="docs"),
]

# O admin do Django é manutenção, não operação: só existe quando ligado de
# propósito (ADMIN_ATIVO) e, em produção, num caminho que não seja /admin/.
if settings.ADMIN_ATIVO:
    urlpatterns.insert(0, path(settings.ADMIN_URL, admin.site.urls))

if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
