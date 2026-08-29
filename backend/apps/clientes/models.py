"""Cliente — o sacado do boleto.

O cadastro aqui não é agenda de contatos: é o que vai impresso no título e
transmitido ao banco. Nome, documento e endereço saem daqui direto para a
remessa, e o banco recusa o registro se qualquer um deles estiver fora do
formato. Por isso o CPF/CNPJ é validado de verdade (dígito verificador) e o
nome tem teto de 40 caracteres na hora de virar CNAB — o truncamento acontece
no adapter, não no cadastro, para que a tela continue mostrando o nome inteiro.
"""
from django.core.exceptions import ValidationError
from django.db import models
from django.db.models.functions import Coalesce

from core.models import TenantModel
from core.validadores import (
    documento_valido,
    formatar_documento,
    so_digitos,
    tipo_de_pessoa,
)


class StatusCliente(models.TextChoices):
    ATIVO = "ATIVO", "Ativo"
    INATIVO = "INATIVO", "Inativo"
    INADIMPLENTE = "INADIMPLENTE", "Inadimplente"
    BLOQUEADO = "BLOQUEADO", "Bloqueado"


class Cliente(TenantModel):
    #: Sequencial por empresa. É o "código do cliente" que o operador usa no
    #: telefone e na planilha de importação.
    codigo = models.PositiveIntegerField(db_index=True, editable=False)

    nome = models.CharField(
        max_length=180, db_index=True,
        help_text="Nome ou razão social, como consta no documento.",
    )
    nome_fantasia = models.CharField(max_length=180, blank=True)
    cpf_cnpj = models.CharField(max_length=14, db_index=True)

    email = models.EmailField(blank=True)
    email_secundario = models.EmailField(blank=True)
    telefone = models.CharField(max_length=20, blank=True, db_index=True)
    telefone_secundario = models.CharField(max_length=20, blank=True)

    cep = models.CharField(max_length=8, blank=True)
    logradouro = models.CharField(max_length=180, blank=True)
    numero = models.CharField(max_length=20, blank=True)
    complemento = models.CharField(max_length=120, blank=True)
    bairro = models.CharField(max_length=120, blank=True, db_index=True)
    cidade = models.CharField(max_length=120, blank=True, db_index=True)
    uf = models.CharField(max_length=2, blank=True)

    observacoes = models.TextField(blank=True)
    status = models.CharField(
        max_length=14, choices=StatusCliente.choices,
        default=StatusCliente.ATIVO, db_index=True,
    )
    #: Chave do cliente no sistema de origem de quem importou. Permite rodar a
    #: mesma planilha duas vezes sem duplicar a carteira.
    codigo_externo = models.CharField(max_length=60, blank=True, db_index=True)

    class Meta:
        db_table = "customers"
        ordering = ("nome",)
        verbose_name = "Cliente"
        verbose_name_plural = "Clientes"
        constraints = [
            models.UniqueConstraint(
                fields=["empresa", "codigo"], name="uniq_codigo_cliente_por_empresa"
            ),
            # Mesmo CPF/CNPJ duas vezes na mesma empresa é quase sempre carga
            # repetida — e duas fichas para o mesmo sacado fazem a cobrança
            # sair dobrada. Empresas diferentes podem ter o mesmo cliente, e
            # devem: são carteiras independentes.
            models.UniqueConstraint(
                fields=["empresa", "cpf_cnpj"],
                condition=~models.Q(cpf_cnpj=""),
                name="uniq_documento_cliente_por_empresa",
            ),
            models.UniqueConstraint(
                fields=["empresa", "codigo_externo"],
                condition=~models.Q(codigo_externo=""),
                name="uniq_codigo_externo_cliente_por_empresa",
            ),
        ]
        indexes = [
            models.Index(fields=["empresa", "status"]),
            models.Index(fields=["empresa", "nome"]),
            models.Index(fields=["empresa", "cidade", "bairro"]),
        ]

    def __str__(self) -> str:
        return f"{self.codigo} — {self.nome}"

    def clean(self):
        super().clean()
        self.cpf_cnpj = so_digitos(self.cpf_cnpj)
        self.cep = so_digitos(self.cep)
        self.uf = (self.uf or "").upper()
        if self.cpf_cnpj and not documento_valido(self.cpf_cnpj):
            raise ValidationError(
                {"cpf_cnpj": "CPF/CNPJ inválido: os dígitos verificadores não conferem."}
            )

    def save(self, *args, **kwargs):
        if self.codigo is None:
            self.codigo = self._proximo_codigo(self.empresa_id)
        super().save(*args, **kwargs)

    @staticmethod
    def _proximo_codigo(empresa_id: int) -> int:
        """Sequencial por empresa. Em concorrência, o UniqueConstraint protege
        e quem chama repete — ver `apps.clientes.services`."""
        agregado = Cliente.objects.filter(empresa_id=empresa_id).aggregate(
            ultimo=Coalesce(models.Max("codigo"), 0)
        )
        return agregado["ultimo"] + 1

    # --------------------------------------------------------- apresentação
    @property
    def documento_formatado(self) -> str:
        return formatar_documento(self.cpf_cnpj)

    @property
    def tipo_pessoa(self) -> str:
        """'F' ou 'J' — o que o CNAB chama de tipo de inscrição."""
        return tipo_de_pessoa(self.cpf_cnpj)

    @property
    def cep_formatado(self) -> str:
        c = self.cep
        return f"{c[:5]}-{c[5:]}" if len(c) == 8 else c

    @property
    def endereco_completo(self) -> str:
        partes = [
            f"{self.logradouro}, {self.numero}" if self.numero else self.logradouro,
            self.complemento, self.bairro,
            f"{self.cidade}/{self.uf}" if self.uf else self.cidade,
        ]
        return " - ".join(p for p in partes if p)

    @property
    def endereco_completo_para_boleto(self) -> bool:
        """O banco exige endereço no registro do título. Sem isto, a rejeição
        vem no retorno do dia seguinte — e um boleto a menos foi emitido."""
        return bool(self.logradouro and self.cidade and self.uf and len(self.cep) == 8)
