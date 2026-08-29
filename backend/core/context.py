"""
Contexto de requisição por thread/task.

Guarda usuário, empresa ativa e IP para que camadas profundas (managers,
services, auditoria) possam aplicar tenancy e trilha de auditoria sem
precisar receber o `request` como parâmetro.
"""
from contextlib import contextmanager
from contextvars import ContextVar
from dataclasses import dataclass
from typing import Any, Optional


@dataclass
class RequestContext:
    user: Any = None
    empresa_id: Optional[int] = None
    ip: Optional[str] = None
    user_agent: str = ""


_ctx: ContextVar[RequestContext] = ContextVar("request_context", default=RequestContext())


def get_context() -> RequestContext:
    return _ctx.get()


def set_context(ctx: RequestContext):
    return _ctx.set(ctx)


def reset_context(token) -> None:
    _ctx.reset(token)


def current_user():
    user = get_context().user
    return user if user and getattr(user, "is_authenticated", False) else None


def current_empresa_id() -> Optional[int]:
    return get_context().empresa_id


@contextmanager
def use_context(**kwargs):
    """Usado por comandos de rotina e webhooks, onde não há usuário autenticado."""
    token = set_context(RequestContext(**kwargs))
    try:
        yield
    finally:
        reset_context(token)
