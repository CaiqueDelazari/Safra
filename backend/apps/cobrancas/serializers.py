from decimal import Decimal

from rest_framework import serializers

from apps.bancos.models import ContaBancaria
from apps.clientes.models import Cliente
from apps.clientes.serializers import ClienteResumoSerializer
from apps.cobrancas.models import Cobranca, ItemCobranca, StatusCobranca
from core.serializers import TenantModelSerializer


class ItemCobrancaSerializer(serializers.ModelSerializer):
    total = serializers.DecimalField(max_digits=14, decimal_places=2, read_only=True)

    class Meta:
        model = ItemCobranca
        fields = ["id", "descricao", "quantidade", "valor_unitario", "total", "ordem"]


class CobrancaListaSerializer(serializers.ModelSerializer):
    """O que a listagem precisa e nada além.

    Uma tela de 500 cobranças com o cadastro completo do cliente em cada linha
    manda alguns megabytes por página. Aqui vão três campos do cliente, que é
    o que aparece na coluna.
    """

    cliente_nome = serializers.CharField(source="cliente.nome", read_only=True)
    cliente_documento = serializers.CharField(
        source="cliente.documento_formatado", read_only=True
    )
    status_label = serializers.CharField(source="get_status_display", read_only=True)
    conta_nome = serializers.CharField(source="conta_bancaria.nome", read_only=True)
    vencida = serializers.BooleanField(read_only=True)
    dias_em_atraso = serializers.IntegerField(read_only=True)

    class Meta:
        model = Cobranca
        fields = [
            "id", "uuid", "numero", "cliente", "cliente_nome", "cliente_documento",
            "descricao", "documento", "seu_numero", "nosso_numero", "valor",
            "data_emissao", "data_vencimento", "status", "status_label",
            "data_pagamento", "valor_pago", "conta_bancaria", "conta_nome",
            "lote", "vencida", "dias_em_atraso", "linha_digitavel",
            "mensagem_erro", "criado_em",
        ]


class CobrancaSerializer(TenantModelSerializer):
    """Cobrança completa.

    `TenantModelSerializer`, não `ModelSerializer`: `cliente` e
    `conta_bancaria` precisam ser resolvidos dentro da empresa ativa. Ver
    core/serializers.py para o que isso evita.
    """

    itens = ItemCobrancaSerializer(many=True, required=False)
    # Explícito porque o ModelSerializer marcaria estes dois como obrigatórios
    # por causa do `UniqueConstraint(conta_bancaria, nosso_numero)`: o DRF
    # exige todo campo de uma restrição composta, e `nosso_numero` é atribuído
    # pelo sistema, nunca enviado. Rascunho sem conta é caso legítimo.
    conta_bancaria = serializers.PrimaryKeyRelatedField(
        queryset=ContaBancaria.objects.all(), required=False, allow_null=True
    )
    cliente_detalhe = ClienteResumoSerializer(source="cliente", read_only=True)
    status_label = serializers.CharField(source="get_status_display", read_only=True)
    vencida = serializers.BooleanField(read_only=True)
    dias_em_atraso = serializers.IntegerField(read_only=True)
    valor_liquido = serializers.DecimalField(
        max_digits=14, decimal_places=2, read_only=True
    )

    class Meta:
        model = Cobranca
        fields = [
            "id", "uuid", "numero", "cliente", "cliente_detalhe", "conta_bancaria",
            "lote", "descricao", "documento", "seu_numero", "nosso_numero",
            "identificador_bancario", "valor", "valor_liquido", "data_emissao",
            "data_vencimento", "juros_mes_percentual", "multa_percentual",
            "desconto", "data_limite_desconto", "abatimento", "status",
            "status_label", "data_pagamento", "data_liquidacao", "valor_pago",
            "valor_juros_recebido", "valor_multa_recebida",
            "valor_desconto_concedido", "valor_tarifa", "linha_digitavel",
            "codigo_barras", "url_boleto", "enviado_ao_cliente_em", "observacoes",
            "mensagem_erro", "chave_externa", "vencida", "dias_em_atraso",
            "itens", "criado_em", "atualizado_em",
        ]
        # As restrições de unicidade ficam no banco (ver o modelo). Aqui elas
        # são desligadas porque envolvem campos que o sistema preenche
        # (`nosso_numero`, `numero`): o DRF exigiria que o cliente os
        # enviasse. Duplicidade volta como 409 pelo handler de exceções, com
        # mensagem própria.
        validators = []
        read_only_fields = [
            "id", "uuid", "numero", "nosso_numero", "identificador_bancario",
            "lote", "status", "data_pagamento", "data_liquidacao", "valor_pago",
            "valor_juros_recebido", "valor_multa_recebida",
            "valor_desconto_concedido", "valor_tarifa", "linha_digitavel",
            "codigo_barras", "url_boleto", "enviado_ao_cliente_em", "mensagem_erro",
            "criado_em", "atualizado_em",
        ]

    def validate(self, dados):
        emissao = dados.get("data_emissao") or getattr(self.instance, "data_emissao", None)
        vencimento = dados.get("data_vencimento") or getattr(
            self.instance, "data_vencimento", None
        )
        if emissao and vencimento and vencimento < emissao:
            raise serializers.ValidationError(
                {"data_vencimento": "Vencimento não pode ser anterior à emissão."}
            )

        valor = dados.get("valor") or getattr(self.instance, "valor", Decimal("0"))
        abatimento = dados.get("abatimento", getattr(self.instance, "abatimento", 0)) or 0
        desconto = dados.get("desconto", getattr(self.instance, "desconto", 0)) or 0
        if abatimento and abatimento >= valor:
            raise serializers.ValidationError(
                {"abatimento": "Abatimento não pode alcançar o valor do título."}
            )
        if desconto and desconto >= valor:
            raise serializers.ValidationError(
                {"desconto": "Desconto não pode alcançar o valor do título."}
            )

        # Título que já existe no banco não se edita por PATCH: mudar valor ou
        # vencimento de um boleto registrado exige instrução de remessa, e
        # deixar o formulário fazer isso criaria divergência silenciosa entre
        # o que o sistema mostra e o que o sacado tem em mãos.
        if self.instance is not None and self.instance.esta_no_banco:
            travados = {"valor", "data_vencimento", "cliente", "conta_bancaria"}
            mexidos = travados & set(dados)
            if mexidos:
                raise serializers.ValidationError({
                    campo: (
                        "A cobrança já está registrada no banco. Para alterar, "
                        "use a instrução de alteração (cancelar e reemitir, ou "
                        "prorrogar vencimento)."
                    ) for campo in mexidos
                })
        return dados

    def create(self, dados_validados):
        itens = dados_validados.pop("itens", [])
        dados_validados.setdefault("status", StatusCobranca.PENDENTE)
        dados_validados["criado_por"] = self.context["request"].user
        cobranca = super().create(dados_validados)
        self._gravar_itens(cobranca, itens)
        return cobranca

    def update(self, instancia, dados_validados):
        itens = dados_validados.pop("itens", None)
        cobranca = super().update(instancia, dados_validados)
        if itens is not None:
            cobranca.itens.all().delete()
            self._gravar_itens(cobranca, itens)
        return cobranca

    def _gravar_itens(self, cobranca, itens):
        ItemCobranca.objects.bulk_create([
            ItemCobranca(
                empresa_id=cobranca.empresa_id, cobranca=cobranca, ordem=ordem, **item
            )
            for ordem, item in enumerate(itens)
        ])


class LinhaEmLoteSerializer(serializers.Serializer):
    """Uma cobrança dentro da criação em massa.

    Serializer próprio, mais leve que o `CobrancaSerializer`: valida 5 mil
    linhas sem instanciar model nenhum, e é a diferença entre uma requisição
    de dois segundos e uma de dois minutos.
    """

    cliente_id = serializers.IntegerField()
    descricao = serializers.CharField(max_length=180)
    valor = serializers.DecimalField(max_digits=14, decimal_places=2,
                                     min_value=Decimal("0.01"))
    data_vencimento = serializers.DateField()
    data_emissao = serializers.DateField(required=False)
    documento = serializers.CharField(max_length=40, required=False, allow_blank=True)
    seu_numero = serializers.CharField(max_length=25, required=False, allow_blank=True)
    conta_bancaria_id = serializers.IntegerField(required=False, allow_null=True)
    juros_mes_percentual = serializers.DecimalField(
        max_digits=6, decimal_places=3, required=False)
    multa_percentual = serializers.DecimalField(
        max_digits=6, decimal_places=3, required=False)
    desconto = serializers.DecimalField(max_digits=14, decimal_places=2, required=False)
    data_limite_desconto = serializers.DateField(required=False, allow_null=True)
    abatimento = serializers.DecimalField(max_digits=14, decimal_places=2, required=False)
    observacoes = serializers.CharField(required=False, allow_blank=True)
    chave_externa = serializers.CharField(max_length=80, required=False, allow_blank=True)
    itens = ItemCobrancaSerializer(many=True, required=False)


class CriacaoEmLoteSerializer(serializers.Serializer):
    conta_bancaria_id = serializers.IntegerField(required=False, allow_null=True)
    cobrancas = LinhaEmLoteSerializer(many=True)

    def validate_cobrancas(self, linhas):
        if not linhas:
            raise serializers.ValidationError("Envie ao menos uma cobrança.")
        if len(linhas) > 50_000:
            raise serializers.ValidationError(
                "Máximo de 50.000 cobranças por chamada. Divida o envio."
            )
        # Uma consulta para validar todos os clientes, em vez de uma por linha.
        empresa_id = self.context["request"].empresa_id
        ids = {l["cliente_id"] for l in linhas}
        existentes = set(
            Cliente.objects.filter(empresa_id=empresa_id, pk__in=ids)
            .values_list("pk", flat=True)
        )
        faltando = sorted(ids - existentes)
        if faltando:
            raise serializers.ValidationError(
                f"Clientes inexistentes nesta empresa: {faltando[:20]}"
                + (" …" if len(faltando) > 20 else "")
            )
        return linhas


class GerarRecorrenciaSerializer(serializers.Serializer):
    """Mensalidade: uma cobrança por mês, para uma lista de clientes.

    É o caso de uso que gerou o produto — 500 mensalidades no dia 10 de cada
    mês — e merece uma rota própria em vez de obrigar o cliente da API a
    montar 500 linhas iguais.
    """

    clientes = serializers.ListField(child=serializers.IntegerField(), allow_empty=False)
    descricao = serializers.CharField(max_length=180)
    valor = serializers.DecimalField(max_digits=14, decimal_places=2,
                                     min_value=Decimal("0.01"))
    primeiro_vencimento = serializers.DateField()
    parcelas = serializers.IntegerField(min_value=1, max_value=120, default=1)
    dia_vencimento = serializers.IntegerField(
        min_value=1, max_value=31, required=False,
        help_text="Fixa o dia das parcelas seguintes. Ausente, usa o dia do "
                  "primeiro vencimento.",
    )
    conta_bancaria_id = serializers.IntegerField(required=False, allow_null=True)
    prefixo_chave = serializers.CharField(
        max_length=40, required=False, allow_blank=True,
        help_text="Base da chave de deduplicação. Reexecutar a mesma geração "
                  "não cria cobrança repetida.",
    )
