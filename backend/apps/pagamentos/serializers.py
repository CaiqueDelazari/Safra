from rest_framework import serializers

from apps.pagamentos.models import Pagamento


class PagamentoSerializer(serializers.ModelSerializer):
    cliente_nome = serializers.CharField(source="cobranca.cliente.nome", read_only=True)
    cobranca_numero = serializers.IntegerField(source="cobranca.numero", read_only=True)
    cobranca_descricao = serializers.CharField(source="cobranca.descricao", read_only=True)
    origem_label = serializers.CharField(source="get_origem_display", read_only=True)
    valor_liquido = serializers.DecimalField(max_digits=14, decimal_places=2, read_only=True)
    conta_nome = serializers.CharField(source="conta_bancaria.nome", read_only=True)

    class Meta:
        model = Pagamento
        fields = [
            "id", "uuid", "cobranca", "cobranca_numero", "cobranca_descricao",
            "cliente_nome", "conta_bancaria", "conta_nome", "origem", "origem_label",
            "data_pagamento", "data_credito", "valor", "juros", "multa", "desconto",
            "abatimento", "tarifa", "valor_liquido", "banco_recebedor",
            "agencia_recebedora", "observacao", "estornado", "estornado_em",
            "motivo_estorno", "criado_em",
        ]
        read_only_fields = fields
