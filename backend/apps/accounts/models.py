"""Usuário e vínculo com empresa.

O papel **não** mora no usuário: mora no vínculo. Num SaaS, a mesma pessoa é
administradora da própria empresa e usuária de consulta na do cliente dela —
um escritório de contabilidade é exatamente isso, e é o caso comum, não o
exótico. Papel global obrigaria a criar dois logins para a mesma pessoa, e
dois logins acabam com a mesma senha.

`user.papel` continua existindo e resolve pelo vínculo da empresa ativa do
contexto (`core/context.py`). Assim toda a camada de permissão segue lendo um
atributo simples, sem passar `empresa_id` de mão em mão.
"""
from django.contrib.auth.models import AbstractBaseUser, BaseUserManager, PermissionsMixin
from django.db import models

from core.midia import upload_avatar_usuario
from core.models import TimeStampedModel
from core.roles import Papel
from core.validadores import validar_imagem


class UserManager(BaseUserManager):
    use_in_migrations = True

    def _create(self, email, password, **extra):
        if not email:
            raise ValueError("E-mail é obrigatório.")
        user = self.model(email=self.normalize_email(email), **extra)
        user.set_password(password)
        user.full_clean(exclude=["password"])
        user.save(using=self._db)
        return user

    def create_user(self, email, password=None, **extra):
        extra.setdefault("is_staff", False)
        extra.setdefault("is_superuser", False)
        return self._create(email, password, **extra)

    def create_superuser(self, email, password=None, **extra):
        extra.setdefault("is_staff", True)
        extra.setdefault("is_superuser", True)
        extra.setdefault("plataforma_admin", True)
        return self._create(email, password, **extra)


class User(AbstractBaseUser, PermissionsMixin, TimeStampedModel):
    email = models.EmailField(unique=True, db_index=True)
    nome_completo = models.CharField(max_length=160)
    telefone = models.CharField(max_length=20, blank=True)

    empresas = models.ManyToManyField(
        "empresas.Empresa", through="UsuarioEmpresa", related_name="usuarios"
    )
    empresa_padrao = models.ForeignKey(
        "empresas.Empresa", on_delete=models.SET_NULL, null=True, blank=True,
        related_name="usuarios_padrao",
    )
    avatar = models.ImageField(
        upload_to=upload_avatar_usuario, blank=True, null=True, validators=[validar_imagem]
    )

    is_active = models.BooleanField(default=True, db_index=True)
    is_staff = models.BooleanField(default=False)
    #: Quem opera a plataforma, não quem a usa. Alcança todas as empresas para
    #: dar suporte, e some das telas de equipe do cliente — a lista de usuários
    #: de uma empresa não deve revelar que existe alguém de fora com acesso.
    #: Só se marca por shell: não existe caminho pela API, de propósito.
    plataforma_admin = models.BooleanField(default=False, db_index=True)

    ultimo_acesso_ip = models.GenericIPAddressField(null=True, blank=True)

    objects = UserManager()

    USERNAME_FIELD = "email"
    REQUIRED_FIELDS = ["nome_completo"]

    class Meta:
        db_table = "users"
        ordering = ("nome_completo",)
        verbose_name = "Usuário"
        verbose_name_plural = "Usuários"

    def __str__(self) -> str:
        return f"{self.nome_completo} <{self.email}>"

    # ------------------------------------------------------------ tenancy
    @property
    def papel(self) -> str | None:
        """Papel na empresa ativa do contexto.

        Sem empresa ativa não há papel: uma rota que precise de permissão de
        módulo sem empresa selecionada deve falhar, e falha — `pode()` com
        papel `None` devolve False. As rotas globais (listar minhas empresas,
        trocar senha) não passam por `PermissaoDeModulo`.
        """
        from core.context import current_empresa_id

        empresa_id = current_empresa_id()
        if empresa_id is None:
            return None
        if self.plataforma_admin:
            return Papel.ADMINISTRADOR
        vinculo = self.vinculos.filter(empresa_id=empresa_id, ativo=True).first()
        return vinculo.papel if vinculo else None

    def papel_em(self, empresa_id) -> str | None:
        if self.plataforma_admin:
            return Papel.ADMINISTRADOR
        vinculo = self.vinculos.filter(empresa_id=empresa_id, ativo=True).first()
        return vinculo.papel if vinculo else None

    def empresas_permitidas_ids(self) -> list[int]:
        if self.plataforma_admin:
            from apps.empresas.models import Empresa

            return list(Empresa.objects.values_list("id", flat=True))
        return list(self.vinculos.filter(ativo=True).values_list("empresa_id", flat=True))

    def tem_acesso_empresa(self, empresa_id) -> bool:
        if self.plataforma_admin:
            # Um X-Empresa-Id inventado precisa ser recusado, e não virar um
            # contexto fantasma onde toda consulta volta vazia.
            from apps.empresas.models import Empresa

            return Empresa.objects.filter(pk=empresa_id).exists()
        return self.vinculos.filter(empresa_id=empresa_id, ativo=True).exists()

    @property
    def ve_valores(self) -> bool:
        from core.roles import ve_valores

        papel = self.papel
        return bool(papel and ve_valores(papel))


class UsuarioEmpresa(TimeStampedModel):
    """Vínculo usuário <-> empresa, com o papel que ele exerce ali."""

    usuario = models.ForeignKey(User, on_delete=models.CASCADE, related_name="vinculos")
    empresa = models.ForeignKey(
        "empresas.Empresa", on_delete=models.CASCADE, related_name="vinculos"
    )
    papel = models.CharField(
        max_length=16, choices=Papel.choices, default=Papel.CONSULTA, db_index=True
    )
    ativo = models.BooleanField(default=True)

    class Meta:
        db_table = "user_tenants"
        constraints = [
            models.UniqueConstraint(
                fields=["usuario", "empresa"], name="uniq_usuario_empresa"
            )
        ]
        indexes = [
            models.Index(fields=["empresa", "ativo"]),
            models.Index(fields=["empresa", "papel", "ativo"]),
        ]

    def __str__(self) -> str:
        return f"{self.usuario_id}@{self.empresa_id} ({self.papel})"


# O segundo fator mora em módulo próprio (apps/accounts/segundo_fator.py) por
# carregar regra de TOTP junto do modelo. O import aqui é o que faz o Django
# enxergar a tabela — não remover.
from apps.accounts.segundo_fator import SegundoFator  # noqa: E402,F401
