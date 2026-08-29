from rest_framework.permissions import BasePermission

from core.roles import TOTAL, Papel, pode, pode_capacidade, ve_valores

ACOES_PADRAO = TOTAL


def _capacidade_da_acao(view) -> str | None:
    """Capacidade declarada pela ação em curso.

    Duas formas, e a do método vence: `@action(...)` decorado com
    `capacidade="enviar_remessa"` no próprio handler, ou o mapa
    `capacidades_por_acao` na classe. A primeira mantém a regra ao lado do
    código que ela protege; a segunda existe para ações herdadas.
    """
    acao = getattr(view, "action", None)
    if acao:
        handler = getattr(view, acao, None)
        declarada = getattr(handler, "capacidade", None)
        if declarada:
            return declarada
    return getattr(view, "capacidades_por_acao", {}).get(acao)


class PermissaoDeModulo(BasePermission):
    """Aplica a matriz RBAC. A view declara `modulo = "cobrancas"`."""

    message = "Seu perfil não tem permissão para esta operação."

    def has_permission(self, request, view):
        user = request.user
        if not user or not user.is_authenticated or not user.is_active:
            return False
        modulo = getattr(view, "modulo", None)
        if modulo is None:
            return False

        # Operação nomeada tem regra própria e ela decide sozinha: "enviar
        # remessa" não é `create` de coisa nenhuma, e tratá-la como CRUD
        # deixaria o Operador despachando arquivo para o banco só por poder
        # cadastrar cobrança.
        capacidade = _capacidade_da_acao(view)
        if capacidade:
            return pode_capacidade(user.papel, capacidade)

        acao = getattr(view, "action", None)
        if acao not in ACOES_PADRAO:
            equivalencias = getattr(view, "permissoes_por_acao", {})
            acao = equivalencias.get(acao) or _acao_por_metodo(request.method)
        return pode(user.papel, modulo, acao)


def _acao_por_metodo(metodo: str) -> str:
    return {
        "GET": "list",
        "HEAD": "list",
        "OPTIONS": "list",
        "POST": "create",
        "PUT": "update",
        "PATCH": "partial_update",
        "DELETE": "destroy",
    }.get(metodo.upper(), "list")


def exige(capacidade: str):
    """Marca o handler de uma `@action` com a capacidade que ela representa.

        @action(detail=True, methods=["post"])
        @exige("enviar_remessa")
        def enviar(self, request, pk=None): ...
    """

    def decorador(func):
        func.capacidade = capacidade
        return func

    return decorador


class PertenceAEmpresa(BasePermission):
    """Garante que a empresa ativa (X-Empresa-Id) pertence ao usuário."""

    message = "Você não tem acesso à empresa selecionada."

    def has_permission(self, request, view):
        user = request.user
        empresa_id = getattr(request, "empresa_id", None)
        if empresa_id is None:
            return True  # rotas globais (ex.: listar empresas do usuário)
        return user.tem_acesso_empresa(empresa_id)

    def has_object_permission(self, request, view, obj):
        empresa_id = getattr(obj, "empresa_id", None)
        if empresa_id is None:
            return True
        return request.user.tem_acesso_empresa(empresa_id)


class SomenteAdministrador(BasePermission):
    message = "Operação restrita a administradores."

    def has_permission(self, request, view):
        return bool(
            request.user
            and request.user.is_authenticated
            and request.user.papel == Papel.ADMINISTRADOR
        )


def usuario_ve_valores(user) -> bool:
    return bool(user and user.is_authenticated and ve_valores(user.papel))
