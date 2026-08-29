"""Orquestração bancária: lote, remessa, retorno.

Este é o módulo em que o produto acontece. Três serviços, e a fronteira entre
eles é a mesma do enunciado: montar o lote é decisão de negócio, montar o
arquivo é tradução (e mora no adapter), aplicar o retorno é decisão de negócio
de novo.

Duas invariantes atravessam tudo aqui e valem mais que qualquer outra coisa:

**Nada trava a requisição.** Todo método pesado é chamado por uma tarefa
Celery e trabalha em blocos de `LOTE_TAMANHO_BLOCO`. A API cria o lote, devolve
o número e volta em milissegundos.

**Processar duas vezes não cobra duas vezes.** A idempotência não é uma
verificação no começo da função — é a forma dos dados: `OcorrenciaBancaria` é
única por (arquivo, linha) e `Pagamento` é um-para-um com a ocorrência. Rodar
o worker dez vezes sobre o mesmo arquivo produz exatamente o mesmo estado que
rodá-lo uma. A verificação por hash existe além disso, para poupar trabalho —
não para garantir correção.
"""
from __future__ import annotations

import hashlib
import logging
from dataclasses import dataclass
from datetime import date
from decimal import Decimal

from django.core.files.base import ContentFile
from django.db import transaction
from django.utils import timezone

from apps.bancos.adapters import adapter_para
from apps.bancos.adapters.base import (
    ArquivoInvalido,
    DadosSacado,
    ErroDeIntegracao,
    OperacaoNaoSuportada,
    Titulo,
)
from apps.bancos.bancos import (
    OCORRENCIAS_DE_LIQUIDACAO,
    StatusArquivo,
    StatusLote,
    TipoArquivo,
    TipoOcorrencia,
)
from apps.bancos.models import ArquivoBancario, ContaBancaria, LoteBancario, OcorrenciaBancaria
from apps.cobrancas.models import Cobranca, StatusCobranca
from apps.pagamentos.models import OrigemPagamento, Pagamento
from core import audit
from core.services import RegraDeNegocioError

logger = logging.getLogger(__name__)


def hash_conteudo(conteudo: bytes) -> str:
    return hashlib.sha256(conteudo).hexdigest()


def ler_arquivo(campo) -> bytes:
    """Lê um `FileField` inteiro, sempre do começo.

    `campo.read()` direto funciona na primeira vez e devolve b"" na segunda:
    o descritor fica no fim. Isso é invisível no caminho feliz — cada tarefa
    carrega o objeto do banco outra vez — e aparece exatamente onde dói: no
    reprocessamento, que é a operação de recuperação do sistema. O arquivo
    "vazio" que não estava vazio.
    """
    campo.open("rb")
    try:
        return campo.read()
    finally:
        campo.close()


# ══════════════════════════════════════════════════════════════════ tradução
def montar_titulo(cobranca: Cobranca) -> Titulo:
    """Cobrança -> `Titulo`, o DTO que o adapter entende.

    Um lugar só faz essa tradução, e nenhum adapter conhece `Cobranca`. É o
    que permite testar um adapter com objetos de mentira e o que impede que
    um banco novo comece a ler campos do ORM.
    """
    cliente = cobranca.cliente
    conta = cobranca.conta_bancaria
    return Titulo(
        id_interno=cobranca.pk,
        nosso_numero=cobranca.nosso_numero,
        seu_numero=cobranca.seu_numero or str(cobranca.numero),
        documento=cobranca.documento or str(cobranca.numero),
        valor=cobranca.valor,
        emissao=cobranca.data_emissao,
        vencimento=cobranca.data_vencimento,
        sacado=DadosSacado(
            nome=cliente.nome,
            documento=cliente.cpf_cnpj,
            logradouro=cliente.logradouro,
            numero=cliente.numero,
            complemento=cliente.complemento,
            bairro=cliente.bairro,
            cidade=cliente.cidade,
            uf=cliente.uf,
            cep=cliente.cep,
            email=cliente.email,
        ),
        especie=conta.especie_titulo if conta else "DS",
        aceite=conta.aceite if conta else False,
        juros_mes_percentual=cobranca.juros_mes_percentual,
        multa_percentual=cobranca.multa_percentual,
        desconto=cobranca.desconto,
        data_limite_desconto=cobranca.data_limite_desconto,
        abatimento=cobranca.abatimento,
        dias_protesto=conta.dias_protesto if conta else 0,
        dias_baixa_automatica=conta.dias_baixa_automatica if conta else 0,
        instrucoes=(conta.instrucoes_boleto if conta else "")[:40],
    )


# ══════════════════════════════════════════════════════════════════ lote
@dataclass
class ResumoValidacao:
    aptas: list[int]
    recusadas: list[tuple[int, str]]

    @property
    def total(self) -> int:
        return len(self.aptas) + len(self.recusadas)


class LoteService:
    """Do 'selecionei 500 cobranças' até o arquivo pronto para o banco."""

    # ------------------------------------------------------------ validação
    @staticmethod
    def validar(cobrancas, conta: ContaBancaria) -> ResumoValidacao:
        """Separa o que pode ir do que não pode, com o motivo de cada recusa.

        Recusar título a título, e não o lote inteiro, é a diferença entre "500
        boletos, 3 pendências para corrigir" e "não foi possível gerar o lote".
        A segunda mensagem faz o operador procurar agulha em palheiro.
        """
        aptas: list[int] = []
        recusadas: list[tuple[int, str]] = []
        vistos: set[tuple] = set()
        hoje = timezone.localdate()

        for cobranca in cobrancas:
            motivo = None
            cliente = cobranca.cliente

            if not cobranca.pode_entrar_em_lote:
                motivo = f"situação '{cobranca.get_status_display()}' não permite envio"
            elif cobranca.valor <= 0:
                motivo = "valor precisa ser maior que zero"
            elif cobranca.data_vencimento < hoje:
                motivo = "vencimento já passou — prorrogue antes de registrar"
            elif not cliente.cpf_cnpj:
                motivo = "cliente sem CPF/CNPJ"
            elif not cliente.endereco_completo_para_boleto:
                motivo = "cliente sem endereço completo (logradouro, cidade, UF e CEP)"
            else:
                # Duplicidade dentro da própria seleção: mesma pessoa, mesmo
                # valor, mesmo vencimento. Quase sempre é a planilha carregada
                # duas vezes, e o banco registraria os dois títulos sem
                # reclamar — a cobrança dobrada só apareceria no telefone.
                chave = (cliente.pk, cobranca.valor, cobranca.data_vencimento)
                if chave in vistos:
                    motivo = "duplicada na seleção (mesmo cliente, valor e vencimento)"
                else:
                    vistos.add(chave)

            if motivo:
                recusadas.append((cobranca.pk, motivo))
            else:
                aptas.append(cobranca.pk)

        return ResumoValidacao(aptas=aptas, recusadas=recusadas)

    # -------------------------------------------------------------- criação
    @staticmethod
    @transaction.atomic
    def criar(*, empresa_id: int, conta: ContaBancaria, cobranca_ids: list[int],
              usuario=None) -> LoteBancario:
        """Cria o lote e reserva a faixa de nosso número, tudo numa transação.

        A reserva acontece aqui, e não na montagem do arquivo, por um motivo
        prático: se o worker morrer no meio da montagem, os números já estão
        presos ao lote e o reprocessamento gera o mesmo arquivo. Reservar
        durante a montagem faria cada retentativa consumir uma faixa nova, e a
        faixa contratada com o banco é finita.
        """
        from django.conf import settings

        if not cobranca_ids:
            raise RegraDeNegocioError("Selecione ao menos uma cobrança.", "cobrancas")
        if len(cobranca_ids) > settings.LOTE_MAX_TITULOS:
            raise RegraDeNegocioError(
                f"Um lote comporta até {settings.LOTE_MAX_TITULOS} títulos. "
                f"Foram selecionados {len(cobranca_ids)} — divida em lotes menores.",
                "cobrancas",
            )
        if not conta.ativa:
            raise RegraDeNegocioError(
                f"A conta '{conta.nome}' está inativa.", "conta_bancaria"
            )

        empresa = conta.empresa
        if not empresa.apta_a_emitir:
            raise RegraDeNegocioError(
                "O cadastro da empresa está incompleto para emitir títulos: "
                "confira CNPJ, razão social e endereço completo.",
                "empresa",
            )
        if not empresa.dentro_do_limite(len(cobranca_ids)):
            raise RegraDeNegocioError(
                f"O plano {empresa.get_plano_display()} permite "
                f"{empresa.limite_titulos_mes()} títulos por mês e este lote "
                "ultrapassa o limite.",
                "plano",
            )

        # `select_for_update` impede que a mesma cobrança entre em dois lotes
        # criados ao mesmo tempo — o que geraria dois registros no banco para
        # o mesmo título e uma cobrança em duplicidade para o sacado.
        cobrancas = list(
            Cobranca.objects.select_for_update()
            .filter(empresa_id=empresa_id, pk__in=cobranca_ids)
            .select_related("cliente")
        )
        if len(cobrancas) != len(set(cobranca_ids)):
            raise RegraDeNegocioError(
                "Parte das cobranças selecionadas não existe ou é de outra empresa.",
                "cobrancas",
            )

        resumo = LoteService.validar(cobrancas, conta)
        if not resumo.aptas:
            detalhe = "; ".join(f"#{pk}: {motivo}" for pk, motivo in resumo.recusadas[:5])
            raise RegraDeNegocioError(
                f"Nenhuma das {resumo.total} cobranças pode ser enviada. {detalhe}",
                "cobrancas",
            )

        aptas = [c for c in cobrancas if c.pk in set(resumo.aptas)]
        faixa = conta.reservar_faixa(len(aptas))

        lote = LoteBancario.objects.create(
            empresa_id=empresa_id,
            conta=conta,
            status=StatusLote.RASCUNHO,
            quantidade=len(aptas),
            valor_total=sum((c.valor for c in aptas), Decimal("0")),
            criado_por=usuario,
            etapa="Aguardando montagem do arquivo",
        )

        for cobranca, numero in zip(aptas, faixa):
            cobranca.lote = lote
            cobranca.conta_bancaria = conta
            cobranca.nosso_numero = str(numero)
            cobranca.status = StatusCobranca.PENDENTE
            cobranca.mensagem_erro = ""
        Cobranca.objects.bulk_update(
            aptas, ["lote", "conta_bancaria", "nosso_numero", "status", "mensagem_erro"]
        )

        # As recusadas ficam marcadas para o operador achá-las depois. Não
        # entram no lote e não travam nada.
        if resumo.recusadas:
            for pk, motivo in resumo.recusadas:
                Cobranca.objects.filter(pk=pk, empresa_id=empresa_id).update(
                    mensagem_erro=f"Fora do lote #{lote.numero}: {motivo}"[:500]
                )

        audit.registrar(
            "LOTE_CRIADO", modulo="bancos", instancia=lote, empresa_id=empresa_id,
            descricao=f"Lote #{lote.numero} com {len(aptas)} título(s)",
            metadados={"recusadas": len(resumo.recusadas), "conta": conta.nome},
        )
        return lote

    # ------------------------------------------------------------- remessa
    @staticmethod
    def montar_remessa(lote: LoteBancario) -> ArquivoBancario:
        """Gera o arquivo de remessa do lote e guarda como `ArquivoBancario`."""
        if lote.status not in (StatusLote.RASCUNHO, StatusLote.ERRO, StatusLote.MONTANDO):
            raise RegraDeNegocioError(
                f"O lote #{lote.numero} está '{lote.get_status_display()}' e não "
                "pode ser remontado. Um arquivo já enviado não se reescreve — "
                "crie um lote novo.",
                "lote",
            )

        LoteBancario.objects.filter(pk=lote.pk).update(
            status=StatusLote.MONTANDO, mensagem_erro=""
        )
        lote.marcar_progresso(5, "Lendo cobranças")

        cobrancas = list(
            lote.cobrancas.select_related("cliente", "conta_bancaria").order_by("pk")
        )
        if not cobrancas:
            raise RegraDeNegocioError(f"O lote #{lote.numero} está vazio.", "lote")

        lote.marcar_progresso(20, "Montando o arquivo")
        adapter = adapter_para(lote.conta)
        titulos = [montar_titulo(c) for c in cobrancas]

        try:
            resultado = adapter.registrar_cobrancas_em_lote(titulos)
        except ErroDeIntegracao as exc:
            LoteService._falhar(lote, str(exc))
            raise

        lote.marcar_progresso(60, "Gravando resultado")
        por_id = {r.id_interno: r for r in resultado.resultados}

        with transaction.atomic():
            arquivo = ArquivoBancario.objects.create(
                empresa_id=lote.empresa_id,
                conta=lote.conta,
                banco=lote.conta.banco,
                tipo=TipoArquivo.REMESSA,
                nome_original=resultado.nome_arquivo,
                hash_arquivo=hash_conteudo(resultado.conteudo),
                tamanho_bytes=len(resultado.conteudo),
                recebido_em=timezone.now(),
                processado_em=timezone.now(),
                data_movimento=timezone.localdate(),
                quantidade_registros=len(resultado.resultados),
                quantidade_processada=resultado.quantidade_ok,
                quantidade_com_erro=resultado.quantidade_erro,
                valor_total=lote.valor_total,
                status=(
                    StatusArquivo.PROCESSADO if not resultado.quantidade_erro
                    else StatusArquivo.PROCESSADO_COM_ERROS
                ),
                origem="SISTEMA",
            )
            arquivo.arquivo.save(
                resultado.nome_arquivo, ContentFile(resultado.conteudo), save=True
            )

            atualizadas = []
            for cobranca in cobrancas:
                r = por_id.get(cobranca.pk)
                if r is None or not r.ok:
                    cobranca.status = StatusCobranca.ERRO
                    cobranca.mensagem_erro = (r.erro if r else "não incluída no arquivo")[:500]
                else:
                    cobranca.status = StatusCobranca.ENVIADA_AO_BANCO
                    cobranca.nosso_numero = r.nosso_numero or cobranca.nosso_numero
                    cobranca.codigo_barras = r.codigo_barras
                    cobranca.linha_digitavel = r.linha_digitavel
                    cobranca.identificador_bancario = r.identificador_bancario
                    cobranca.mensagem_erro = ""
                atualizadas.append(cobranca)

            Cobranca.objects.bulk_update(
                atualizadas,
                ["status", "nosso_numero", "codigo_barras", "linha_digitavel",
                 "identificador_bancario", "mensagem_erro"],
                batch_size=500,
            )

            LoteBancario.objects.filter(pk=lote.pk).update(
                status=StatusLote.PRONTO,
                arquivo_remessa=arquivo,
                numero_remessa=resultado.numero_remessa,
                quantidade_rejeitada=resultado.quantidade_erro,
                progresso=100,
                etapa="Arquivo pronto para envio",
            )

        audit.registrar(
            "REMESSA_GERADA", modulo="bancos", instancia=lote, empresa_id=lote.empresa_id,
            descricao=f"Remessa {resultado.nome_arquivo} com {resultado.quantidade_ok} título(s)",
            metadados={"arquivo_id": arquivo.pk, "erros": resultado.quantidade_erro},
        )
        return arquivo

    @staticmethod
    def enviar(lote: LoteBancario) -> str:
        """Transmite a remessa ao banco, quando a conta tem canal automático.

        Sem canal, não é falha: o arquivo fica para download e o lote vai para
        `ENVIADO` mesmo assim, porque quem envia passa a ser o operador. Marcar
        como erro faria o painel mentir sobre um fluxo que funciona.
        """
        if lote.status not in (StatusLote.PRONTO, StatusLote.ERRO):
            raise RegraDeNegocioError(
                f"O lote #{lote.numero} está '{lote.get_status_display()}'.", "lote"
            )
        if lote.arquivo_remessa is None:
            raise RegraDeNegocioError("O lote ainda não tem arquivo de remessa.", "lote")

        conteudo = ler_arquivo(lote.arquivo_remessa.arquivo)
        adapter = adapter_para(lote.conta)
        protocolo = ""
        try:
            protocolo = adapter.transmitir(conteudo, lote.arquivo_remessa.nome_original)
        except OperacaoNaoSuportada:
            from apps.bancos.transporte import gravar_diretorio_saida

            protocolo = gravar_diretorio_saida(
                lote.arquivo_remessa.nome_original, conteudo
            )
            logger.info("Lote #%s sem transmissão automática: arquivo em %s",
                        lote.numero, protocolo)
        except ErroDeIntegracao as exc:
            LoteService._falhar(lote, str(exc))
            raise

        LoteBancario.objects.filter(pk=lote.pk).update(
            status=StatusLote.ENVIADO,
            protocolo_banco=protocolo[:120],
            enviado_em=timezone.now(),
            progresso=100,
            etapa="Enviado — aguardando confirmação do banco",
        )
        audit.registrar(
            "REMESSA_ENVIADA", modulo="bancos", instancia=lote, empresa_id=lote.empresa_id,
            descricao=f"Lote #{lote.numero} enviado", metadados={"protocolo": protocolo},
        )
        return protocolo

    @staticmethod
    def _falhar(lote: LoteBancario, mensagem: str) -> None:
        LoteBancario.objects.filter(pk=lote.pk).update(
            status=StatusLote.ERRO, mensagem_erro=mensagem[:2000], etapa="Falhou"
        )
        logger.error("Lote #%s falhou: %s", lote.numero, mensagem)


# ══════════════════════════════════════════════════════════════════ retorno
class RetornoService:
    """Do arquivo do banco até a cobrança atualizada."""

    @staticmethod
    def registrar_arquivo(*, empresa_id: int, nome: str, conteudo: bytes,
                          banco: str, conta: ContaBancaria | None = None,
                          origem: str = "UPLOAD") -> tuple[ArquivoBancario, bool]:
        """Guarda o arquivo. Devolve (arquivo, é_novo).

        Conteúdo idêntico já registrado devolve o registro existente em vez de
        criar outro. Não é otimização: é o que impede que o operador, ao subir
        o mesmo retorno duas vezes porque "não pareceu ter funcionado", gere
        dois conjuntos de ocorrências.
        """
        if not conteudo:
            raise RegraDeNegocioError("Arquivo vazio.", "arquivo")

        digest = hash_conteudo(conteudo)
        existente = ArquivoBancario.objects.filter(
            empresa_id=empresa_id, hash_arquivo=digest
        ).first()
        if existente is not None:
            logger.info("Retorno %s já conhecido (arquivo #%s)", nome, existente.pk)
            return existente, False

        arquivo = ArquivoBancario(
            empresa_id=empresa_id,
            conta=conta,
            banco=banco,
            tipo=TipoArquivo.RETORNO,
            nome_original=nome[:255],
            hash_arquivo=digest,
            tamanho_bytes=len(conteudo),
            recebido_em=timezone.now(),
            status=StatusArquivo.PENDENTE,
            origem=origem,
        )
        arquivo.arquivo.save(nome, ContentFile(conteudo), save=False)
        arquivo.save()
        return arquivo, True

    @staticmethod
    def processar(arquivo: ArquivoBancario) -> dict:
        """Lê o arquivo inteiro e aplica tudo. Idempotente por construção.

        Devolve um resumo — é ele que vira o relatório de processamento da
        regra 8: quantos registros, quantos aplicados, quantos órfãos, quantos
        ilegíveis.
        """
        from django.conf import settings

        if arquivo.tipo != TipoArquivo.RETORNO:
            raise RegraDeNegocioError("Só arquivo de retorno é processado.", "arquivo")

        conta = arquivo.conta or RetornoService._descobrir_conta(arquivo)
        if conta is None:
            RetornoService._falhar(
                arquivo,
                "Não foi possível determinar a conta bancária deste retorno. "
                "Selecione a conta e reprocesse.",
            )
            raise RegraDeNegocioError("Retorno sem conta bancária identificável.", "arquivo")

        ArquivoBancario.objects.filter(pk=arquivo.pk).update(
            status=StatusArquivo.PROCESSANDO, mensagem_erro=""
        )

        adapter = adapter_para(conta)
        try:
            retorno = adapter.processar_retorno(ler_arquivo(arquivo.arquivo))
        except ArquivoInvalido as exc:
            RetornoService._falhar(arquivo, str(exc))
            raise
        except Exception as exc:  # noqa: BLE001
            RetornoService._falhar(arquivo, f"Falha ao ler o arquivo: {exc}")
            raise

        resumo = {
            "registros": len(retorno.registros),
            "aplicados": 0,
            "orfaos": 0,
            "pagamentos": 0,
            "valor_pago": Decimal("0"),
            "ignoradas": len(retorno.linhas_ignoradas),
            "rejeicoes": 0,
        }

        bloco = settings.LOTE_TAMANHO_BLOCO
        registros = retorno.registros
        for inicio in range(0, len(registros), bloco):
            # Um bloco por transação. Arquivo de 50 mil linhas numa transação
            # só seguraria locks por minutos e estouraria a memória do worker;
            # em blocos, uma falha no bloco 40 preserva os 39 anteriores e o
            # reprocessamento retoma sem duplicar (as ocorrências já gravadas
            # são reconhecidas).
            with transaction.atomic():
                for registro in registros[inicio:inicio + bloco]:
                    RetornoService._aplicar(arquivo, conta, registro, resumo)

        com_erro = resumo["orfaos"] + resumo["ignoradas"]
        ArquivoBancario.objects.filter(pk=arquivo.pk).update(
            conta=conta,
            status=(StatusArquivo.PROCESSADO if not com_erro
                    else StatusArquivo.PROCESSADO_COM_ERROS),
            processado_em=timezone.now(),
            data_movimento=retorno.cabecalho.data_movimento,
            quantidade_registros=resumo["registros"],
            quantidade_processada=resumo["aplicados"],
            quantidade_com_erro=com_erro,
            valor_total=resumo["valor_pago"],
            mensagem_erro=RetornoService._descrever_pendencias(retorno, resumo),
        )

        audit.registrar(
            "RETORNO_PROCESSADO", modulo="bancos", instancia=arquivo,
            empresa_id=arquivo.empresa_id,
            descricao=(
                f"{arquivo.nome_original}: {resumo['aplicados']} de "
                f"{resumo['registros']} registro(s), {resumo['pagamentos']} pagamento(s)"
            ),
            metadados={k: str(v) for k, v in resumo.items()},
        )
        logger.info("Retorno #%s processado: %s", arquivo.pk, resumo)
        return resumo

    # ------------------------------------------------------------- efeitos
    @staticmethod
    def _aplicar(arquivo, conta, registro, resumo: dict) -> None:
        cobranca = RetornoService._achar_cobranca(arquivo.empresa_id, conta, registro)

        ocorrencia, criada = OcorrenciaBancaria.objects.get_or_create(
            arquivo=arquivo,
            linha=registro.linha,
            defaults={
                "empresa_id": arquivo.empresa_id,
                "cobranca": cobranca,
                "tipo": registro.tipo,
                "codigo": registro.codigo,
                "descricao": registro.descricao[:180],
                "motivos": registro.motivos,
                "motivos_descricao": registro.motivos_descricao[:500],
                "nosso_numero": registro.nosso_numero[:20],
                "seu_numero": registro.seu_numero[:40],
                "data_ocorrencia": registro.data_ocorrencia,
                "data_credito": registro.data_credito,
                "valor_titulo": registro.valor_titulo,
                "valor_pago": registro.valor_pago,
                "valor_juros": registro.valor_juros,
                "valor_multa": registro.valor_multa,
                "valor_desconto": registro.valor_desconto,
                "valor_abatimento": registro.valor_abatimento,
                "valor_tarifa": registro.valor_tarifa,
                "banco_recebedor": registro.banco_recebedor[:3],
                "agencia_recebedora": registro.agencia_recebedora[:8],
                "conteudo_linha": registro.conteudo,
            },
        )

        # Reprocessamento de ocorrência órfã que agora encontrou dona: o
        # título foi cadastrado depois do retorno chegar. Acontece, e a
        # segunda passada resolve sem intervenção.
        if not criada and ocorrencia.cobranca_id is None and cobranca is not None:
            ocorrencia.cobranca = cobranca
            ocorrencia.save(update_fields=["cobranca", "atualizado_em"])

        if registro.tipo == TipoOcorrencia.ENTRADA_REJEITADA:
            resumo["rejeicoes"] += 1

        if cobranca is None:
            resumo["orfaos"] += 1
            return

        if ocorrencia.aplicada:
            # Já aplicada numa passada anterior. Sair aqui é o coração da
            # idempotência do dinheiro.
            resumo["aplicados"] += 1
            return

        RetornoService._efeito_na_cobranca(cobranca, ocorrencia, registro, conta, resumo)

        OcorrenciaBancaria.objects.filter(pk=ocorrencia.pk).update(aplicada=True)
        resumo["aplicados"] += 1

    @staticmethod
    def _efeito_na_cobranca(cobranca, ocorrencia, registro, conta, resumo: dict) -> None:
        tipo = registro.tipo
        campos: list[str] = []

        if tipo in OCORRENCIAS_DE_LIQUIDACAO:
            pagamento, criado = Pagamento.objects.get_or_create(
                ocorrencia=ocorrencia,
                defaults={
                    "empresa_id": cobranca.empresa_id,
                    "cobranca": cobranca,
                    "conta_bancaria": conta,
                    "origem": OrigemPagamento.RETORNO,
                    "data_pagamento": registro.data_ocorrencia or timezone.localdate(),
                    "data_credito": registro.data_credito,
                    "valor": registro.valor_pago or registro.valor_titulo,
                    "juros": registro.valor_juros,
                    "multa": registro.valor_multa,
                    "desconto": registro.valor_desconto,
                    "abatimento": registro.valor_abatimento,
                    "tarifa": registro.valor_tarifa,
                    "banco_recebedor": registro.banco_recebedor[:3],
                    "agencia_recebedora": registro.agencia_recebedora[:8],
                },
            )
            if criado:
                resumo["pagamentos"] += 1
                resumo["valor_pago"] += pagamento.valor

            cobranca.status = StatusCobranca.PAGA
            cobranca.data_pagamento = pagamento.data_pagamento
            cobranca.data_liquidacao = pagamento.data_credito or pagamento.data_pagamento
            cobranca.valor_pago = pagamento.valor
            cobranca.valor_juros_recebido = pagamento.juros
            cobranca.valor_multa_recebida = pagamento.multa
            cobranca.valor_desconto_concedido = pagamento.desconto
            cobranca.valor_tarifa = pagamento.tarifa
            cobranca.mensagem_erro = ""
            campos = ["status", "data_pagamento", "data_liquidacao", "valor_pago",
                      "valor_juros_recebido", "valor_multa_recebida",
                      "valor_desconto_concedido", "valor_tarifa", "mensagem_erro"]

        elif tipo == TipoOcorrencia.ENTRADA_CONFIRMADA:
            # Confirmada é o marco em que o boleto pode ser cobrado do sacado:
            # o título existe no banco e o pagamento será reconhecido.
            cobranca.status = StatusCobranca.REGISTRADA
            cobranca.mensagem_erro = ""
            campos = ["status", "mensagem_erro"]

        elif tipo == TipoOcorrencia.ENTRADA_REJEITADA:
            cobranca.status = StatusCobranca.REJEITADA
            cobranca.mensagem_erro = (
                registro.motivos_descricao or registro.descricao
            )[:500]
            # Devolve o título ao pool: sem lote, ele reaparece na tela de
            # "prontas para envio" depois de corrigido.
            cobranca.lote = None
            campos = ["status", "mensagem_erro", "lote"]

        elif tipo == TipoOcorrencia.BAIXA:
            # Baixa em título já pago não o "despaga". O banco manda baixa
            # depois da liquidação em algumas carteiras, e obedecer cegamente
            # apagaria um pagamento real do dashboard.
            if cobranca.status != StatusCobranca.PAGA:
                cobranca.status = StatusCobranca.BAIXADA
                campos = ["status"]

        elif tipo == TipoOcorrencia.VENCIMENTO_ALTERADO:
            if registro.data_vencimento:
                cobranca.data_vencimento = registro.data_vencimento
                if cobranca.status == StatusCobranca.VENCIDA:
                    cobranca.status = StatusCobranca.REGISTRADA
                campos = ["data_vencimento", "status"]

        elif tipo == TipoOcorrencia.ABATIMENTO_CONCEDIDO:
            cobranca.abatimento = registro.valor_abatimento
            campos = ["abatimento"]

        elif tipo == TipoOcorrencia.ABATIMENTO_CANCELADO:
            cobranca.abatimento = Decimal("0")
            campos = ["abatimento"]

        elif tipo == TipoOcorrencia.TARIFA:
            cobranca.valor_tarifa = (cobranca.valor_tarifa or 0) + registro.valor_tarifa
            campos = ["valor_tarifa"]

        # Ocorrências informativas (protesto, alteração confirmada, tipo
        # desconhecido) ficam registradas e não mexem no estado. É de
        # propósito: elas contam uma história, não mudam o saldo.

        if campos:
            cobranca.save(update_fields=[*campos, "atualizado_em"])

    # ------------------------------------------------------------ auxiliares
    @staticmethod
    def _achar_cobranca(empresa_id: int, conta, registro):
        """Casa a linha do retorno com uma cobrança.

        Ordem deliberada. O nosso número é o identificador que o banco carimba
        e devolve — é a única chave confiável, e vem primeiro. O seu número é
        nosso e o banco *deveria* devolvê-lo intacto, mas nem sempre devolve
        limpo; serve de rede. Casar por valor e vencimento não entra na lista:
        duas cobranças de mesmo valor no mesmo dia são o caso comum de uma
        carteira de mensalidades, e errar aqui dá baixa no título do cliente
        errado.
        """
        base = Cobranca.objects.filter(empresa_id=empresa_id)

        numero = (registro.nosso_numero or "").lstrip("0")
        if numero:
            cobranca = base.filter(
                conta_bancaria=conta, nosso_numero=numero
            ).select_related("cliente").first()
            if cobranca:
                return cobranca

        seu = (registro.seu_numero or "").strip()
        if seu:
            cobranca = base.filter(
                conta_bancaria=conta, seu_numero=seu
            ).select_related("cliente").first()
            if cobranca:
                return cobranca

        return None

    @staticmethod
    def _descobrir_conta(arquivo: ArquivoBancario) -> ContaBancaria | None:
        """Uma conta ativa daquele banco na empresa. Duas: não adivinha.

        Adivinhar entre duas contas do mesmo banco daria baixa em títulos do
        convênio errado — o nosso número pode coincidir entre convênios.
        """
        contas = list(
            ContaBancaria.objects.filter(
                empresa_id=arquivo.empresa_id, banco=arquivo.banco, ativa=True
            )[:2]
        )
        return contas[0] if len(contas) == 1 else None

    @staticmethod
    def _descrever_pendencias(retorno, resumo: dict) -> str:
        partes = []
        if resumo["orfaos"]:
            partes.append(
                f"{resumo['orfaos']} título(s) do retorno não foram encontrados "
                "no sistema — veja a tela de ocorrências sem cobrança."
            )
        if retorno.linhas_ignoradas:
            amostra = "; ".join(
                f"linha {n}: {m}" for n, m in retorno.linhas_ignoradas[:3]
            )
            partes.append(
                f"{len(retorno.linhas_ignoradas)} linha(s) não interpretada(s). {amostra}"
            )
        return " ".join(partes)[:2000]

    @staticmethod
    def _falhar(arquivo: ArquivoBancario, mensagem: str) -> None:
        ArquivoBancario.objects.filter(pk=arquivo.pk).update(
            status=StatusArquivo.ERRO, mensagem_erro=mensagem[:2000]
        )
        logger.error("Retorno #%s falhou: %s", arquivo.pk, mensagem)


# ═════════════════════════════════════════════════════════════ instruções
def _pedir_instrucao(cobranca: Cobranca, instrucao: str) -> ArquivoBancario:
    """Manda ao banco uma instrução sobre um título já registrado.

    Cancelar, baixar ou prorrogar um título que está no banco não é editar uma
    linha aqui: é um novo registro de remessa, com outro código de ocorrência,
    sobre o mesmo nosso número. Este é o caminho — e ele existe separado da
    montagem de lote porque é sempre de um título só e precisa sair na hora
    (o operador acabou de clicar em "cancelar" e o sacado está no telefone).

    O arquivo gerado é pequeno e vai pelo mesmo canal da remessa normal.
    Quando não há canal automático, ele fica para download como qualquer
    outra remessa — e a cobrança muda de estado aqui de todo jeito, porque a
    decisão de cancelar é da empresa, não do banco. O que o banco confirma
    depois vem no retorno como ocorrência de baixa.
    """
    conta = cobranca.conta_bancaria
    if conta is None:
        raise RegraDeNegocioError(
            "A cobrança não tem conta bancária: não há instrução a enviar.",
            "conta_bancaria",
        )

    adapter = adapter_para(conta)
    titulo = montar_titulo(cobranca)
    titulo.ocorrencia = instrucao

    try:
        resultado = adapter.registrar_cobrancas_em_lote([titulo])
    except OperacaoNaoSuportada as exc:
        # Meio de integração sem instrução avulsa (API pendente, por exemplo).
        # Não impede a decisão local: registra e segue, com o aviso no log.
        logger.warning("Instrução %s não enviada ao banco: %s", instrucao, exc)
        raise RegraDeNegocioError(
            f"Esta conta não sabe enviar a instrução '{instrucao}' ao banco. "
            "Faça a instrução pelo internet banking e depois registre aqui.",
            "conta_bancaria",
        ) from exc

    arquivo = ArquivoBancario.objects.create(
        empresa_id=cobranca.empresa_id,
        conta=conta,
        banco=conta.banco,
        tipo=TipoArquivo.REMESSA,
        nome_original=resultado.nome_arquivo,
        hash_arquivo=hash_conteudo(resultado.conteudo),
        tamanho_bytes=len(resultado.conteudo),
        recebido_em=timezone.now(),
        processado_em=timezone.now(),
        data_movimento=timezone.localdate(),
        quantidade_registros=1,
        quantidade_processada=resultado.quantidade_ok,
        quantidade_com_erro=resultado.quantidade_erro,
        valor_total=cobranca.valor,
        status=StatusArquivo.PROCESSADO,
        origem="SISTEMA",
    )
    arquivo.arquivo.save(resultado.nome_arquivo, ContentFile(resultado.conteudo), save=True)

    try:
        adapter.transmitir(resultado.conteudo, resultado.nome_arquivo)
    except OperacaoNaoSuportada:
        from apps.bancos.transporte import gravar_diretorio_saida

        gravar_diretorio_saida(resultado.nome_arquivo, resultado.conteudo)

    audit.registrar(
        "INSTRUCAO_ENVIADA", modulo="bancos", instancia=cobranca,
        empresa_id=cobranca.empresa_id,
        descricao=f"Instrução {instrucao} para o título {cobranca.nosso_numero}",
        metadados={"arquivo_id": arquivo.pk},
    )
    return arquivo
