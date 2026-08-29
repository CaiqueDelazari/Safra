from rest_framework import status
from rest_framework.decorators import action
from rest_framework.parsers import FormParser, MultiPartParser
from rest_framework.response import Response

from apps.clientes.repositories import repositorio
from apps.clientes.serializers import ClienteSerializer
from core.permissions import exige
from core.viewsets import TenantViewSet


class ClienteViewSet(TenantViewSet):
    modulo = "clientes"
    repository = repositorio
    serializer_class = ClienteSerializer
    filterset_fields = ["status", "cidade", "uf", "bairro"]
    search_fields = ["nome", "nome_fantasia", "cpf_cnpj", "email", "telefone",
                     "codigo_externo"]
    ordering_fields = ["nome", "codigo", "criado_em", "valor_em_aberto"]
    ordering = ["nome"]

    @action(detail=False, methods=["post"], url_path="import",
            parser_classes=[MultiPartParser, FormParser], throttle_scope="upload_retorno", url_name="import")
    @exige("importar_clientes")
    def importar(self, request):
        """Sobe uma planilha e devolve o id da tarefa que a processa.

        O arquivo é lido aqui — é barato e permite recusar na hora uma
        planilha sem as colunas obrigatórias. O que vai para a fila é a
        gravação, que é o que demora.
        """
        from apps.clientes.importacao import ler_planilha, mapear_colunas, OBRIGATORIOS
        from apps.clientes.tasks import importar_planilha
        from core.validadores import validar_planilha

        arquivo = request.FILES.get("arquivo")
        if arquivo is None:
            return Response(
                {"detail": "Envie a planilha no campo 'arquivo'.", "codigo": "sem_arquivo"},
                status=status.HTTP_400_BAD_REQUEST,
            )
        validar_planilha(arquivo)

        try:
            cabecalho, linhas = ler_planilha(arquivo, arquivo.name)
        except ValueError as exc:
            return Response({"detail": str(exc), "codigo": "planilha_invalida"},
                            status=status.HTTP_422_UNPROCESSABLE_ENTITY)

        if not linhas:
            return Response({"detail": "A planilha não tem linhas de dados.",
                             "codigo": "planilha_vazia"},
                            status=status.HTTP_422_UNPROCESSABLE_ENTITY)

        mapa, ignoradas = mapear_colunas(cabecalho)
        faltando = [c for c in OBRIGATORIOS if c not in mapa.values()]
        if faltando:
            return Response(
                {
                    "detail": "A planilha não tem as colunas obrigatórias.",
                    "codigo": "colunas_faltando",
                    "faltando": faltando,
                    "colunas_reconhecidas": {cabecalho[i]: c for i, c in mapa.items()},
                    "colunas_ignoradas": ignoradas,
                },
                status=status.HTTP_422_UNPROCESSABLE_ENTITY,
            )

        atualizar = str(request.data.get("atualizar_existentes", "true")).lower() != "false"
        tarefa = importar_planilha.delay(
            request.empresa_id, cabecalho, linhas, atualizar, request.user.pk
        )
        return Response(
            {
                "tarefa_id": tarefa.id,
                "linhas": len(linhas),
                "colunas_reconhecidas": {cabecalho[i]: c for i, c in mapa.items()},
                "colunas_ignoradas": ignoradas,
                "mensagem": f"{len(linhas)} linha(s) em processamento.",
            },
            status=status.HTTP_202_ACCEPTED,
        )

    @action(detail=False, methods=["get"], url_path="import/template", url_name="import-template")
    def modelo_planilha(self, request):
        """Cabeçalho de exemplo, para quem prefere partir do formato certo."""
        from apps.clientes.importacao import COLUNAS

        return Response({
            "colunas": {campo: sinonimos[0] for campo, sinonimos in COLUNAS.items()},
            "obrigatorias": ["nome", "cpf_cnpj"],
            "exemplo_csv": (
                "nome;cpf_cnpj;email;telefone;cep;logradouro;numero;bairro;cidade;uf\n"
                "Empresa Exemplo LTDA;12345678000195;contato@exemplo.com.br;"
                "1133334444;01310100;Avenida Paulista;1000;Bela Vista;São Paulo;SP\n"
            ),
        })

    @action(detail=True, methods=["get"], url_path="charges", url_name="charges")
    def cobrancas(self, request, pk=None):
        """Histórico financeiro do cliente, na própria ficha."""
        from apps.cobrancas.serializers import CobrancaListaSerializer

        cliente = self.get_object()
        qs = cliente.cobrancas.select_related("conta_bancaria").order_by("-data_vencimento")
        pagina = self.paginate_queryset(qs)
        serializer = CobrancaListaSerializer(pagina, many=True, context=self.get_serializer_context())
        return self.get_paginated_response(serializer.data)
