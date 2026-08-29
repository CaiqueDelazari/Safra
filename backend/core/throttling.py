"""Tetos de requisição.

O padrão anterior era só `ScopedRateThrottle`: quem não declarasse
`throttle_scope` ficava sem limite nenhum: dava para varrer a base inteira,
ou repetir `refresh` à vontade, com um token válido e um laço de shell.

As duas classes abaixo fecham esse buraco por baixo, sem atropelar quem já tem
escopo próprio — integrações bancárias e a entrega de mídia precisam de tetos
muito mais altos que o de uma tela.
"""
from hashlib import sha256

from rest_framework.throttling import (
    AnonRateThrottle,
    SimpleRateThrottle,
    UserRateThrottle,
)


class _RespeitaEscopo:
    """Sai da frente quando a view declara o próprio escopo."""

    def allow_request(self, request, view):
        if getattr(view, "throttle_scope", None):
            return True
        return super().allow_request(request, view)


class AnonimoThrottle(_RespeitaEscopo, AnonRateThrottle):
    pass


class UsuarioThrottle(_RespeitaEscopo, UserRateThrottle):
    pass


class LoginPorContaThrottle(SimpleRateThrottle):
    """Teto de tentativas por e-mail, somado ao teto por origem.

    O limite por IP sozinho não protege de força bruta distribuída: basta
    trocar de máquina a cada dez tentativas para martelar a mesma conta a noite
    inteira. Aqui a chave é o e-mail tentado, venha de onde vier.

    Só conta tentativa de login: uma vez autenticado, a rota não é mais usada.
    """

    scope = "login_conta"

    def get_cache_key(self, request, view):
        email = (request.data.get("email") or "").strip().lower()
        if not email:
            return None  # sem e-mail não há conta para proteger; o teto por IP resolve
        return self.cache_format % {"scope": self.scope, "ident": sha256(
            email.encode()).hexdigest()}
