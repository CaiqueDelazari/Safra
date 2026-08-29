"""Cria a primeira empresa e o primeiro administrador.

    python manage.py criar_admin

Interativo por padrão, porque é rodado uma vez, à mão, no servidor. Aceita
argumentos para poder entrar num script de provisionamento.

A senha nunca vem por argumento com valor padrão e nunca é inventada com um
valor "temporário" conhecido: ou vem do ambiente, ou é pedida sem eco, ou é
gerada aleatória e mostrada uma única vez.
"""
import getpass
import os

from django.core.management.base import BaseCommand, CommandError
from django.db import transaction
from django.utils.crypto import get_random_string

from apps.accounts.models import User, UsuarioEmpresa
from apps.empresas.models import Empresa
from core.roles import Papel
from core.validadores import cnpj_valido, so_digitos


class Command(BaseCommand):
    help = "Cria a primeira empresa e o usuário administrador dela."

    def add_arguments(self, parser):
        parser.add_argument("--email")
        parser.add_argument("--nome")
        parser.add_argument("--cnpj")
        parser.add_argument("--razao-social")
        parser.add_argument("--nome-fantasia")
        parser.add_argument(
            "--sem-interacao", action="store_true",
            help="Falha em vez de perguntar. Para provisionamento automatizado.",
        )

    def handle(self, *args, **opcoes):
        interativo = not opcoes["sem_interacao"]

        email = (opcoes.get("email") or self._perguntar("E-mail do administrador",
                                                        interativo)).strip().lower()
        if not email:
            raise CommandError("E-mail é obrigatório.")
        if User.objects.filter(email__iexact=email).exists():
            raise CommandError(f"Já existe usuário com o e-mail {email}.")

        nome = (opcoes.get("nome") or self._perguntar("Nome completo", interativo)).strip()
        cnpj = so_digitos(opcoes.get("cnpj") or self._perguntar("CNPJ da empresa",
                                                                interativo))
        if not cnpj_valido(cnpj):
            raise CommandError(
                "CNPJ inválido. Ele vai impresso no boleto e transmitido ao "
                "banco — não dá para corrigir depois sem reemitir."
            )
        if Empresa.objects.filter(cnpj=cnpj).exists():
            raise CommandError("Já existe empresa com este CNPJ.")

        razao = (opcoes.get("razao_social")
                 or self._perguntar("Razão social", interativo)).strip()
        fantasia = (opcoes.get("nome_fantasia")
                    or self._perguntar("Nome fantasia", interativo, obrigatorio=False)
                    or razao).strip()

        senha, gerada = self._senha(interativo)

        with transaction.atomic():
            empresa = Empresa.objects.create(
                cnpj=cnpj, razao_social=razao, nome_fantasia=fantasia[:120]
            )
            usuario = User(email=email, nome_completo=nome, empresa_padrao=empresa,
                           is_staff=True)
            usuario.set_password(senha)
            usuario.full_clean(exclude=["password"])
            usuario.save()
            UsuarioEmpresa.objects.create(
                usuario=usuario, empresa=empresa, papel=Papel.ADMINISTRADOR, ativo=True
            )

        self.stdout.write(self.style.SUCCESS(
            f"\nEmpresa '{empresa.nome_fantasia}' e administrador {email} criados."
        ))
        if gerada:
            self.stdout.write(self.style.WARNING(
                f"Senha gerada (aparece uma vez só): {senha}"
            ))
        self.stdout.write(
            "\nPróximos passos:\n"
            "  1. Complete o endereço da empresa (é exigido pelo banco).\n"
            "  2. Cadastre a conta bancária, com carteira e código do cedente.\n"
            "  3. Rode `manage.py conferir_layout --conta <id>` e confira contra\n"
            "     o manual do banco antes da primeira remessa.\n"
            "  4. Ative o segundo fator desta conta: ela administra credencial\n"
            "     bancária.\n"
        )

    def _perguntar(self, rotulo: str, interativo: bool, obrigatorio: bool = True) -> str:
        if not interativo:
            if obrigatorio:
                raise CommandError(f"Faltou informar: {rotulo}.")
            return ""
        return input(f"{rotulo}: ")

    def _senha(self, interativo: bool) -> tuple[str, bool]:
        do_ambiente = os.environ.get("ADMIN_SENHA")
        if do_ambiente:
            return do_ambiente, False
        if interativo:
            senha = getpass.getpass("Senha (deixe vazio para gerar uma): ")
            if senha:
                repetida = getpass.getpass("Repita a senha: ")
                if senha != repetida:
                    raise CommandError("As senhas não conferem.")
                return senha, False
        return get_random_string(16), True
