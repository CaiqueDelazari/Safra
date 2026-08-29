"""Papéis e matriz de permissões (RBAC) — fonte única de verdade.

Quatro perfis, desenhados em cima de quem faz o quê numa operação de cobrança:

ADMINISTRADOR — dono da conta da empresa. Faz tudo, inclusive o que é
                irreversível: cadastrar conta bancária, guardar credencial do
                banco, administrar usuários.
FINANCEIRO    — conduz a régua de cobrança. Cria cobrança, gera lote, envia
                remessa, processa retorno, concilia, exporta. Não mexe em
                usuário nem em credencial bancária.
OPERADOR      — alimenta a base. Cadastra cliente e cobrança, acompanha o
                andamento. Não envia nada ao banco e não cancela cobrança
                registrada — as duas coisas custam dinheiro ou tarifa.
CONSULTA      — só lê. Contador, auditor, sócio que acompanha o caixa.

Duas camadas de decisão, e elas respondem a perguntas diferentes:

* `MATRIZ` — "este papel pode fazer esta ação neste módulo?" É o CRUD, e é o
  que `PermissaoDeModulo` consulta em toda view.
* `CAPACIDADES` — "este papel pode disparar esta operação nomeada?" São os
  atos que não são CRUD de nada: enviar remessa, processar retorno, girar
  credencial bancária. Um POST em `/lotes/{id}/enviar/` é `create` para o
  verbo HTTP e "enviar remessa" para o negócio; sem esta camada, o segundo
  significado se perderia no primeiro.
"""
from django.db import models


class Papel(models.TextChoices):
    ADMINISTRADOR = "ADMINISTRADOR", "Administrador"
    FINANCEIRO = "FINANCEIRO", "Financeiro"
    OPERADOR = "OPERADOR", "Operador"
    CONSULTA = "CONSULTA", "Consulta"


LEITURA = frozenset({"list", "retrieve"})
ESCRITA = frozenset({"create", "update", "partial_update"})
TOTAL = frozenset({"list", "retrieve", "create", "update", "partial_update", "destroy"})
SEM_EXCLUIR = TOTAL - {"destroy"}

# módulo -> papel -> ações permitidas
MATRIZ = {
    "empresas": {
        Papel.ADMINISTRADOR: TOTAL,
        Papel.FINANCEIRO: LEITURA,
        Papel.OPERADOR: LEITURA,
        Papel.CONSULTA: LEITURA,
    },
    "usuarios": {Papel.ADMINISTRADOR: TOTAL},
    # A conta bancária guarda a credencial que assina a remessa. Quem a lê,
    # lê por onde o dinheiro entra; quem a escreve, redireciona o dinheiro.
    # Por isso nem Financeiro escreve aqui — ver CAPACIDADES.
    "contas_bancarias": {
        Papel.ADMINISTRADOR: TOTAL,
        Papel.FINANCEIRO: LEITURA,
        Papel.OPERADOR: LEITURA,
        Papel.CONSULTA: LEITURA,
    },
    "clientes": {
        Papel.ADMINISTRADOR: TOTAL,
        Papel.FINANCEIRO: SEM_EXCLUIR,
        Papel.OPERADOR: SEM_EXCLUIR,
        Papel.CONSULTA: LEITURA,
    },
    "cobrancas": {
        Papel.ADMINISTRADOR: TOTAL,
        Papel.FINANCEIRO: SEM_EXCLUIR,
        # Operador cria e corrige rascunho; cancelar cobrança já registrada no
        # banco é outra coisa, e mora em CAPACIDADES.
        Papel.OPERADOR: SEM_EXCLUIR,
        Papel.CONSULTA: LEITURA,
    },
    "lotes": {
        Papel.ADMINISTRADOR: TOTAL,
        Papel.FINANCEIRO: SEM_EXCLUIR,
        Papel.OPERADOR: LEITURA,
        Papel.CONSULTA: LEITURA,
    },
    "arquivos": {
        Papel.ADMINISTRADOR: TOTAL,
        Papel.FINANCEIRO: SEM_EXCLUIR,
        Papel.OPERADOR: LEITURA,
        Papel.CONSULTA: LEITURA,
    },
    "pagamentos": {
        Papel.ADMINISTRADOR: LEITURA,
        Papel.FINANCEIRO: LEITURA,
        Papel.OPERADOR: LEITURA,
        Papel.CONSULTA: LEITURA,
    },
    "conciliacao": {
        Papel.ADMINISTRADOR: LEITURA,
        Papel.FINANCEIRO: LEITURA,
        Papel.OPERADOR: LEITURA,
        Papel.CONSULTA: LEITURA,
    },
    "relatorios": {
        Papel.ADMINISTRADOR: LEITURA,
        Papel.FINANCEIRO: LEITURA,
        Papel.OPERADOR: LEITURA,
        Papel.CONSULTA: LEITURA,
    },
    "auditoria": {Papel.ADMINISTRADOR: LEITURA},
    "dashboard": {
        Papel.ADMINISTRADOR: LEITURA,
        Papel.FINANCEIRO: LEITURA,
        Papel.OPERADOR: LEITURA,
        Papel.CONSULTA: LEITURA,
    },
    "busca": {
        Papel.ADMINISTRADOR: LEITURA,
        Papel.FINANCEIRO: LEITURA,
        Papel.OPERADOR: LEITURA,
        Papel.CONSULTA: LEITURA,
    },
    "tarefas": {
        Papel.ADMINISTRADOR: LEITURA,
        Papel.FINANCEIRO: LEITURA,
        Papel.OPERADOR: LEITURA,
        Papel.CONSULTA: LEITURA,
    },
}

#: Operações nomeadas — o que não é CRUD de nada. A view declara
#: `capacidade = "enviar_remessa"` na ação e `PermissaoDeModulo` cobra.
CAPACIDADES = {
    "importar_clientes": {Papel.ADMINISTRADOR, Papel.FINANCEIRO, Papel.OPERADOR},
    "criar_cobranca_em_lote": {Papel.ADMINISTRADOR, Papel.FINANCEIRO, Papel.OPERADOR},
    # Cancelar e baixar mexem com registro que já está no banco: geram
    # instrução de remessa e, em muitos contratos, tarifa.
    "cancelar_cobranca": {Papel.ADMINISTRADOR, Papel.FINANCEIRO},
    "baixar_cobranca": {Papel.ADMINISTRADOR, Papel.FINANCEIRO},
    "gerar_lote": {Papel.ADMINISTRADOR, Papel.FINANCEIRO},
    "enviar_remessa": {Papel.ADMINISTRADOR, Papel.FINANCEIRO},
    "processar_retorno": {Papel.ADMINISTRADOR, Papel.FINANCEIRO},
    "exportar_relatorio": {
        Papel.ADMINISTRADOR, Papel.FINANCEIRO, Papel.OPERADOR, Papel.CONSULTA,
    },
    "enviar_boleto_cliente": {Papel.ADMINISTRADOR, Papel.FINANCEIRO, Papel.OPERADOR},
    "administrar_usuarios": {Papel.ADMINISTRADOR},
    "administrar_integracao_bancaria": {Papel.ADMINISTRADOR},
}

#: Papéis que enxergam valor monetário. Todos, aqui: o produto *é* o dinheiro.
#: A constante existe porque o serializer base a consulta — e porque o dia em
#: que um perfil de call center entrar, ele entra por esta linha e mais nada.
PAPEIS_COM_VALORES = frozenset(
    {Papel.ADMINISTRADOR, Papel.FINANCEIRO, Papel.OPERADOR, Papel.CONSULTA}
)


def pode(papel: str, modulo: str, acao: str) -> bool:
    return acao in MATRIZ.get(modulo, {}).get(papel, frozenset())


def pode_capacidade(papel: str, capacidade: str) -> bool:
    """Papel desconhecido ou capacidade não declarada: nega. Falha fechado."""
    return papel in CAPACIDADES.get(capacidade, frozenset())


def ve_valores(papel: str) -> bool:
    return papel in PAPEIS_COM_VALORES
