"""Confere se todo endereço que o painel chama existe no backend.

O erro que isto pega é dos mais chatos de descobrir tarde: a tela compila, o
`tsc` passa, os testes do backend passam — e só clicando, em produção,
aparece um 404, porque o caminho é `/clientes/` de um lado e `/clients/` do
outro.

TypeScript não enxerga string de URL. Teste de backend não enxerga o que o
frontend pede. A costura entre os dois não tem dono, e é exatamente ali que
esse defeito mora.

    python manage.py conferir_rotas

Sai com código 1 quando falta rota, para poder entrar num pipeline. Não
precisa de banco: lê o resolvedor do Django e o código do painel.
"""
import re
from pathlib import Path

from django.core.management.base import BaseCommand
from django.urls import get_resolver
from django.urls.resolvers import URLPattern, URLResolver

#: O painel, a partir deste arquivo:
#: backend/core/management/commands/ -> backend/ -> raiz -> frontend/src
FRONTEND = Path(__file__).resolve().parents[4] / "frontend" / "src"

#: `api.get<Tipo>("/clients/")` e as demais formas do cliente HTTP.
CHAMADA = re.compile(
    r"""api\.(?:get|post|patch|put|delete|upload)<[^>]*>?\(\s*[`"']([^`"']+)"""
)
#: `useLista<Tipo>("/charges/")`, `useRecurso`, `useRecursoVivo`.
HOOK = re.compile(r"""use(?:Lista|Recurso|RecursoVivo)<[^>]*>\(\s*[`"']([^`"']+)""")


def _rotas(resolver, prefixo=""):
    for padrao in resolver.url_patterns:
        atual = prefixo + str(padrao.pattern)
        if isinstance(padrao, URLResolver):
            yield from _rotas(padrao, atual)
        elif isinstance(padrao, URLPattern):
            yield atual


def _normalizar(rota: str) -> str:
    """`/api/v1/clients/<pk>/charges/` vira `/clients/{}/charges/`.

    Os dois lados precisam falar a mesma língua para poderem ser comparados:
    o Django escreve parâmetro como `<pk>`, o painel escreve `${id}`.
    """
    rota = "/" + rota.lstrip("^/").replace("\\.", ".")
    rota = re.sub(r"\(\?P<[^>]+>[^)]*\)", "{}", rota)
    rota = re.sub(r"<[^>]+>", "{}", rota)
    rota = rota.replace("$", "").replace("^", "")
    if not rota.endswith("/"):
        rota += "/"
    return rota.replace("/api/v1", "", 1)


class Command(BaseCommand):
    help = "Confere se os endereços chamados pelo painel existem no backend."

    def handle(self, *args, **opcoes):
        backend = {_normalizar(r) for r in _rotas(get_resolver())}

        if not FRONTEND.exists():
            self.stdout.write(
                self.style.WARNING(
                    f"Painel não encontrado em {FRONTEND}. Nada a conferir."
                )
            )
            return

        chamadas: dict[str, set[str]] = {}
        for arquivo in FRONTEND.rglob("*.ts*"):
            texto = arquivo.read_text(encoding="utf-8")
            for achado in [*CHAMADA.findall(texto), *HOOK.findall(texto)]:
                # `/clients/${id}/charges/` vira `/clients/{}/charges/`
                caminho = re.sub(r"\$\{[^}]+\}", "{}", achado).split("?")[0]
                if not caminho.startswith("/"):
                    continue
                if not caminho.endswith("/"):
                    caminho += "/"
                chamadas.setdefault(caminho, set()).add(
                    str(arquivo.relative_to(FRONTEND)).replace("\\", "/")
                )

        faltando = {c: onde for c, onde in sorted(chamadas.items()) if c not in backend}

        self.stdout.write(
            f"{len(backend)} rotas no backend, {len(chamadas)} endereços "
            "chamados pelo painel."
        )

        if not faltando:
            self.stdout.write(
                self.style.SUCCESS("Todos os endereços do painel existem no backend.")
            )
            return

        self.stdout.write("")
        self.stdout.write(
            self.style.ERROR(f"{len(faltando)} endereço(s) sem rota correspondente:")
        )
        for caminho, onde in faltando.items():
            self.stdout.write(self.style.ERROR(f"  {caminho}"))
            for arquivo in sorted(onde):
                self.stdout.write(f"      chamado em {arquivo}")
            # Sugerir o parecido poupa a garimpagem manual: quase sempre o
            # certo está ali, com uma letra de diferença.
            raiz = caminho.strip("/").split("/")[0][:5]
            for parecida in sorted(
                r for r in backend if r.strip("/").startswith(raiz)
            )[:4]:
                self.stdout.write(f"      talvez seja {parecida}")

        raise SystemExit(1)
