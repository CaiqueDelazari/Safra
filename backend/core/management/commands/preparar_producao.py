"""Verificação pré-implantação: aponta tudo que ainda não está pronto.

    python manage.py preparar_producao

Sai com código 1 se encontrar bloqueio, para poder travar o deploy. Avisos não
travam — mas são o que costuma explicar o primeiro incidente.

A lista foi montada de trás para frente: cada item aqui é uma forma conhecida
de o sistema falhar em produção de um jeito que não dá exceção. Chave de cifra
trocada não quebra nada na subida; quebra na hora de ler a credencial do
banco. Faixa de nosso número no fim não dá erro; dá remessa recusada. É esse
tipo de coisa que este comando existe para perguntar antes.
"""
from django.conf import settings
from django.core.management.base import BaseCommand
from django.db import connection
from django.utils.crypto import get_random_string

ALFABETO = "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789!@#%^&*(-_=+)"

#: Abaixo disto, a faixa de "nosso número" contratada com o banco acaba em
#: semanas e a remessa começa a ser recusada sem aviso.
FOLGA_MINIMA_NOSSO_NUMERO = 1000


class Command(BaseCommand):
    help = "Confere se o sistema está pronto para ir ao ar."

    def handle(self, *args, **opcoes):
        bloqueios: list[str] = []
        avisos: list[str] = []

        self._conferir_django(bloqueios, avisos)
        self._conferir_infra(bloqueios, avisos)
        self._conferir_cifra(bloqueios, avisos)
        self._conferir_empresas(bloqueios, avisos)
        self._conferir_contas(bloqueios, avisos)
        self._conferir_acesso(bloqueios, avisos)

        self._relatar(bloqueios, avisos)
        if bloqueios:
            raise SystemExit(1)

    # ------------------------------------------------------------- Django
    def _conferir_django(self, bloqueios, avisos):
        if settings.DEBUG:
            bloqueios.append("DEBUG está ligado. Defina DEBUG=False no .env.")

        if settings.SECRET_KEY in ("dev-insecure-change-me", "") or \
                len(settings.SECRET_KEY) < 40:
            bloqueios.append(
                "SECRET_KEY fraca ou padrão. Gere uma nova:\n"
                f"      SECRET_KEY={get_random_string(64, ALFABETO)}"
            )

        if "*" in settings.ALLOWED_HOSTS:
            bloqueios.append("ALLOWED_HOSTS=* . Liste os domínios reais.")

        if not settings.CORS_ALLOWED_ORIGINS or any(
            o.startswith("http://localhost") for o in settings.CORS_ALLOWED_ORIGINS
        ):
            avisos.append(
                "CORS_ALLOWED_ORIGINS ainda aponta para localhost. O painel em "
                "produção não conseguirá falar com a API."
            )

        if settings.ADMIN_ATIVO and settings.ADMIN_URL == "admin/":
            avisos.append(
                "O admin do Django está ligado no caminho padrão /admin/. "
                "Defina ADMIN_URL para algo não óbvio, ou ADMIN_ATIVO=False."
            )

    # -------------------------------------------------------------- infra
    def _conferir_infra(self, bloqueios, avisos):
        try:
            with connection.cursor() as cursor:
                cursor.execute("SELECT 1")
        except Exception as exc:  # noqa: BLE001
            bloqueios.append(f"Banco de dados inacessível: {exc}")

        try:
            from django.core.cache import cache

            cache.set("preparar_producao", "1", 10)
            if cache.get("preparar_producao") != "1":
                bloqueios.append("Redis responde, mas não guarda valor.")
        except Exception as exc:  # noqa: BLE001
            bloqueios.append(
                f"Redis inacessível: {exc}\n"
                "      Sem ele não há fila: nenhum lote é montado e nenhum "
                "retorno é processado."
            )

        try:
            from config.celery import app

            respostas = app.control.ping(timeout=2)
            if not respostas:
                bloqueios.append(
                    "Nenhum worker Celery respondeu. O sistema aceitaria lotes "
                    "e nunca os processaria — o pior modo de falha possível, "
                    "porque a tela diz 'em processamento' para sempre."
                )
            else:
                self.stdout.write(f"  worker(s) ativo(s): {len(respostas)}")
        except Exception as exc:  # noqa: BLE001
            avisos.append(f"Não foi possível consultar os workers: {exc}")

    # -------------------------------------------------------------- cifra
    def _conferir_cifra(self, bloqueios, avisos):
        from apps.bancos.models import ContaBancaria
        from core.cripto import legivel

        if not settings.CAMPOS_CHAVE:
            avisos.append(
                "CAMPOS_CHAVE não definida: a chave da cifra é derivada da "
                "SECRET_KEY. Trocar a SECRET_KEY tornará as credenciais "
                "bancárias ilegíveis. Gere uma:\n"
                '      python -c "from cryptography.fernet import Fernet; '
                'print(Fernet.generate_key().decode())"'
            )

        # Lê o valor cru direto do banco: passar pelo ORM já decifraria (e
        # devolveria vazio em silêncio, que é justamente o que se quer detectar).
        ilegiveis = []
        with connection.cursor() as cursor:
            cursor.execute(
                "SELECT id, nome, api_client_secret, sftp_senha FROM contas_bancarias"
            )
            for conta_id, nome, segredo, senha in cursor.fetchall():
                for valor in (segredo, senha):
                    if valor and not legivel(valor):
                        ilegiveis.append(f"#{conta_id} {nome}")
                        break
        if ilegiveis:
            bloqueios.append(
                "Credenciais ilegíveis (a chave de cifra mudou) nas contas: "
                + ", ".join(ilegiveis)
                + ".\n      Recadastre-as, ou restaure a CAMPOS_CHAVE anterior."
            )

    # ------------------------------------------------------------ empresa
    def _conferir_empresas(self, bloqueios, avisos):
        from apps.empresas.models import Empresa

        if not Empresa.objects.exists():
            avisos.append("Nenhuma empresa cadastrada — o sistema sobe vazio.")
            return

        inaptas = [e for e in Empresa.objects.filter(ativa=True) if not e.apta_a_emitir]
        if inaptas:
            avisos.append(
                "Empresas com cadastro incompleto para emitir título "
                "(CNPJ, razão social ou endereço): "
                + ", ".join(e.nome_fantasia for e in inaptas[:5])
            )

    # ------------------------------------------------------- conta bancária
    def _conferir_contas(self, bloqueios, avisos):
        from apps.bancos.bancos import MeioDeIntegracao
        from apps.bancos.models import ContaBancaria

        contas = list(ContaBancaria.objects.filter(ativa=True).select_related("empresa"))
        if not contas:
            avisos.append(
                "Nenhuma conta bancária ativa. Sem ela não há como registrar título."
            )
            return

        for conta in contas:
            rotulo = f"{conta.empresa.nome_fantasia} / {conta.nome}"

            if not conta.producao:
                avisos.append(
                    f"{rotulo}: apontando para HOMOLOGAÇÃO. Os títulos não são "
                    "registrados de verdade."
                )

            folga = conta.nosso_numero_maximo - conta.proximo_nosso_numero
            if folga < FOLGA_MINIMA_NOSSO_NUMERO:
                bloqueios.append(
                    f"{rotulo}: restam {folga} números na faixa de nosso número "
                    f"(atual {conta.proximo_nosso_numero}, teto "
                    f"{conta.nosso_numero_maximo}). Peça faixa nova ao banco "
                    "antes que a remessa comece a ser recusada."
                )

            if conta.meio_integracao == MeioDeIntegracao.API and not (
                conta.api_client_id and conta.api_client_secret
            ):
                bloqueios.append(
                    f"{rotulo}: configurada como API e sem credencial. Nenhum "
                    "título seria registrado."
                )

            if not conta.transmissao_automatica:
                avisos.append(
                    f"{rotulo}: sem transmissão automática. A remessa fica para "
                    "download e alguém precisa levá-la ao banco — fluxo válido, "
                    "desde que a operação saiba disso."
                )

    # -------------------------------------------------------------- acesso
    def _conferir_acesso(self, bloqueios, avisos):
        from apps.accounts.models import User, UsuarioEmpresa
        from apps.empresas.models import Empresa
        from core.roles import Papel

        if not User.objects.filter(is_active=True).exists():
            bloqueios.append(
                "Nenhum usuário ativo. Crie o primeiro: "
                "python manage.py criar_admin"
            )
            return

        sem_dono = Empresa.objects.filter(ativa=True).exclude(
            id__in=UsuarioEmpresa.objects.filter(
                papel=Papel.ADMINISTRADOR, ativo=True
            ).values("empresa_id")
        )
        for empresa in sem_dono[:5]:
            avisos.append(
                f"A empresa '{empresa.nome_fantasia}' não tem administrador — "
                "ninguém pode gerenciar a equipe nem as contas bancárias dela."
            )

        sem_segundo_fator = User.objects.filter(
            is_active=True,
            vinculos__papel=Papel.ADMINISTRADOR,
            segundo_fator__isnull=True,
        ).distinct()
        if sem_segundo_fator.exists():
            avisos.append(
                f"{sem_segundo_fator.count()} administrador(es) sem segundo "
                "fator. São as contas que administram credencial bancária."
            )

    # ------------------------------------------------------------ relatório
    def _relatar(self, bloqueios, avisos):
        self.stdout.write("")
        if bloqueios:
            self.stdout.write(self.style.ERROR(f"BLOQUEIOS ({len(bloqueios)})"))
            for item in bloqueios:
                self.stdout.write(self.style.ERROR(f"  ✗ {item}"))
            self.stdout.write("")
        if avisos:
            self.stdout.write(self.style.WARNING(f"AVISOS ({len(avisos)})"))
            for item in avisos:
                self.stdout.write(self.style.WARNING(f"  ! {item}"))
            self.stdout.write("")
        if not bloqueios and not avisos:
            self.stdout.write(self.style.SUCCESS("Tudo pronto para produção."))
        elif not bloqueios:
            self.stdout.write(self.style.SUCCESS(
                "Nenhum bloqueio. Os avisos acima não impedem a publicação."
            ))
