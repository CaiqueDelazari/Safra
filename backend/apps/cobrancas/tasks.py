"""Tarefas de fila do módulo de cobranças."""
from __future__ import annotations

import logging

from celery import shared_task

from apps.cobrancas.services import CobrancaService
from core.context import use_context

logger = logging.getLogger(__name__)


@shared_task(name="cobrancas.gerar_em_lote", bind=True)
def gerar_em_lote(self, empresa_id: int, linhas: list[dict], usuario_id: int | None = None,
                  conta_bancaria_id: int | None = None):
    """Cria N cobranças em segundo plano.

    O progresso vai para o `update_state` do Celery, que é o que a rota
    `/tarefas/<id>/` lê para responder "50%". Guardar isso numa tabela própria
    seria mais durável e é desnecessário: uma carga que morre no meio é
    recriada, e as já criadas são reconhecidas pela `chave_externa`.
    """
    from apps.accounts.models import User

    usuario = User.objects.filter(pk=usuario_id).first() if usuario_id else None

    def progresso(pct: int):
        self.update_state(state="PROGRESS", meta={"progresso": pct, "total": len(linhas)})

    with use_context(user=usuario, empresa_id=empresa_id):
        resultado = CobrancaService.criar_em_lote(
            empresa_id=empresa_id, linhas=linhas, usuario=usuario,
            conta_bancaria_id=conta_bancaria_id, progresso=progresso,
        )

    return {
        "criadas": len(resultado.criadas),
        "duplicadas": len(resultado.duplicadas),
        "erros": resultado.erros[:50],
        "total": resultado.total,
    }


@shared_task(name="cobrancas.marcar_vencidas")
def marcar_vencidas():
    """Varre a base e passa para VENCIDA o que passou do vencimento.

    Cross-tenant de propósito: é manutenção da plataforma, não operação de uma
    empresa. Um `UPDATE` só, sem contexto de empresa, porque o filtro é a data
    e o status — não há decisão por empresa a tomar.
    """
    total = CobrancaService.marcar_vencidas()
    logger.info("Cobranças marcadas como vencidas: %s", total)
    return {"atualizadas": total}


@shared_task(name="cobrancas.enviar_boleto_email")
def enviar_boleto_email(cobranca_id: int, empresa_id: int, destinatario: str = ""):
    """Manda o boleto ao sacado por e-mail.

    Só o link e a linha digitável — o PDF não vai anexado de propósito: anexo
    de boleto é o formato preferido de golpe por e-mail, e treinar o sacado a
    abrir anexos de cobrança é um desserviço. O link aponta para o painel, com
    token assinado e prazo.
    """
    from django.conf import settings
    from django.core.mail import EmailMessage

    from apps.cobrancas.models import Cobranca
    from apps.cobrancas.services import CobrancaService

    with use_context(empresa_id=empresa_id):
        cobranca = Cobranca.objects.select_related("cliente", "empresa").get(
            pk=cobranca_id, empresa_id=empresa_id
        )
        destino = destinatario or cobranca.cliente.email
        if not destino:
            logger.warning("Cobrança %s: cliente sem e-mail.", cobranca_id)
            return {"enviado": False, "motivo": "cliente sem e-mail"}

        dados = CobrancaService.dados_do_boleto(cobranca)
        empresa = cobranca.empresa
        from apps.bancos.boleto import formatar_linha_digitavel

        corpo = (
            f"Olá, {cobranca.cliente.nome}.\n\n"
            f"Segue a cobrança de {empresa.razao_social}:\n\n"
            f"Descrição: {cobranca.descricao}\n"
            f"Valor: R$ {cobranca.valor:.2f}\n"
            f"Vencimento: {cobranca.data_vencimento:%d/%m/%Y}\n\n"
            f"Linha digitável:\n{formatar_linha_digitavel(dados['linha_digitavel'])}\n\n"
            f"Boleto: {settings.URL_PAINEL}/boleto/{cobranca.uuid}\n\n"
            f"Em caso de dúvida, responda este e-mail.\n"
        )
        mensagem = EmailMessage(
            subject=f"Cobrança {cobranca.descricao} — vencimento "
                    f"{cobranca.data_vencimento:%d/%m/%Y}",
            body=corpo,
            from_email=empresa.email_cobranca or settings.DEFAULT_FROM_EMAIL,
            to=[destino],
        )
        mensagem.send(fail_silently=False)

        from django.utils import timezone

        Cobranca.objects.filter(pk=cobranca.pk).update(
            enviado_ao_cliente_em=timezone.now()
        )
        return {"enviado": True, "destinatario": destino}


@shared_task(name="cobrancas.enviar_boletos_em_lote")
def enviar_boletos_em_lote(cobranca_ids: list[int], empresa_id: int):
    """Dispara o envio de vários boletos, um e-mail por tarefa.

    Uma tarefa por e-mail, e não um laço aqui dentro: assim um endereço
    inválido no meio de 500 não derruba os 499 restantes, e a repetição do
    Celery reenvia só o que falhou.
    """
    for cobranca_id in cobranca_ids:
        enviar_boleto_email.delay(cobranca_id, empresa_id)
    return {"enfileirados": len(cobranca_ids)}
