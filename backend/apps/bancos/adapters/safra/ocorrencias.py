"""Tradução dos códigos de retorno do Safra para o vocabulário do sistema.

Este é o único lugar onde "06" significa alguma coisa. Acima daqui existe
`TipoOcorrencia.LIQUIDACAO`, e é por isso que acrescentar um banco não exige
tocar em nenhuma regra de negócio — cada banco traz a própria tabela e o
`processar_retorno` de todos devolve os mesmos nomes.

Uma decisão que parece detalhe e não é: código desconhecido vira
`DESCONHECIDA`, não erro. Banco acrescenta código sem avisar, e derrubar o
processamento de um arquivo de 500 títulos por causa de uma linha
inesperada trocaria um problema pequeno (uma ocorrência que ninguém
interpretou, visível na tela) por um grande (500 pagamentos que não entraram).
A ocorrência fica gravada em bruto e aparece como pendência.

Tabela conferida contra o manual Safra CNAB 400, versão maio/2026.
"""
from apps.bancos.bancos import TipoOcorrencia as T

#: código do banco -> (tipo do sistema, descrição legível)
OCORRENCIAS: dict[str, tuple[str, str]] = {
    "02": (T.ENTRADA_CONFIRMADA, "Entrada confirmada"),
    "03": (T.ENTRADA_REJEITADA, "Entrada rejeitada"),
    "04": (T.ALTERACAO_CONFIRMADA, "Transferência de carteira — entrada"),
    "05": (T.BAIXA, "Transferência de carteira — baixa"),
    "06": (T.LIQUIDACAO, "Liquidação normal"),
    "09": (T.BAIXA, "Baixa automática"),
    "10": (T.BAIXA, "Baixa conforme solicitação do beneficiário"),
    "11": (T.ALTERACAO_CONFIRMADA, "Título em ser (arquivo de posição)"),
    "12": (T.ABATIMENTO_CONCEDIDO, "Abatimento concedido"),
    "13": (T.ABATIMENTO_CANCELADO, "Abatimento cancelado"),
    "14": (T.VENCIMENTO_ALTERADO, "Vencimento alterado"),
    "15": (T.LIQUIDACAO, "Liquidação em cartório"),
    "19": (T.PROTESTO, "Confirmação de instrução de protesto"),
    "20": (T.SUSTACAO_PROTESTO, "Confirmação de sustação de protesto"),
    "21": (T.ALTERACAO_CONFIRMADA, "Transferência de beneficiário — conta origem"),
    "23": (T.PROTESTO, "Título enviado a cartório"),
    "24": (T.ALTERACAO_REJEITADA, "Instrução de protesto rejeitada"),
    "25": (T.ALTERACAO_CONFIRMADA, "Alegação do sacado"),
    "26": (T.ALTERACAO_CONFIRMADA, "Tarifa de aviso de cobrança"),
    "27": (T.ALTERACAO_REJEITADA, "Alteração de dados rejeitada"),
    "28": (T.TARIFA, "Débito de tarifas e custas"),
    "29": (T.ALTERACAO_CONFIRMADA, "Ocorrências do sacado"),
    "30": (T.ALTERACAO_REJEITADA, "Alteração de dados rejeitada"),
    "32": (T.ALTERACAO_REJEITADA, "Instrução rejeitada"),
    "33": (T.ALTERACAO_CONFIRMADA, "Confirmação de alteração de outros dados"),
    "34": (T.SUSTACAO_PROTESTO, "Retirado de cartório e manutenção em carteira"),
    "35": (T.ALTERACAO_CONFIRMADA, "Cancelamento do agendamento de débito automático"),
    "40": (T.BAIXA_REJEITADA, "Baixa rejeitada"),
    "68": (T.TARIFA, "Acerto dos dados do rateio de crédito"),
    "69": (T.ALTERACAO_REJEITADA, "Cancelamento dos dados do rateio"),
}

#: Motivos de rejeição/ocorrência. Vêm concatenados em duplas no campo
#: `motivos_rejeicao`. Só os mais frequentes estão nomeados — os demais
#: aparecem como o próprio código, que é o que o gerente do banco entende.
MOTIVOS: dict[str, str] = {
    "037": "Data de vencimento inválida",
    "048": "Valor do desconto inválido",
    "068": "CEP do pagador/beneficiário final não consta na tabela",
    "01": "Código do banco inválido",
    "02": "Código do registro detalhe inválido",
    "03": "Código da ocorrência inválido",
    "04": "Código de ocorrência não permitido para a carteira",
    "05": "Código de ocorrência não numérico",
    "07": "Agência/conta/dígito inválidos",
    "08": "Nosso número inválido",
    "09": "Nosso número duplicado",
    "10": "Carteira inválida",
    "16": "Data de vencimento inválida",
    "17": "Data de vencimento anterior à data de emissão",
    "18": "Vencimento fora do prazo de operação",
    "20": "Valor do título inválido",
    "21": "Espécie do título inválida",
    "22": "Espécie não permitida para a carteira",
    "24": "Data de emissão inválida",
    "27": "Valor/taxa de juros de mora inválido",
    "28": "Código do desconto inválido",
    "38": "Prazo para protesto inválido",
    "44": "Agência cedente não prevista",
    "45": "Nome do sacado não informado",
    "46": "Tipo/número de inscrição do sacado inválidos",
    "47": "Endereço do sacado não informado",
    "48": "CEP inválido",
    "49": "CEP sem praça de cobrança",
    "50": "CEP referente a banco correspondente",
    "53": "Tipo/número de inscrição do sacador/avalista inválidos",
    "54": "Sacador/avalista não informado",
    "57": "Código da multa inválido",
    "60": "Movimento para título não cadastrado",
    "61": "Título já baixado ou liquidado",
    "63": "Entrada para título já cadastrado",
    "64": "Número da linha inválido",
    "65": "Código do banco para débito inválido",
    "80": "Data de desconto inválida",
    "86": "Seu número inválido",
}

#: Códigos que só existem para explicar uma rejeição. Junto com o tipo, é o
#: que a tela mostra ao operador — "rejeitado: CEP inválido" resolve sozinho,
#: "rejeitado: 48" manda alguém procurar o manual.
TAMANHO_MOTIVO = 3
MAX_MOTIVOS = 1


def traduzir(codigo: str) -> tuple[str, str]:
    """Código do banco -> (tipo do sistema, descrição)."""
    codigo = (codigo or "").strip().zfill(2)
    return OCORRENCIAS.get(codigo, (T.DESCONHECIDA, f"Ocorrência {codigo} não mapeada"))


def separar_motivos(campo: str) -> list[str]:
    """Lê o código de rejeição de três dígitos do retorno Safra."""
    texto = (campo or "").strip()
    motivos = []
    for i in range(0, min(len(texto), TAMANHO_MOTIVO * MAX_MOTIVOS), TAMANHO_MOTIVO):
        pedaco = texto[i:i + TAMANHO_MOTIVO].strip()
        if pedaco and pedaco != "00":
            motivos.append(pedaco.zfill(3))
    return motivos


def descrever_motivos(motivos: list[str]) -> str:
    """Texto legível para a tela e para o relatório de rejeições."""
    if not motivos:
        return ""
    return "; ".join(f"{m} — {MOTIVOS.get(m, 'motivo não mapeado')}" for m in motivos)
