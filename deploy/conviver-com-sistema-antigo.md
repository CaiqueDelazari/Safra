# Conviver com o sistema antigo na mesma VPS

As duas pilhas podem usar o mesmo servidor, mas somente um Caddy pode ocupar as
portas 80 e 443. Enquanto o sistema antigo estiver no ar, ele continua sendo o
proxy público.

## Primeira publicação em paralelo

1. Aponte os domínios do painel e da API para a VPS.
2. Clone este repositório em um diretório próprio, por exemplo `/opt/safra`.
3. Rode `./deploy/preparar-env.sh dominio.com.br` e guarde fora do servidor a
   chave privada de backup que o script gerar.
4. Suba esta pilha sem o perfil `proxy`:

   ```bash
   docker compose -f docker-compose.prod.yml up -d --build
   ```

5. Copie os dois blocos de `deploy/Caddyfile` para o Caddyfile do sistema
   antigo. Nos `reverse_proxy`, use endereços que o Caddy antigo alcance. Se
   ele estiver em outra rede Docker, conecte-o também à rede desta pilha ou
   publique portas locais apenas para esse proxy.
6. Valide e recarregue o Caddy antigo. Depois confira os dois endereços HTTPS e
   rode no backend:

   ```bash
   python manage.py preparar_producao
   ```

## Quando o sistema antigo sair

Remova os blocos dele e suba o Caddy desta pilha com o perfil `proxy`:

```bash
docker compose -f docker-compose.prod.yml --profile proxy up -d
```

Antes da troca, confirme que nenhuma outra aplicação ainda depende do Caddy
antigo. A troca das portas interrompe todos os domínios atendidos por ele.
