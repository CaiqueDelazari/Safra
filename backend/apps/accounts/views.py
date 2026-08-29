from django.contrib.auth import update_session_auth_hash
from rest_framework import status, viewsets
from rest_framework.decorators import action
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.throttling import ScopedRateThrottle
from rest_framework.views import APIView
from rest_framework_simplejwt.exceptions import TokenError
from rest_framework_simplejwt.tokens import RefreshToken
from rest_framework_simplejwt.views import TokenObtainPairView, TokenRefreshView

from apps.accounts.models import User, UsuarioEmpresa
from apps.accounts.segundo_fator import SegundoFator
from apps.accounts.serializers import (
    LoginSerializer,
    PerfilSerializer,
    SegundoFatorConfirmacaoSerializer,
    SegundoFatorRemocaoSerializer,
    TrocaSenhaSerializer,
    UsuarioMeSerializer,
    UsuarioSerializer,
)
from core.audit import registrar
from core.context import get_context
from core.permissions import (
    PermissaoDeModulo,
    PertenceAEmpresa,
    SomenteAdministrador,
)
from core.throttling import LoginPorContaThrottle


class LoginView(TokenObtainPairView):
    serializer_class = LoginSerializer
    #: Dois tetos somados: um por origem (o escopo, contra varredura de senhas
    #: numa mesma máquina) e um por conta (contra o mesmo e-mail sendo tentado
    #: de vários IPs).
    throttle_scope = "login"
    throttle_classes = [LoginPorContaThrottle, ScopedRateThrottle]

    def post(self, request, *args, **kwargs):
        resposta = super().post(request, *args, **kwargs)
        if resposta.status_code == 200:
            usuario = User.objects.filter(email=request.data.get("email")).first()
            if usuario:
                ip = get_context().ip
                User.objects.filter(pk=usuario.pk).update(ultimo_acesso_ip=ip or None)
                registrar("LOGIN", modulo="accounts", usuario=usuario,
                          descricao=f"Login realizado por {usuario.email}")
        else:
            registrar("LOGIN_FALHA", modulo="accounts",
                      descricao=f"Tentativa de login: {request.data.get('email')}")
        return resposta


class LogoutView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request):
        refresh = request.data.get("refresh")
        if refresh:
            try:
                RefreshToken(refresh).blacklist()
            except TokenError:
                pass
        registrar("LOGOUT", modulo="accounts", descricao=f"Logout de {request.user.email}")
        return Response(status=status.HTTP_204_NO_CONTENT)


class MeView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        return Response(UsuarioMeSerializer(request.user,
                                            context={"request": request}).data)

    def patch(self, request):
        serializer = PerfilSerializer(data=request.data,
                                      context={"usuario": request.user})
        serializer.is_valid(raise_exception=True)
        for campo, valor in serializer.validated_data.items():
            setattr(request.user,
                    "empresa_padrao_id" if campo == "empresa_padrao" else campo, valor)
        request.user.save()
        return Response(UsuarioMeSerializer(request.user,
                                            context={"request": request}).data)


class TrocaSenhaView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request):
        serializer = TrocaSenhaSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        if not request.user.check_password(serializer.validated_data["senha_atual"]):
            return Response({"detail": "Senha atual incorreta."},
                            status=status.HTTP_400_BAD_REQUEST)
        request.user.set_password(serializer.validated_data["nova_senha"])
        request.user.save()
        update_session_auth_hash(request, request.user)
        registrar("TROCA_SENHA", modulo="accounts", descricao="Senha alterada pelo usuário")
        return Response(status=status.HTTP_204_NO_CONTENT)


class UsuarioViewSet(viewsets.ModelViewSet):
    """A equipe da empresa ativa — quem tem acesso e com que papel.

    Escopada pela empresa, e isso não é detalhe: sem o filtro, o
    administrador de uma empresa listaria o nome e o e-mail de todos os
    usuários da plataforma, incluindo os dos concorrentes dele. Num sistema
    monoempresa isso passa; num SaaS é vazamento.

    Contas da plataforma (suporte) ficam de fora da lista pelo mesmo
    princípio: quem mantém o sistema não é da equipe do cliente, não ocupa
    lugar na tela dele e não pode ser desativado por ele.
    """

    modulo = "usuarios"
    serializer_class = UsuarioSerializer
    permission_classes = [SomenteAdministrador, PermissaoDeModulo, PertenceAEmpresa]
    search_fields = ("nome_completo", "email")
    filterset_fields = ("is_active",)
    ordering_fields = ("nome_completo", "criado_em")
    ordering = ("nome_completo",)

    def get_queryset(self):
        empresa_id = getattr(self.request, "empresa_id", None)
        if empresa_id is None:
            return User.objects.none()
        return (
            User.objects.filter(vinculos__empresa_id=empresa_id)
            .exclude(plataforma_admin=True)
            .prefetch_related("vinculos")
            .distinct()
        )

    def get_serializer_context(self):
        contexto = super().get_serializer_context()
        contexto["empresa_id"] = getattr(self.request, "empresa_id", None)
        return contexto

    def perform_destroy(self, instancia):
        """Remover da equipe desliga o vínculo — não apaga a pessoa.

        Apagar o usuário arrastaria junto a autoria de tudo que ele fez, e a
        trilha de auditoria de um sistema financeiro não pode perder o "quem".
        Se ele também atende outra empresa, apagar aqui o expulsaria de lá.
        """
        empresa_id = self.request.empresa_id
        UsuarioEmpresa.objects.filter(
            usuario=instancia, empresa_id=empresa_id
        ).update(ativo=False)
        registrar("EXCLUSAO", modulo="usuarios", instancia=instancia,
                  empresa_id=empresa_id,
                  descricao=f"{instancia.email} removido da equipe")

    @action(detail=True, methods=["post"], url_path="toggle-active", url_name="toggle-active")
    def alternar_status(self, request, pk=None):
        """Liga/desliga o acesso desta pessoa **a esta empresa**."""
        usuario = self.get_object()
        vinculo = UsuarioEmpresa.objects.filter(
            usuario=usuario, empresa_id=request.empresa_id
        ).first()
        if vinculo is None:
            return Response({"detail": "Vínculo não encontrado."},
                            status=status.HTTP_404_NOT_FOUND)
        if usuario.pk == request.user.pk:
            # Um administrador que se desativa perde a única tela onde poderia
            # se reativar — e se for o único da empresa, a empresa fica sem dono.
            return Response(
                {"detail": "Você não pode desativar o próprio acesso."},
                status=status.HTTP_400_BAD_REQUEST,
            )
        vinculo.ativo = not vinculo.ativo
        vinculo.save(update_fields=["ativo", "atualizado_em"])
        registrar("EDICAO", modulo="usuarios", instancia=usuario,
                  empresa_id=request.empresa_id,
                  descricao=f"Acesso {'liberado' if vinculo.ativo else 'bloqueado'}")
        return Response(
            UsuarioSerializer(usuario, context=self.get_serializer_context()).data
        )


class RefreshView(TokenRefreshView):
    """Renovação do access token — com teto próprio.

    Sem isto a rota ficava sem limite: um refresh token vazado renderia acessos
    ilimitados sem nunca reaparecer na tela de login.
    """

    throttle_scope = "refresh"


class SegundoFatorView(APIView):
    """Cadastro do segundo fator do próprio usuário.

    Três passos: `POST` inicia e devolve o QR, `PUT` confirma com o primeiro
    código (e devolve os códigos de recuperação, uma única vez), `DELETE`
    desliga mediante a senha.
    """

    permission_classes = [IsAuthenticated]
    throttle_scope = "segundo_fator"

    def get(self, request):
        registro = getattr(request.user, "segundo_fator", None)
        return Response({
            "ativo": bool(registro and registro.ativo),
            "codigos_restantes": len(registro.codigos_recuperacao) if registro else 0,
        })

    def post(self, request):
        registro = SegundoFator.iniciar(request.user)
        registrar("SEGUNDO_FATOR", modulo="accounts",
                  descricao="Cadastro de segundo fator iniciado")
        return Response({"qr_svg": registro.qr_svg(), "uri": registro.uri(),
                         "segredo": registro.segredo})

    def put(self, request):
        serializer = SegundoFatorConfirmacaoSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        registro = getattr(request.user, "segundo_fator", None)
        if registro is None:
            return Response({"detail": "Comece o cadastro antes de confirmar."},
                            status=status.HTTP_400_BAD_REQUEST)
        codigos = registro.confirmar(serializer.validated_data["codigo"])
        if not codigos:
            return Response({"detail": "Código inválido. Confira o horário do celular."},
                            status=status.HTTP_400_BAD_REQUEST)
        registrar("SEGUNDO_FATOR", modulo="accounts",
                  descricao="Segundo fator ativado")
        return Response({"ativo": True, "codigos_recuperacao": codigos})

    def delete(self, request):
        serializer = SegundoFatorRemocaoSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        if not request.user.check_password(serializer.validated_data["senha"]):
            return Response({"detail": "Senha incorreta."},
                            status=status.HTTP_400_BAD_REQUEST)
        SegundoFator.objects.filter(usuario=request.user).delete()
        registrar("SEGUNDO_FATOR", modulo="accounts",
                  descricao="Segundo fator desativado")
        return Response(status=status.HTTP_204_NO_CONTENT)
