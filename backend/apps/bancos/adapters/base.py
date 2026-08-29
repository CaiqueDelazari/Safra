"""A fronteira entre o sistema e qualquer banco.

Regra 24: acrescentar um banco não pode exigir reescrever nada. O que torna
isso verdade não é a existência de uma classe abstrata — é o formato dos dados
que atravessam a fronteira. Por isso os DTOs abaixo são *do sistema*, não de
nenhum banco: não há "código de ocorrência 06" aqui, há
`TipoOcorrencia.LIQUIDACAO`; não há "posição 109 do registro tipo 1", há
`nosso_numero`.

O adapter é o único lugar do sistema autorizado a saber que existe CNAB, que
o Safra chama a conta de "código do cedente" ou que a API de um banco pede
mTLS. Nada acima desta linha importa `apps.bancos.adapters.safra`.

Quatro operações, e a assimetria entre elas é proposital:

* **registrar em lote** é o caminho normal — banco nenhum foi feito para
  receber mil chamadas individuais, e o produto inteiro existe para não fazer
  isso (regra 6). `registrar` de um título só existe e delega ao lote;
* **transmitir** é separado de **montar**, porque em CNAB o operador
  legitimamente baixa o arquivo e leva ao internet banking. Um adapter que só
  soubesse "enviar" impediria o fluxo mais comum do mercado;
* **ler retorno** não recebe cobrança nenhuma: recebe bytes e devolve fatos.
  Quem casa fato com cobrança é o serviço (`apps/bancos/services.py`), porque
  esse casamento é regra de negócio, não de protocolo;
* **consultar** é opcional. Em CNAB não existe consulta — a resposta vem no
  retorno do dia seguinte. Adapter que não sabe consultar levanta
  `OperacaoNaoSuportada`, e a camada de cima trata isso como informação, não
  como falha.
"""
from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import date
from decimal import Decimal
from typing import Iterable, Optional


class ErroDeIntegracao(Exception):
    """Falha ao conversar com o banco. Vira status ERRO e entra no log."""

    def __init__(self, mensagem: str, *, detalhes: Optional[dict] = None):
        super().__init__(mensagem)
        self.mensagem = mensagem
        self.detalhes = detalhes or {}


class OperacaoNaoSuportada(ErroDeIntegracao):
    """O banco/meio não oferece a operação. Não é erro de execução."""


class ArquivoInvalido(ErroDeIntegracao):
    """O arquivo não é do formato esperado — banco errado, truncado, vazio."""


# --------------------------------------------------------------------- DTOs
@dataclass(frozen=True)
class DadosCedente:
    """Quem recebe. Sai da empresa e da conta bancária."""

    nome: str
    documento: str  # dígitos, 11 ou 14
    agencia: str
    agencia_dv: str
    conta: str
    conta_dv: str
    carteira: str
    codigo_cedente: str
    variacao_carteira: str = ""
    logradouro: str = ""
    numero: str = ""
    bairro: str = ""
    cidade: str = ""
    uf: str = ""
    cep: str = ""


@dataclass(frozen=True)
class DadosSacado:
    """Quem paga. Sai do cliente."""

    nome: str
    documento: str  # dígitos, 11 ou 14
    logradouro: str = ""
    numero: str = ""
    complemento: str = ""
    bairro: str = ""
    cidade: str = ""
    uf: str = ""
    cep: str = ""
    email: str = ""


@dataclass
class Titulo:
    """Um título a registrar. É a cobrança, traduzida para o vocabulário
    bancário e já com o `nosso_numero` reservado pelo sistema."""

    id_interno: int
    nosso_numero: str
    seu_numero: str
    documento: str
    valor: Decimal
    emissao: date
    vencimento: date
    sacado: DadosSacado
    especie: str = "DS"
    aceite: bool = False
    juros_mes_percentual: Decimal = Decimal("0")
    multa_percentual: Decimal = Decimal("0")
    desconto: Decimal = Decimal("0")
    data_limite_desconto: Optional[date] = None
    abatimento: Decimal = Decimal("0")
    dias_protesto: int = 0
    dias_baixa_automatica: int = 0
    instrucoes: str = ""
    #: O que fazer com este título no banco. 'ENTRADA' registra; 'BAIXA' pede
    #: baixa; 'CANCELAMENTO' pede exclusão; 'ALTERACAO_VENCIMENTO' prorroga.
    #: Um mesmo arquivo de remessa pode carregar instruções diferentes, e
    #: separá-las em métodos distintos obrigaria a gerar três arquivos.
    ocorrencia: str = "ENTRADA"


@dataclass
class ResultadoTitulo:
    """O que o banco (ou o cálculo local) devolveu para um título."""

    id_interno: int
    ok: bool
    nosso_numero: str = ""
    identificador_bancario: str = ""
    codigo_barras: str = ""
    linha_digitavel: str = ""
    url_boleto: str = ""
    erro: str = ""


@dataclass
class ResultadoLote:
    """O resultado de registrar N títulos de uma vez.

    Em CNAB, `conteudo` é o arquivo de remessa e `protocolo` só existe depois
    da transmissão. Em API, `conteudo` é vazio e cada `ResultadoTitulo` já vem
    com o identificador do banco. A camada de cima trata os dois pelo mesmo
    caminho — é esse o ponto.
    """

    resultados: list[ResultadoTitulo] = field(default_factory=list)
    conteudo: bytes = b""
    nome_arquivo: str = ""
    protocolo: str = ""
    numero_remessa: Optional[int] = None

    @property
    def quantidade_ok(self) -> int:
        return sum(1 for r in self.resultados if r.ok)

    @property
    def quantidade_erro(self) -> int:
        return sum(1 for r in self.resultados if not r.ok)


@dataclass
class RegistroRetorno:
    """Uma linha do arquivo de retorno, já traduzida.

    `tipo` é do vocabulário do sistema (`TipoOcorrencia`); `codigo` é o código
    cru do banco, preservado porque é a linguagem do suporte do banco.
    """

    linha: int
    tipo: str
    codigo: str
    descricao: str = ""
    nosso_numero: str = ""
    seu_numero: str = ""
    documento: str = ""
    data_ocorrencia: Optional[date] = None
    data_credito: Optional[date] = None
    data_vencimento: Optional[date] = None
    valor_titulo: Decimal = Decimal("0")
    valor_pago: Decimal = Decimal("0")
    valor_juros: Decimal = Decimal("0")
    valor_multa: Decimal = Decimal("0")
    valor_desconto: Decimal = Decimal("0")
    valor_abatimento: Decimal = Decimal("0")
    valor_tarifa: Decimal = Decimal("0")
    banco_recebedor: str = ""
    agencia_recebedora: str = ""
    motivos: list[str] = field(default_factory=list)
    motivos_descricao: str = ""
    conteudo: str = ""


@dataclass
class CabecalhoRetorno:
    """O que o cabeçalho do arquivo diz sobre ele mesmo.

    Serve para uma pergunta que vem antes de qualquer processamento: *este
    arquivo é meu?* Retorno de outra empresa, ou de outra conta, processado
    por engano, casaria "nosso número" por coincidência e daria baixa em
    títulos errados.
    """

    banco: str = ""
    agencia: str = ""
    conta: str = ""
    codigo_cedente: str = ""
    nome_cedente: str = ""
    data_movimento: Optional[date] = None
    numero_arquivo: Optional[int] = None


@dataclass
class Retorno:
    cabecalho: CabecalhoRetorno
    registros: list[RegistroRetorno] = field(default_factory=list)
    #: Linhas que o parser não soube ler. Não impedem o processamento do
    #: resto: um arquivo com 500 títulos não pode ser descartado inteiro por
    #: causa de uma linha estranha — mas cada uma delas é contada e reportada.
    linhas_ignoradas: list[tuple[int, str]] = field(default_factory=list)


# ------------------------------------------------------------------ interface
class BankAdapter(ABC):
    """Contrato que todo banco cumpre.

    Instanciado com a `ContaBancaria` — e não com credenciais soltas — porque
    tudo que muda entre dois convênios do mesmo banco está lá: carteira,
    faixa de nosso número, ambiente, credencial.
    """

    #: Código FEBRABAN. Usado pelo registro para achar o adapter.
    codigo_banco: str = ""
    nome: str = ""
    #: Meios que esta implementação atende.
    meios: tuple[str, ...] = ()

    def __init__(self, conta):
        self.conta = conta

    # --------------------------------------------------------- registro
    def registrar_cobranca(self, titulo: Titulo) -> ResultadoTitulo:
        """Um título só. Delega ao lote — não existe caminho paralelo."""
        resultado = self.registrar_cobrancas_em_lote([titulo])
        return resultado.resultados[0]

    @abstractmethod
    def registrar_cobrancas_em_lote(self, titulos: Iterable[Titulo]) -> ResultadoLote:
        """Registra N títulos. É o caminho principal do produto."""

    @abstractmethod
    def gerar_boleto(self, titulo: Titulo) -> ResultadoTitulo:
        """Código de barras e linha digitável, sem falar com o banco.

        Em carteiras registradas o número é determinístico: dá para imprimir o
        boleto no mesmo instante em que a cobrança é criada, antes de o banco
        confirmar. O que não se pode é *cobrar* antes da confirmação — quem
        controla isso é o status da cobrança, não este método.
        """

    # ------------------------------------------------------- transmissão
    def transmitir(self, conteudo: bytes, nome_arquivo: str) -> str:
        """Entrega a remessa ao banco e devolve o protocolo.

        Padrão: não sabe transmitir. É o comportamento correto para um
        convênio CNAB sem SFTP — o arquivo fica para download e o operador o
        leva ao internet banking, que é como a maior parte do mercado opera.
        """
        raise OperacaoNaoSuportada(
            "Esta conta não tem transmissão automática configurada. "
            "Baixe o arquivo de remessa e envie pelo canal do banco."
        )

    def obter_retornos(self) -> list[tuple[str, bytes]]:
        """Busca arquivos de retorno novos: [(nome, conteúdo)].

        Padrão: nenhum. Em convênio sem SFTP/API o retorno entra por upload na
        tela, e a varredura automática simplesmente não encontra nada — o que
        é o correto, não uma falha.
        """
        return []

    # ----------------------------------------------------------- retorno
    @abstractmethod
    def processar_retorno(self, conteudo: bytes) -> Retorno:
        """Lê o arquivo e devolve fatos. Não toca no banco de dados."""

    # --------------------------------------------------------- consultas
    def consultar_cobranca(self, nosso_numero: str) -> ResultadoTitulo:
        raise OperacaoNaoSuportada(
            "Consulta título a título não existe neste meio de integração. "
            "A situação atual vem no próximo arquivo de retorno."
        )

    def consultar_lote(self, protocolo: str) -> ResultadoLote:
        raise OperacaoNaoSuportada(
            "Consulta de lote não existe neste meio de integração."
        )

    # -------------------------------------------------------- instruções
    def cancelar_cobranca(self, titulo: Titulo) -> ResultadoTitulo:
        """Pede a exclusão do título no banco."""
        titulo.ocorrencia = "CANCELAMENTO"
        return self.registrar_cobranca(titulo)

    def baixar_cobranca(self, titulo: Titulo) -> ResultadoTitulo:
        """Pede a baixa do título (recebido por fora, negociado, desistido)."""
        titulo.ocorrencia = "BAIXA"
        return self.registrar_cobranca(titulo)
