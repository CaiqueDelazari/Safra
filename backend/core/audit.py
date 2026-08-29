"""Trilha de auditoria — registra tudo: quem, o quê, quando, de onde."""
import logging
from decimal import Decimal
from typing import Any, Optional

from django.apps import apps
from django.db.models import Model
from django.db.models.signals import post_delete, post_save, pre_save
from django.forms.models import model_to_dict

from core.context import current_empresa_id, current_user

logger = logging.getLogger(__name__)

CAMPOS_IGNORADOS = {"criado_em", "atualizado_em", "password", "last_login"}


def _json_safe(valor: Any) -> Any:
    if isinstance(valor, Decimal):
        return str(valor)
    if isinstance(valor, Model):
        return valor.pk
    if hasattr(valor, "isoformat"):
        return valor.isoformat()
    if isinstance(valor, (list, tuple)):
        return [_json_safe(v) for v in valor]
    if isinstance(valor, dict):
        return {k: _json_safe(v) for k, v in valor.items()}
    if valor is None or isinstance(valor, (str, int, float, bool)):
        return valor
    return str(valor)


def snapshot(instancia: Model) -> dict:
    dados = model_to_dict(instancia)
    return {k: _json_safe(v) for k, v in dados.items() if k not in CAMPOS_IGNORADOS}


def diff(antes: dict, depois: dict) -> dict:
    mudancas = {}
    for campo in set(antes) | set(depois):
        a, d = antes.get(campo), depois.get(campo)
        if a != d:
            mudancas[campo] = {"de": a, "para": d}
    return mudancas


def registrar(
    acao: str,
    *,
    modulo: str = "",
    descricao: str = "",
    instancia: Optional[Model] = None,
    empresa_id: Optional[int] = None,
    usuario=None,
    alteracoes: Optional[dict] = None,
    metadados: Optional[dict] = None,
) -> None:
    from apps.auditoria.models import LogAuditoria  # import tardio: evita ciclo
    from core.context import get_context

    ctx = get_context()
    usuario = usuario or current_user()
    try:
        LogAuditoria.objects.create(
            empresa_id=empresa_id
            or getattr(instancia, "empresa_id", None)
            or current_empresa_id(),
            usuario=usuario,
            usuario_nome=getattr(usuario, "nome_completo", "") or "sistema",
            acao=acao,
            modulo=modulo or (instancia._meta.app_label if instancia else ""),
            objeto_tipo=instancia._meta.model_name if instancia else "",
            objeto_id=str(getattr(instancia, "pk", "") or ""),
            objeto_descricao=(str(instancia)[:255] if instancia else ""),
            descricao=descricao[:500],
            alteracoes=_json_safe(alteracoes or {}),
            metadados=_json_safe(metadados or {}),
            ip=ctx.ip or None,
            user_agent=ctx.user_agent,
        )
    except Exception:  # auditoria jamais derruba a operação principal
        logger.exception("Falha ao gravar log de auditoria (%s/%s)", modulo, acao)


# ------------------------------------------------------------------ signals
#: Modelos cujo histórico completo é gravado por signal.
#:
#: `bancos.OcorrenciaBancaria` e `pagamentos.Pagamento` NÃO entram, e a
#: ausência é deliberada: os dois já são append-only e carregam a própria
#: proveniência (o arquivo, a linha). Auditá-los duplicaria o volume de log
#: mais pesado do sistema — um retorno de 50 mil títulos viraria 100 mil
#: linhas — para registrar exatamente a mesma informação duas vezes. As
#: operações sobre eles são registradas por chamada explícita a `registrar`,
#: nos serviços.
MODELOS_AUDITADOS = [
    "clientes.Cliente",
    "cobrancas.Cobranca",
    "bancos.ContaBancaria",
    "bancos.LoteBancario",
    "empresas.Empresa",
    "accounts.User",
    "accounts.UsuarioEmpresa",
]


def _pre_save(sender, instance, **kwargs):
    if instance.pk:
        anterior = sender.objects.filter(pk=instance.pk).first()
        instance._snapshot_anterior = snapshot(anterior) if anterior else {}
    else:
        instance._snapshot_anterior = None


def _post_save(sender, instance, created, **kwargs):
    depois = snapshot(instance)
    if created:
        registrar("CRIACAO", modulo=sender._meta.app_label, instancia=instance,
                  alteracoes={"criado": depois})
        return
    antes = getattr(instance, "_snapshot_anterior", None) or {}
    mudancas = diff(antes, depois)
    if mudancas:
        registrar("EDICAO", modulo=sender._meta.app_label, instancia=instance,
                  alteracoes=mudancas)


def _post_delete(sender, instance, **kwargs):
    registrar("EXCLUSAO", modulo=sender._meta.app_label, instancia=instance,
              alteracoes={"removido": snapshot(instance)})


def conectar_signals() -> None:
    for label in MODELOS_AUDITADOS:
        try:
            modelo = apps.get_model(label)
        except LookupError:  # app ainda não carregado / removido
            continue
        pre_save.connect(_pre_save, sender=modelo, dispatch_uid=f"aud_pre_{label}")
        post_save.connect(_post_save, sender=modelo, dispatch_uid=f"aud_post_{label}")
        post_delete.connect(_post_delete, sender=modelo, dispatch_uid=f"aud_del_{label}")
