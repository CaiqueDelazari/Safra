"""ViewSets base: tenancy + RBAC + serializer sensível ao papel."""
from rest_framework import viewsets

from core.permissions import PermissaoDeModulo, PertenceAEmpresa


class BaseViewSet(viewsets.ModelViewSet):
    # `PertenceAEmpresa` primeiro, de propósito. Um usuário que manda o
    # `X-Empresa-Id` de outra empresa não tem papel nenhum ali, então
    # `PermissaoDeModulo` o barraria antes — com "seu perfil não tem
    # permissão", que manda o suporte procurar um problema de papel que não
    # existe. Nesta ordem a resposta é "você não tem acesso a esta empresa",
    # que é a verdade.
    permission_classes = [PertenceAEmpresa, PermissaoDeModulo]
    modulo: str = ""
    repository = None
    #: Declarado aqui para que uma `@action` possa sobrepô-lo. O DRF só aceita
    #: em `@action(...)` argumentos que existam como atributo da classe — sem
    #: esta linha, `@action(throttle_scope="upload_retorno")` derruba a
    #: importação das rotas, não a requisição. Vale para o upload de retorno e
    #: a importação de planilha, que precisam de teto próprio.
    throttle_scope = None

    def get_serializer_context(self):
        ctx = super().get_serializer_context()
        ctx["papel"] = getattr(self.request.user, "papel", None)
        ctx["empresa_id"] = getattr(self.request, "empresa_id", None)
        return ctx


class TenantViewSet(BaseViewSet):
    """Todo queryset é derivado do repositório, já filtrado pela empresa ativa."""

    def get_queryset(self):
        return self.repository.query(getattr(self.request, "empresa_id", None))

    def perform_create(self, serializer):
        serializer.save(empresa_id=self.request.empresa_id)
