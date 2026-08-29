from django.db.models import Count, Sum
from django_filters import rest_framework as filters
from rest_framework.decorators import action
from rest_framework.response import Response

from apps.pagamentos.models import Pagamento
from apps.pagamentos.serializers import PagamentoSerializer
from core.repositories import TenantRepository
from core.viewsets import TenantViewSet


class PagamentoRepository(TenantRepository[Pagamento]):
    model = Pagamento
    select_related = ("cobranca", "cobranca__cliente", "conta_bancaria")


class PagamentoFilter(filters.FilterSet):
    cliente = filters.NumberFilter(field_name="cobranca__cliente_id")
    conta_bancaria = filters.NumberFilter(field_name="conta_bancaria_id")
    origem = filters.CharFilter(field_name="origem")
    pagamento_de = filters.DateFilter(field_name="data_pagamento", lookup_expr="gte")
    pagamento_ate = filters.DateFilter(field_name="data_pagamento", lookup_expr="lte")
    credito_de = filters.DateFilter(field_name="data_credito", lookup_expr="gte")
    credito_ate = filters.DateFilter(field_name="data_credito", lookup_expr="lte")
    estornado = filters.BooleanFilter(field_name="estornado")

    class Meta:
        model = Pagamento
        fields = []


class PagamentoViewSet(TenantViewSet):
    """Somente leitura, e é uma decisão de projeto.

    Pagamento não se cria pela API nem se edita: ele nasce de uma ocorrência
    de retorno (ou de uma baixa manual feita pela cobrança, que registra quem
    a fez). Abrir POST aqui daria um caminho para dinheiro aparecer no sistema
    sem prova de origem — que é exatamente o que a regra 22 proíbe.
    """

    modulo = "pagamentos"
    repository = PagamentoRepository()
    serializer_class = PagamentoSerializer
    filterset_class = PagamentoFilter
    http_method_names = ["get", "head", "options"]
    search_fields = ["cobranca__cliente__nome", "cobranca__descricao",
                     "cobranca__nosso_numero"]
    ordering_fields = ["data_pagamento", "data_credito", "valor"]
    ordering = ["-data_pagamento"]

    @action(detail=False, methods=["get"], url_path="summary", url_name="summary")
    def resumo(self, request):
        qs = self.filter_queryset(self.get_queryset()).filter(estornado=False)
        totais = qs.aggregate(
            quantidade=Count("id"),
            bruto=Sum("valor"),
            juros=Sum("juros"),
            multa=Sum("multa"),
            desconto=Sum("desconto"),
            tarifa=Sum("tarifa"),
        )
        bruto = totais["bruto"] or 0
        tarifa = totais["tarifa"] or 0
        return Response({
            **{k: (v or 0) for k, v in totais.items()},
            "liquido": bruto - tarifa,
        })
