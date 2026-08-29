from rest_framework import serializers

from apps.clientes.models import Cliente
from core.validadores import documento_valido, so_digitos


class ClienteSerializer(serializers.ModelSerializer):
    documento_formatado = serializers.CharField(read_only=True)
    cep_formatado = serializers.CharField(read_only=True)
    endereco_completo = serializers.CharField(read_only=True)
    pronto_para_boleto = serializers.BooleanField(
        source="endereco_completo_para_boleto", read_only=True
    )
    # Vêm do `annotate` do repositório; não existem quando o serializer é
    # usado fora da listagem, daí o `required=False`.
    cobrancas_abertas = serializers.IntegerField(read_only=True, required=False)
    valor_em_aberto = serializers.DecimalField(
        max_digits=16, decimal_places=2, read_only=True, required=False
    )

    class Meta:
        model = Cliente
        fields = [
            "id", "uuid", "codigo", "nome", "nome_fantasia", "cpf_cnpj",
            "documento_formatado", "email", "email_secundario", "telefone",
            "telefone_secundario", "cep", "cep_formatado", "logradouro", "numero",
            "complemento", "bairro", "cidade", "uf", "observacoes", "status",
            "codigo_externo", "endereco_completo", "pronto_para_boleto",
            "cobrancas_abertas", "valor_em_aberto", "criado_em", "atualizado_em",
        ]
        read_only_fields = ["id", "uuid", "codigo", "criado_em", "atualizado_em"]

    def validate_cpf_cnpj(self, valor):
        digitos = so_digitos(valor)
        if not digitos:
            raise serializers.ValidationError(
                "CPF/CNPJ é obrigatório: sem ele o banco recusa o registro do título."
            )
        if not documento_valido(digitos):
            raise serializers.ValidationError(
                "Documento inválido — os dígitos verificadores não conferem."
            )
        return digitos

    def validate_cep(self, valor):
        return so_digitos(valor)

    def validate_uf(self, valor):
        return (valor or "").upper()


class ClienteResumoSerializer(serializers.ModelSerializer):
    """Versão enxuta para embutir na cobrança — evita mandar o cadastro
    inteiro em cada linha de uma lista de mil cobranças."""

    documento_formatado = serializers.CharField(read_only=True)

    class Meta:
        model = Cliente
        fields = ["id", "codigo", "nome", "cpf_cnpj", "documento_formatado", "email"]
