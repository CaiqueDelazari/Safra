"""Segundo fator por aplicativo (TOTP, RFC 6238).

Duas contas Master abrem tudo neste sistema: carteira completa, valores,
auditoria, gestão de usuários. Senha sozinha protege isso até o dia em que
alguém reusar a senha em outro lugar que vazou.

O aplicativo (Google Authenticator, Authy, 1Password, o que o dono já usar)
guarda um segredo; o servidor guarda o mesmo segredo e confere o número de seis
dígitos. Nada trafega além do código, que vale por trinta segundos.

Códigos de recuperação existem para o dia do celular perdido: são gravados só
como hash, mostrados uma única vez e queimados no uso.
"""
import hashlib
import io
import secrets
import time

import pyotp
import qrcode
import qrcode.image.svg
from django.conf import settings
from django.db import models
from django.utils import timezone

from core.models import TimeStampedModel

QUANTIDADE_CODIGOS = 8
JANELA = 1  # tolera um passo de 30s para cada lado: relógio de celular atrasa


def _hash(codigo: str) -> str:
    """SHA-256 basta: são 40 bits aleatórios nossos, não senha escolhida por gente."""
    return hashlib.sha256(codigo.encode()).hexdigest()


class SegundoFator(TimeStampedModel):
    usuario = models.OneToOneField("accounts.User", on_delete=models.CASCADE,
                                   related_name="segundo_fator")
    segredo = models.CharField(max_length=64)
    #: Enquanto for nulo, o cadastro está pela metade e o login ignora o fator.
    confirmado_em = models.DateTimeField(null=True, blank=True)
    codigos_recuperacao = models.JSONField(default=list, blank=True)
    #: Índice do último passo de 30s aceito. Guardar o passo, e não o código,
    #: recusa também um código anterior ainda dentro da janela de tolerância —
    #: o que só guardar o último código deixava passar.
    ultimo_passo = models.BigIntegerField(null=True, blank=True)
    usado_em = models.DateTimeField(null=True, blank=True)

    class Meta:
        db_table = "usuarios_segundo_fator"
        verbose_name = "Segundo fator"
        verbose_name_plural = "Segundos fatores"

    def __str__(self) -> str:
        return f"2FA de {self.usuario_id}"

    @property
    def ativo(self) -> bool:
        return self.confirmado_em is not None

    # ------------------------------------------------------------- cadastro
    @classmethod
    def iniciar(cls, usuario) -> "SegundoFator":
        """Cria (ou recomeça) o cadastro. Só vale depois de `confirmar`."""
        registro, _ = cls.objects.update_or_create(
            usuario=usuario,
            defaults={"segredo": pyotp.random_base32(), "confirmado_em": None,
                      "codigos_recuperacao": [], "ultimo_passo": None, "usado_em": None},
        )
        return registro

    def uri(self) -> str:
        emissor = getattr(settings, "NOME_DO_SISTEMA", "Plataforma de Cobranças")
        return pyotp.TOTP(self.segredo).provisioning_uri(
            name=self.usuario.email, issuer_name=emissor
        )

    def qr_svg(self) -> str:
        """QR em SVG embutido na resposta — sem imagem servida, sem Pillow."""
        imagem = qrcode.make(self.uri(), image_factory=qrcode.image.svg.SvgPathImage)
        buffer = io.BytesIO()
        imagem.save(buffer)
        return buffer.getvalue().decode()

    def confirmar(self, codigo: str) -> list[str]:
        """Ativa o fator e devolve os códigos de recuperação, uma única vez."""
        if not self.verificar_totp(codigo):
            return []
        codigos = [
            f"{secrets.token_hex(2)}-{secrets.token_hex(3)}"
            for _ in range(QUANTIDADE_CODIGOS)
        ]
        self.codigos_recuperacao = [_hash(c) for c in codigos]
        self.confirmado_em = timezone.now()
        self.save(update_fields=["codigos_recuperacao", "confirmado_em", "atualizado_em"])
        return codigos

    # ------------------------------------------------------------ validação
    def verificar_totp(self, codigo: str) -> bool:
        codigo = (codigo or "").strip().replace(" ", "")
        if not codigo.isdigit():
            return False
        passo = self._passo_do_codigo(codigo)
        if passo is None:
            return False
        # Nenhum código já usado, nem anterior a ele, entra de novo: quem
        # capturou um código na rede não o reaproveita dentro da janela.
        if self.ultimo_passo is not None and passo <= self.ultimo_passo:
            return False
        self.ultimo_passo = passo
        self.usado_em = timezone.now()
        self.save(update_fields=["ultimo_passo", "usado_em", "atualizado_em"])
        return True

    def _passo_do_codigo(self, codigo: str) -> int | None:
        """Em qual intervalo de 30s este código é válido — `None` se em nenhum."""
        totp = pyotp.TOTP(self.segredo)
        agora = int(time.time())
        for salto in range(-JANELA, JANELA + 1):
            momento = agora + salto * totp.interval
            if secrets.compare_digest(totp.at(momento), codigo):
                return momento // totp.interval
        return None

    def verificar_recuperacao(self, codigo: str) -> bool:
        """Código de recuperação vale uma vez só — é queimado no uso."""
        alvo = _hash((codigo or "").strip().lower())
        if alvo not in self.codigos_recuperacao:
            return False
        self.codigos_recuperacao = [c for c in self.codigos_recuperacao if c != alvo]
        self.usado_em = timezone.now()
        self.save(update_fields=["codigos_recuperacao", "usado_em", "atualizado_em"])
        return True

    def verificar(self, codigo: str) -> bool:
        return self.verificar_totp(codigo) or self.verificar_recuperacao(codigo)


def exigido_para(usuario) -> bool:
    """O fator só entra no login de quem terminou o cadastro."""
    registro = getattr(usuario, "segundo_fator", None)
    return bool(registro and registro.ativo)
