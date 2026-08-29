"""Código de barras, linha digitável e dígitos verificadores.

Tudo aqui é padrão FEBRABAN e vale para qualquer banco — o que muda de banco
para banco é o **campo livre** (25 posições), e essa parte mora no adapter de
cada um (`adapters/safra/campo_livre.py`). Foi a divisão escolhida porque a
aritmética do módulo 10 e do módulo 11 é a mesma no país inteiro, e duplicá-la
por banco garantiria que um dia uma cópia seria corrigida e a outra não.

Um dígito errado aqui não dá erro em lugar nenhum: gera um boleto que o caixa
eletrônico recusa e o cliente liga reclamando. Por isso cada função tem teste
com valor conferido contra boleto real (`tests/test_boleto.py`).
"""
from datetime import date
from decimal import ROUND_HALF_UP, Decimal

#: Data base do fator de vencimento, definida pela FEBRABAN. O fator é a
#: contagem simples de dias desde ela — **sem somar nada**. É o ponto em que a
#: implementação apressada erra: a tentação é fazer `dias + 1000`, porque a
#: documentação diz "o fator começa em 1000", e o resultado fica 1000 dias
#: adiantado em todo boleto do sistema. O que a norma diz é outra coisa: o
#: fator só passou a ser usado quando chegou a 1000, o que aconteceu em
#: 03/07/2000 — exatamente 1000 dias depois da data base.
BASE_FATOR = date(1997, 10, 7)
#: O fator anda de 1000 a 9999 e recomeça em 1000. O primeiro giro se fechou
#: em 21/02/2025 (fator 9999); 22/02/2025 voltou a 1000. Sem tratar a volta,
#: todo boleto emitido daqui em diante sairia com cinco dígitos no campo e
#: seria recusado na hora do pagamento.
FATOR_MIN = 1000
FATOR_MAX = 9999
CICLO_FATOR = FATOR_MAX - FATOR_MIN + 1  # 9000


def so_digitos(valor: str) -> str:
    return "".join(c for c in str(valor or "") if c.isdigit())


def zfill(valor, tamanho: int) -> str:
    """Dígitos à direita, zeros à esquerda — e trunca pela esquerda se estourar.

    Truncar é a escolha certa aqui: o campo tem tamanho fixo no arquivo e no
    código de barras. Estourar significaria deslocar tudo que vem depois e
    invalidar a linha inteira, o que é pior do que um valor errado num campo.
    Quem não pode estourar valida antes — ver `validar_valor`.
    """
    texto = so_digitos(valor)
    return texto[-tamanho:].zfill(tamanho)


# --------------------------------------------------------------- módulo 10
def modulo10(numero: str) -> int:
    """DV dos campos da linha digitável.

    Pesos 2 e 1 alternados da direita para a esquerda; resultado de dois
    dígitos é somado algarismo a algarismo (18 -> 1+8 = 9).
    """
    digitos = so_digitos(numero)
    soma = 0
    peso = 2
    for c in reversed(digitos):
        produto = int(c) * peso
        soma += produto if produto < 10 else produto - 9
        peso = 1 if peso == 2 else 2
    resto = soma % 10
    return 0 if resto == 0 else 10 - resto


# --------------------------------------------------------------- módulo 11
def modulo11(numero: str, *, pesos=range(2, 10), base: int = 11) -> int:
    """Soma ponderada cíclica, da direita para a esquerda. Devolve o resto.

    Só o resto: o que fazer com ele muda por campo — no DV do código de barras
    o resultado 0, 10 e 11 vira 1; no nosso número do Safra, 10 e 11 viram 0.
    Embutir uma dessas regras aqui faria a outra virar exceção silenciosa.
    """
    digitos = so_digitos(numero)
    pesos = list(pesos)
    soma = 0
    for i, c in enumerate(reversed(digitos)):
        soma += int(c) * pesos[i % len(pesos)]
    return soma % base


def dv_codigo_barras(barras_sem_dv: str) -> int:
    """DV geral do código de barras (posição 5), sobre as outras 43 posições.

    Pesos 2 a 9, cíclicos. Resto 0, 1 ou 10 resulta em DV igual a 1 — regra
    da FEBRABAN, e é a que mais se erra: a tentação é devolver 0.
    """
    resto = modulo11(barras_sem_dv)
    dv = 11 - resto
    return 1 if dv in (0, 1, 10, 11) else dv


# ----------------------------------------------------- fator de vencimento
def fator_vencimento(vencimento: date) -> str:
    """Quatro dígitos que codificam a data de vencimento no código de barras.

    Data anterior a 03/07/2000 daria fator abaixo de 1000, que a norma não
    usa: devolve '0000', o valor de "sem vencimento", que o caixa lê como
    boleto sem data. Na prática só acontece com data digitada errada.
    """
    if vencimento is None:
        return "0000"
    fator = (vencimento - BASE_FATOR).days
    if fator < FATOR_MIN:
        return "0000"
    while fator > FATOR_MAX:
        fator -= CICLO_FATOR
    return str(fator)


def data_do_fator(fator: str, referencia: date | None = None) -> date | None:
    """Caminho inverso — usado ao ler um código de barras de terceiro.

    Ambíguo por natureza depois do giro de 2025: o mesmo fator vale para duas
    datas com 9000 dias de diferença. Resolve-se pela referência (hoje, por
    padrão), escolhendo a ocorrência mais próxima dela.
    """
    from datetime import timedelta

    valor = int(so_digitos(fator) or 0)
    if valor < FATOR_MIN:
        return None
    referencia = referencia or date.today()
    candidata = BASE_FATOR + timedelta(days=valor)
    while candidata < referencia - timedelta(days=CICLO_FATOR // 2):
        candidata += timedelta(days=CICLO_FATOR)
    return candidata


# ---------------------------------------------------------------- valores
def valor_em_centavos(valor: Decimal | float | int | None, tamanho: int = 10) -> str:
    """Valor monetário como inteiro de centavos, zeros à esquerda.

    `Decimal` com arredondamento explícito, nunca `float`: 1.15 em float é
    1.14999… e viraria 114 centavos num `int()`. Um centavo a menos por título
    é o tipo de erro que só aparece na conciliação do mês seguinte.
    """
    if valor is None:
        return "0" * tamanho
    centavos = (Decimal(str(valor)) * 100).quantize(Decimal("1"), rounding=ROUND_HALF_UP)
    if centavos < 0:
        centavos = Decimal(0)
    return str(int(centavos)).zfill(tamanho)[-tamanho:]


def centavos_para_decimal(texto: str) -> Decimal:
    """Caminho inverso, para ler valores do arquivo de retorno."""
    digitos = so_digitos(texto) or "0"
    return (Decimal(digitos) / 100).quantize(Decimal("0.01"))


def validar_valor(valor: Decimal) -> None:
    """O código de barras reserva 10 dígitos para o valor: R$ 99.999.999,99.

    Acima disso o valor seria truncado e o boleto sairia com outro número —
    silenciosamente. Melhor recusar a emissão.
    """
    from core.services import RegraDeNegocioError

    if valor is None or Decimal(str(valor)) <= 0:
        raise RegraDeNegocioError("Valor da cobrança precisa ser maior que zero.", "valor")
    if Decimal(str(valor)) > Decimal("99999999.99"):
        raise RegraDeNegocioError(
            "Valor acima de R$ 99.999.999,99 não cabe no código de barras.", "valor"
        )


# ------------------------------------------------------------ código de barras
def montar_codigo_barras(
    *, banco: str, vencimento: date, valor: Decimal, campo_livre: str, moeda: str = "9"
) -> str:
    """As 44 posições do código de barras.

    1-3 banco | 4 moeda | 5 DV geral | 6-9 fator | 10-19 valor | 20-44 campo livre
    """
    campo_livre = so_digitos(campo_livre)
    if len(campo_livre) != 25:
        raise ValueError(
            f"Campo livre precisa ter 25 dígitos, veio com {len(campo_livre)}. "
            "É responsabilidade do adapter do banco montá-lo."
        )
    corpo = (
        zfill(banco, 3)
        + moeda
        + fator_vencimento(vencimento)
        + valor_em_centavos(valor)
        + campo_livre
    )
    dv = dv_codigo_barras(corpo)
    return corpo[:4] + str(dv) + corpo[4:]


def linha_digitavel(codigo_barras: str) -> str:
    """Converte o código de barras nas 5 partes que o caixa aceita digitar.

    Não é o mesmo número reordenado por estética: cada um dos três primeiros
    campos ganha um DV próprio de módulo 10, justamente para que um erro de
    digitação seja pego no caixa em vez de virar pagamento em outro título.
    """
    b = so_digitos(codigo_barras)
    if len(b) != 44:
        raise ValueError(f"Código de barras precisa ter 44 dígitos, veio com {len(b)}.")

    banco_moeda = b[0:4]
    dv_geral = b[4]
    fator_valor = b[5:19]
    livre = b[19:44]

    c1 = banco_moeda + livre[0:5]
    c2 = livre[5:15]
    c3 = livre[15:25]

    return (
        f"{c1}{modulo10(c1)}"
        f"{c2}{modulo10(c2)}"
        f"{c3}{modulo10(c3)}"
        f"{dv_geral}"
        f"{fator_valor}"
    )


def formatar_linha_digitavel(linha: str) -> str:
    """A linha com a pontuação que aparece impressa no boleto."""
    n = so_digitos(linha)
    if len(n) != 47:
        return n
    return (
        f"{n[0:5]}.{n[5:10]} {n[10:15]}.{n[15:21]} "
        f"{n[21:26]}.{n[26:32]} {n[32]} {n[33:47]}"
    )
