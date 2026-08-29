"""Empresa — o tenant, e o beneficiário impresso no boleto.

Um CNPJ = uma empresa = um conjunto isolado de dados. Nenhum modelo do domínio
existe sem apontar para uma linha desta tabela, e nenhuma consulta escapa do
filtro (`core/repositories.py`). Isolamento por `empresa_id` é a decisão
central da regra 3 — um schema por cliente daria isolamento mais forte e um
custo operacional que uma plataforma com milhares de empresas não paga:
migração vira mil migrações, e `pg_dump` vira mil dumps.

Além de tenant, a empresa é o **cedente**: razão social, CNPJ e endereço daqui
saem impressos no boleto e transmitidos no registro do título. Um endereço
incompleto aqui rejeita a remessa inteira, não um título só.
"""
from django.core.validators import RegexValidator
from django.db import models

from core.midia import upload_logo_empresa
from core.models import TimeStampedModel
from core.validadores import cnpj_valido, formatar_documento, validar_imagem

apenas_digitos = RegexValidator(r"^\d+$", "Informe apenas números.")


class PlanoEmpresa(models.TextChoices):
    """O que a empresa contratou. Governa limite, não funcionalidade: cortar
    função por plano espalharia `if plano ==` pelo domínio inteiro. Limite
    é uma pergunta só, feita num lugar só (`dentro_do_limite`)."""

    TESTE = "TESTE", "Avaliação"
    ESSENCIAL = "ESSENCIAL", "Essencial"
    PROFISSIONAL = "PROFISSIONAL", "Profissional"
    ILIMITADO = "ILIMITADO", "Ilimitado"


#: Teto de títulos registrados por mês em cada plano. `None` = sem teto.
LIMITE_TITULOS_MES = {
    PlanoEmpresa.TESTE: 50,
    PlanoEmpresa.ESSENCIAL: 1000,
    PlanoEmpresa.PROFISSIONAL: 10000,
    PlanoEmpresa.ILIMITADO: None,
}


class Empresa(TimeStampedModel):
    cnpj = models.CharField(
        max_length=14, unique=True, validators=[apenas_digitos], db_index=True
    )
    razao_social = models.CharField(max_length=180)
    nome_fantasia = models.CharField(max_length=120, db_index=True)
    inscricao_estadual = models.CharField(max_length=30, blank=True)
    inscricao_municipal = models.CharField(max_length=30, blank=True)
    logo = models.ImageField(
        upload_to=upload_logo_empresa, blank=True, null=True, validators=[validar_imagem]
    )

    cep = models.CharField(max_length=8, blank=True)
    logradouro = models.CharField(max_length=180, blank=True)
    numero = models.CharField(max_length=20, blank=True)
    complemento = models.CharField(max_length=120, blank=True)
    bairro = models.CharField(max_length=120, blank=True)
    cidade = models.CharField(max_length=120, blank=True)
    uf = models.CharField(max_length=2, blank=True)

    telefone = models.CharField(max_length=20, blank=True)
    email = models.EmailField(blank=True)
    email_cobranca = models.EmailField(
        blank=True,
        help_text="Remetente e caixa de resposta dos boletos enviados ao sacado.",
    )

    plano = models.CharField(
        max_length=14, choices=PlanoEmpresa.choices,
        default=PlanoEmpresa.TESTE, db_index=True,
    )
    cor_primaria = models.CharField(max_length=7, default="#1F4E79")
    configuracoes = models.JSONField(default=dict, blank=True)
    ativa = models.BooleanField(default=True, db_index=True)
    #: Empresa suspensa continua enxergando o histórico e não perde dado, mas
    #: para de registrar título novo. Inadimplência do cliente da plataforma
    #: não pode virar inadimplência da carteira dele.
    suspensa_em = models.DateTimeField(null=True, blank=True)
    motivo_suspensao = models.CharField(max_length=300, blank=True)

    class Meta:
        db_table = "tenants"
        ordering = ("nome_fantasia",)
        verbose_name = "Empresa"
        verbose_name_plural = "Empresas"
        indexes = [models.Index(fields=["ativa", "nome_fantasia"])]

    def __str__(self) -> str:
        return self.nome_fantasia or self.razao_social

    @property
    def cnpj_formatado(self) -> str:
        return formatar_documento(self.cnpj)

    @property
    def cnpj_ok(self) -> bool:
        return cnpj_valido(self.cnpj)

    @property
    def endereco_completo(self) -> str:
        partes = [
            f"{self.logradouro}, {self.numero}" if self.numero else self.logradouro,
            self.bairro, f"{self.cidade}/{self.uf}" if self.uf else self.cidade,
        ]
        return " - ".join(p for p in partes if p)

    @property
    def apta_a_emitir(self) -> bool:
        """Tudo que o banco exige do cedente está preenchido."""
        return bool(
            self.ativa
            and not self.suspensa_em
            and self.cnpj_ok
            and self.razao_social
            and self.logradouro
            and self.cidade
            and self.uf
            and len(self.cep) == 8
        )

    def limite_titulos_mes(self) -> int | None:
        return LIMITE_TITULOS_MES.get(self.plano)

    def titulos_registrados_no_mes(self) -> int:
        from django.utils import timezone

        from apps.cobrancas.models import Cobranca

        hoje = timezone.localdate()
        return Cobranca.objects.filter(
            empresa_id=self.pk,
            criado_em__year=hoje.year,
            criado_em__month=hoje.month,
        ).exclude(status="RASCUNHO").count()

    def dentro_do_limite(self, novos: int = 0) -> bool:
        limite = self.limite_titulos_mes()
        if limite is None:
            return True
        return self.titulos_registrados_no_mes() + novos <= limite
