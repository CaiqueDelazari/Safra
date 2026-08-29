"""Importação de planilha em segundo plano."""
from __future__ import annotations

import logging

from celery import shared_task

from core.context import use_context

logger = logging.getLogger(__name__)


@shared_task(name="clientes.importar_planilha", bind=True)
def importar_planilha(self, empresa_id: int, cabecalho: list, linhas: list,
                      atualizar_existentes: bool = True, usuario_id: int | None = None):
    """Roda a importação já lida em memória.

    A leitura do arquivo acontece na view — é rápida e permite recusar na hora
    uma planilha sem as colunas obrigatórias, em vez de aceitar o upload e
    devolver o erro cinco minutos depois. O que vai para a fila é só a
    gravação, que é a parte demorada.
    """
    from apps.accounts.models import User
    from apps.clientes.importacao import importar
    from core import audit

    usuario = User.objects.filter(pk=usuario_id).first() if usuario_id else None

    def progresso(pct: int):
        self.update_state(state="PROGRESS", meta={"progresso": pct, "total": len(linhas)})

    with use_context(user=usuario, empresa_id=empresa_id):
        resultado = importar(
            empresa_id=empresa_id, cabecalho=cabecalho, linhas=linhas,
            atualizar_existentes=atualizar_existentes, progresso=progresso,
        )
        audit.registrar(
            "IMPORTACAO", modulo="clientes", empresa_id=empresa_id, usuario=usuario,
            descricao=(
                f"{resultado.criados} criado(s), {resultado.atualizados} atualizado(s), "
                f"{len(resultado.erros)} com erro"
            ),
        )

    return {
        "criados": resultado.criados,
        "atualizados": resultado.atualizados,
        "ignorados": resultado.ignorados,
        "erros": resultado.erros[:100],
        "total": resultado.total,
        "colunas_reconhecidas": resultado.colunas_reconhecidas,
        "colunas_ignoradas": resultado.colunas_ignoradas,
    }
