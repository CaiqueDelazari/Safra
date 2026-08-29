"""Mapa de posições do CNAB 400 de cobrança do Banco Safra.

LEIA ANTES DE IR A PRODUÇÃO
---------------------------
Este mapa segue o layout CNAB 400 de cobrança (a família derivada do padrão
FEBRABAN que o Safra adota), e é o ponto do sistema que **precisa ser
conferido contra o manual técnico que o banco entrega junto com o convênio**.
Layout de cobrança tem variação por banco e, às vezes, por carteira dentro do
mesmo banco — um campo deslocado não gera exceção nenhuma aqui: gera um
arquivo que o Safra recusa inteiro, no dia seguinte, sem apontar a coluna.

A conferência é mecânica e leva minutos, não semanas:

    python manage.py conferir_layout --conta <id>

O comando imprime a tabela abaixo campo a campo, com uma linha de exemplo
montada com dados reais da conta, no formato "posição inicial-final, tamanho,
conteúdo". É isso que se põe lado a lado com a página do manual. Cada campo
marcado com `nota="CONFERIR"` é um que varia entre bancos da mesma família e
merece atenção primeiro.

Ajustar significa mudar números neste arquivo e mais nada — nenhuma lógica lê
posição fixa fora daqui, e a conferência de cobertura (`Registro._conferir`)
recusa na subida qualquer alteração que deixe buraco ou sobreposição.
"""
from apps.bancos.adapters.cnab import ALFA, NUMERICO, Campo, Registro

BANCO = "422"
NOME_BANCO = "BANCO SAFRA"
TAMANHO = 400


# ─────────────────────────────────────────────────────── REMESSA — cabeçalho
REMESSA_HEADER = Registro("Remessa · Header (tipo 0)", [
    Campo("registro", 1, 1, ALFA, fixo="0"),
    Campo("operacao", 2, 2, ALFA, fixo="1"),
    Campo("literal_remessa", 3, 9, ALFA, fixo="REMESSA"),
    Campo("codigo_servico", 10, 11, NUMERICO, fixo="01"),
    Campo("literal_servico", 12, 26, ALFA, fixo="COBRANCA"),
    Campo("codigo_empresa", 27, 46, NUMERICO,
          nota="CONFERIR — composição do código do cedente (agência+conta+dv)"),
    Campo("nome_cedente", 47, 76, ALFA),
    Campo("banco", 77, 79, NUMERICO, fixo=BANCO),
    Campo("nome_banco", 80, 94, ALFA, fixo=NOME_BANCO),
    Campo("data_gravacao", 95, 100, NUMERICO),
    Campo("uso_banco", 101, 394, ALFA),
    Campo("sequencial", 395, 400, NUMERICO),
], TAMANHO)


# ─────────────────────────────────────────────────────── REMESSA — detalhe
REMESSA_DETALHE = Registro("Remessa · Detalhe (tipo 1)", [
    Campo("registro", 1, 1, ALFA, fixo="1"),
    Campo("tipo_inscricao_cedente", 2, 3, NUMERICO),
    Campo("documento_cedente", 4, 17, NUMERICO),
    Campo("codigo_empresa", 18, 37, NUMERICO,
          nota="CONFERIR — mesmo código do header"),
    Campo("uso_empresa", 38, 61, ALFA,
          nota="Seu número. O banco devolve intacto no retorno."),
    # Nove posições, não oito: é o tamanho do nosso número que entra no campo
    # livre do código de barras (adapters/safra/campo_livre.py). Um campo mais
    # estreito aqui cortaria o dígito mais significativo — o banco registraria
    # um número, o boleto impresso teria outro, e o retorno nunca casaria com
    # a cobrança. Não dá exceção em lugar nenhum; some no meio da carteira.
    # Se o manual do convênio disser outro tamanho, ajuste AQUI e o
    # `_detalhe` recusa a montagem em vez de truncar.
    Campo("nosso_numero", 62, 70, NUMERICO,
          nota="CONFERIR — precisa comportar os 9 dígitos do código de barras"),
    Campo("dv_nosso_numero", 71, 71, ALFA),
    Campo("desconto_bonificacao_dia", 72, 77, NUMERICO),
    Campo("condicao_emissao", 78, 78, ALFA, fixo="2",
          nota="2 = boleto emitido pelo cedente. CONFERIR na carteira."),
    Campo("emite_boleto_debito_automatico", 79, 79, ALFA, fixo="N"),
    Campo("identificacao_operacao_banco", 80, 89, ALFA),
    Campo("indicador_rateio", 90, 90, ALFA),
    Campo("endereco_aviso_debito", 91, 92, NUMERICO),
    Campo("quantidade_pagamentos", 93, 94, NUMERICO),
    Campo("codigo_ocorrencia", 95, 96, NUMERICO,
          nota="01=entrada, 02=baixa, 06=prorrogação. CONFERIR tabela do manual."),
    Campo("numero_documento", 97, 106, ALFA),
    Campo("data_vencimento", 107, 112, NUMERICO),
    Campo("valor_titulo", 113, 125, NUMERICO),
    Campo("banco_cobrador", 126, 128, NUMERICO, fixo=BANCO),
    Campo("agencia_cobradora", 129, 133, NUMERICO),
    Campo("especie_titulo", 134, 135, NUMERICO,
          nota="CONFERIR — tabela de espécie do Safra (DM/DS/NP têm códigos próprios)"),
    Campo("aceite", 136, 136, ALFA),
    Campo("data_emissao", 137, 142, NUMERICO),
    Campo("instrucao_1", 143, 144, NUMERICO),
    Campo("instrucao_2", 145, 146, NUMERICO),
    Campo("juros_mora_dia", 147, 159, NUMERICO,
          nota="Valor em reais por dia, não percentual — o sistema converte."),
    Campo("data_limite_desconto", 160, 165, NUMERICO),
    Campo("valor_desconto", 166, 178, NUMERICO),
    Campo("valor_iof", 179, 191, NUMERICO),
    Campo("valor_abatimento", 192, 204, NUMERICO),
    Campo("tipo_inscricao_sacado", 205, 206, NUMERICO),
    Campo("documento_sacado", 207, 220, NUMERICO),
    Campo("nome_sacado", 221, 260, ALFA),
    Campo("brancos_1", 261, 263, ALFA),
    Campo("endereco_sacado", 264, 303, ALFA),
    Campo("primeira_mensagem", 304, 315, ALFA),
    Campo("cep_sacado", 316, 320, NUMERICO),
    Campo("sufixo_cep_sacado", 321, 323, NUMERICO),
    Campo("sacador_avalista", 324, 363, ALFA,
          nota="Também usado como segunda mensagem do boleto."),
    Campo("prazo_protesto", 364, 365, NUMERICO),
    Campo("codigo_moeda", 366, 366, NUMERICO, fixo="0"),
    Campo("brancos_2", 367, 394, ALFA),
    Campo("sequencial", 395, 400, NUMERICO),
], TAMANHO)


# ─────────────────────────────────────────────────────── REMESSA — trailer
REMESSA_TRAILER = Registro("Remessa · Trailer (tipo 9)", [
    Campo("registro", 1, 1, ALFA, fixo="9"),
    Campo("brancos", 2, 394, ALFA),
    Campo("sequencial", 395, 400, NUMERICO),
], TAMANHO)


# ─────────────────────────────────────────────────────── RETORNO — cabeçalho
RETORNO_HEADER = Registro("Retorno · Header (tipo 0)", [
    Campo("registro", 1, 1, ALFA),
    Campo("operacao", 2, 2, ALFA),
    Campo("literal_retorno", 3, 9, ALFA),
    Campo("codigo_servico", 10, 11, NUMERICO),
    Campo("literal_servico", 12, 26, ALFA),
    Campo("codigo_empresa", 27, 46, NUMERICO),
    Campo("nome_cedente", 47, 76, ALFA),
    Campo("banco", 77, 79, NUMERICO),
    Campo("nome_banco", 80, 94, ALFA),
    Campo("data_movimento", 95, 100, NUMERICO),
    Campo("uso_banco", 101, 394, ALFA),
    Campo("sequencial", 395, 400, NUMERICO),
], TAMANHO)


# ─────────────────────────────────────────────────────── RETORNO — detalhe
RETORNO_DETALHE = Registro("Retorno · Detalhe (tipo 1)", [
    Campo("registro", 1, 1, ALFA),
    Campo("tipo_inscricao_cedente", 2, 3, NUMERICO),
    Campo("documento_cedente", 4, 17, NUMERICO),
    Campo("codigo_empresa", 18, 37, NUMERICO),
    Campo("uso_empresa", 38, 61, ALFA,
          nota="Seu número, como foi enviado na remessa."),
    Campo("nosso_numero", 62, 70, NUMERICO,
          nota="CONFERIR — precisa casar exatamente com a posição da remessa"),
    Campo("dv_nosso_numero", 71, 71, ALFA),
    Campo("uso_banco_1", 72, 82, ALFA),
    Campo("uso_banco_2", 83, 92, ALFA),
    Campo("carteira", 93, 94, NUMERICO),
    Campo("codigo_ocorrencia", 95, 96, NUMERICO,
          nota="CONFERIR — a tabela de ocorrências está em ocorrencias.py"),
    Campo("data_ocorrencia", 97, 102, NUMERICO),
    Campo("numero_documento", 103, 112, ALFA),
    Campo("identificacao_titulo_banco", 113, 126, ALFA),
    Campo("data_vencimento", 127, 132, NUMERICO),
    Campo("valor_titulo", 133, 145, NUMERICO),
    Campo("banco_cobrador", 146, 148, NUMERICO),
    Campo("agencia_cobradora", 149, 153, NUMERICO),
    Campo("dv_agencia_cobradora", 154, 155, ALFA),
    Campo("valor_tarifa", 156, 168, NUMERICO),
    Campo("outras_despesas", 169, 181, NUMERICO),
    Campo("juros_operacao_atraso", 182, 194, NUMERICO),
    Campo("valor_iof", 195, 207, NUMERICO),
    Campo("valor_abatimento", 208, 220, NUMERICO),
    Campo("valor_desconto", 221, 233, NUMERICO),
    Campo("valor_principal", 234, 246, NUMERICO,
          nota="O valor efetivamente pago pelo sacado."),
    Campo("juros_mora", 247, 259, NUMERICO),
    Campo("outros_creditos", 260, 272, NUMERICO),
    Campo("brancos_1", 273, 274, ALFA),
    Campo("motivo_ocorrencia", 275, 275, ALFA),
    Campo("data_credito", 276, 281, NUMERICO,
          nota="Quando o dinheiro fica disponível. Vazia em ocorrência que não liquida."),
    Campo("origem_pagamento", 282, 289, ALFA),
    Campo("brancos_2", 290, 294, ALFA),
    Campo("motivos_rejeicao", 295, 304, ALFA,
          nota="CONFERIR — até 5 códigos de 2 dígitos, concatenados."),
    Campo("brancos_3", 305, 318, ALFA),
    Campo("valor_multa", 319, 331, NUMERICO, nota="CONFERIR"),
    Campo("brancos_4", 332, 394, ALFA),
    Campo("sequencial", 395, 400, NUMERICO),
], TAMANHO)


# ─────────────────────────────────────────────────────── RETORNO — trailer
RETORNO_TRAILER = Registro("Retorno · Trailer (tipo 9)", [
    Campo("registro", 1, 1, ALFA),
    Campo("operacao", 2, 2, ALFA),
    Campo("banco", 3, 5, NUMERICO),
    Campo("uso_banco", 6, 394, ALFA),
    Campo("sequencial", 395, 400, NUMERICO),
], TAMANHO)


#: Todos os registros, para o comando de conferência percorrer.
REGISTROS = {
    "remessa_header": REMESSA_HEADER,
    "remessa_detalhe": REMESSA_DETALHE,
    "remessa_trailer": REMESSA_TRAILER,
    "retorno_header": RETORNO_HEADER,
    "retorno_detalhe": RETORNO_DETALHE,
    "retorno_trailer": RETORNO_TRAILER,
}


#: Códigos de ocorrência enviados NA REMESSA (o que se pede ao banco).
#: Do lado de cá do arquivo — a tabela do que o banco responde está em
#: `ocorrencias.py`, e as duas não se misturam de propósito: são vocabulários
#: diferentes que por acaso usam números parecidos.
OCORRENCIA_REMESSA = {
    "ENTRADA": "01",
    "BAIXA": "02",
    "CANCELAMENTO": "02",
    "ABATIMENTO_CONCEDER": "04",
    "ABATIMENTO_CANCELAR": "05",
    "ALTERACAO_VENCIMENTO": "06",
    "PROTESTAR": "09",
    "SUSTAR_PROTESTO": "18",
}

#: Espécie do título, do nosso código de duas letras para o código numérico do
#: arquivo. CONFERIR contra o manual: a numeração varia entre bancos.
ESPECIE_TITULO = {
    "DM": "01",
    "NP": "02",
    "DS": "12",
    "RC": "17",
    "AP": "20",
    "ME": "16",
    "LC": "07",
    "OU": "99",
}
