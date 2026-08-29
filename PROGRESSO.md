# Onde paramos

Sessão de 28/08/2026. Backend **completo e testado**; frontend com o núcleo
pronto e algumas telas de apoio faltando.

## Como voltar a rodar

```bash
docker compose up -d                  # Postgres em 55432, Redis em 56379
cd backend
../.venv/Scripts/python.exe manage.py migrate
../.venv/Scripts/python.exe manage.py test tests      # 130 testes, todos passando
../.venv/Scripts/python.exe manage.py runserver
```

As portas do compose de desenvolvimento são deslocadas de propósito: esta
máquina já tem um PostgreSQL nativo em 5432, e o Windows deixa os dois
"bindarem" sem erro — o que conecta é o nativo, e a mensagem que aparece é
"autenticação falhou".

O worker roda separado:

```bash
cd backend && ../.venv/Scripts/python.exe -m celery -A config worker -l info -Q padrao,lotes,retorno
```

## Feito

**Backend (Django 5.1 + DRF + Celery + Postgres)** — 130 testes passando.

- Multiempresa de verdade: papel por vínculo (a mesma pessoa é administradora
  numa empresa e consulta em outra), isolamento na leitura *e* na escrita.
- `apps/bancos/` — conta bancária, lote, arquivo, ocorrência; camada de
  adapter com Safra CNAB 400 implementado e o adapter de API com o
  encanamento pronto (falta só o mapeamento de campos, ver abaixo).
- `apps/cobrancas/`, `apps/clientes/`, `apps/pagamentos/`,
  `apps/conciliacao/`, `apps/relatorios/`.
- Fila com três filas separadas (padrao/lotes/retorno), lock de idempotência
  e rotinas agendadas (varrer retornos, marcar vencidas, recolher preso).
- Comandos: `criar_admin`, `preparar_producao`, `conferir_layout`.

**Frontend (Next 16)** — telas prontas:
dashboard, pendências, clientes (lista + importação de planilha), cobranças
(lista com seleção em massa e geração de lote), cobrança nova (individual e
mensalidade em lote), cobrança detalhe, lotes (lista + detalhe com progresso),
retornos (upload e reprocessamento), remessas, contas bancárias, pagamentos,
conciliação.

**Infra**: `docker-compose.prod.yml` (com Redis, worker e beat), Caddyfile,
`.env.example` da raiz e do backend, Dockerfile do backend.

## Verificações que existem

```bash
cd backend
../.venv/Scripts/python.exe manage.py test tests      # 130 testes
../.venv/Scripts/python.exe manage.py conferir_rotas  # painel x backend
cd ../frontend && npm run build                       # 23 rotas
```

O `conferir_rotas` compara cada endereço que o painel chama com as rotas
registradas no Django. É a costura que não tem dono: o TypeScript não enxerga
string de URL e o teste de backend não enxerga o que o frontend pede, então
`/clientes/` de um lado e `/clients/` do outro só apareceria clicando em
produção.

## Falta

**Fluxo ponta a ponta.** As telas compilam e os endereços conferem, mas o
sistema nunca rodou de verdade com banco: criar empresa, cadastrar cliente,
gerar lote, subir retorno e ver a cobrança virar paga. É o próximo passo, e
precisa do Docker no ar (`docker compose up -d`).

**Deploy**

- `deploy/publicar.sh` ainda é o copiado do sistema antigo; precisa apontar
  para esta pilha.
- Documento de convivência: enquanto o sistema antigo estiver no ar, quem tem
  as portas 80/443 é o Caddy dele — os dois blocos do nosso `Caddyfile` entram
  no Caddyfile daquele projeto, e o serviço `proxy` daqui só sobe (perfil
  `proxy`) quando o antigo sair.

## O que precisa de decisão sua

**O layout CNAB 400 precisa ser conferido contra o manual do Safra** antes da
primeira remessa real. Isso não é opcional: layout de cobrança varia por banco
e às vezes por carteira, e um campo deslocado não gera erro em lugar nenhum —
gera um arquivo que o banco recusa no dia seguinte, sem apontar a coluna.

A conferência é mecânica:

```bash
python manage.py conferir_layout --conta <id>
```

O comando imprime a tabela campo a campo com uma linha de exemplo montada com
dados reais da conta. Põe-se lado a lado com a página do manual. Os campos
marcados com `CONFERIR` em `apps/bancos/adapters/safra/layout400.py` são os
que mais variam — comece por eles. Ajustar é mudar números naquele arquivo e
mais nada.

Dois pontos merecem atenção especial, porque erram em silêncio:

1. **Código do cedente** (posições 27-46 do header). O banco fornece na
   abertura do convênio. Sem ele o sistema deduz de agência+conta, o que
   funciona em muitos convênios e falha nos outros.
2. **Campo livre do código de barras**
   (`apps/bancos/adapters/safra/campo_livre.py`). Um erro aqui não é recusado
   pelo banco: gera um boleto que o caixa lê e credita em outro lugar. O teste
   `tests/test_boleto.py` precisa ser refeito comparando com um boleto real do
   convênio.

**API do Safra**: `apps/bancos/adapters/safra/api.py` tem OAuth2, mTLS, cache
de token e retentativa prontos. Faltam `_montar_payload` e `_ler_resposta`,
que dependem da documentação do contrato — deliberadamente não adivinhados,
porque um palpite ali gera requisições que o banco aceita com o valor no campo
errado, e isso não aparece em teste nenhum: aparece no extrato do cliente.

## Dois defeitos reais que os testes pegaram

Ficam registrados porque valem para a próxima revisão do layout:

1. **Fator de vencimento** estava somando 1000 à contagem de dias. A norma diz
   "o fator começa em 1000", e a leitura apressada vira `dias + 1000` — o que
   adiantaria todo boleto do sistema em mil dias. O fator é a contagem simples
   de dias desde 07/10/1997.
2. **Nosso número** tinha 8 posições no layout e 9 no código de barras. O
   dígito mais significativo era cortado em silêncio: o banco registraria um
   número e o boleto impresso teria outro, e o retorno nunca casaria com a
   cobrança. Agora o adapter recusa a montagem em vez de truncar.
