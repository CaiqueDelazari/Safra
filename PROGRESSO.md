# Andamento do projeto Safra

Atualizado em 29/08/2026 após revisão executável do backend, painel e layout bancário.

## Pronto no repositório

- Backend Django/DRF multiempresa, clientes, cobranças, lotes, remessas, retornos,
  pagamentos, conciliação, relatórios, auditoria, equipe e 2FA.
- Painel Next.js com 21 páginas geradas e lint limpo.
- Filas Celery separadas, tarefas periódicas e proteção de idempotência.
- Infra de produção com Docker Compose, Caddy, publicação, backup e restauração.
- Credenciais da API Safra configuráveis no painel e cifradas no banco: client ID,
  chave/secret, certificado mTLS e chave privada. Segredos nunca retornam pela API.
- CNAB 400 corrigido pelo manual oficial do Banco Safra, versão maio/2026:
  posições de header/detalhe/trailer, retorno, código da empresa, campo livre,
  carteira, espécie, protesto, endereço e totais do arquivo.
- Teste do código de barras com o exemplo numérico publicado no manual Safra.

## Verificação

```bash
cd backend
../.venv/Scripts/python.exe manage.py test tests
../.venv/Scripts/python.exe manage.py makemigrations --check --dry-run
../.venv/Scripts/python.exe manage.py conferir_rotas

cd ../frontend
npm run lint
npm run build
```

## Dependências externas que ainda impedem produção real

1. **Homologação do CNAB com o Safra.** O manual exige abertura de chamado pelo
   gerente e envio de remessa de teste à Mesa de Implantação. A agência e a conta
   usadas no teste são as mesmas de produção.
2. **Contrato privado da API.** OAuth2, mTLS e armazenamento das chaves estão
   prontos, mas os campos de emissão/consulta e os endpoints não são publicados
   no site do banco. `_montar_payload` e `_ler_resposta` permanecem bloqueados de
   propósito até o cliente fornecer a documentação do produto contratado.
3. **Primeira publicação.** Os artefatos foram validados localmente, mas ainda é
   necessário exercitar publicação, worker, beat, backup/restauração e Caddy em
   um VPS de teste.

Manual oficial: https://www.safra.com.br/servicos/pessoa-juridica/cash-management.htm

Mesa de Implantação informada no manual: (11) 3175-4790 / 0300 371 4602 e
mesa.implantacao@safra.com.br.
