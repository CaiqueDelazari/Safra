from django_filters import rest_framework as filters
from rest_framework import status
from rest_framework.decorators import action
from rest_framework.parsers import FormParser, MultiPartParser
from rest_framework.response import Response

from apps.bancos.bancos import StatusArquivo, StatusLote, TipoArquivo
from apps.bancos.models import ArquivoBancario, ContaBancaria, LoteBancario, OcorrenciaBancaria
from apps.bancos.serializers import (
    ArquivoBancarioSerializer,
    ContaBancariaSerializer,
    CriarLoteSerializer,
    LoteBancarioSerializer,
    OcorrenciaBancariaSerializer,
)
from apps.bancos.services import LoteService, RetornoService
from core.permissions import exige
from core.repositories import TenantRepository
from core.services import RegraDeNegocioError
from core.viewsets import TenantViewSet


# ══════════════════════════════════════════════════════════ contas bancárias
class ContaBancariaRepository(TenantRepository[ContaBancaria]):
    model = ContaBancaria


class ContaBancariaViewSet(TenantViewSet):
    modulo = "contas_bancarias"
    repository = ContaBancariaRepository()
    serializer_class = ContaBancariaSerializer
    filterset_fields = ["banco", "ativa", "meio_integracao"]
    search_fields = ["nome", "agencia", "conta"]
    ordering = ["banco", "nome"]
    # Criar e editar conta bancária é administrar a integração — a matriz já
    # restringe a Administrador, e a capacidade nomeia o ato na auditoria.
    capacidades_por_acao = {
        "create": "administrar_integracao_bancaria",
        "update": "administrar_integracao_bancaria",
        "partial_update": "administrar_integracao_bancaria",
        "destroy": "administrar_integracao_bancaria",
    }

    def perform_create(self, serializer):
        conta = serializer.save(empresa_id=self.request.empresa_id)
        self._garantir_padrao_unico(conta)

    def perform_update(self, serializer):
        conta = serializer.save()
        self._garantir_padrao_unico(conta)

    def _garantir_padrao_unico(self, conta):
        """Marcar uma conta como padrão desmarca a anterior.

        O banco tem um `UniqueConstraint` condicional que impede duas padrão —
        sem isto, salvar a segunda daria erro de integridade em vez de fazer o
        que o usuário claramente quis.
        """
        if conta.padrao:
            ContaBancaria.objects.filter(
                empresa_id=conta.empresa_id, padrao=True
            ).exclude(pk=conta.pk).update(padrao=False)

    @action(detail=True, methods=["get"], url_path="conferir-layout", url_name="conferir-layout")
    @exige("administrar_integracao_bancaria")
    def conferir_layout(self, request, pk=None):
        """Devolve a tabela de posições do CNAB com uma linha de exemplo.

        É o que se põe lado a lado com o manual do banco. Existe como rota, e
        não só como comando de terminal, porque quem confere o layout costuma
        ser o financeiro com o PDF do banco aberto — não alguém com acesso SSH.
        """
        from apps.bancos.adapters.safra import layout400 as L

        conta = self.get_object()
        if conta.banco != L.BANCO:
            raise RegraDeNegocioError(
                f"A conferência de layout existe hoje para o banco {L.BANCO}.", "banco"
            )
        return Response({
            "banco": conta.banco,
            "registros": {
                nome: {
                    "titulo": registro.nome,
                    "tamanho": registro.tamanho,
                    "campos": [
                        {
                            "nome": c.nome, "inicio": c.inicio, "fim": c.fim,
                            "tamanho": c.tamanho, "tipo": c.tipo,
                            "fixo": c.fixo, "nota": c.nota,
                        }
                        for c in registro.campos
                    ],
                }
                for nome, registro in L.REGISTROS.items()
            },
        })


# ═══════════════════════════════════════════════════════════════════ lotes
class LoteRepository(TenantRepository[LoteBancario]):
    model = LoteBancario
    select_related = ("conta", "arquivo_remessa", "criado_por")


class LoteFilter(filters.FilterSet):
    status = filters.MultipleChoiceFilter(choices=StatusLote.choices)
    conta = filters.NumberFilter(field_name="conta_id")
    criado_de = filters.DateFilter(field_name="criado_em", lookup_expr="date__gte")
    criado_ate = filters.DateFilter(field_name="criado_em", lookup_expr="date__lte")

    class Meta:
        model = LoteBancario
        fields = []


class LoteViewSet(TenantViewSet):
    modulo = "lotes"
    repository = LoteRepository()
    serializer_class = LoteBancarioSerializer
    filterset_class = LoteFilter
    ordering = ["-numero"]
    http_method_names = ["get", "post", "head", "options"]

    def create(self, request, *args, **kwargs):
        """Cria o lote e enfileira a montagem do arquivo.

        Responde em milissegundos com o número do lote. A montagem de 20 mil
        títulos leva minutos e roda no worker — a tela acompanha por
        `progresso`.
        """
        from apps.bancos.tasks import montar_remessa

        serializer = CriarLoteSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        dados = serializer.validated_data

        conta = ContaBancaria.objects.filter(
            pk=dados["conta_bancaria"], empresa_id=request.empresa_id
        ).select_related("empresa").first()
        if conta is None:
            raise RegraDeNegocioError("Conta bancária não encontrada.", "conta_bancaria")

        lote = LoteService.criar(
            empresa_id=request.empresa_id,
            conta=conta,
            cobranca_ids=dados["cobrancas"],
            usuario=request.user,
        )
        tarefa = montar_remessa.delay(lote.pk, request.empresa_id, dados["enviar"])

        corpo = LoteBancarioSerializer(lote, context=self.get_serializer_context()).data
        corpo["tarefa_id"] = tarefa.id
        corpo["recusadas"] = len(dados["cobrancas"]) - lote.quantidade
        corpo["mensagem"] = (
            f"Lote #{lote.numero} criado com {lote.quantidade} título(s). "
            "Montagem do arquivo em andamento."
        )
        return Response(corpo, status=status.HTTP_202_ACCEPTED)

    create.capacidade = "gerar_lote"

    @action(detail=False, methods=["post"], url_path="validate", url_name="validate")
    @exige("gerar_lote")
    def validar(self, request):
        """Simula a criação e diz o que entraria e o que ficaria de fora.

        Existe para que ninguém descubra as 40 pendências *depois* de gerar o
        lote e consumir 500 números da faixa contratada com o banco.
        """
        from apps.cobrancas.models import Cobranca

        ids = request.data.get("cobrancas") or []
        conta = ContaBancaria.objects.filter(
            pk=request.data.get("conta_bancaria"), empresa_id=request.empresa_id
        ).first()
        if conta is None:
            raise RegraDeNegocioError("Conta bancária não encontrada.", "conta_bancaria")

        cobrancas = list(
            Cobranca.objects.filter(empresa_id=request.empresa_id, pk__in=ids)
            .select_related("cliente")
        )
        resumo = LoteService.validar(cobrancas, conta)
        por_id = {c.pk: c for c in cobrancas}
        return Response({
            "aptas": len(resumo.aptas),
            "recusadas": [
                {
                    "id": pk,
                    "numero": getattr(por_id.get(pk), "numero", None),
                    "cliente": getattr(getattr(por_id.get(pk), "cliente", None), "nome", ""),
                    "motivo": motivo,
                }
                for pk, motivo in resumo.recusadas
            ],
            "valor_total": sum(
                (por_id[pk].valor for pk in resumo.aptas if pk in por_id), 0
            ),
        })

    @action(detail=True, methods=["post"], url_path="submit", url_name="submit")
    @exige("enviar_remessa")
    def enviar(self, request, pk=None):
        from apps.bancos.tasks import enviar_remessa

        lote = self.get_object()
        tarefa = enviar_remessa.delay(lote.pk, request.empresa_id)
        return Response({"tarefa_id": tarefa.id, "lote": lote.numero},
                        status=status.HTTP_202_ACCEPTED)

    @action(detail=True, methods=["post"], url_path="rebuild", url_name="rebuild")
    @exige("gerar_lote")
    def remontar(self, request, pk=None):
        """Refaz o arquivo de um lote que falhou.

        Só de lote em RASCUNHO ou ERRO — o serviço recusa o resto. Como os
        nossos números já estão presos ao lote, o arquivo refeito é idêntico
        ao que teria sido gerado, sem consumir faixa nova.
        """
        from apps.bancos.tasks import montar_remessa

        lote = self.get_object()
        tarefa = montar_remessa.delay(lote.pk, request.empresa_id, False)
        return Response({"tarefa_id": tarefa.id}, status=status.HTTP_202_ACCEPTED)

    @action(detail=True, methods=["get"], url_path="charges", url_name="charges")
    def cobrancas(self, request, pk=None):
        from apps.cobrancas.serializers import CobrancaListaSerializer

        lote = self.get_object()
        qs = lote.cobrancas.select_related("cliente", "conta_bancaria").order_by("numero")
        pagina = self.paginate_queryset(qs)
        return self.get_paginated_response(
            CobrancaListaSerializer(pagina, many=True,
                                    context=self.get_serializer_context()).data
        )


# ═══════════════════════════════════════════════════════════════ arquivos
class ArquivoRepository(TenantRepository[ArquivoBancario]):
    model = ArquivoBancario
    select_related = ("conta",)


class ArquivoFilter(filters.FilterSet):
    tipo = filters.ChoiceFilter(choices=TipoArquivo.choices)
    status = filters.MultipleChoiceFilter(choices=StatusArquivo.choices)
    conta = filters.NumberFilter(field_name="conta_id")
    movimento_de = filters.DateFilter(field_name="data_movimento", lookup_expr="gte")
    movimento_ate = filters.DateFilter(field_name="data_movimento", lookup_expr="lte")

    class Meta:
        model = ArquivoBancario
        fields = []


class ArquivoBancarioViewSet(TenantViewSet):
    modulo = "arquivos"
    repository = ArquivoRepository()
    serializer_class = ArquivoBancarioSerializer
    filterset_class = ArquivoFilter
    search_fields = ["nome_original", "hash_arquivo"]
    ordering = ["-recebido_em"]
    http_method_names = ["get", "post", "head", "options"]

    @action(detail=False, methods=["post"], url_path="returns/process",
            parser_classes=[MultiPartParser, FormParser],
            throttle_scope="upload_retorno", url_name="returns-process")
    @exige("processar_retorno")
    def subir_retorno(self, request):
        """Sobe um arquivo de retorno e enfileira o processamento.

        Subir o mesmo arquivo duas vezes é seguro e comum — o operador não tem
        como saber se funcionou da primeira. A resposta diz claramente qual dos
        dois casos aconteceu, em vez de fingir que criou algo novo.
        """
        from apps.bancos.tasks import processar_retorno
        from core.validadores import validar_arquivo_bancario

        arquivo = request.FILES.get("arquivo")
        if arquivo is None:
            return Response({"detail": "Envie o arquivo no campo 'arquivo'.",
                             "codigo": "sem_arquivo"},
                            status=status.HTTP_400_BAD_REQUEST)
        validar_arquivo_bancario(arquivo)

        conta = None
        if request.data.get("conta_bancaria"):
            conta = ContaBancaria.objects.filter(
                pk=request.data["conta_bancaria"], empresa_id=request.empresa_id
            ).first()

        banco = conta.banco if conta else request.data.get("banco", "422")
        registro, novo = RetornoService.registrar_arquivo(
            empresa_id=request.empresa_id,
            nome=arquivo.name,
            conteudo=arquivo.read(),
            banco=banco,
            conta=conta,
            origem="UPLOAD",
        )

        corpo = ArquivoBancarioSerializer(
            registro, context=self.get_serializer_context()
        ).data

        if not novo and registro.status == StatusArquivo.PROCESSADO:
            corpo["mensagem"] = (
                "Este arquivo já foi processado antes (mesmo conteúdo). "
                "Nada foi duplicado."
            )
            corpo["ja_processado"] = True
            return Response(corpo, status=status.HTTP_200_OK)

        tarefa = processar_retorno.delay(registro.pk, request.empresa_id)
        corpo["tarefa_id"] = tarefa.id
        corpo["ja_processado"] = False
        corpo["mensagem"] = (
            "Arquivo recebido. O processamento está em andamento."
            if novo else
            "Arquivo já conhecido, mas ainda não processado. Reprocessando."
        )
        return Response(corpo, status=status.HTTP_202_ACCEPTED)

    @action(detail=True, methods=["post"], url_path="reprocess", url_name="reprocess")
    @exige("processar_retorno")
    def reprocessar(self, request, pk=None):
        """Roda o arquivo de novo. Seguro: não duplica ocorrência nem pagamento.

        Serve para dois casos reais: o processamento falhou no meio, e o
        título que estava faltando foi cadastrado depois — a segunda passada
        adota as ocorrências órfãs.
        """
        from apps.bancos.tasks import processar_retorno

        arquivo = self.get_object()
        if arquivo.tipo != TipoArquivo.RETORNO:
            raise RegraDeNegocioError("Só arquivo de retorno é processado.", "tipo")
        tarefa = processar_retorno.delay(arquivo.pk, request.empresa_id)
        return Response({"tarefa_id": tarefa.id}, status=status.HTTP_202_ACCEPTED)

    @action(detail=True, methods=["get"], url_path="occurrences", url_name="occurrences")
    def ocorrencias(self, request, pk=None):
        arquivo = self.get_object()
        qs = arquivo.ocorrencias.select_related("cobranca", "cobranca__cliente")
        pagina = self.paginate_queryset(qs)
        return self.get_paginated_response(
            OcorrenciaBancariaSerializer(pagina, many=True,
                                         context=self.get_serializer_context()).data
        )


# ═════════════════════════════════════════════════════════════ ocorrências
class OcorrenciaRepository(TenantRepository[OcorrenciaBancaria]):
    model = OcorrenciaBancaria
    select_related = ("arquivo", "cobranca", "cobranca__cliente")


class OcorrenciaFilter(filters.FilterSet):
    tipo = filters.MultipleChoiceFilter(field_name="tipo")
    arquivo = filters.NumberFilter(field_name="arquivo_id")
    cobranca = filters.NumberFilter(field_name="cobranca_id")
    orfas = filters.BooleanFilter(field_name="cobranca_id", lookup_expr="isnull")
    data_de = filters.DateFilter(field_name="data_ocorrencia", lookup_expr="gte")
    data_ate = filters.DateFilter(field_name="data_ocorrencia", lookup_expr="lte")

    class Meta:
        model = OcorrenciaBancaria
        fields = []


class OcorrenciaViewSet(TenantViewSet):
    """Somente leitura: é a prova documental do que o banco disse.

    Uma ocorrência não se corrige — corrige-se o efeito dela e reprocessa. Um
    PATCH aqui destruiria a única fonte confiável para responder "por que este
    título ficou pago?".
    """

    modulo = "arquivos"
    repository = OcorrenciaRepository()
    serializer_class = OcorrenciaBancariaSerializer
    filterset_class = OcorrenciaFilter
    search_fields = ["nosso_numero", "seu_numero", "codigo", "descricao"]
    ordering = ["-data_ocorrencia", "-id"]
    http_method_names = ["get", "head", "options"]
