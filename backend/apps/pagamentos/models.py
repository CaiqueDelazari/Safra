"""Pagamento: dinheiro que entrou, com a prova de onde veio.

Um pagamento nunca é digitado. Ele nasce de uma ocorrência de liquidação num
arquivo de retorno, e a ligação é um-para-um com essa ocorrência. Essa escolha
é o que faz "processar o mesmo arquivo duas vezes não duplica pagamento"
(regra 9) ser uma garantia do banco de dados e não uma promessa do código: a
segunda tentativa esbarra na chave única e o `get_or_create` devolve o
pagamento que já existia.

Baixa manual — o caso raro de quem recebeu por fora e precisa fechar o título
— também passa por aqui, mas com `ocorrencia` nula e `origem=MANUAL`, e com o
usuário registrado. Dinheiro sem rastro não entra.
"""
from decimal import Decimal

from django.db import models

from core.models import TenantModel


class OrigemPagamento(models.TextChoices):
    RETORNO = "RETORNO", "Retorno bancário"
    API = "API", "Consulta à API do banco"
    MANUAL = "MANUAL", "Baixa manual"


class Pagamento(TenantModel):
    cobranca = models.ForeignKey(
        "cobrancas.Cobranca", on_delete=models.PROTECT, related_name="pagamentos"
    )
    #: A ocorrência que originou este pagamento. Única: é a trava de
    #: idempotência do reprocessamento.
    ocorrencia = models.OneToOneField(
        "bancos.OcorrenciaBancaria", on_delete=models.PROTECT,
        null=True, blank=True, related_name="pagamento",
    )
    conta_bancaria = models.ForeignKey(
        "bancos.ContaBancaria", on_delete=models.PROTECT, related_name="pagamentos",
        null=True, blank=True,
    )

    origem = models.CharField(
        max_length=8, choices=OrigemPagamento.choices,
        default=OrigemPagamento.RETORNO, db_index=True,
    )

    data_pagamento = models.DateField(
        db_index=True, help_text="Quando o sacado pagou."
    )
    data_credito = models.DateField(
        null=True, blank=True, db_index=True,
        help_text="Quando o dinheiro fica disponível na conta. É a data do "
                  "fluxo de caixa, e costuma ser um ou dois dias depois.",
    )

    valor = models.DecimalField(
        max_digits=14, decimal_places=2,
        help_text="Valor pago pelo sacado, bruto.",
    )
    juros = models.DecimalField(max_digits=14, decimal_places=2, default=0)
    multa = models.DecimalField(max_digits=14, decimal_places=2, default=0)
    desconto = models.DecimalField(max_digits=14, decimal_places=2, default=0)
    abatimento = models.DecimalField(max_digits=14, decimal_places=2, default=0)
    #: Tarifa cobrada pelo banco por este título. Sai do valor creditado e é o
    #: que explica a diferença entre "o cliente pagou 100" e "entraram 97,50".
    tarifa = models.DecimalField(max_digits=14, decimal_places=2, default=0)

    banco_recebedor = models.CharField(max_length=3, blank=True)
    agencia_recebedora = models.CharField(max_length=8, blank=True)

    observacao = models.CharField(max_length=300, blank=True)
    registrado_por = models.ForeignKey(
        "accounts.User", on_delete=models.SET_NULL, null=True, blank=True,
        related_name="pagamentos_registrados",
        help_text="Preenchido apenas em baixa manual.",
    )
    estornado = models.BooleanField(
        default=False, db_index=True,
        help_text="Pagamento desfeito pelo banco (devolução, cheque sem fundo). "
                  "Nunca se apaga um pagamento — marca-se estornado, e o "
                  "estorno também tem data e motivo.",
    )
    estornado_em = models.DateTimeField(null=True, blank=True)
    motivo_estorno = models.CharField(max_length=300, blank=True)

    class Meta:
        db_table = "payments"
        ordering = ("-data_pagamento", "-id")
        verbose_name = "Pagamento"
        verbose_name_plural = "Pagamentos"
        indexes = [
            models.Index(fields=["empresa", "-data_pagamento"]),
            models.Index(fields=["empresa", "-data_credito"]),
            models.Index(fields=["empresa", "cobranca"]),
            models.Index(fields=["empresa", "origem", "-data_pagamento"]),
            models.Index(fields=["empresa", "estornado", "-data_credito"]),
        ]

    def __str__(self) -> str:
        return f"{self.valor} em {self.data_pagamento:%d/%m/%Y}"

    @property
    def valor_liquido(self) -> Decimal:
        """O que efetivamente entra na conta: o pago menos a tarifa do banco."""
        return (self.valor - (self.tarifa or 0)).quantize(Decimal("0.01"))
