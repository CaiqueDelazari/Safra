"""Cobrança: a verdade interna sobre o que se espera receber.

Regra 22, escrita em código: a cobrança é a fonte da verdade do *que se
cobra*; o retorno do banco é a fonte da verdade do *que foi pago*. O PDF do
boleto não é fonte de verdade de nada — é apresentação, e por isso mora num
campo que pode ser apagado e regerado sem que ninguém perca dinheiro.

O encontro entre as duas verdades acontece por `nosso_numero`, que é o
identificador que o banco carimba no título e devolve em todo retorno.
"""
from decimal import Decimal

from django.core.validators import MinValueValidator
from django.db import models
from django.db.models.functions import Coalesce
from django.utils import timezone

from core.midia import upload_boleto
from core.models import TenantModel


class StatusCobranca(models.TextChoices):
    """O ciclo de vida de um título, do rascunho ao dinheiro na conta.

    A ordem importa: `RASCUNHO` e `PENDENTE` são internos e ninguém no banco
    sabe que existem; de `ENVIADA_AO_BANCO` em diante existe um título lá fora
    e cada mudança tem custo — instrução de remessa, tarifa, ou as duas.
    """

    RASCUNHO = "RASCUNHO", "Rascunho"
    PENDENTE = "PENDENTE", "Pendente"
    ENVIADA_AO_BANCO = "ENVIADA_AO_BANCO", "Enviada ao banco"
    REGISTRADA = "REGISTRADA", "Registrada"
    DISPONIVEL = "DISPONIVEL", "Disponível"
    PAGA = "PAGA", "Paga"
    VENCIDA = "VENCIDA", "Vencida"
    CANCELADA = "CANCELADA", "Cancelada"
    BAIXADA = "BAIXADA", "Baixada"
    REJEITADA = "REJEITADA", "Rejeitada"
    ERRO = "ERRO", "Erro"


#: Estados a partir dos quais existe título no banco. Editar valor ou
#: vencimento aqui não é edição: é instrução de alteração, e passa pelo
#: serviço, nunca por um PATCH direto.
NO_BANCO = frozenset({
    StatusCobranca.ENVIADA_AO_BANCO,
    StatusCobranca.REGISTRADA,
    StatusCobranca.DISPONIVEL,
    StatusCobranca.VENCIDA,
})

#: Estados finais. Nada mais acontece com o título — nem retorno reabre.
FINAIS = frozenset({
    StatusCobranca.PAGA,
    StatusCobranca.CANCELADA,
    StatusCobranca.BAIXADA,
})

#: O que pode entrar num lote de remessa.
ELEGIVEIS_PARA_LOTE = frozenset({
    StatusCobranca.RASCUNHO,
    StatusCobranca.PENDENTE,
    StatusCobranca.REJEITADA,
    StatusCobranca.ERRO,
})

#: O que conta como "em aberto" no dashboard e na conciliação.
EM_ABERTO = frozenset({
    StatusCobranca.PENDENTE,
    StatusCobranca.ENVIADA_AO_BANCO,
    StatusCobranca.REGISTRADA,
    StatusCobranca.DISPONIVEL,
    StatusCobranca.VENCIDA,
})


class Cobranca(TenantModel):
    numero = models.PositiveIntegerField(
        db_index=True, editable=False,
        help_text="Sequencial por empresa. É o número que o operador diz no telefone.",
    )
    cliente = models.ForeignKey(
        "clientes.Cliente", on_delete=models.PROTECT, related_name="cobrancas"
    )
    conta_bancaria = models.ForeignKey(
        "bancos.ContaBancaria", on_delete=models.PROTECT, related_name="cobrancas",
        null=True, blank=True,
        help_text="Nulo só em rascunho: sem conta não há como registrar.",
    )
    lote = models.ForeignKey(
        "bancos.LoteBancario", on_delete=models.SET_NULL, null=True, blank=True,
        related_name="cobrancas",
    )

    descricao = models.CharField(max_length=180)
    #: Documento que originou a cobrança (nota, contrato, competência). Vai
    #: para o campo "número do documento" do boleto, que é o que o sacado vê.
    documento = models.CharField(max_length=40, blank=True, db_index=True)
    #: "Seu número" no vocabulário do CNAB: o identificador que *nós* damos ao
    #: título e que o banco devolve intacto. Preenchido com o número da
    #: cobrança quando não informado.
    seu_numero = models.CharField(max_length=25, blank=True, db_index=True)
    #: "Nosso número": o identificador que o *banco* usa. Reservado da faixa da
    #: conta no momento em que a cobrança entra num lote, e nunca reutilizado.
    nosso_numero = models.CharField(max_length=20, blank=True, db_index=True)
    #: O que a integração devolveu como id do título (API) — vazio em CNAB.
    identificador_bancario = models.CharField(max_length=120, blank=True, db_index=True)

    valor = models.DecimalField(
        max_digits=14, decimal_places=2, validators=[MinValueValidator(Decimal("0.01"))]
    )
    data_emissao = models.DateField(db_index=True)
    data_vencimento = models.DateField(db_index=True)

    juros_mes_percentual = models.DecimalField(max_digits=6, decimal_places=3, default=0)
    multa_percentual = models.DecimalField(max_digits=6, decimal_places=3, default=0)
    desconto = models.DecimalField(max_digits=14, decimal_places=2, default=0)
    data_limite_desconto = models.DateField(null=True, blank=True)
    abatimento = models.DecimalField(max_digits=14, decimal_places=2, default=0)

    status = models.CharField(
        max_length=20, choices=StatusCobranca.choices,
        default=StatusCobranca.RASCUNHO, db_index=True,
    )

    # ------------------------------------------------- liquidação (do banco)
    # Preenchidos exclusivamente pelo processamento de retorno. Nenhuma tela
    # escreve aqui: dizer "está pago" é prerrogativa do banco.
    data_pagamento = models.DateField(null=True, blank=True, db_index=True)
    data_liquidacao = models.DateField(
        null=True, blank=True, db_index=True,
        help_text="Quando o dinheiro fica disponível. Difere da data de "
                  "pagamento e é a que vale no fluxo de caixa.",
    )
    valor_pago = models.DecimalField(max_digits=14, decimal_places=2, default=0)
    valor_juros_recebido = models.DecimalField(max_digits=14, decimal_places=2, default=0)
    valor_multa_recebida = models.DecimalField(max_digits=14, decimal_places=2, default=0)
    valor_desconto_concedido = models.DecimalField(max_digits=14, decimal_places=2, default=0)
    valor_tarifa = models.DecimalField(max_digits=14, decimal_places=2, default=0)

    # ------------------------------------------------------------- boleto
    linha_digitavel = models.CharField(max_length=60, blank=True)
    codigo_barras = models.CharField(max_length=44, blank=True)
    url_boleto = models.URLField(
        blank=True, help_text="Boleto hospedado pelo banco, quando a API devolve um."
    )
    boleto_pdf = models.FileField(upload_to=upload_boleto, blank=True, null=True)
    boleto_gerado_em = models.DateTimeField(null=True, blank=True)

    enviado_ao_cliente_em = models.DateTimeField(null=True, blank=True)
    observacoes = models.TextField(blank=True)
    mensagem_erro = models.CharField(max_length=500, blank=True)
    #: Chave de deduplicação informada por quem cria em lote. Duas cargas da
    #: mesma planilha não geram duas cobranças para o mesmo cliente/competência.
    chave_externa = models.CharField(max_length=80, blank=True, db_index=True)

    criado_por = models.ForeignKey(
        "accounts.User", on_delete=models.SET_NULL, null=True, blank=True,
        related_name="cobrancas_criadas",
    )

    class Meta:
        db_table = "charges"
        ordering = ("-data_vencimento", "-numero")
        verbose_name = "Cobrança"
        verbose_name_plural = "Cobranças"
        constraints = [
            models.UniqueConstraint(
                fields=["empresa", "numero"], name="uniq_numero_cobranca_por_empresa"
            ),
            # Nosso número é o que o banco usa para achar o título no retorno.
            # Repetido dentro da mesma conta, o pagamento de um cairia no
            # outro — e seria descoberto meses depois, na conciliação.
            models.UniqueConstraint(
                fields=["conta_bancaria", "nosso_numero"],
                condition=~models.Q(nosso_numero=""),
                name="uniq_nosso_numero_por_conta",
            ),
            # Deduplicação da carga em lote, quando quem chama informa a chave.
            models.UniqueConstraint(
                fields=["empresa", "chave_externa"],
                condition=~models.Q(chave_externa=""),
                name="uniq_chave_externa_por_empresa",
            ),
            models.CheckConstraint(
                condition=models.Q(data_vencimento__gte=models.F("data_emissao")),
                name="vencimento_nao_antecede_emissao",
            ),
        ]
        indexes = [
            models.Index(fields=["empresa", "status", "data_vencimento"]),
            models.Index(fields=["empresa", "cliente", "-data_vencimento"]),
            models.Index(fields=["empresa", "conta_bancaria", "status"]),
            models.Index(fields=["empresa", "-data_pagamento"]),
            models.Index(fields=["empresa", "documento"]),
            models.Index(fields=["empresa", "lote"]),
            # A varredura de vencidas roda todo dia sobre a base inteira: sem
            # este índice parcial ela lê a tabela toda para achar um punhado.
            models.Index(
                fields=["data_vencimento"],
                condition=models.Q(status__in=["PENDENTE", "REGISTRADA", "DISPONIVEL",
                                               "ENVIADA_AO_BANCO"]),
                name="idx_cobranca_a_vencer",
            ),
        ]

    def __str__(self) -> str:
        return f"#{self.numero} — {self.descricao} ({self.valor})"

    def save(self, *args, **kwargs):
        if self.numero is None:
            self.numero = self._proximo_numero(self.empresa_id)
        if not self.seu_numero:
            self.seu_numero = str(self.numero)
        super().save(*args, **kwargs)

    @staticmethod
    def _proximo_numero(empresa_id: int) -> int:
        agregado = Cobranca.objects.filter(empresa_id=empresa_id).aggregate(
            ultimo=Coalesce(models.Max("numero"), 0)
        )
        return agregado["ultimo"] + 1

    # ------------------------------------------------------------- estado
    @property
    def esta_no_banco(self) -> bool:
        return self.status in NO_BANCO

    @property
    def esta_finalizada(self) -> bool:
        return self.status in FINAIS

    @property
    def pode_entrar_em_lote(self) -> bool:
        return self.status in ELEGIVEIS_PARA_LOTE

    @property
    def vencida(self) -> bool:
        return (
            self.status in EM_ABERTO
            and self.data_vencimento < timezone.localdate()
        )

    @property
    def dias_em_atraso(self) -> int:
        if not self.vencida:
            return 0
        return (timezone.localdate() - self.data_vencimento).days

    @property
    def valor_liquido(self) -> Decimal:
        """O que o sacado deve hoje, antes de juros e multa."""
        return (self.valor - (self.abatimento or 0)).quantize(Decimal("0.01"))

    @property
    def saldo_em_aberto(self) -> Decimal:
        if self.status == StatusCobranca.PAGA:
            return Decimal("0.00")
        return self.valor_liquido


class ItemCobranca(TenantModel):
    """Composição da cobrança — o que o cliente vê discriminado.

    Existe porque "R$ 1.240,00" numa fatura de serviço não se defende sozinho
    no telefone; "3 × mensalidade + taxa de adesão" se defende. A soma dos
    itens não é imposta como igual ao valor da cobrança de propósito: desconto
    comercial e arredondamento de contrato acontecem, e travar isso obrigaria
    a inventar um item "ajuste" toda vez.
    """

    cobranca = models.ForeignKey(
        Cobranca, on_delete=models.CASCADE, related_name="itens"
    )
    descricao = models.CharField(max_length=180)
    quantidade = models.DecimalField(max_digits=12, decimal_places=3, default=1)
    valor_unitario = models.DecimalField(max_digits=14, decimal_places=2)
    ordem = models.PositiveSmallIntegerField(default=0)

    class Meta:
        db_table = "charge_items"
        ordering = ("cobranca_id", "ordem", "id")
        verbose_name = "Item de cobrança"
        verbose_name_plural = "Itens de cobrança"
        indexes = [models.Index(fields=["cobranca", "ordem"])]

    def __str__(self) -> str:
        return f"{self.descricao} ({self.quantidade} × {self.valor_unitario})"

    @property
    def total(self) -> Decimal:
        return (self.quantidade * self.valor_unitario).quantize(Decimal("0.01"))
