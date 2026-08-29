from datetime import date, timedelta

from django.db.models import Count, Sum
from rest_framework import status
from rest_framework.decorators import action
from rest_framework.response import Response

from apps.cobrancas.filters import CobrancaFilter
from apps.cobrancas.models import EM_ABERTO, Cobranca, StatusCobranca
from apps.cobrancas.repositories import repositorio
from apps.cobrancas.serializers import (
    CobrancaListaSerializer,
    CobrancaSerializer,
    CriacaoEmLoteSerializer,
    GerarRecorrenciaSerializer,
)
from apps.cobrancas.services import CobrancaService
from core.permissions import exige
from core.viewsets import TenantViewSet


class CobrancaViewSet(TenantViewSet):
    modulo = "cobrancas"
    repository = repositorio
    serializer_class = CobrancaSerializer
    filterset_class = CobrancaFilter
    search_fields = ["descricao", "documento", "seu_numero", "nosso_numero",
                     "cliente__nome", "cliente__cpf_cnpj"]
    ordering_fields = ["numero", "data_vencimento", "data_emissao", "valor",
                       "data_pagamento", "criado_em"]
    ordering = ["-data_vencimento"]

    def get_serializer_class(self):
        # Listagem usa o serializer enxuto: a mesma tela com o serializer
        # completo manda o cadastro do cliente 25 vezes por página.
        if self.action == "list":
            return CobrancaListaSerializer
        return CobrancaSerializer

    def get_queryset(self):
        qs = super().get_queryset()
        if self.action in ("retrieve", "update", "partial_update"):
            return qs.prefetch_related("itens", "ocorrencias", "pagamentos")
        return qs

    # ══════════════════════════════════════════════════════ criação em massa
    @action(detail=False, methods=["post"], url_path="bulk", url_name="bulk")
    @exige("criar_cobranca_em_lote")
    def criar_em_lote(self, request):
        """Cria N cobranças de uma vez. Responde na hora, processa na fila."""
        from apps.cobrancas.tasks import gerar_em_lote

        serializer = CriacaoEmLoteSerializer(data=request.data, context=self.get_serializer_context())
        serializer.is_valid(raise_exception=True)
        dados = serializer.validated_data

        linhas = [
            {k: (v.isoformat() if isinstance(v, date) else v) for k, v in linha.items()}
            for linha in dados["cobrancas"]
        ]
        tarefa = gerar_em_lote.delay(
            request.empresa_id, linhas, request.user.pk, dados.get("conta_bancaria_id")
        )
        return Response(
            {
                "tarefa_id": tarefa.id,
                "total": len(linhas),
                "mensagem": f"{len(linhas)} cobrança(s) em processamento.",
            },
            status=status.HTTP_202_ACCEPTED,
        )

    @action(detail=False, methods=["post"], url_path="recurring", url_name="recurring")
    @exige("criar_cobranca_em_lote")
    def recorrencia(self, request):
        """Mensalidade: N clientes × M parcelas, numa chamada.

        Gera as linhas aqui e delega à mesma criação em massa — a recorrência
        não é um mecanismo à parte, é um atalho para montar as linhas. Isso
        mantém uma única regra de criação de cobrança no sistema.
        """
        from apps.cobrancas.tasks import gerar_em_lote

        serializer = GerarRecorrenciaSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        d = serializer.validated_data

        prefixo = d.get("prefixo_chave") or ""
        linhas = []
        for cliente_id in d["clientes"]:
            for parcela in range(d["parcelas"]):
                vencimento = _somar_meses(
                    d["primeiro_vencimento"], parcela, d.get("dia_vencimento")
                )
                sufixo = f"/{parcela + 1}" if d["parcelas"] > 1 else ""
                linhas.append({
                    "cliente_id": cliente_id,
                    "descricao": f"{d['descricao']}{sufixo}",
                    "valor": str(d["valor"]),
                    "data_vencimento": vencimento.isoformat(),
                    "conta_bancaria_id": d.get("conta_bancaria_id"),
                    # A chave é o que torna a geração repetível: rodar duas
                    # vezes o fechamento do mês não gera cobrança dobrada.
                    "chave_externa": (
                        f"{prefixo}:{cliente_id}:{vencimento:%Y%m}" if prefixo else ""
                    ),
                })

        tarefa = gerar_em_lote.delay(
            request.empresa_id, linhas, request.user.pk, d.get("conta_bancaria_id")
        )
        return Response(
            {"tarefa_id": tarefa.id, "total": len(linhas),
             "mensagem": f"{len(linhas)} cobrança(s) em processamento."},
            status=status.HTTP_202_ACCEPTED,
        )

    # ═══════════════════════════════════════════════════════════ instruções
    @action(detail=True, methods=["post"], url_path="cancel", url_name="cancel")
    @exige("cancelar_cobranca")
    def cancelar(self, request, pk=None):
        cobranca = self.get_object()
        CobrancaService.cancelar(
            cobranca, motivo=request.data.get("motivo", ""), usuario=request.user
        )
        return Response(CobrancaSerializer(cobranca, context=self.get_serializer_context()).data)

    @action(detail=True, methods=["post"], url_path="write-off", url_name="write-off")
    @exige("baixar_cobranca")
    def baixar(self, request, pk=None):
        cobranca = self.get_object()
        CobrancaService.baixar(
            cobranca, motivo=request.data.get("motivo", ""), usuario=request.user
        )
        return Response(CobrancaSerializer(cobranca, context=self.get_serializer_context()).data)

    @action(detail=True, methods=["post"], url_path="manual-payment", url_name="manual-payment")
    @exige("baixar_cobranca")
    def pagamento_manual(self, request, pk=None):
        """Baixa manual. Fica marcada como tal e a conciliação a separa."""
        from decimal import Decimal

        from django.utils import timezone

        cobranca = self.get_object()
        valor = Decimal(str(request.data.get("valor") or cobranca.valor))
        data_pagamento = request.data.get("data_pagamento")
        pagamento = CobrancaService.registrar_pagamento_manual(
            cobranca,
            valor=valor,
            data_pagamento=date.fromisoformat(data_pagamento) if data_pagamento
            else timezone.localdate(),
            usuario=request.user,
            observacao=request.data.get("observacao", ""),
        )
        return Response(
            {"pagamento_id": pagamento.pk,
             "cobranca": CobrancaSerializer(cobranca, context=self.get_serializer_context()).data},
            status=status.HTTP_201_CREATED,
        )

    # ══════════════════════════════════════════════════════════════ boleto
    @action(detail=True, methods=["get"], url_path="boleto", url_name="boleto")
    def boleto(self, request, pk=None):
        """Dados do boleto: linha digitável, código de barras e link."""
        from apps.bancos.boleto import formatar_linha_digitavel
        from core.midia import url_assinada

        cobranca = self.get_object()
        dados = CobrancaService.dados_do_boleto(cobranca)
        return Response({
            "linha_digitavel": dados["linha_digitavel"],
            "linha_digitavel_formatada": formatar_linha_digitavel(dados["linha_digitavel"]),
            "codigo_barras": dados["codigo_barras"],
            "url_banco": cobranca.url_boleto or None,
            "pdf": url_assinada(cobranca.boleto_pdf, request) if cobranca.boleto_pdf else None,
            "nosso_numero": cobranca.nosso_numero,
            "vencimento": cobranca.data_vencimento,
            "valor": cobranca.valor,
            "beneficiario": cobranca.empresa.razao_social,
            "sacado": cobranca.cliente.nome,
        })

    @action(detail=True, methods=["post"], url_path="send", url_name="send")
    @exige("enviar_boleto_cliente")
    def enviar_boleto(self, request, pk=None):
        from apps.cobrancas.tasks import enviar_boleto_email

        cobranca = self.get_object()
        tarefa = enviar_boleto_email.delay(
            cobranca.pk, request.empresa_id, request.data.get("email", "")
        )
        return Response({"tarefa_id": tarefa.id}, status=status.HTTP_202_ACCEPTED)

    @action(detail=False, methods=["post"], url_path="send-bulk", url_name="send-bulk")
    @exige("enviar_boleto_cliente")
    def enviar_boletos(self, request):
        from apps.cobrancas.tasks import enviar_boletos_em_lote

        ids = request.data.get("cobrancas") or []
        if not ids:
            return Response({"detail": "Informe as cobranças.", "codigo": "sem_selecao"},
                            status=status.HTTP_400_BAD_REQUEST)
        # Confere que todas são da empresa ativa antes de enfileirar: a tarefa
        # roda fora do contexto da requisição e não teria como saber.
        validos = list(
            self.get_queryset().filter(pk__in=ids).values_list("pk", flat=True)
        )
        tarefa = enviar_boletos_em_lote.delay(validos, request.empresa_id)
        return Response({"tarefa_id": tarefa.id, "enfileirados": len(validos)},
                        status=status.HTTP_202_ACCEPTED)

    # ══════════════════════════════════════════════════════════════ resumo
    @action(detail=False, methods=["get"], url_path="summary", url_name="summary")
    def resumo(self, request):
        """Totais por situação, respeitando os filtros da tela.

        Uma consulta agregada, não uma por status: a diferença aparece quando
        a base passa de algumas centenas de milhares de linhas.
        """
        qs = self.filter_queryset(self.get_queryset())
        por_status = {
            linha["status"]: {
                "quantidade": linha["quantidade"],
                "valor": linha["valor"] or 0,
            }
            for linha in qs.values("status").annotate(
                quantidade=Count("id"), valor=Sum("valor")
            )
        }
        total = qs.aggregate(quantidade=Count("id"), valor=Sum("valor"))
        return Response({
            "total": {"quantidade": total["quantidade"] or 0, "valor": total["valor"] or 0},
            "por_status": por_status,
            "em_aberto": sum(
                por_status.get(s, {}).get("valor", 0) or 0 for s in EM_ABERTO
            ),
            "pago": por_status.get(StatusCobranca.PAGA, {}).get("valor", 0) or 0,
        })


def _somar_meses(inicial: date, meses: int, dia_fixo: int | None = None) -> date:
    """Avança N meses preservando o dia — e recuando quando o mês é curto.

    Vencimento dia 31 em fevereiro não existe. A convenção usada aqui é a
    mesma dos bancos: cai no último dia do mês, nunca no primeiro do seguinte,
    porque antecipar um vencimento é menos danoso do que atrasá-lo.
    """
    dia = dia_fixo or inicial.day
    ano = inicial.year + (inicial.month - 1 + meses) // 12
    mes = (inicial.month - 1 + meses) % 12 + 1
    # Último dia do mês alvo, sem depender de calendar.monthrange por clareza:
    proximo = date(ano + (mes // 12), (mes % 12) + 1, 1)
    ultimo_dia = (proximo - timedelta(days=1)).day
    return date(ano, mes, min(dia, ultimo_dia))
