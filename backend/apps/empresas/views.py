from rest_framework import viewsets
from rest_framework.decorators import action
from rest_framework.parsers import FormParser, JSONParser, MultiPartParser
from rest_framework.response import Response

from apps.empresas.models import Empresa
from apps.empresas.serializers import EmpresaSerializer
from core.permissions import PermissaoDeModulo, PertenceAEmpresa


class EmpresaViewSet(viewsets.ModelViewSet):
    """Cadastro das empresas que o usuário alcança.

    Não herda de `TenantViewSet` porque a empresa **é** o tenant: filtrá-la
    por `empresa_id` seria circular. O isolamento aqui vem de
    `empresas_permitidas_ids`, que é a mesma fonte que as permissões usam —
    então o que aparece no seletor é exatamente o que se alcança.
    """

    modulo = "empresas"
    serializer_class = EmpresaSerializer
    permission_classes = [PermissaoDeModulo, PertenceAEmpresa]
    parser_classes = [JSONParser, MultiPartParser, FormParser]
    search_fields = ("razao_social", "nome_fantasia", "cnpj")
    filterset_fields = ("ativa", "uf")
    ordering = ("nome_fantasia",)

    def get_queryset(self):
        return Empresa.objects.filter(
            id__in=self.request.user.empresas_permitidas_ids()
        ).order_by("nome_fantasia")

    def get_serializer_context(self):
        contexto = super().get_serializer_context()
        contexto["papel"] = getattr(self.request.user, "papel", None)
        contexto["empresa_id"] = getattr(self.request, "empresa_id", None)
        return contexto

    def perform_create(self, serializer):
        """Quem cria uma empresa vira administrador dela.

        Sem isto, a empresa nasceria sem ninguém dentro: existiria na base,
        responderia na API e não apareceria no seletor de quem a cadastrou —
        que é o único lugar por onde se entra nela.
        """
        from apps.accounts.models import UsuarioEmpresa
        from core.roles import Papel

        empresa = serializer.save()
        UsuarioEmpresa.objects.get_or_create(
            usuario=self.request.user, empresa=empresa,
            defaults={"papel": Papel.ADMINISTRADOR, "ativo": True},
        )
        if self.request.user.empresa_padrao_id is None:
            self.request.user.empresa_padrao = empresa
            self.request.user.save(update_fields=["empresa_padrao", "atualizado_em"])

    @action(detail=True, methods=["get"], url_path="readiness", url_name="readiness")
    def prontidao(self, request, pk=None):
        """Um diagnóstico do que falta para a empresa operar de verdade.

        Junta as três perguntas que aparecem no primeiro dia: o cadastro está
        completo? existe conta bancária? existe cliente com endereço? A tela
        inicial mostra isso como uma lista de tarefas.
        """
        from apps.bancos.models import ContaBancaria
        from apps.clientes.models import Cliente

        empresa = self.get_object()
        contas = ContaBancaria.objects.filter(empresa=empresa, ativa=True)
        serializer = self.get_serializer(empresa)

        return Response({
            "apta_a_emitir": empresa.apta_a_emitir,
            "pendencias_cadastro": serializer.data.get("pendencias_cadastro", []),
            "contas_bancarias": contas.count(),
            "contas_com_transmissao": sum(
                1 for c in contas if c.transmissao_automatica
            ),
            "clientes": Cliente.objects.filter(empresa=empresa).count(),
            "clientes_prontos_para_boleto": sum(
                1 for c in Cliente.objects.filter(empresa=empresa, status="ATIVO")
                .only("logradouro", "cidade", "uf", "cep")
                if c.endereco_completo_para_boleto
            ),
        })
