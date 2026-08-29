"""Modelos base: identidade, timestamps, soft delete e isolamento multiempresa."""
import uuid

from django.db import models

from core.context import current_empresa_id


class TimeStampedModel(models.Model):
    id = models.BigAutoField(primary_key=True)
    uuid = models.UUIDField(default=uuid.uuid4, editable=False, unique=True, db_index=True)
    criado_em = models.DateTimeField(auto_now_add=True, db_index=True)
    atualizado_em = models.DateTimeField(auto_now=True)

    class Meta:
        abstract = True


class TenantQuerySet(models.QuerySet):
    def da_empresa(self, empresa_id):
        return self.filter(empresa_id=empresa_id)

    def do_contexto(self):
        """Aplica a empresa ativa do contexto da requisição, se houver."""
        empresa_id = current_empresa_id()
        return self.filter(empresa_id=empresa_id) if empresa_id else self


class TenantManager(models.Manager.from_queryset(TenantQuerySet)):
    """Manager padrão dos modelos multiempresa.

    `objects` NÃO filtra automaticamente — o filtro é explícito na camada de
    repositório (`.do_contexto()`), o que evita vazamento silencioso e mantém
    tasks/webhooks capazes de acessar dados cross-empresa de forma consciente.
    """


class TenantModel(TimeStampedModel):
    empresa = models.ForeignKey(
        "empresas.Empresa",
        on_delete=models.PROTECT,
        related_name="%(class)ss",
        db_index=True,
    )

    objects = TenantManager()

    class Meta:
        abstract = True
