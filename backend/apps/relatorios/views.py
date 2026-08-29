"""Relatórios e exportação.

Exportação é onde um sistema financeiro costuma cair de joelhos: alguém pede
"todas as cobranças do ano" e o processo carrega 400 mil objetos na memória
para montar uma planilha. Aqui não: a exportação usa `StreamingHttpResponse`
com um iterador sobre o queryset, e o arquivo começa a descer antes de a
consulta terminar. A memória usada é a de um bloco, não a da base.

Os relatórios são os da regra 20, e cada um é uma consulta com um recorte
diferente sobre as mesmas duas tabelas — não há relatório que precise de
tabela própria.
"""
import csv
from datetime import date

from django.http import StreamingHttpResponse
from django.utils import timezone
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.bancos.models import ArquivoBancario, LoteBancario, OcorrenciaBancaria
from apps.cobrancas.models import EM_ABERTO, Cobranca
from apps.pagamentos.models import Pagamento
from core import audit
from core.permissions import PermissaoDeModulo, PertenceAEmpresa
from core.services import RegraDeNegocioError

#: Blocos de 2000: é o ponto em que o `iterator()` do Django deixa de fazer
#: consultas demais e ainda não segura memória demais.
BLOCO = 2000


class _Buffer:
    """`csv.writer` exige um objeto com `write`. Este devolve a linha em vez
    de guardá-la — é o truque que faz o CSV virar um gerador."""

    def write(self, valor):
        return valor


def _streaming_csv(nome_arquivo: str, cabecalho: list[str], linhas):
    escritor = csv.writer(_Buffer(), delimiter=";")

    def gerar():
        # BOM: sem ele o Excel em português abre o CSV com acentuação
        # quebrada, e a primeira impressão do relatório é de sistema ruim.
        yield "﻿"
        yield escritor.writerow(cabecalho)
        for linha in linhas:
            yield escritor.writerow(linha)

    resposta = StreamingHttpResponse(gerar(), content_type="text/csv; charset=utf-8")
    resposta["Content-Disposition"] = f'attachment; filename="{nome_arquivo}"'
    return resposta


class _Base(APIView):
    permission_classes = [IsAuthenticated, PermissaoDeModulo, PertenceAEmpresa]
    modulo = "relatorios"

    def periodo(self, request):
        hoje = timezone.localdate()
        inicio = request.query_params.get("inicio")
        fim = request.query_params.get("fim")
        return (
            date.fromisoformat(inicio) if inicio else hoje.replace(day=1),
            date.fromisoformat(fim) if fim else hoje,
        )

    def registrar_exportacao(self, request, nome: str, quantidade: int | None = None):
        """Exportação é evento de auditoria, não detalhe de UI.

        Quem levou a carteira inteira embora num CSV é a primeira pergunta em
        qualquer incidente de vazamento — e a resposta precisa existir antes
        do incidente.
        """
        audit.registrar(
            "EXPORTACAO", modulo="relatorios", empresa_id=request.empresa_id,
            usuario=request.user, descricao=f"Exportou {nome}",
            metadados={"filtros": dict(request.query_params), "linhas": quantidade},
        )


class RelatorioCobrancasView(_Base):
    """Cobranças do período, com o recorte pedido. CSV ou JSON."""

    def get(self, request):
        inicio, fim = self.periodo(request)
        qs = (
            Cobranca.objects.filter(
                empresa_id=request.empresa_id,
                data_vencimento__gte=inicio, data_vencimento__lte=fim,
            )
            .select_related("cliente", "conta_bancaria")
            .order_by("data_vencimento", "numero")
        )
        situacao = request.query_params.getlist("status")
        if situacao:
            qs = qs.filter(status__in=situacao)
        if request.query_params.get("cliente"):
            qs = qs.filter(cliente_id=request.query_params["cliente"])

        if request.query_params.get("formato", "csv") != "csv":
            from apps.cobrancas.serializers import CobrancaListaSerializer

            dados = CobrancaListaSerializer(qs[:5000], many=True).data
            self.registrar_exportacao(request, "cobranças (JSON)", len(dados))
            return Response(dados)

        self.registrar_exportacao(request, "cobranças (CSV)")
        cabecalho = [
            "Número", "Cliente", "CPF/CNPJ", "Descrição", "Documento",
            "Nosso número", "Valor", "Emissão", "Vencimento", "Situação",
            "Pagamento", "Valor pago", "Conta", "Dias em atraso",
        ]

        def linhas():
            for c in qs.iterator(chunk_size=BLOCO):
                yield [
                    c.numero, c.cliente.nome, c.cliente.documento_formatado,
                    c.descricao, c.documento, c.nosso_numero,
                    f"{c.valor:.2f}".replace(".", ","),
                    c.data_emissao.strftime("%d/%m/%Y"),
                    c.data_vencimento.strftime("%d/%m/%Y"),
                    c.get_status_display(),
                    c.data_pagamento.strftime("%d/%m/%Y") if c.data_pagamento else "",
                    f"{c.valor_pago:.2f}".replace(".", ",") if c.valor_pago else "",
                    c.conta_bancaria.nome if c.conta_bancaria else "",
                    c.dias_em_atraso or "",
                ]

        return _streaming_csv(
            f"cobrancas-{inicio:%Y%m%d}-{fim:%Y%m%d}.csv", cabecalho, linhas()
        )


class RelatorioPagamentosView(_Base):
    def get(self, request):
        inicio, fim = self.periodo(request)
        qs = (
            Pagamento.objects.filter(
                empresa_id=request.empresa_id, estornado=False,
                data_pagamento__gte=inicio, data_pagamento__lte=fim,
            )
            .select_related("cobranca", "cobranca__cliente", "conta_bancaria")
            .order_by("data_pagamento")
        )
        self.registrar_exportacao(request, "pagamentos")
        cabecalho = [
            "Data pagamento", "Data crédito", "Cliente", "Cobrança", "Descrição",
            "Valor", "Juros", "Multa", "Desconto", "Tarifa", "Líquido",
            "Origem", "Conta",
        ]

        def linhas():
            for p in qs.iterator(chunk_size=BLOCO):
                yield [
                    p.data_pagamento.strftime("%d/%m/%Y"),
                    p.data_credito.strftime("%d/%m/%Y") if p.data_credito else "",
                    p.cobranca.cliente.nome, p.cobranca.numero, p.cobranca.descricao,
                    f"{p.valor:.2f}".replace(".", ","),
                    f"{p.juros:.2f}".replace(".", ","),
                    f"{p.multa:.2f}".replace(".", ","),
                    f"{p.desconto:.2f}".replace(".", ","),
                    f"{p.tarifa:.2f}".replace(".", ","),
                    f"{p.valor_liquido:.2f}".replace(".", ","),
                    p.get_origem_display(),
                    p.conta_bancaria.nome if p.conta_bancaria else "",
                ]

        return _streaming_csv(
            f"pagamentos-{inicio:%Y%m%d}-{fim:%Y%m%d}.csv", cabecalho, linhas()
        )


class RelatorioInadimplenciaView(_Base):
    """Quem deve, quanto e há quanto tempo — agrupado por cliente.

    Agrupa no banco, não em Python: uma carteira inadimplente de 20 mil
    títulos vira 800 linhas de cliente, e trazer os 20 mil para somar aqui
    seria o caminho para o timeout.
    """

    def get(self, request):
        from django.db.models import Count, Min, Sum

        hoje = timezone.localdate()
        qs = (
            Cobranca.objects.filter(
                empresa_id=request.empresa_id,
                status__in=EM_ABERTO, data_vencimento__lt=hoje,
            )
            .values("cliente_id", "cliente__nome", "cliente__cpf_cnpj",
                    "cliente__telefone", "cliente__email")
            .annotate(
                titulos=Count("id"),
                valor=Sum("valor"),
                vencimento_mais_antigo=Min("data_vencimento"),
            )
            .order_by("-valor")
        )

        if request.query_params.get("formato", "json") == "csv":
            self.registrar_exportacao(request, "inadimplência (CSV)")
            cabecalho = ["Cliente", "CPF/CNPJ", "Telefone", "E-mail", "Títulos",
                         "Valor em aberto", "Vencimento mais antigo", "Dias"]

            def linhas():
                for l in qs.iterator(chunk_size=BLOCO):
                    dias = (hoje - l["vencimento_mais_antigo"]).days
                    yield [
                        l["cliente__nome"], l["cliente__cpf_cnpj"],
                        l["cliente__telefone"], l["cliente__email"], l["titulos"],
                        f"{l['valor']:.2f}".replace(".", ","),
                        l["vencimento_mais_antigo"].strftime("%d/%m/%Y"), dias,
                    ]

            return _streaming_csv(f"inadimplencia-{hoje:%Y%m%d}.csv", cabecalho, linhas())

        self.registrar_exportacao(request, "inadimplência")
        return Response([
            {
                "cliente_id": l["cliente_id"],
                "cliente": l["cliente__nome"],
                "documento": l["cliente__cpf_cnpj"],
                "telefone": l["cliente__telefone"],
                "email": l["cliente__email"],
                "titulos": l["titulos"],
                "valor": l["valor"],
                "vencimento_mais_antigo": l["vencimento_mais_antigo"],
                "dias_em_atraso": (hoje - l["vencimento_mais_antigo"]).days,
            }
            for l in qs[:2000]
        ])


class RelatorioRemessasView(_Base):
    def get(self, request):
        inicio, fim = self.periodo(request)
        qs = (
            LoteBancario.objects.filter(
                empresa_id=request.empresa_id,
                criado_em__date__gte=inicio, criado_em__date__lte=fim,
            )
            .select_related("conta", "arquivo_remessa", "criado_por")
            .order_by("-numero")
        )
        from apps.bancos.serializers import LoteBancarioSerializer

        self.registrar_exportacao(request, "remessas")
        return Response(LoteBancarioSerializer(
            qs[:1000], many=True, context={"request": request}
        ).data)


class RelatorioRetornosView(_Base):
    def get(self, request):
        from apps.bancos.bancos import TipoArquivo
        from apps.bancos.serializers import ArquivoBancarioSerializer

        inicio, fim = self.periodo(request)
        qs = (
            ArquivoBancario.objects.filter(
                empresa_id=request.empresa_id, tipo=TipoArquivo.RETORNO,
                recebido_em__date__gte=inicio, recebido_em__date__lte=fim,
            )
            .select_related("conta")
            .order_by("-recebido_em")
        )
        self.registrar_exportacao(request, "retornos")
        return Response(ArquivoBancarioSerializer(
            qs[:1000], many=True, context={"request": request}
        ).data)


class RelatorioRejeicoesView(_Base):
    """Por que os títulos foram recusados — agrupado por motivo.

    É o relatório que faz a taxa de rejeição cair: quando 80% das recusas são
    'CEP inválido', o problema é o cadastro, e conserta-se de uma vez.
    """

    def get(self, request):
        from django.db.models import Count

        from apps.bancos.bancos import TipoOcorrencia

        inicio, fim = self.periodo(request)
        qs = OcorrenciaBancaria.objects.filter(
            empresa_id=request.empresa_id,
            tipo__in=[TipoOcorrencia.ENTRADA_REJEITADA, TipoOcorrencia.BAIXA_REJEITADA,
                      TipoOcorrencia.ALTERACAO_REJEITADA],
            data_ocorrencia__gte=inicio, data_ocorrencia__lte=fim,
        )

        # Os motivos vêm numa lista JSON por ocorrência; a contagem por motivo
        # é feita aqui porque agrupar dentro de JSON no Postgres exigiria SQL
        # cru para pouco ganho — o volume de rejeições é pequeno por natureza.
        from apps.bancos.adapters.safra.ocorrencias import MOTIVOS

        contagem: dict[str, int] = {}
        for ocorrencia in qs.only("motivos").iterator(chunk_size=BLOCO):
            for motivo in ocorrencia.motivos or ["--"]:
                contagem[motivo] = contagem.get(motivo, 0) + 1

        self.registrar_exportacao(request, "rejeições")
        return Response({
            "total": qs.count(),
            "por_codigo": list(
                qs.values("codigo", "descricao").annotate(quantidade=Count("id"))
                .order_by("-quantidade")
            ),
            "por_motivo": sorted(
                (
                    {
                        "motivo": codigo,
                        "descricao": MOTIVOS.get(codigo, "motivo não mapeado"),
                        "quantidade": quantidade,
                    }
                    for codigo, quantidade in contagem.items()
                ),
                key=lambda l: -l["quantidade"],
            ),
        })


class RelatorioConciliacaoView(_Base):
    """Atalho para a conciliação, dentro do menu de relatórios."""

    def get(self, request):
        from apps.conciliacao.views import ConciliacaoView

        self.registrar_exportacao(request, "conciliação")
        return ConciliacaoView().get(request)
