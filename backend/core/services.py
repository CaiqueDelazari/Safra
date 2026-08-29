"""Service Layer — regras de negócio isoladas de HTTP e de ORM."""
from dataclasses import dataclass


class RegraDeNegocioError(Exception):
    """Violação de invariante de domínio. Vira HTTP 422 no handler da API."""

    def __init__(self, mensagem: str, campo: str | None = None):
        super().__init__(mensagem)
        self.mensagem = mensagem
        self.campo = campo


@dataclass
class Resultado:
    ok: bool
    dados: object = None
    mensagem: str = ""

    @classmethod
    def sucesso(cls, dados=None, mensagem=""):
        return cls(True, dados, mensagem)

    @classmethod
    def falha(cls, mensagem):
        return cls(False, None, mensagem)


class BaseService:
    repository = None
