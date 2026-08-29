"""As 25 posições que são só do Safra dentro do código de barras.

O código de barras tem 44 posições e 19 delas são iguais em todo banco do país
(`apps/bancos/boleto.py`). As outras 25 — o "campo livre" — cada banco monta
do seu jeito, e é o que este módulo faz.

Composição usada aqui:

    1 posição   constante '7'
    5 posições  agência
    9 posições  conta de cobrança, incluindo o dígito
    9 posições  nosso número
    1 posição   constante '2'
    ─────────
    25 posições

Composição conferida no manual oficial Safra CNAB 400, versão maio/2026.
`tests/test_boleto.py` também fixa o exemplo numérico publicado no manual.
"""
from apps.bancos.boleto import so_digitos, zfill

TAMANHO_NOSSO_NUMERO = 9


def montar(conta, nosso_numero: str) -> str:
    """As 25 posições, para uma conta e um nosso número."""
    numero = zfill(nosso_numero, TAMANHO_NOSSO_NUMERO)
    return (
        "7"
        + zfill(conta.agencia, 5)
        + zfill(so_digitos(conta.conta) + so_digitos(getattr(conta, "conta_dv", "")), 9)
        + numero
        + "2"
    )


def nosso_numero_formatado(nosso_numero: str) -> str:
    """Nosso número de nove posições como aparece no boleto."""
    return zfill(nosso_numero, TAMANHO_NOSSO_NUMERO)


def extrair_nosso_numero(campo_livre: str) -> str:
    """Caminho inverso — usado para ler o boleto de volta em suporte."""
    digitos = so_digitos(campo_livre)
    if len(digitos) != 25:
        return ""
    return digitos[15:24]
