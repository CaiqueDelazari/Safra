"""Regras de cobrança: criação em massa, cancelamento, baixa, boleto.

O que separa este módulo do de bancos: aqui nada sabe o que é CNAB, arquivo ou
protocolo. Uma cobrança é criada, cancelada ou paga em termos do negócio; o
que isso significa para o Safra é problema do adapter. A única ponte é
`apps.bancos.services`, chamado sempre a partir daqui e nunca ao contrário.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import date
from decimal import Decimal

from django.db import IntegrityError, transaction
from django.db.models import Max
from django.utils import timezone

from apps.cobrancas.models import (
    EM_ABERTO,
    Cobranca,
    ItemCobranca,
    StatusCobranca,
)
from core import audit
from core.services import RegraDeNegocioError

logger = logging.getLogger(__name__)


@dataclass
class ResultadoCriacao:
    criadas: list[int] = field(default_factory=list)
    duplicadas: list[str] = field(default_factory=list)
    erros: list[dict] = field(default_factory=list)

    @property
    def total(self) -> int:
        return len(self.criadas) + len(self.duplicadas) + len(self.erros)


class CobrancaService:
    # ═════════════════════════════════════════════════════ criação em massa
    @staticmethod
    def criar_em_lote(*, empresa_id: int, linhas: list[dict], usuario=None,
                      conta_bancaria_id: int | None = None,
                      progresso=None) -> ResultadoCriacao:
        """Cria N cobranças de uma vez.

        `linhas` é uma lista de dicionários já validados pelo serializer. O que
        esta função acrescenta é o que só existe no conjunto: numeração
        sequencial sem uma consulta por linha, deduplicação por `chave_externa`
        e um relatório do que entrou e do que não entrou.

        A numeração merece explicação. Chamar `Cobranca._proximo_numero` por
        linha faria 500 `SELECT MAX` e ainda assim daria colisão sob
        concorrência. Aqui o número é calculado uma vez, sob lock da própria
        tabela de sequência lógica, e distribuído em memória. Colisão residual
        (duas cargas simultâneas) cai no `IntegrityError` e a linha é
        recontada — raro o bastante para não valer uma tabela de sequência
        dedicada, e tratado o bastante para não perder dado.
        """
        resultado = ResultadoCriacao()
        if not linhas:
            return resultado

        from django.conf import settings

        bloco = settings.LOTE_TAMANHO_BLOCO
        total = len(linhas)

        # Deduplicação contra o que já existe: uma consulta, não N.
        chaves = {l.get("chave_externa") for l in linhas if l.get("chave_externa")}
        existentes = set()
        if chaves:
            existentes = set(
                Cobranca.objects.filter(
                    empresa_id=empresa_id, chave_externa__in=chaves
                ).values_list("chave_externa", flat=True)
            )

        vistas_na_carga: set[str] = set()

        for inicio in range(0, total, bloco):
            pedaco = linhas[inicio:inicio + bloco]
            with transaction.atomic():
                proximo = (
                    Cobranca.objects.select_for_update()
                    .filter(empresa_id=empresa_id)
                    .aggregate(ultimo=Max("numero"))["ultimo"] or 0
                ) + 1

                a_criar: list[Cobranca] = []
                itens_por_indice: dict[int, list[dict]] = {}

                for linha in pedaco:
                    chave = linha.get("chave_externa") or ""
                    if chave and (chave in existentes or chave in vistas_na_carga):
                        resultado.duplicadas.append(chave)
                        continue
                    if chave:
                        vistas_na_carga.add(chave)

                    try:
                        cobranca = CobrancaService._montar(
                            empresa_id=empresa_id, linha=linha, numero=proximo,
                            usuario=usuario, conta_bancaria_id=conta_bancaria_id,
                        )
                    except RegraDeNegocioError as exc:
                        resultado.erros.append({
                            "linha": inicio + pedaco.index(linha) + 1,
                            "erro": exc.mensagem,
                            "dados": {k: str(v) for k, v in list(linha.items())[:6]},
                        })
                        continue

                    itens_por_indice[len(a_criar)] = linha.get("itens") or []
                    a_criar.append(cobranca)
                    proximo += 1

                if not a_criar:
                    continue

                try:
                    criadas = Cobranca.objects.bulk_create(a_criar, batch_size=bloco)
                except IntegrityError:
                    # Carga concorrente pegou a mesma faixa de números. Refaz
                    # este bloco uma a uma — lento, mas só acontece na colisão.
                    criadas = CobrancaService._criar_uma_a_uma(a_criar, resultado)

                resultado.criadas.extend(c.pk for c in criadas if c.pk)

                itens = []
                for indice, cobranca in enumerate(criadas):
                    for ordem, item in enumerate(itens_por_indice.get(indice, [])):
                        itens.append(ItemCobranca(
                            empresa_id=empresa_id,
                            cobranca=cobranca,
                            descricao=item["descricao"][:180],
                            quantidade=Decimal(str(item.get("quantidade", 1))),
                            valor_unitario=Decimal(str(item["valor_unitario"])),
                            ordem=ordem,
                        ))
                if itens:
                    ItemCobranca.objects.bulk_create(itens, batch_size=bloco)

            if progresso:
                progresso(min(99, int((inicio + len(pedaco)) / total * 100)))

        audit.registrar(
            "COBRANCA_LOTE", modulo="cobrancas", empresa_id=empresa_id, usuario=usuario,
            descricao=(
                f"{len(resultado.criadas)} cobrança(s) criada(s); "
                f"{len(resultado.duplicadas)} duplicada(s); {len(resultado.erros)} com erro"
            ),
        )
        return resultado

    @staticmethod
    def _montar(*, empresa_id: int, linha: dict, numero: int, usuario,
                conta_bancaria_id) -> Cobranca:
        vencimento = linha["data_vencimento"]
        emissao = linha.get("data_emissao") or timezone.localdate()
        if isinstance(vencimento, str):
            vencimento = date.fromisoformat(vencimento)
        if isinstance(emissao, str):
            emissao = date.fromisoformat(emissao)
        if vencimento < emissao:
            raise RegraDeNegocioError(
                "Vencimento anterior à emissão.", "data_vencimento"
            )

        valor = Decimal(str(linha["valor"]))
        if valor <= 0:
            raise RegraDeNegocioError("Valor precisa ser maior que zero.", "valor")

        return Cobranca(
            empresa_id=empresa_id,
            numero=numero,
            cliente_id=linha["cliente_id"],
            conta_bancaria_id=linha.get("conta_bancaria_id") or conta_bancaria_id,
            descricao=str(linha["descricao"])[:180],
            documento=str(linha.get("documento") or "")[:40],
            seu_numero=str(linha.get("seu_numero") or numero)[:25],
            valor=valor,
            data_emissao=emissao,
            data_vencimento=vencimento,
            juros_mes_percentual=Decimal(str(linha.get("juros_mes_percentual") or 0)),
            multa_percentual=Decimal(str(linha.get("multa_percentual") or 0)),
            desconto=Decimal(str(linha.get("desconto") or 0)),
            data_limite_desconto=linha.get("data_limite_desconto") or None,
            abatimento=Decimal(str(linha.get("abatimento") or 0)),
            observacoes=str(linha.get("observacoes") or ""),
            chave_externa=str(linha.get("chave_externa") or "")[:80],
            status=StatusCobranca.PENDENTE,
            criado_por=usuario,
        )

    @staticmethod
    def _criar_uma_a_uma(objetos: list[Cobranca], resultado: ResultadoCriacao):
        criadas = []
        for obj in objetos:
            try:
                with transaction.atomic():
                    obj.numero = None  # deixa o `save` recalcular
                    obj.save()
                    criadas.append(obj)
            except IntegrityError as exc:
                resultado.erros.append({"erro": f"conflito ao gravar: {exc}"})
        return criadas

    # ═════════════════════════════════════════════════════════ instruções
    @staticmethod
    @transaction.atomic
    def cancelar(cobranca: Cobranca, *, motivo: str = "", usuario=None) -> Cobranca:
        """Cancela a cobrança — e, se ela já está no banco, pede a exclusão.

        A ordem importa: primeiro o pedido ao banco, depois o estado local. Se
        o banco recusar, a cobrança continua ativa aqui, que é a verdade. O
        inverso deixaria o título vivo no banco e morto no sistema — o sacado
        pagaria um boleto que ninguém está esperando.
        """
        if cobranca.status == StatusCobranca.PAGA:
            raise RegraDeNegocioError(
                "Cobrança já paga não se cancela. Se houve devolução, registre "
                "o estorno do pagamento.", "status",
            )
        if cobranca.status == StatusCobranca.CANCELADA:
            return cobranca

        if cobranca.esta_no_banco:
            from apps.bancos.services import _pedir_instrucao

            _pedir_instrucao(cobranca, "CANCELAMENTO")

        cobranca.status = StatusCobranca.CANCELADA
        cobranca.observacoes = (
            f"{cobranca.observacoes}\n[{timezone.localdate():%d/%m/%Y}] "
            f"Cancelada: {motivo}".strip()
        )
        cobranca.save(update_fields=["status", "observacoes", "atualizado_em"])
        audit.registrar(
            "COBRANCA_CANCELADA", modulo="cobrancas", instancia=cobranca,
            usuario=usuario, descricao=motivo or "sem motivo informado",
        )
        return cobranca

    @staticmethod
    @transaction.atomic
    def baixar(cobranca: Cobranca, *, motivo: str = "", usuario=None) -> Cobranca:
        """Baixa sem pagamento: negociado, perdoado, recebido por fora."""
        if cobranca.esta_finalizada:
            raise RegraDeNegocioError(
                f"Cobrança já está '{cobranca.get_status_display()}'.", "status"
            )
        if cobranca.esta_no_banco:
            from apps.bancos.services import _pedir_instrucao

            _pedir_instrucao(cobranca, "BAIXA")

        cobranca.status = StatusCobranca.BAIXADA
        cobranca.save(update_fields=["status", "atualizado_em"])
        audit.registrar(
            "COBRANCA_BAIXADA", modulo="cobrancas", instancia=cobranca,
            usuario=usuario, descricao=motivo,
        )
        return cobranca

    @staticmethod
    @transaction.atomic
    def registrar_pagamento_manual(cobranca: Cobranca, *, valor: Decimal,
                                   data_pagamento: date, usuario=None,
                                   observacao: str = ""):
        """Baixa manual — o caso raro de quem recebeu por fora do boleto.

        Fica marcada como MANUAL e com o usuário registrado, e a conciliação a
        separa das liquidações do banco. Não é o caminho normal e não deve
        parecer que é: dinheiro que entra sem retorno bancário é dinheiro sem
        prova documental.
        """
        from apps.pagamentos.models import OrigemPagamento, Pagamento

        if cobranca.status == StatusCobranca.PAGA:
            raise RegraDeNegocioError("Cobrança já está paga.", "status")

        pagamento = Pagamento.objects.create(
            empresa_id=cobranca.empresa_id,
            cobranca=cobranca,
            conta_bancaria=cobranca.conta_bancaria,
            origem=OrigemPagamento.MANUAL,
            data_pagamento=data_pagamento,
            data_credito=data_pagamento,
            valor=valor,
            observacao=observacao[:300],
            registrado_por=usuario,
        )
        cobranca.status = StatusCobranca.PAGA
        cobranca.data_pagamento = data_pagamento
        cobranca.data_liquidacao = data_pagamento
        cobranca.valor_pago = valor
        cobranca.save(update_fields=[
            "status", "data_pagamento", "data_liquidacao", "valor_pago", "atualizado_em"
        ])
        audit.registrar(
            "PAGAMENTO_MANUAL", modulo="cobrancas", instancia=cobranca, usuario=usuario,
            descricao=f"Baixa manual de {valor}", metadados={"observacao": observacao},
        )
        return pagamento

    # ═══════════════════════════════════════════════════════════ boleto
    @staticmethod
    def dados_do_boleto(cobranca: Cobranca) -> dict:
        """Código de barras e linha digitável, calculados na hora se faltarem.

        Recalcular é seguro porque o cálculo é determinístico: mesma conta,
        mesmo nosso número, mesmo vencimento e mesmo valor dão sempre o mesmo
        código. O que muda o código é mudar o título — e mudar título
        registrado exige instrução ao banco, que passa por outro caminho.
        """
        if not cobranca.nosso_numero or not cobranca.conta_bancaria_id:
            raise RegraDeNegocioError(
                "A cobrança ainda não foi enviada ao banco: não há boleto.", "status"
            )
        if cobranca.codigo_barras and cobranca.linha_digitavel:
            return {
                "codigo_barras": cobranca.codigo_barras,
                "linha_digitavel": cobranca.linha_digitavel,
            }

        from apps.bancos.adapters import adapter_para
        from apps.bancos.services import montar_titulo

        resultado = adapter_para(cobranca.conta_bancaria).gerar_boleto(
            montar_titulo(cobranca)
        )
        Cobranca.objects.filter(pk=cobranca.pk).update(
            codigo_barras=resultado.codigo_barras,
            linha_digitavel=resultado.linha_digitavel,
            boleto_gerado_em=timezone.now(),
        )
        return {
            "codigo_barras": resultado.codigo_barras,
            "linha_digitavel": resultado.linha_digitavel,
        }

    # ═══════════════════════════════════════════════════════════ vencidas
    @staticmethod
    def marcar_vencidas(empresa_id: int | None = None) -> int:
        """Passa para VENCIDA o que passou do vencimento e continua em aberto.

        Um `UPDATE` em massa, sem carregar objeto: são potencialmente milhares
        de linhas e nenhuma regra por linha. Não toca em título pago, cancelado
        ou baixado — o filtro de status é o que garante isso.
        """
        hoje = timezone.localdate()
        qs = Cobranca.objects.filter(
            data_vencimento__lt=hoje,
            status__in=[s for s in EM_ABERTO if s != StatusCobranca.VENCIDA],
        )
        if empresa_id:
            qs = qs.filter(empresa_id=empresa_id)
        return qs.update(status=StatusCobranca.VENCIDA, atualizado_em=timezone.now())
