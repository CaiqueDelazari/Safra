"""Rotas do módulo bancário.

Dois roteadores, e a divisão segue os caminhos que o enunciado fixou (regra
17): `/batches/` fica na raiz da API porque lote é um recurso de primeira
classe do produto, e o resto vive sob `/bank/`, que é o guarda-chuva da
integração — conta, arquivo e ocorrência só fazem sentido com um banco atrás.
"""
from rest_framework.routers import DefaultRouter

from apps.bancos.views import (
    ArquivoBancarioViewSet,
    ContaBancariaViewSet,
    LoteViewSet,
    OcorrenciaViewSet,
)

# /api/v1/batches/
lotes = DefaultRouter()
lotes.register("", LoteViewSet, basename="batch")

# /api/v1/bank/...
banco = DefaultRouter()
banco.register("accounts", ContaBancariaViewSet, basename="bank-account")
banco.register("files", ArquivoBancarioViewSet, basename="bank-file")
banco.register("occurrences", OcorrenciaViewSet, basename="bank-occurrence")

urlpatterns_lotes = lotes.urls
urlpatterns_banco = banco.urls
