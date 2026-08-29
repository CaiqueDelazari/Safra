"""Filtros da listagem de cobranças.

A tela de cobrança é a mais usada do sistema e a única que precisa de faixa de
data em quatro campos diferentes (emissão, vencimento, pagamento, criação).
Deixar isso em `filterset_fields` daria nomes automáticos ilegíveis na URL;
aqui os nomes são os que o painel usa.
"""
from django_filters import rest_framework as filters

from apps.cobrancas.models import Cobranca, StatusCobranca


class CobrancaFilter(filters.FilterSet):
    status = filters.MultipleChoiceFilter(choices=StatusCobranca.choices)
    cliente = filters.NumberFilter(field_name="cliente_id")
    conta_bancaria = filters.NumberFilter(field_name="conta_bancaria_id")
    lote = filters.NumberFilter(field_name="lote_id")
    banco = filters.CharFilter(field_name="conta_bancaria__banco")

    vencimento_de = filters.DateFilter(field_name="data_vencimento", lookup_expr="gte")
    vencimento_ate = filters.DateFilter(field_name="data_vencimento", lookup_expr="lte")
    emissao_de = filters.DateFilter(field_name="data_emissao", lookup_expr="gte")
    emissao_ate = filters.DateFilter(field_name="data_emissao", lookup_expr="lte")
    pagamento_de = filters.DateFilter(field_name="data_pagamento", lookup_expr="gte")
    pagamento_ate = filters.DateFilter(field_name="data_pagamento", lookup_expr="lte")

    valor_min = filters.NumberFilter(field_name="valor", lookup_expr="gte")
    valor_max = filters.NumberFilter(field_name="valor", lookup_expr="lte")

    vencidas = filters.BooleanFilter(method="filtrar_vencidas")
    sem_lote = filters.BooleanFilter(field_name="lote_id", lookup_expr="isnull")

    class Meta:
        model = Cobranca
        fields = []

    def filtrar_vencidas(self, queryset, nome, valor):
        """'Vencida' é situação *e* data: um título pode estar com status
        REGISTRADA e já ter passado do vencimento, porque a varredura roda uma
        vez por dia. O filtro considera as duas coisas para não mentir na tela
        entre a meia-noite e a execução da rotina."""
        from django.db.models import Q
        from django.utils import timezone

        from apps.cobrancas.models import EM_ABERTO

        condicao = Q(status__in=EM_ABERTO, data_vencimento__lt=timezone.localdate())
        return queryset.filter(condicao) if valor else queryset.exclude(condicao)
