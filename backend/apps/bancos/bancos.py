"""Catálogo de bancos e a moeda corrente entre o sistema e cada integração.

Banco não é tabela: é código FEBRABAN, e código FEBRABAN não muda de valor
entre uma empresa e outra. Uma tabela aqui só criaria a chance de duas
empresas cadastrarem o "Safra" com códigos diferentes e a remessa sair errada
para uma delas.

Quem sabe *falar* com cada banco é o adapter (`apps/bancos/adapters/`). Este
módulo diz apenas quais existem e como se chamam.
"""
from django.db import models


class CodigoBanco(models.TextChoices):
    """Códigos de compensação FEBRABAN. Três dígitos, com zero à esquerda —
    guardar como texto é o que preserva o zero: '033' vira 33 em inteiro e a
    remessa sai com um dígito a menos."""

    SAFRA = "422", "422 — Banco Safra"
    BANCO_DO_BRASIL = "001", "001 — Banco do Brasil"
    SANTANDER = "033", "033 — Santander"
    CAIXA = "104", "104 — Caixa Econômica Federal"
    BRADESCO = "237", "237 — Bradesco"
    ITAU = "341", "341 — Itaú Unibanco"
    SICOOB = "756", "756 — Sicoob"
    SICREDI = "748", "748 — Sicredi"


#: Bancos com adapter implementado. A tela de conta bancária só oferece estes;
#: os demais ficam no enum porque o cadastro pode existir antes da integração
#: (empresa que já emite pelo internet banking e vai migrar).
BANCOS_INTEGRADOS = frozenset({CodigoBanco.SAFRA})


class MeioDeIntegracao(models.TextChoices):
    """Como o sistema conversa com o banco. É escolha por conta bancária, não
    por banco: a mesma empresa pode ter um convênio antigo em CNAB e um novo
    em API no mesmo Safra, e migrar um sem parar o outro."""

    CNAB400 = "CNAB400", "Arquivo CNAB 400"
    CNAB240 = "CNAB240", "Arquivo CNAB 240"
    API = "API", "API REST"


class TipoArquivo(models.TextChoices):
    REMESSA = "REMESSA", "Remessa"
    RETORNO = "RETORNO", "Retorno"


class StatusArquivo(models.TextChoices):
    PENDENTE = "PENDENTE", "Pendente"
    PROCESSANDO = "PROCESSANDO", "Processando"
    PROCESSADO = "PROCESSADO", "Processado"
    PROCESSADO_COM_ERROS = "PROCESSADO_COM_ERROS", "Processado com erros"
    ERRO = "ERRO", "Erro"


class StatusLote(models.TextChoices):
    RASCUNHO = "RASCUNHO", "Rascunho"
    MONTANDO = "MONTANDO", "Montando"
    PRONTO = "PRONTO", "Pronto para envio"
    ENVIANDO = "ENVIANDO", "Enviando"
    ENVIADO = "ENVIADO", "Enviado ao banco"
    CONFIRMADO = "CONFIRMADO", "Confirmado pelo banco"
    PARCIAL = "PARCIAL", "Confirmado com rejeições"
    ERRO = "ERRO", "Erro"
    CANCELADO = "CANCELADO", "Cancelado"


class TipoOcorrencia(models.TextChoices):
    """O que o banco disse que aconteceu com um título.

    O código bruto do banco fica em `OcorrenciaBancaria.codigo`; aqui está a
    tradução para o vocabulário do sistema, que é o que o resto do código
    consulta. Sem essa tradução, cada regra de negócio precisaria conhecer a
    tabela de códigos de cada banco — e é exatamente isso que a camada de
    adapter existe para evitar.
    """

    ENTRADA_CONFIRMADA = "ENTRADA_CONFIRMADA", "Entrada confirmada"
    ENTRADA_REJEITADA = "ENTRADA_REJEITADA", "Entrada rejeitada"
    LIQUIDACAO = "LIQUIDACAO", "Liquidação (pagamento)"
    BAIXA = "BAIXA", "Baixa"
    BAIXA_REJEITADA = "BAIXA_REJEITADA", "Baixa rejeitada"
    ABATIMENTO_CONCEDIDO = "ABATIMENTO_CONCEDIDO", "Abatimento concedido"
    ABATIMENTO_CANCELADO = "ABATIMENTO_CANCELADO", "Abatimento cancelado"
    VENCIMENTO_ALTERADO = "VENCIMENTO_ALTERADO", "Vencimento alterado"
    PROTESTO = "PROTESTO", "Protesto"
    SUSTACAO_PROTESTO = "SUSTACAO_PROTESTO", "Sustação de protesto"
    TARIFA = "TARIFA", "Tarifa / despesa"
    ALTERACAO_CONFIRMADA = "ALTERACAO_CONFIRMADA", "Alteração confirmada"
    ALTERACAO_REJEITADA = "ALTERACAO_REJEITADA", "Alteração rejeitada"
    DESCONHECIDA = "DESCONHECIDA", "Ocorrência não mapeada"


#: Ocorrências que movem dinheiro. Só estas geram `Pagamento` — e é aqui, num
#: lugar só, que se decide isso. Espalhar essa lista pelo código seria o
#: caminho mais curto para um dia uma tarifa virar pagamento do cliente.
OCORRENCIAS_DE_LIQUIDACAO = frozenset({TipoOcorrencia.LIQUIDACAO})


class EspecieTitulo(models.TextChoices):
    DUPLICATA_MERCANTIL = "DM", "DM — Duplicata mercantil"
    DUPLICATA_SERVICO = "DS", "DS — Duplicata de serviço"
    NOTA_PROMISSORIA = "NP", "NP — Nota promissória"
    RECIBO = "RC", "RC — Recibo"
    APOLICE_SEGURO = "AP", "AP — Apólice de seguro"
    MENSALIDADE_ESCOLAR = "ME", "ME — Mensalidade escolar"
    LETRA_CAMBIO = "LC", "LC — Letra de câmbio"
    OUTROS = "OU", "OU — Outros"
