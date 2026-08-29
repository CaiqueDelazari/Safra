"""Tarefas de fila do módulo bancário.

Toda operação que fala com o banco ou lê arquivo grande está aqui, e nenhuma
delas é chamada direto por uma view — a view enfileira e responde. É a regra
18/19 do enunciado, e a razão prática é simples: montar remessa de 20 mil
títulos leva minutos, e um `gunicorn` com timeout de 120 s desconectaria o
usuário no meio, deixando o lote num estado que ninguém sabe qual é.

Sobre repetição: `acks_late` está ligado no Celery (config/settings.py), então
worker morto devolve a tarefa para a fila. Isso só é seguro porque cada tarefa
aqui pode rodar duas vezes sem estragar nada — e cada uma diz abaixo *por que*
pode.
"""
from __future__ import annotations

import logging

from celery import shared_task
from django.core.cache import cache
from django.utils import timezone

from apps.bancos.bancos import StatusArquivo, TipoArquivo
from apps.bancos.models import ArquivoBancario, ContaBancaria, LoteBancario
from apps.bancos.services import LoteService, RetornoService
from core.context import use_context

logger = logging.getLogger(__name__)

#: Trava de execução. Um arquivo por vez, mesmo com vários workers: a
#: idempotência garante que o resultado final é o mesmo, mas duas passadas
#: simultâneas se atropelariam nos locks do Postgres e dobrariam o trabalho.
#: Curta o bastante para não travar para sempre se o worker morrer.
LOCK_SEGUNDOS = 3600


def _travar(chave: str) -> bool:
    """`add` é atômico no Redis: ou este processo pegou a trava, ou não pegou."""
    return cache.add(f"lock:{chave}", timezone.now().isoformat(), LOCK_SEGUNDOS)


def _destravar(chave: str) -> None:
    cache.delete(f"lock:{chave}")


# ══════════════════════════════════════════════════════════════════ remessa
@shared_task(name="bancos.montar_remessa", bind=True, max_retries=2, default_retry_delay=60)
def montar_remessa(self, lote_id: int, empresa_id: int, enviar: bool = False):
    """Monta o arquivo do lote e, opcionalmente, transmite.

    Segura para repetir: `montar_remessa` recusa lote que já saiu do estado
    montável, então uma segunda execução após sucesso não gera segundo arquivo.
    Os "nossos números" já estavam reservados na criação do lote — a remontagem
    de um lote que falhou produz exatamente o mesmo arquivo.
    """
    chave = f"lote:{lote_id}"
    if not _travar(chave):
        logger.info("Lote %s já está sendo montado por outro worker.", lote_id)
        return {"ignorado": "em processamento"}

    try:
        with use_context(empresa_id=empresa_id):
            lote = LoteBancario.objects.select_related("conta", "conta__empresa").get(
                pk=lote_id, empresa_id=empresa_id
            )
            LoteBancario.objects.filter(pk=lote.pk).update(task_id=self.request.id or "")
            arquivo = LoteService.montar_remessa(lote)
            resultado = {"arquivo_id": arquivo.pk, "nome": arquivo.nome_original}
            if enviar:
                lote.refresh_from_db()
                resultado["protocolo"] = LoteService.enviar(lote)
            return resultado
    except LoteBancario.DoesNotExist:
        logger.warning("Lote %s não existe mais.", lote_id)
        return {"erro": "lote inexistente"}
    finally:
        _destravar(chave)


@shared_task(name="bancos.enviar_remessa", bind=True, max_retries=3, default_retry_delay=120)
def enviar_remessa(self, lote_id: int, empresa_id: int):
    """Transmite um lote já montado.

    Repetição aqui é o caso delicado: reenviar um arquivo que o banco já
    recebeu poderia duplicar títulos. O que protege é o NSA — o banco recusa
    arquivo com sequencial repetido, que é exatamente para isso que ele
    existe. Por via das dúvidas, só transmite quem está em PRONTO ou ERRO.
    """
    from apps.bancos.adapters.base import ErroDeIntegracao

    with use_context(empresa_id=empresa_id):
        lote = LoteBancario.objects.select_related("conta", "conta__empresa").get(
            pk=lote_id, empresa_id=empresa_id
        )
        try:
            return {"protocolo": LoteService.enviar(lote)}
        except ErroDeIntegracao as exc:
            # Instabilidade de rede/SFTP merece nova tentativa; o serviço já
            # marcou o lote como ERRO, e o reenvio o tira de lá.
            raise self.retry(exc=exc)


# ══════════════════════════════════════════════════════════════════ retorno
@shared_task(name="bancos.processar_retorno", bind=True, max_retries=2,
             default_retry_delay=120)
def processar_retorno(self, arquivo_id: int, empresa_id: int):
    """Processa um arquivo de retorno inteiro.

    Pode rodar quantas vezes for: `OcorrenciaBancaria` é única por (arquivo,
    linha) e `Pagamento` é um-para-um com a ocorrência. Uma segunda passada
    reconhece o que já aplicou, tenta aplicar o que ficou pendente, e não cria
    dinheiro novo.
    """
    chave = f"retorno:{arquivo_id}"
    if not _travar(chave):
        logger.info("Retorno %s já está sendo processado.", arquivo_id)
        return {"ignorado": "em processamento"}

    try:
        with use_context(empresa_id=empresa_id):
            arquivo = ArquivoBancario.objects.select_related("conta", "conta__empresa").get(
                pk=arquivo_id, empresa_id=empresa_id
            )
            resumo = RetornoService.processar(arquivo)
            return {k: str(v) for k, v in resumo.items()}
    except ArquivoBancario.DoesNotExist:
        return {"erro": "arquivo inexistente"}
    finally:
        _destravar(chave)


@shared_task(name="bancos.varrer_retornos")
def varrer_retornos():
    """Busca retornos novos em todos os canais e enfileira o processamento.

    Roda de hora em hora (CELERY_BEAT_SCHEDULE). Percorre todas as empresas —
    é uma das poucas tarefas legitimamente cross-tenant, e por isso entra em
    cada empresa pelo `use_context` explícito, em vez de rodar sem contexto e
    torcer para os filtros estarem certos.

    Nada aqui duplica trabalho: o hash do conteúdo decide se o arquivo é novo,
    então varrer dez vezes o mesmo diretório registra um arquivo só.
    """
    from apps.bancos.adapters.base import ErroDeIntegracao
    from apps.bancos.transporte import ler_diretorio_entrada

    total = {"novos": 0, "conhecidos": 0, "falhas": 0}

    # 1) Volume local: arquivos que chegaram por fora (rclone, montagem, script
    #    do cliente). Não têm empresa declarada; a identificação vem da conta,
    #    e por isso só entram quando há uma única empresa com conta ativa
    #    naquele banco — o resto vai para upload manual, com aviso.
    for nome, conteudo in ler_diretorio_entrada():
        contas = list(ContaBancaria.objects.filter(ativa=True).select_related("empresa")[:2])
        if len(contas) != 1:
            logger.warning(
                "Retorno %s no diretório de entrada, mas há %d contas ativas: "
                "não dá para saber de quem é. Suba pela tela.", nome, len(contas)
            )
            total["falhas"] += 1
            continue
        conta = contas[0]
        _registrar_e_enfileirar(conta, nome, conteudo, "SFTP", total)

    # 2) Contas com SFTP configurado.
    contas = ContaBancaria.objects.filter(ativa=True).exclude(sftp_host="").select_related(
        "empresa"
    )
    for conta in contas:
        with use_context(empresa_id=conta.empresa_id):
            from apps.bancos.adapters import adapter_para

            try:
                arquivos = adapter_para(conta).obter_retornos()
            except ErroDeIntegracao as exc:
                logger.warning("SFTP da conta %s indisponível: %s", conta.pk, exc)
                total["falhas"] += 1
                continue
            for nome, conteudo in arquivos:
                _registrar_e_enfileirar(conta, nome, conteudo, "SFTP", total)

    logger.info("Varredura de retornos: %s", total)
    return total


def _registrar_e_enfileirar(conta, nome: str, conteudo: bytes, origem: str, total: dict):
    with use_context(empresa_id=conta.empresa_id):
        arquivo, novo = RetornoService.registrar_arquivo(
            empresa_id=conta.empresa_id, nome=nome, conteudo=conteudo,
            banco=conta.banco, conta=conta, origem=origem,
        )
        if novo:
            total["novos"] += 1
            processar_retorno.delay(arquivo.pk, conta.empresa_id)
        else:
            total["conhecidos"] += 1


@shared_task(name="bancos.reprocessar_presos")
def reprocessar_presos():
    """Recolhe o que ficou pelo caminho.

    Um arquivo em PROCESSANDO há mais de uma hora é um worker que morreu — o
    `acks_late` devolveria a tarefa, mas se o Redis também tiver perdido a
    mensagem, ninguém mais olharia para esse arquivo. Meia em meia hora, esta
    tarefa devolve os presos à fila. Sem ela, um pagamento fica invisível para
    sempre e ninguém descobre até a conciliação do mês.
    """
    from datetime import timedelta

    limite = timezone.now() - timedelta(hours=1)
    presos = ArquivoBancario.objects.filter(
        tipo=TipoArquivo.RETORNO,
        status=StatusArquivo.PROCESSANDO,
        atualizado_em__lt=limite,
    )[:50]

    recolhidos = 0
    for arquivo in presos:
        logger.warning("Retorno #%s preso em PROCESSANDO; recolocando na fila.", arquivo.pk)
        ArquivoBancario.objects.filter(pk=arquivo.pk).update(status=StatusArquivo.PENDENTE)
        _destravar(f"retorno:{arquivo.pk}")
        processar_retorno.delay(arquivo.pk, arquivo.empresa_id)
        recolhidos += 1

    # Pendentes que nunca foram enfileirados (upload cujo broker estava fora).
    orfaos = ArquivoBancario.objects.filter(
        tipo=TipoArquivo.RETORNO, status=StatusArquivo.PENDENTE, criado_em__lt=limite
    )[:50]
    for arquivo in orfaos:
        processar_retorno.delay(arquivo.pk, arquivo.empresa_id)
        recolhidos += 1

    return {"recolhidos": recolhidos}
