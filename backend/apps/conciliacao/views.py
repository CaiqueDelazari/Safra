"""Conciliação — o encontro entre o que se cobrou e o que entrou.

**Não existe tabela de conciliação neste sistema, e é de propósito.** O
enunciado lista `reconciliation` entre as entidades, mas uma tabela aqui seria
uma cópia de números que já existem em `charges` e `payments` — e cópia de
número financeiro é dívida: ou alguém a mantém sincronizada em toda mudança de
status, ou ela mente. E ela sempre acaba mentindo, porque a atualização
esquecida é sempre a de um caso raro (o estorno, a baixa manual, o
reprocessamento), que é justamente o caso em que a conciliação importa.

A conciliação aqui é **derivada**: agregações sobre a verdade, calculadas na
hora, com os mesmos filtros da tela de cobranças. Quando o volume exigir, o
caminho é uma view materializada no Postgres, atualizada pelo banco — não uma
tabela mantida por código de aplicação.
"""
from datetime import date, timedelta
from decimal import Decimal

from django.db.models import Count, DecimalField, Q, Sum, Value
from django.db.models.functions import Coalesce, TruncMonth
from django.utils import timezone
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.cobrancas.models import EM_ABERTO, Cobranca, StatusCobranca
from apps.pagamentos.models import Pagamento
from core.permissions import PermissaoDeModulo, PertenceAEmpresa

ZERO = Value(Decimal("0"), output_field=DecimalField(max_digits=16, decimal_places=2))


def _soma(campo, filtro=None):
    return Coalesce(Sum(campo, filter=filtro), ZERO)


class ConciliacaoView(APIView):
    """Fechamento do período: cobrado, recebido, em aberto, vencido.

    Aceita os mesmos filtros da listagem de cobranças (período, cliente,
    status, banco, conta), porque a pergunta do financeiro é sempre "e no
    recorte que eu estou olhando?".
    """

    permission_classes = [IsAuthenticated, PermissaoDeModulo, PertenceAEmpresa]
    modulo = "conciliacao"

    def get(self, request):
        empresa_id = request.empresa_id
        inicio, fim = _periodo(request)

        cobrancas = Cobranca.objects.filter(empresa_id=empresa_id)
        pagamentos = Pagamento.objects.filter(empresa_id=empresa_id, estornado=False)

        if request.query_params.get("cliente"):
            cobrancas = cobrancas.filter(cliente_id=request.query_params["cliente"])
            pagamentos = pagamentos.filter(cobranca__cliente_id=request.query_params["cliente"])
        if request.query_params.get("conta_bancaria"):
            conta = request.query_params["conta_bancaria"]
            cobrancas = cobrancas.filter(conta_bancaria_id=conta)
            pagamentos = pagamentos.filter(conta_bancaria_id=conta)
        if request.query_params.get("banco"):
            banco = request.query_params["banco"]
            cobrancas = cobrancas.filter(conta_bancaria__banco=banco)
            pagamentos = pagamentos.filter(conta_bancaria__banco=banco)

        # O recorte de data é diferente para cada lado, e a diferença é a razão
        # de a conciliação existir: cobrança se conta pelo vencimento (é quando
        # ela *deveria* entrar), pagamento se conta pelo crédito (é quando o
        # dinheiro *entrou*). Usar a mesma data nos dois esconde exatamente o
        # descasamento que se quer enxergar.
        cobrancas_periodo = cobrancas.filter(
            data_vencimento__gte=inicio, data_vencimento__lte=fim
        )
        pagamentos_periodo = pagamentos.filter(
            data_pagamento__gte=inicio, data_pagamento__lte=fim
        )

        hoje = timezone.localdate()
        totais = cobrancas_periodo.aggregate(
            quantidade=Count("id"),
            valor_total=_soma("valor"),
            registrado=_soma("valor", Q(status__in=[
                StatusCobranca.REGISTRADA, StatusCobranca.DISPONIVEL,
                StatusCobranca.ENVIADA_AO_BANCO, StatusCobranca.VENCIDA,
                StatusCobranca.PAGA,
            ])),
            pago=_soma("valor_pago", Q(status=StatusCobranca.PAGA)),
            em_aberto=_soma("valor", Q(status__in=EM_ABERTO)),
            vencido=_soma("valor", Q(status__in=EM_ABERTO, data_vencimento__lt=hoje)),
            cancelado=_soma("valor", Q(status=StatusCobranca.CANCELADA)),
            baixado=_soma("valor", Q(status=StatusCobranca.BAIXADA)),
            rejeitado=_soma("valor", Q(status=StatusCobranca.REJEITADA)),
        )

        recebimentos = pagamentos_periodo.aggregate(
            quantidade=Count("id"),
            bruto=_soma("valor"),
            juros=_soma("juros"),
            multa=_soma("multa"),
            desconto=_soma("desconto"),
            tarifa=_soma("tarifa"),
        )
        recebimentos["liquido"] = recebimentos["bruto"] - recebimentos["tarifa"]

        por_status = list(
            cobrancas_periodo.values("status")
            .annotate(quantidade=Count("id"), valor=_soma("valor"))
            .order_by("-valor")
        )

        return Response({
            "periodo": {"inicio": inicio, "fim": fim},
            "cobrancas": totais,
            "recebimentos": recebimentos,
            "por_status": por_status,
            # A diferença que o financeiro procura: do que venceu no período,
            # quanto ainda não entrou.
            "inadimplencia": {
                "valor": totais["vencido"],
                "percentual": _percentual(totais["vencido"], totais["valor_total"]),
            },
        })


class FluxoView(APIView):
    """Série mensal para os gráficos: emitido × recebido × inadimplente."""

    permission_classes = [IsAuthenticated, PermissaoDeModulo, PertenceAEmpresa]
    modulo = "conciliacao"

    def get(self, request):
        empresa_id = request.empresa_id
        meses = min(int(request.query_params.get("meses", 12)), 36)
        hoje = timezone.localdate()
        inicio = (hoje.replace(day=1) - timedelta(days=31 * meses)).replace(day=1)

        emitido = (
            Cobranca.objects.filter(empresa_id=empresa_id, data_vencimento__gte=inicio)
            .annotate(mes=TruncMonth("data_vencimento"))
            .values("mes")
            .annotate(quantidade=Count("id"), valor=_soma("valor"))
            .order_by("mes")
        )
        recebido = (
            Pagamento.objects.filter(
                empresa_id=empresa_id, estornado=False, data_pagamento__gte=inicio
            )
            .annotate(mes=TruncMonth("data_pagamento"))
            .values("mes")
            .annotate(quantidade=Count("id"), valor=_soma("valor"))
            .order_by("mes")
        )

        # Junta as duas séries num só eixo de meses: o gráfico precisa de
        # linhas alinhadas, e um mês sem pagamento tem de aparecer como zero,
        # não como buraco.
        serie: dict = {}
        for linha in emitido:
            chave = linha["mes"].strftime("%Y-%m")
            serie.setdefault(chave, {"mes": chave, "emitido": 0, "recebido": 0,
                                     "quantidade_emitida": 0, "quantidade_recebida": 0})
            serie[chave]["emitido"] = linha["valor"]
            serie[chave]["quantidade_emitida"] = linha["quantidade"]
        for linha in recebido:
            chave = linha["mes"].strftime("%Y-%m")
            serie.setdefault(chave, {"mes": chave, "emitido": 0, "recebido": 0,
                                     "quantidade_emitida": 0, "quantidade_recebida": 0})
            serie[chave]["recebido"] = linha["valor"]
            serie[chave]["quantidade_recebida"] = linha["quantidade"]

        return Response(sorted(serie.values(), key=lambda l: l["mes"]))


class PendenciasView(APIView):
    """O que precisa de gente: rejeições, órfãos, lotes travados.

    A tela mais importante depois do dashboard. Sem ela, uma rejeição do banco
    fica invisível até alguém reparar que o cliente não recebeu o boleto — o
    que costuma ser no telefone, no dia do vencimento.
    """

    permission_classes = [IsAuthenticated, PermissaoDeModulo, PertenceAEmpresa]
    modulo = "conciliacao"

    def get(self, request):
        from apps.bancos.bancos import StatusArquivo, StatusLote
        from apps.bancos.models import ArquivoBancario, LoteBancario, OcorrenciaBancaria

        empresa_id = request.empresa_id
        return Response({
            "cobrancas_rejeitadas": Cobranca.objects.filter(
                empresa_id=empresa_id, status=StatusCobranca.REJEITADA
            ).count(),
            "cobrancas_com_erro": Cobranca.objects.filter(
                empresa_id=empresa_id, status=StatusCobranca.ERRO
            ).count(),
            "ocorrencias_orfas": OcorrenciaBancaria.objects.filter(
                empresa_id=empresa_id, cobranca__isnull=True
            ).count(),
            "arquivos_com_erro": ArquivoBancario.objects.filter(
                empresa_id=empresa_id,
                status__in=[StatusArquivo.ERRO, StatusArquivo.PROCESSADO_COM_ERROS],
            ).count(),
            "arquivos_pendentes": ArquivoBancario.objects.filter(
                empresa_id=empresa_id, status=StatusArquivo.PENDENTE
            ).count(),
            "lotes_com_erro": LoteBancario.objects.filter(
                empresa_id=empresa_id, status=StatusLote.ERRO
            ).count(),
            "lotes_aguardando_envio": LoteBancario.objects.filter(
                empresa_id=empresa_id, status=StatusLote.PRONTO
            ).count(),
            "clientes_sem_endereco": _clientes_incompletos(empresa_id),
        })


def _clientes_incompletos(empresa_id: int) -> int:
    from apps.clientes.models import Cliente

    return Cliente.objects.filter(empresa_id=empresa_id, status="ATIVO").filter(
        Q(logradouro="") | Q(cidade="") | Q(uf="") | Q(cep="")
    ).count()


def _periodo(request):
    """Período padrão: o mês corrente. É o recorte que o financeiro abre."""
    hoje = timezone.localdate()
    inicio = request.query_params.get("inicio")
    fim = request.query_params.get("fim")
    return (
        date.fromisoformat(inicio) if inicio else hoje.replace(day=1),
        date.fromisoformat(fim) if fim else hoje,
    )


def _percentual(parte, total) -> float:
    if not total:
        return 0.0
    return round(float(parte) / float(total) * 100, 2)
