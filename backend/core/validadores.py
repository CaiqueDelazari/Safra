"""Validações de entrada compartilhadas entre modelos e serializers.

CPF/CNPJ tem peso desproporcional neste sistema: é ele que vai para o registro
do título no banco. Documento inválido não é erro de cadastro que alguém
corrige depois — é rejeição do banco no dia seguinte, uma linha de ocorrência
no retorno e um boleto que o cliente não recebeu. Barrar na entrada custa
microssegundos; barrar no retorno custa um ciclo de cobrança.
"""
import re
from pathlib import Path

from django.conf import settings
from django.core.exceptions import ValidationError

from core.midia import ARQUIVOS_BANCARIOS, IMAGENS

_NAO_DIGITO = re.compile(r"\D")


def so_digitos(valor: str | None) -> str:
    return _NAO_DIGITO.sub("", valor or "")


# ------------------------------------------------------------ CPF / CNPJ
def _digito_mod11(base: str, pesos: list[int]) -> str:
    soma = sum(int(d) * p for d, p in zip(base, pesos))
    resto = soma % 11
    return "0" if resto < 2 else str(11 - resto)


def cpf_valido(valor: str) -> bool:
    cpf = so_digitos(valor)
    if len(cpf) != 11 or cpf == cpf[0] * 11:
        return False
    d1 = _digito_mod11(cpf[:9], list(range(10, 1, -1)))
    d2 = _digito_mod11(cpf[:9] + d1, list(range(11, 1, -1)))
    return cpf[9:] == d1 + d2


def cnpj_valido(valor: str) -> bool:
    cnpj = so_digitos(valor)
    if len(cnpj) != 14 or cnpj == cnpj[0] * 14:
        return False
    pesos1 = [5, 4, 3, 2, 9, 8, 7, 6, 5, 4, 3, 2]
    pesos2 = [6] + pesos1
    d1 = _digito_mod11(cnpj[:12], pesos1)
    d2 = _digito_mod11(cnpj[:12] + d1, pesos2)
    return cnpj[12:] == d1 + d2


def documento_valido(valor: str) -> bool:
    digitos = so_digitos(valor)
    if len(digitos) == 11:
        return cpf_valido(digitos)
    if len(digitos) == 14:
        return cnpj_valido(digitos)
    return False


def validar_documento_federal(valor: str) -> str:
    """Normaliza para dígitos e devolve. Levanta `ValidationError` se inválido."""
    digitos = so_digitos(valor)
    if not digitos:
        raise ValidationError("Informe o CPF ou CNPJ.")
    if len(digitos) not in (11, 14):
        raise ValidationError("CPF tem 11 dígitos e CNPJ tem 14.")
    if not documento_valido(digitos):
        tipo = "CPF" if len(digitos) == 11 else "CNPJ"
        raise ValidationError(f"{tipo} inválido: os dígitos verificadores não conferem.")
    return digitos


def formatar_documento(valor: str) -> str:
    d = so_digitos(valor)
    if len(d) == 11:
        return f"{d[:3]}.{d[3:6]}.{d[6:9]}-{d[9:]}"
    if len(d) == 14:
        return f"{d[:2]}.{d[2:5]}.{d[5:8]}/{d[8:12]}-{d[12:]}"
    return valor or ""


def tipo_de_pessoa(valor: str) -> str:
    """'F' ou 'J' — é o que o CNAB pede no campo de tipo de inscrição."""
    return "F" if len(so_digitos(valor)) == 11 else "J"


# ------------------------------------------------------------- arquivos
def validar_imagem(arquivo) -> None:
    """Extensão conhecida e tamanho de foto, não de vídeo."""
    limite = settings.UPLOAD_IMAGEM_MAX_MB * 1024 * 1024
    tamanho = getattr(arquivo, "size", 0) or 0
    if tamanho > limite:
        raise ValidationError(
            f"Imagem de {tamanho / 1048576:.1f} MB. O limite é "
            f"{settings.UPLOAD_IMAGEM_MAX_MB} MB."
        )
    nome = getattr(arquivo, "name", "") or ""
    if Path(nome).suffix.lower() not in IMAGENS:
        raise ValidationError("Formato não aceito. Use " + ", ".join(sorted(IMAGENS)) + ".")


def validar_arquivo_bancario(arquivo) -> None:
    """Retorno do banco: texto de posição fixa, do tamanho de um dia de
    movimento.

    O teto é generoso de propósito — um retorno de 50 mil títulos passa de
    20 MB em CNAB 240 — mas existe: sem ele, um envio errado enche o disco da
    VPS e derruba a aplicação inteira junto.
    """
    limite = settings.UPLOAD_ARQUIVO_BANCO_MAX_MB * 1024 * 1024
    tamanho = getattr(arquivo, "size", 0) or 0
    if tamanho > limite:
        raise ValidationError(
            f"Arquivo de {tamanho / 1048576:.1f} MB. O limite é "
            f"{settings.UPLOAD_ARQUIVO_BANCO_MAX_MB} MB."
        )
    ext = Path((getattr(arquivo, "name", "") or "")).suffix.lower()
    if ext not in ARQUIVOS_BANCARIOS:
        raise ValidationError(
            "Envie o arquivo do banco como texto ("
            + ", ".join(sorted(ARQUIVOS_BANCARIOS)) + ")."
        )


def validar_planilha(arquivo) -> None:
    """Importação em massa: CSV ou XLSX."""
    limite = settings.UPLOAD_PLANILHA_MAX_MB * 1024 * 1024
    tamanho = getattr(arquivo, "size", 0) or 0
    if tamanho > limite:
        raise ValidationError(
            f"Planilha de {tamanho / 1048576:.1f} MB. O limite é "
            f"{settings.UPLOAD_PLANILHA_MAX_MB} MB."
        )
    ext = Path((getattr(arquivo, "name", "") or "")).suffix.lower()
    if ext not in {".csv", ".xlsx", ".xls", ".txt"}:
        raise ValidationError("Envie um arquivo .csv ou .xlsx.")
