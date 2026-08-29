from django.contrib.auth.password_validation import validate_password
from django.utils.crypto import get_random_string
from rest_framework import serializers
from rest_framework.exceptions import AuthenticationFailed
from rest_framework_simplejwt.serializers import TokenObtainPairSerializer

from apps.accounts.models import User, UsuarioEmpresa
from apps.accounts.segundo_fator import exigido_para
from apps.empresas.serializers import EmpresaResumoSerializer
from core.audit import registrar
from core.midia import url_assinada
from core.roles import CAPACIDADES, MATRIZ, Papel


class LoginSerializer(TokenObtainPairSerializer):
    @classmethod
    def get_token(cls, user):
        token = super().get_token(user)
        token["nome"] = user.nome_completo
        token["empresa_padrao"] = user.empresa_padrao_id
        # O papel NÃO entra no token, e a ausência é deliberada: papel agora
        # depende da empresa ativa, que muda a cada troca no seletor do topo.
        # Um papel carimbado no JWT ficaria velho no instante seguinte, e
        # decisões de permissão tomadas com ele estariam erradas em silêncio.
        return token

    def validate(self, attrs):
        dados = super().validate(attrs)
        self._conferir_segundo_fator()
        # O contexto carrega o request: sem ele o link do avatar sairia
        # relativo, e o painel mora em outro domínio.
        dados["usuario"] = UsuarioMeSerializer(self.user, context=self.context).data
        return dados

    def _conferir_segundo_fator(self) -> None:
        """Senha certa ainda não é entrada, para quem tem o fator cadastrado.

        O erro sai com `codigo` próprio para o painel saber a diferença entre
        "falta o código" (mostrar o campo) e "código errado" (avisar).
        """
        if not exigido_para(self.user):
            return
        codigo = (self.initial_data.get("codigo") or "").strip()
        if not codigo:
            raise AuthenticationFailed(
                {"detail": "Informe o código do aplicativo autenticador.",
                 "codigo": "segundo_fator_exigido"}
            )
        if not self.user.segundo_fator.verificar(codigo):
            registrar("LOGIN_FALHA", modulo="accounts", usuario=self.user,
                      descricao=f"Segundo fator inválido para {self.user.email}")
            raise AuthenticationFailed(
                {"detail": "Código inválido ou já usado.",
                 "codigo": "segundo_fator_invalido"}
            )


class PermissoesSerializer(serializers.Serializer):
    """Espelha a matriz RBAC para o painel montar menu e esconder botão.

    O painel esconder o que o usuário não pode fazer é conveniência, não
    segurança — quem recusa de verdade é `core/permissions.py`, a cada
    requisição. Mandar a matriz para o cliente evita que ele adivinhe as
    regras e as reimplemente em JavaScript, que é como as duas versões acabam
    divergindo.
    """

    def to_representation(self, user):
        papel = user.papel
        return {
            "papel": papel,
            "ve_valores": user.ve_valores,
            "modulos": {
                modulo: sorted(papeis.get(papel, set()))
                for modulo, papeis in MATRIZ.items()
                if papeis.get(papel)
            },
            "capacidades": sorted(
                nome for nome, papeis in CAPACIDADES.items() if papel in papeis
            ),
        }


class UsuarioMeSerializer(serializers.ModelSerializer):
    empresas = serializers.SerializerMethodField()
    permissoes = serializers.SerializerMethodField()
    avatar = serializers.SerializerMethodField()
    segundo_fator_ativo = serializers.SerializerMethodField()

    class Meta:
        model = User
        fields = ("id", "uuid", "email", "nome_completo", "telefone", "papel", "avatar",
                  "empresa_padrao", "empresas", "permissoes", "is_active",
                  "segundo_fator_ativo", "plataforma_admin")
        read_only_fields = fields

    def get_empresas(self, obj):
        """As empresas que ele ALCANÇA, com o papel que exerce em cada uma.

        É o que monta o seletor do topo do painel. O papel vem junto porque a
        mesma pessoa pode ser administradora aqui e consulta ali — e a tela
        precisa saber disso antes de trocar, não depois.
        """
        from apps.empresas.models import Empresa

        qs = Empresa.objects.filter(
            id__in=obj.empresas_permitidas_ids(), ativa=True
        ).order_by("nome_fantasia")
        papeis = dict(
            obj.vinculos.filter(ativo=True).values_list("empresa_id", "papel")
        )
        dados = EmpresaResumoSerializer(qs, many=True, context=self.context).data
        for empresa in dados:
            empresa["papel"] = papeis.get(
                empresa["id"], Papel.ADMINISTRADOR if obj.plataforma_admin else None
            )
        return dados

    def get_permissoes(self, obj):
        return PermissoesSerializer().to_representation(obj)

    def get_segundo_fator_ativo(self, obj) -> bool:
        return exigido_para(obj)

    def get_avatar(self, obj) -> str | None:
        return url_assinada(obj.avatar, self.context.get("request"))


class UsuarioSerializer(serializers.ModelSerializer):
    """Usuário visto de dentro de uma empresa.

    O papel não é campo do usuário: é do vínculo com a empresa ativa (ver
    `apps/accounts/models.py`). Este serializer esconde a indireção do painel
    — ele manda e recebe `papel` como se fosse um campo comum, e a gravação
    vai para `UsuarioEmpresa`.

    Consequência que importa na prática: cadastrar alguém que já tem conta na
    plataforma (o contador que atende três clientes nossos) **não** cria um
    usuário novo nem mexe na senha dele. Cria um vínculo. Recusar com
    "e-mail já em uso" seria tecnicamente correto e praticamente inútil.
    """

    senha = serializers.CharField(
        write_only=True, required=False, validators=[validate_password]
    )
    papel = serializers.ChoiceField(choices=Papel.choices)
    avatar = serializers.SerializerMethodField()
    ativo_na_empresa = serializers.SerializerMethodField()
    segundo_fator_ativo = serializers.SerializerMethodField()

    class Meta:
        model = User
        fields = ("id", "uuid", "email", "nome_completo", "telefone", "papel",
                  "avatar", "is_active", "ativo_na_empresa", "segundo_fator_ativo",
                  "senha", "criado_em")
        read_only_fields = ("id", "uuid", "criado_em")

    # ------------------------------------------------------------- leitura
    def _empresa_id(self):
        return self.context.get("empresa_id")

    def _vinculo(self, obj):
        # `vinculos` vem do `prefetch_related` da viewset; percorrer a lista já
        # carregada evita uma consulta por linha na tela de equipe.
        for vinculo in obj.vinculos.all():
            if vinculo.empresa_id == self._empresa_id():
                return vinculo
        return None

    def get_avatar(self, obj) -> str | None:
        return url_assinada(obj.avatar, self.context.get("request"))

    def get_ativo_na_empresa(self, obj) -> bool:
        vinculo = self._vinculo(obj)
        return bool(vinculo and vinculo.ativo)

    def get_segundo_fator_ativo(self, obj) -> bool:
        return exigido_para(obj)

    def to_representation(self, obj):
        dados = super().to_representation(obj)
        vinculo = self._vinculo(obj)
        dados["papel"] = vinculo.papel if vinculo else None
        return dados

    # ------------------------------------------------------------- escrita
    def create(self, validados):
        empresa_id = self._empresa_id()
        senha = validados.pop("senha", None)
        papel = validados.pop("papel")

        email = validados.pop("email").lower().strip()
        usuario = User.objects.filter(email__iexact=email).first()

        if usuario is None:
            usuario = User(email=email, **validados)
            # Sem senha informada, gera uma aleatória: a conta existe, ninguém
            # entra nela, e o convite/redefinição é o caminho de entrada. Uma
            # senha padrão seria a mesma em toda conta criada assim.
            usuario.set_password(senha or get_random_string(24))
            usuario.full_clean(exclude=["password"])
            usuario.save()
        elif senha:
            # Conta que já existe em outra empresa: nunca se troca a senha por
            # aqui. O administrador desta empresa não tem autoridade sobre a
            # credencial de quem também atende outra.
            raise serializers.ValidationError({
                "senha": (
                    "Esta pessoa já tem conta na plataforma. O vínculo com a sua "
                    "empresa será criado e ela entra com a senha que já usa."
                )
            })

        vinculo, criado = UsuarioEmpresa.objects.get_or_create(
            usuario=usuario, empresa_id=empresa_id,
            defaults={"papel": papel, "ativo": True},
        )
        if not criado:
            vinculo.papel = papel
            vinculo.ativo = True
            vinculo.save(update_fields=["papel", "ativo", "atualizado_em"])

        if usuario.empresa_padrao_id is None:
            usuario.empresa_padrao_id = empresa_id
            usuario.save(update_fields=["empresa_padrao", "atualizado_em"])

        registrar("CRIACAO", modulo="usuarios", instancia=usuario, empresa_id=empresa_id,
                  descricao=f"{usuario.email} vinculado como {papel}")
        return usuario

    def update(self, instancia, validados):
        empresa_id = self._empresa_id()
        senha = validados.pop("senha", None)
        papel = validados.pop("papel", None)

        for campo, valor in validados.items():
            setattr(instancia, campo, valor)

        if senha:
            # Só quando a pessoa pertence a esta empresa e a nenhuma outra;
            # caso contrário, o administrador daqui redefiniria o acesso dela lá.
            if instancia.vinculos.exclude(empresa_id=empresa_id).exists():
                raise serializers.ValidationError({
                    "senha": (
                        "Esta pessoa também acessa outras empresas. A senha só pode "
                        "ser trocada por ela mesma."
                    )
                })
            instancia.set_password(senha)
        instancia.save()

        if papel:
            UsuarioEmpresa.objects.filter(
                usuario=instancia, empresa_id=empresa_id
            ).update(papel=papel)
        return instancia


class TrocaSenhaSerializer(serializers.Serializer):
    senha_atual = serializers.CharField()
    nova_senha = serializers.CharField(validators=[validate_password])


class PerfilSerializer(serializers.Serializer):
    """Campos que o próprio usuário pode mudar em si — e só eles.

    Gravar direto o que vem no corpo permitiria apontar `empresa_padrao` para
    uma empresa alheia (a permissão barraria depois, mas o cadastro ficaria
    sujo) e estourar o tamanho da coluna, o que vira 500 em vez de mensagem.
    """

    nome_completo = serializers.CharField(max_length=160, required=False)
    telefone = serializers.CharField(max_length=20, required=False, allow_blank=True)
    empresa_padrao = serializers.IntegerField(required=False, allow_null=True)

    def validate_empresa_padrao(self, valor):
        if valor is None:
            return None
        if valor not in self.context["usuario"].empresas_permitidas_ids():
            raise serializers.ValidationError("Você não tem acesso a esta empresa.")
        return valor


class SegundoFatorConfirmacaoSerializer(serializers.Serializer):
    codigo = serializers.CharField(max_length=32)


class SegundoFatorRemocaoSerializer(serializers.Serializer):
    """Desligar o fator pede a senha: um navegador esquecido aberto não basta."""

    senha = serializers.CharField()
