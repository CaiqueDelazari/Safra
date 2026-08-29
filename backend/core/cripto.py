"""Segredos de integração guardados fora de claro no banco.

Motivo: a `asaas_api_key` de uma empresa movimenta dinheiro na conta dela. Ser
write-only na API protege quem chega pela porta da frente; não protege um dump
do Postgres — backup extraviado, réplica esquecida, acesso de manutenção ao
banco, `pg_dump` num notebook. Aqui o segredo só existe em claro dentro do
processo do Django.

O que isto **não** é: proteção contra invasão do servidor. Quem lê o
`backend/.env` lê a chave e decifra tudo. O ganho está em separar "quem tem o
banco" de "quem tem a aplicação" — que hoje são a mesma pessoa por acidente, e
deixam de ser no dia do primeiro backup restaurado em outra máquina.

Dois mecanismos, escolhidos pelo uso do segredo:

* **Cifra** (`CampoCifrado`) para o que precisa voltar em claro — a chave do
  Asaas é enviada no header de cada chamada, então tem de ser recuperável.
* **Hash** (`hash_token`) para o que só é comparado — o token do webhook é
  conferido contra o que o Asaas manda e nunca é reexibido. Guardar o hash
  fecha o caso: vazar o banco não entrega token nenhum.

## A chave da cifra

`CAMPOS_CHAVE` no `.env` (formato Fernet, `Fernet.generate_key()`). Sem ela,
deriva-se uma da `SECRET_KEY` — o sistema sobe em desenvolvimento sem
configuração extra e a chave derivada continua valendo como *fallback* de
leitura mesmo depois que uma `CAMPOS_CHAVE` própria entra, então a transição
não perde dado: o valor volta a ser gravado com a chave nova no próximo save.

**Consequência que morde:** sem `CAMPOS_CHAVE`, trocar a `SECRET_KEY` torna as
chaves do Asaas ilegíveis e elas precisam ser recadastradas uma a uma. É por
isso que `preparar_producao` avisa quando ela não está definida.
"""
import base64
import hashlib
import logging
from functools import lru_cache

from cryptography.fernet import Fernet, InvalidToken, MultiFernet
from django.conf import settings
from django.core.exceptions import ImproperlyConfigured
from django.db import models

logger = logging.getLogger(__name__)

#: Marca o que já passou pela cifra. Valor sem o prefixo é lido como texto em
#: claro — é assim que as linhas anteriores à migração continuam funcionando.
PREFIXO = "cif1:"

#: Sal fixo da derivação. Não é segredo: separa esta chave de qualquer outro
#: uso da SECRET_KEY (assinatura de mídia, JWT) para que um não sirva ao outro.
SAL_DERIVACAO = b"erp-monitoramento/campos-cifrados/v1"


def _chave_derivada(secret: str) -> bytes:
    bruto = hashlib.pbkdf2_hmac("sha256", secret.encode(), SAL_DERIVACAO, 200_000)
    return base64.urlsafe_b64encode(bruto)


@lru_cache(maxsize=8)
def _cofre_para(declarada: str, secret: str) -> MultiFernet:
    """A primeira chave cifra; todas decifram (MultiFernet tenta na ordem)."""
    chaves = []
    if declarada:
        try:
            chaves.append(Fernet(declarada.encode()))
        except (ValueError, TypeError) as exc:
            raise ImproperlyConfigured(
                "CAMPOS_CHAVE não está no formato Fernet. Gere uma nova:\n"
                '  python -c "from cryptography.fernet import Fernet; '
                'print(Fernet.generate_key().decode())"'
            ) from exc
    chaves.append(Fernet(_chave_derivada(secret)))
    return MultiFernet(chaves)


def _cofre() -> MultiFernet:
    return _cofre_para(getattr(settings, "CAMPOS_CHAVE", "") or "", settings.SECRET_KEY)


def cifrar(valor: str) -> str:
    if not valor:
        return ""
    if valor.startswith(PREFIXO):  # já cifrado: não cifra duas vezes
        return valor
    return PREFIXO + _cofre().encrypt(valor.encode()).decode()


def decifrar(valor: str | None) -> str:
    """Devolve o texto em claro. Segredo ilegível vira vazio, com log de erro.

    Explodir aqui derrubaria qualquer listagem de empresas — inclusive a tela
    onde a chave seria recadastrada. Some da operação e grita no log; quem
    fecha o diagnóstico é `preparar_producao`, que confere linha a linha.
    """
    if not valor:
        return ""
    if not valor.startswith(PREFIXO):
        return valor  # legado em claro, anterior à migração
    try:
        return _cofre().decrypt(valor[len(PREFIXO):].encode()).decode()
    except InvalidToken:
        logger.error(
            "Segredo ilegível no banco: a chave de cifra mudou (CAMPOS_CHAVE ou "
            "SECRET_KEY). O valor precisa ser recadastrado."
        )
        return ""


def legivel(valor: str | None) -> bool:
    """True se o valor bruto do banco ainda abre com as chaves atuais."""
    if not valor or not valor.startswith(PREFIXO):
        return True
    try:
        _cofre().decrypt(valor[len(PREFIXO):].encode())
        return True
    except InvalidToken:
        return False


def hash_token(valor: str) -> str:
    """Hash de um token de alta entropia, para comparação por igualdade.

    SHA-256 puro, sem sal e sem alongamento, de propósito: o token é aleatório
    e longo (não é senha escolhida por gente), então não há dicionário a
    resistir — e o hash precisa ser determinístico para virar `filter()`.
    """
    return hashlib.sha256(valor.encode()).hexdigest() if valor else ""


class CampoCifrado(models.CharField):
    """CharField que grava cifrado e entrega em claro.

    Não dá para filtrar por igualdade num valor preenchido: a cifra é
    aleatorizada, dois `encrypt` do mesmo texto dão resultados diferentes.
    Comparar `== ""` continua valendo (vazio não é cifrado). Segredo que só
    precisa ser conferido não é caso para este campo — use `hash_token`.

    `max_length` mede a **coluna**, não o segredo: a cifra cresce cerca de 4/3
    mais 80 caracteres. Quem limita o texto de entrada é o serializer.
    """

    def from_db_value(self, value, expression, connection):
        return decifrar(value)

    def get_prep_value(self, value):
        return cifrar(super().get_prep_value(value) or "")
