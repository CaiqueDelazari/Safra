"""Registro de adapters — como o sistema acha o banco certo.

O resto do código nunca importa um adapter concreto. Pede
`adapter_para(conta)` e recebe alguém que cumpre `BankAdapter`. É essa
indireção que faz "adicionar um banco" ser: escrever a classe, decorá-la com
`@registrar`, importá-la aqui. Nenhuma linha muda em cobranças, lotes,
serviços ou telas.

A chave é (código do banco, meio de integração), não só o banco: o mesmo Safra
tem um adapter para CNAB 400 e outro para API, e uma empresa pode estar
migrando de um para o outro sem parar a operação.
"""
from apps.bancos.adapters.base import (  # noqa: F401 — reexport da fronteira
    ArquivoInvalido,
    BankAdapter,
    CabecalhoRetorno,
    DadosCedente,
    DadosSacado,
    ErroDeIntegracao,
    OperacaoNaoSuportada,
    RegistroRetorno,
    ResultadoLote,
    ResultadoTitulo,
    Retorno,
    Titulo,
)

_REGISTRO: dict[tuple[str, str], type[BankAdapter]] = {}


def registrar(cls: type[BankAdapter]) -> type[BankAdapter]:
    """Decorador de classe. Registra o adapter para cada meio que ele atende."""
    if not cls.codigo_banco:
        raise ValueError(f"{cls.__name__} não declarou `codigo_banco`.")
    if not cls.meios:
        raise ValueError(f"{cls.__name__} não declarou `meios`.")
    for meio in cls.meios:
        chave = (cls.codigo_banco, meio)
        anterior = _REGISTRO.get(chave)
        if anterior is not None and anterior is not cls:
            raise ValueError(
                f"Já existe adapter para banco {cls.codigo_banco} via {meio}: "
                f"{anterior.__name__}. Dois adapters para o mesmo par tornariam "
                "a escolha dependente da ordem de import."
            )
        _REGISTRO[chave] = cls
    return cls


def adapter_para(conta) -> BankAdapter:
    """O adapter da conta. Levanta se o par (banco, meio) não tem implementação."""
    from core.services import RegraDeNegocioError

    chave = (conta.banco, conta.meio_integracao)
    cls = _REGISTRO.get(chave)
    if cls is None:
        disponiveis = ", ".join(
            f"{b}/{m}" for b, m in sorted(_REGISTRO)
        ) or "nenhum"
        raise RegraDeNegocioError(
            f"Não há integração implementada para o banco {conta.banco} via "
            f"{conta.meio_integracao}. Disponíveis: {disponiveis}.",
            "conta_bancaria",
        )
    return cls(conta)


def suporta(banco: str, meio: str) -> bool:
    return (banco, meio) in _REGISTRO


def pares_suportados() -> list[tuple[str, str]]:
    return sorted(_REGISTRO)


# Os imports abaixo são o que popula o registro. Ficam no fim para que
# `base` já esteja carregado quando cada adapter subir.
from apps.bancos.adapters.safra import adapter as _safra_cnab  # noqa: E402,F401
from apps.bancos.adapters.safra import api as _safra_api  # noqa: E402,F401
