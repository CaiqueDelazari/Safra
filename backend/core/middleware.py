from rest_framework_simplejwt.authentication import JWTAuthentication

from core.context import RequestContext, reset_context, set_context

_jwt = JWTAuthentication()


def _client_ip(request) -> str:
    forwarded = request.META.get("HTTP_X_FORWARDED_FOR", "")
    if forwarded:
        return forwarded.split(",")[0].strip()
    return request.META.get("REMOTE_ADDR", "")


class RequestContextMiddleware:
    """Popula o contexto (usuário, empresa ativa, IP) antes das views.

    A empresa ativa vem do header `X-Empresa-Id`. A validação de que o usuário
    pode acessar aquela empresa acontece em `core.permissions.PertenceAEmpresa`.
    """

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        user = getattr(request, "user", None)
        if user is None or not getattr(user, "is_authenticated", False):
            try:
                auth = _jwt.authenticate(request)
                user = auth[0] if auth else None
            except Exception:
                user = None

        empresa_id = request.headers.get("X-Empresa-Id")
        try:
            empresa_id = int(empresa_id) if empresa_id else None
        except (TypeError, ValueError):
            empresa_id = None

        if empresa_id is None and user is not None and getattr(user, "is_authenticated", False):
            empresa_id = user.empresa_padrao_id

        token = set_context(
            RequestContext(
                user=user,
                empresa_id=empresa_id,
                ip=_client_ip(request),
                user_agent=request.META.get("HTTP_USER_AGENT", "")[:400],
            )
        )
        request.empresa_id = empresa_id
        try:
            return self.get_response(request)
        finally:
            reset_context(token)
