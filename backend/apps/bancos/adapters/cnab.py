"""Ferramental de arquivo posicional — vale para qualquer banco em CNAB.

Um registro CNAB é uma linha de tamanho fixo onde cada campo é uma faixa de
colunas. Escrever isso à mão vira uma sequência de fatias e `ljust` que
ninguém consegue conferir contra o manual do banco, e o erro típico — um campo
deslocado uma coluna — não dá exceção: gera um arquivo que o banco recusa
inteiro, no dia seguinte, sem dizer onde.

A saída aqui é tratar posição como **dado**: cada registro é uma tabela de
`Campo(nome, início, fim, tipo)`, conferida na importação do módulo contra
duas invariantes que pegam praticamente todo erro de transcrição do manual:

1. os campos cobrem a linha inteira, sem buraco e sem sobreposição;
2. a linha montada tem exatamente o tamanho declarado.

Com isso, `manage.py conferir_layout` consegue imprimir a tabela lado a lado
com uma régua de colunas, que é como se confere um layout contra o PDF do
banco em quinze minutos em vez de em duas semanas de rejeição.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from decimal import Decimal
from typing import Iterable, Sequence

from apps.bancos.boleto import valor_em_centavos

#: Tipos de campo. 'N' = numérico, alinhado à direita com zeros; 'A' =
#: alfanumérico, alinhado à esquerda com brancos. O CNAB não tem outros.
NUMERICO = "N"
ALFA = "A"


@dataclass(frozen=True)
class Campo:
    nome: str
    inicio: int  # 1-based, como no manual do banco
    fim: int  # inclusivo, como no manual do banco
    tipo: str = ALFA
    #: Valor fixo do campo (literais como 'REMESSA', identificadores de
    #: registro). Quando presente, quem monta a linha não precisa informá-lo.
    fixo: str | None = None
    #: Nota de conferência contra o manual. Aparece no `conferir_layout`.
    nota: str = ""

    @property
    def tamanho(self) -> int:
        return self.fim - self.inicio + 1


class Registro:
    """Uma tabela de campos que sabe montar e ler uma linha."""

    def __init__(self, nome: str, campos: Sequence[Campo], tamanho: int = 400):
        self.nome = nome
        self.campos = tuple(campos)
        self.tamanho = tamanho
        self.por_nome = {c.nome: c for c in self.campos}
        self._conferir()

    def _conferir(self) -> None:
        """Cobertura completa e sem sobreposição. Roda na importação: um
        layout torto derruba o processo na subida, não na hora da remessa."""
        esperado = 1
        for campo in self.campos:
            if campo.inicio != esperado:
                raise ValueError(
                    f"{self.nome}: campo '{campo.nome}' começa em {campo.inicio}, "
                    f"esperado {esperado}. "
                    + ("Há um buraco no layout." if campo.inicio > esperado
                       else "Há sobreposição com o campo anterior.")
                )
            if campo.fim < campo.inicio:
                raise ValueError(
                    f"{self.nome}: campo '{campo.nome}' termina antes de começar."
                )
            esperado = campo.fim + 1
        if esperado - 1 != self.tamanho:
            raise ValueError(
                f"{self.nome}: os campos cobrem {esperado - 1} posições, "
                f"mas o registro tem {self.tamanho}."
            )
        if len(self.por_nome) != len(self.campos):
            raise ValueError(f"{self.nome}: há nomes de campo repetidos.")

    # ------------------------------------------------------------ escrita
    def montar(self, valores: dict) -> str:
        partes = []
        for campo in self.campos:
            if campo.fixo is not None:
                bruto = campo.fixo
            else:
                bruto = valores.get(campo.nome, "")
            partes.append(formatar(bruto, campo))
        linha = "".join(partes)
        if len(linha) != self.tamanho:
            # Só acontece se `formatar` for alterado de forma incorreta; a
            # conferência de layout já garante a soma dos tamanhos.
            raise ValueError(
                f"{self.nome}: linha montada com {len(linha)} posições, "
                f"esperado {self.tamanho}."
            )
        return linha

    # ------------------------------------------------------------ leitura
    def ler(self, linha: str, nome: str) -> str:
        campo = self.por_nome[nome]
        return linha[campo.inicio - 1:campo.fim]

    def ler_int(self, linha: str, nome: str) -> int:
        texto = "".join(c for c in self.ler(linha, nome) if c.isdigit())
        return int(texto) if texto else 0

    def ler_decimal(self, linha: str, nome: str, casas: int = 2) -> Decimal:
        texto = "".join(c for c in self.ler(linha, nome) if c.isdigit()) or "0"
        return (Decimal(texto) / (10 ** casas)).quantize(Decimal("0.01"))

    def ler_data(self, linha: str, nome: str, formato: str = "DDMMAA") -> date | None:
        return converter_data(self.ler(linha, nome), formato)

    def ler_texto(self, linha: str, nome: str) -> str:
        return self.ler(linha, nome).strip()

    # ---------------------------------------------------------- diagnóstico
    def regua(self, linha: str = "") -> str:
        """Tabela campo a campo com o conteúdo, para conferir com o manual."""
        larguras = max((len(c.nome) for c in self.campos), default=10)
        saida = [f"{self.nome} ({self.tamanho} posições)", ""]
        saida.append(f"{'pos':>9}  {'tam':>3}  {'t':1}  {'campo'.ljust(larguras)}  conteúdo")
        saida.append("-" * (9 + 2 + 3 + 2 + 1 + 2 + larguras + 2 + 20))
        for c in self.campos:
            conteudo = linha[c.inicio - 1:c.fim] if linha else ""
            marca = f"[{conteudo}]" if linha else ""
            nota = f"   ← {c.nota}" if c.nota else ""
            saida.append(
                f"{c.inicio:>4}-{c.fim:<4} {c.tamanho:>3}  {c.tipo}  "
                f"{c.nome.ljust(larguras)}  {marca}{nota}"
            )
        return "\n".join(saida)


# -------------------------------------------------------------- formatação
def formatar(valor, campo: Campo) -> str:
    """Um valor Python virando as N colunas do campo.

    Trunca em silêncio quando estoura — e isso é deliberado. Nome de sacado
    com 60 letras cabe em 40 no arquivo; recusar a remessa inteira por causa
    disso seria pior do que imprimir o nome cortado, que é o que todo banco faz
    de qualquer forma. O que **não** pode ser truncado é valor: quem cuida
    disso é `boleto.validar_valor`, antes de chegar aqui.
    """
    if valor is None:
        valor = ""
    if isinstance(valor, bool):
        valor = "1" if valor else "0"
    if isinstance(valor, date):
        valor = valor.strftime("%d%m%y") if campo.tamanho == 6 else valor.strftime("%d%m%Y")
    if isinstance(valor, Decimal | float | int) and campo.tipo == NUMERICO:
        if isinstance(valor, Decimal | float):
            valor = valor_em_centavos(valor, campo.tamanho)
        else:
            valor = str(valor)

    texto = str(valor)
    if campo.tipo == NUMERICO:
        digitos = "".join(c for c in texto if c.isdigit())
        return digitos[-campo.tamanho:].rjust(campo.tamanho, "0")
    return normalizar_texto(texto)[:campo.tamanho].ljust(campo.tamanho, " ")


#: O CNAB é ASCII. Acento vira byte que o mainframe do banco lê como outra
#: coisa, e nome de sacado com cedilha é a regra, não a exceção.
_ACENTOS = str.maketrans(
    "áàâãäéèêëíìîïóòôõöúùûüçñÁÀÂÃÄÉÈÊËÍÌÎÏÓÒÔÕÖÚÙÛÜÇÑ",
    "aaaaaeeeeiiiiooooouuuucnAAAAAEEEEIIIIOOOOOUUUUCN",
)


def normalizar_texto(texto: str) -> str:
    """Maiúsculas, sem acento, sem caractere de controle."""
    limpo = (texto or "").translate(_ACENTOS).upper()
    return "".join(c if 32 <= ord(c) < 127 else " " for c in limpo)


def converter_data(texto: str, formato: str = "DDMMAA") -> date | None:
    """Data do arquivo. Zeros ou lixo viram `None`, não exceção.

    Campo de data zerado é comum e significativo — "sem data de crédito"
    é informação, não erro —, e uma exceção aqui derrubaria o processamento de
    um arquivo inteiro por causa de um campo opcional.
    """
    digitos = "".join(c for c in (texto or "") if c.isdigit())
    try:
        if formato == "DDMMAA" and len(digitos) == 6:
            dia, mes, ano = int(digitos[0:2]), int(digitos[2:4]), int(digitos[4:6])
            # Janela de dois dígitos: o CNAB 400 não tem século. Retorno é
            # sempre recente, então 70-99 é 1900 e o resto é 2000.
            ano += 1900 if ano >= 70 else 2000
            return date(ano, mes, dia)
        if formato == "DDMMAAAA" and len(digitos) == 8:
            return date(int(digitos[4:8]), int(digitos[2:4]), int(digitos[0:2]))
    except ValueError:
        return None
    return None


def quebrar_linhas(conteudo: bytes, tamanho: int = 400) -> list[str]:
    """Divide o arquivo em registros, aceitando as três formas que aparecem.

    Banco entrega CNAB com CRLF, com LF, e — mais frequentemente do que se
    esperaria — sem separador nenhum, como um bloco contínuo. Assumir só a
    primeira faz o parser devolver "arquivo vazio" para um retorno perfeito.
    """
    texto = conteudo.decode("latin-1", errors="replace")
    if "\n" in texto or "\r" in texto:
        linhas = [linha.rstrip("\r\n") for linha in texto.splitlines()]
    else:
        linhas = [texto[i:i + tamanho] for i in range(0, len(texto), tamanho)]
    # Linha curta demais é rodapé em branco ou sujeira de transferência.
    return [linha.ljust(tamanho) for linha in linhas if linha.strip()]


def juntar_linhas(linhas: Iterable[str]) -> bytes:
    """CRLF: é o que os mainframes esperam, e o que todo manual pede."""
    return ("\r\n".join(linhas) + "\r\n").encode("latin-1", errors="replace")
