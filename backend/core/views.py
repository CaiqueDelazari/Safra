"""Rotas transversais: saúde, dashboard, busca, mídia e acompanhamento de tarefa."""
from datetime import timedelta
from decimal import Decimal

from django.conf import settings
from django.db import connection
from django.db.models import Count, DecimalField, Q, Sum, Value
from django.db.models.functions import Coalesce, TruncMonth
from django.http import FileResponse
from django.utils import timezone
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from core.midia import EXTENSOES, abrir
from core.permissions import PermissaoDeModulo, PertenceAEmpresa

ZERO = Value(Decimal("0"), output_field=DecimalField(max_digits=16, decimal_places=2))


def _soma(campo, filtro=None):
    return Coalesce(Sum(campo, filter=filtro), ZERO)


class SaudeView(APIView):
    """Verificação de vida, usada pelo healthcheck do contêiner e pelo deploy.

    Confere banco e broker, porque um backend que responde 200 com o Postgres
    fora não é um backend saudável — é um que ainda não recebeu requisição de
    verdade. O Redis entra na conta pelo mesmo motivo: sem ele, nenhum lote é
    processado e o sistema parece funcionar até alguém clicar em "gerar".
    """

    permission_classes = [AllowAny]
    authentication_classes = []

    def get(self, request):
        estado = {"api": "ok"}
        codigo = 200

        try:
            with connection.cursor() as cursor:
                cursor.execute("SELECT 1")
            estado["banco"] = "ok"
        except Exception as exc:  # noqa: BLE001
            estado["banco"] = f"erro: {exc}"
            codigo = 503

        try:
            from django.core.cache import cache

            cache.set("saude", "1", 10)
            estado["cache"] = "ok" if cache.get("saude") == "1" else "erro: sem resposta"
        except Exception as exc:  # noqa: BLE001
            estado["cache"] = f"erro: {exc}"
            codigo = 503

        return Response(estado, status=codigo)


class DashboardView(APIView):
    """Os números da regra 11, numa consulta agregada por bloco.

    Tudo que a tela inicial mostra sai de duas tabelas e três consultas: uma
    para os totais de cobrança, uma para recebimento e uma para a série do
    gráfico. Fazer uma consulta por cartão daria oito, e o dashboard é a tela
    que todo mundo abre ao entrar.
    """

    permission_classes = [IsAuthenticated, PermissaoDeModulo, PertenceAEmpresa]
    modulo = "dashboard"

    def get(self, request):
        from apps.cobrancas.models import EM_ABERTO, Cobranca, StatusCobranca
        from apps.pagamentos.models import Pagamento

        empresa_id = request.empresa_id
        hoje = timezone.localdate()
        inicio_mes = hoje.replace(day=1)
        em_dias = hoje + timedelta(days=7)

        cobrancas = Cobranca.objects.filter(empresa_id=empresa_id)
        totais = cobrancas.aggregate(
            a_receber=_soma("valor", Q(status__in=EM_ABERTO)),
            em_aberto=_soma("valor", Q(status__in=EM_ABERTO, data_vencimento__gte=hoje)),
            vencido=_soma("valor", Q(status__in=EM_ABERTO, data_vencimento__lt=hoje)),
            cancelado=_soma("valor", Q(status=StatusCobranca.CANCELADA)),
            rejeitado=_soma("valor", Q(status=StatusCobranca.REJEITADA)),
            vencendo_em_7_dias=_soma("valor", Q(
                status__in=EM_ABERTO, data_vencimento__gte=hoje, data_vencimento__lte=em_dias
            )),
            quantidade_aberta=Count("id", filter=Q(status__in=EM_ABERTO)),
            quantidade_vencida=Count("id", filter=Q(
                status__in=EM_ABERTO, data_vencimento__lt=hoje
            )),
        )

        recebido = Pagamento.objects.filter(
            empresa_id=empresa_id, estornado=False
        ).aggregate(
            no_mes=_soma("valor", Q(data_pagamento__gte=inicio_mes)),
            hoje=_soma("valor", Q(data_pagamento=hoje)),
            total=_soma("valor"),
            tarifas_no_mes=_soma("tarifa", Q(data_pagamento__gte=inicio_mes)),
            quantidade_no_mes=Count("id", filter=Q(data_pagamento__gte=inicio_mes)),
        )

        # Série dos últimos 6 meses para o gráfico da tela inicial. O
        # detalhado, com filtro, mora em /conciliacao/fluxo/.
        seis_meses = (inicio_mes - timedelta(days=185)).replace(day=1)
        serie = list(
            Pagamento.objects.filter(
                empresa_id=empresa_id, estornado=False, data_pagamento__gte=seis_meses
            )
            .annotate(mes=TruncMonth("data_pagamento"))
            .values("mes")
            .annotate(valor=_soma("valor"), quantidade=Count("id"))
            .order_by("mes")
        )

        inadimplencia = 0.0
        if totais["a_receber"]:
            inadimplencia = round(
                float(totais["vencido"]) / float(totais["a_receber"]) * 100, 2
            )

        return Response({
            "referencia": hoje,
            "totais": totais,
            "recebido": recebido,
            "inadimplencia_percentual": inadimplencia,
            "recebimentos_por_mes": [
                {"mes": l["mes"].strftime("%Y-%m"), "valor": l["valor"],
                 "quantidade": l["quantidade"]}
                for l in serie
            ],
            "proximos_vencimentos": self._proximos(cobrancas, hoje, em_dias),
        })

    def _proximos(self, cobrancas, hoje, limite):
        from apps.cobrancas.models import EM_ABERTO

        qs = (
            cobrancas.filter(
                status__in=EM_ABERTO, data_vencimento__gte=hoje,
                data_vencimento__lte=limite,
            )
            .select_related("cliente")
            .order_by("data_vencimento")[:10]
        )
        return [
            {
                "id": c.pk, "numero": c.numero, "cliente": c.cliente.nome,
                "descricao": c.descricao, "valor": c.valor,
                "vencimento": c.data_vencimento,
            }
            for c in qs
        ]


class BuscaGlobalView(APIView):
    """Uma caixa de busca que encontra cliente, cobrança ou boleto.

    O operador tem na mão o que o cliente falou ao telefone: um nome, um CPF,
    um número de boleto, uma linha digitável colada do WhatsApp. Obrigá-lo a
    escolher a tela certa antes de procurar é o tipo de atrito que faz
    ninguém usar a busca.
    """

    permission_classes = [IsAuthenticated, PermissaoDeModulo, PertenceAEmpresa]
    modulo = "busca"

    def get(self, request):
        from apps.clientes.models import Cliente
        from apps.cobrancas.models import Cobranca
        from core.validadores import so_digitos

        termo = (request.query_params.get("q") or "").strip()
        if len(termo) < 2:
            return Response({"clientes": [], "cobrancas": []})

        empresa_id = request.empresa_id
        digitos = so_digitos(termo)

        filtro_cliente = Q(nome__icontains=termo) | Q(email__icontains=termo)
        if digitos:
            # Só entra quando o termo tem dígitos: `contains=""` casaria com
            # todo mundo e a busca por nome devolveria a base inteira.
            filtro_cliente |= Q(cpf_cnpj__startswith=digitos) | Q(telefone__contains=digitos)

        clientes = (
            Cliente.objects.filter(empresa_id=empresa_id)
            .filter(filtro_cliente)
            .order_by("nome")[:10]
        )

        filtro_cobranca = (
            Q(descricao__icontains=termo)
            | Q(documento__icontains=termo)
            | Q(cliente__nome__icontains=termo)
        )
        if digitos:
            filtro_cobranca |= (
                Q(nosso_numero=digitos.lstrip("0"))
                | Q(seu_numero=digitos)
                | Q(codigo_barras=digitos)
                | Q(linha_digitavel=digitos)
            )
            if digitos.isdigit() and len(digitos) < 10:
                filtro_cobranca |= Q(numero=int(digitos))

        cobrancas = (
            Cobranca.objects.filter(empresa_id=empresa_id)
            .filter(filtro_cobranca)
            .select_related("cliente")
            .order_by("-data_vencimento")[:10]
        )

        return Response({
            "clientes": [
                {"id": c.pk, "codigo": c.codigo, "nome": c.nome,
                 "documento": c.documento_formatado, "status": c.status}
                for c in clientes
            ],
            "cobrancas": [
                {"id": c.pk, "numero": c.numero, "cliente": c.cliente.nome,
                 "descricao": c.descricao, "valor": c.valor,
                 "vencimento": c.data_vencimento, "status": c.status}
                for c in cobrancas
            ],
        })


class TarefaView(APIView):
    """Andamento de uma tarefa de fila — é o 0%…100% da regra 19.

    Lê o resultado do Celery, que já guarda estado e progresso. Não expõe o
    traceback de uma falha: mensagem de erro interna vira informação para
    quem tenta entrar. O operador vê "falhou"; o log tem o resto.
    """

    permission_classes = [IsAuthenticated]

    def get(self, request, task_id: str):
        from celery.result import AsyncResult

        from config.celery import app

        resultado = AsyncResult(task_id, app=app)
        corpo = {"id": task_id, "estado": resultado.state, "progresso": 0}

        if resultado.state == "PROGRESS":
            info = resultado.info or {}
            corpo["progresso"] = info.get("progresso", 0)
            corpo["total"] = info.get("total")
        elif resultado.successful():
            corpo["progresso"] = 100
            corpo["resultado"] = resultado.result
        elif resultado.failed():
            corpo["progresso"] = 100
            corpo["erro"] = "A tarefa falhou. Consulte os arquivos ou lotes com erro."
        return Response(corpo)


class MidiaView(APIView):
    """Entrega de arquivo por link assinado (ver core/midia.py)."""

    permission_classes = [AllowAny]
    authentication_classes = []
    throttle_scope = "midia"

    def get(self, request, token: str):
        caminho = abrir(token)
        from pathlib import Path

        tipo = EXTENSOES.get(Path(caminho).suffix.lower(), "application/octet-stream")
        resposta = FileResponse(open(caminho, "rb"), content_type=tipo)
        # Arquivo bancário e boleto sempre baixam, nunca renderizam: um CNAB
        # aberto no navegador é uma parede de texto, e um PDF renderizado
        # dentro do domínio da API amplia a superfície de ataque à toa.
        if tipo != "image/jpeg" and not tipo.startswith("image/"):
            resposta["Content-Disposition"] = f'attachment; filename="{Path(caminho).name}"'
        resposta["Cache-Control"] = f"private, max-age={settings.MIDIA_URL_VALIDADE_SEGUNDOS}"
        resposta["X-Content-Type-Options"] = "nosniff"
        return resposta
