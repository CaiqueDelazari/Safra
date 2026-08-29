"""As 25 posições que são só do Safra dentro do código de barras.

O código de barras tem 44 posições e 19 delas são iguais em todo banco do país
(`apps/bancos/boleto.py`). As outras 25 — o "campo livre" — cada banco monta
do seu jeito, e é o que este módulo faz. É também onde mora o dígito
verificador do nosso número, que é regra do Safra e de mais ninguém.

Composição usada aqui:

    1 posição   constante '7'
    5 posições  agência
    8 posições  conta corrente
    9 posições  nosso número
    1 posição   DV do nosso número
    1 posição   constante '2'
    ─────────
    25 posições

CONFERIR contra o manual, como todo o resto do layout — mas com uma diferença
importante em relação ao arquivo de remessa: um erro aqui **não** é recusado
pelo banco. Ele gera um boleto que o caixa lê e credita em outro lugar, ou não
lê. Por isso `tests/test_boleto.py` compara a saída com boletos reais, e é o
teste que precisa ser refeito com um boleto do convênio antes de emitir em
produção.
"""
from apps.bancos.boleto import modulo11, so_digitos, zfill

TAMANHO_NOSSO_NUMERO = 9


def dv_nosso_numero(nosso_numero: str) -> str:
    """DV do nosso número no padrão Safra.

    Módulo 11 com pesos cíclicos de 2 a 7, da direita para a esquerda; o
    dígito é o complemento do resto para 11, e o resultado 10 vira 1 (0
    continua 0). É a única regra do sistema em que 10 vira 1 e não 0 — no
    código de barras a exceção é outra —, e trocá-las gera boleto que passa em
    toda validação interna e falha no caixa.
    """
    resto = modulo11(nosso_numero, pesos=range(2, 8))
    dv = (11 - resto) % 11
    return "1" if dv == 10 else str(dv)


def montar(conta, nosso_numero: str) -> str:
    """As 25 posições, para uma conta e um nosso número."""
    numero = zfill(nosso_numero, TAMANHO_NOSSO_NUMERO)
    return (
        "7"
        + zfill(conta.agencia, 5)
        + zfill(conta.conta, 8)
        + numero
        + dv_nosso_numero(numero)
        + "2"
    )


def nosso_numero_formatado(nosso_numero: str) -> str:
    """Como aparece impresso no boleto: número e dígito separados por barra."""
    numero = zfill(nosso_numero, TAMANHO_NOSSO_NUMERO)
    return f"{numero}/{dv_nosso_numero(numero)}"


def extrair_nosso_numero(campo_livre: str) -> str:
    """Caminho inverso — usado para ler o boleto de volta em suporte."""
    digitos = so_digitos(campo_livre)
    if len(digitos) != 25:
        return ""
    return digitos[14:23]
