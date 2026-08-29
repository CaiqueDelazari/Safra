#!/usr/bin/env bash
# Cria os dois .env de produção com segredos gerados na hora, no servidor.
#
#   ./deploy/preparar-env.sh suaempresa.com.br
#
# Existem dois .env com papéis diferentes, e uma senha que precisa ser a MESMA
# nos dois (a do Postgres). Digitada à mão, essa senha é o erro mais comum da
# implantação: o banco sobe, o backend não autentica, e a mensagem não diz o
# porquê. Aqui ela é gerada uma vez e escrita nos dois lugares.
#
# Nenhum segredo vem do repositório: tudo nasce em /dev/urandom nesta máquina.
set -euo pipefail

cd "$(dirname "$0")/.."

DOMINIO="${1:-}"
if [ -z "$DOMINIO" ]; then
  echo "uso: $0 <dominio.com.br>"
  echo "     informe o domínio raiz, sem 'painel.' nem 'api.' — o script monta os dois."
  exit 1
fi

PAINEL="painel.$DOMINIO"
API="api.$DOMINIO"

# Nunca sobrescrever: um .env perdido leva junto o acesso ao banco existente.
for arquivo in .env backend/.env; do
  if [ -e "$arquivo" ]; then
    echo "ERRO: $arquivo já existe. Renomeie ou apague antes de gerar de novo."
    exit 1
  fi
done

# 'tr < /dev/urandom | head -c N' parece o caminho óbvio e é uma armadilha: o
# head fecha o cano assim que junta N bytes, o tr morre de SIGPIPE e o
# 'pipefail' derruba o script inteiro. Aqui o head vem PRIMEIRO, lendo uma
# quantidade limitada, e todo mundo termina naturalmente.
segredo() {
  local n="$1" valor
  valor="$(head -c "$(( n * 16 ))" /dev/urandom | LC_ALL=C tr -dc 'A-Za-z0-9' | cut -c1-"$n")"
  if [ "${#valor}" -ne "$n" ]; then
    echo "ERRO: não consegui gerar um segredo de $n caracteres." >&2
    exit 1
  fi
  printf '%s' "$valor"
}

SECRET_KEY="$(segredo 64)"
SENHA_BANCO="$(segredo 32)"
TOKEN_ASAAS="$(segredo 40)"

# Chave da cifra dos segredos guardados no banco (a API key do Asaas de cada
# empresa). Formato Fernet: 32 bytes em base64 url-safe. Gerada aqui, e não
# derivada da SECRET_KEY, para que trocar a SECRET_KEY um dia não torne as
# chaves das empresas ilegíveis.
CAMPOS_CHAVE="$(head -c 32 /dev/urandom | base64 -w0 | tr '+/' '-_')"

# ------------------------------------------------------------------- backup
# Preferido: age (assimétrico). O servidor guarda só a chave pública, então
# invadir a máquina não abre backup nenhum — nem os antigos.
CHAVE_PUBLICA=""
if command -v age-keygen > /dev/null 2>&1; then
  age-keygen -o chave-backup.txt 2> /dev/null
  chmod 600 chave-backup.txt
  CHAVE_PUBLICA="$(grep -o 'age1[a-z0-9]*' chave-backup.txt | head -1)"
fi

# --------------------------------------------------------- .env da raiz
cat > .env <<EOF
# Gerado por deploy/preparar-env.sh em $(date '+%d/%m/%Y %H:%M').
# Usado apenas pelo docker-compose.prod.yml.

DOMINIO_PAINEL=$PAINEL
DOMINIO_API=$API
API_URL=https://$API/api/v1

POSTGRES_DB=erp_monitoramento
POSTGRES_USER=erp
POSTGRES_PASSWORD=$SENHA_BANCO

# Cifragem do backup. A chave PRIVADA correspondente está em chave-backup.txt
# e precisa sair deste servidor.
BACKUP_CHAVE_PUBLICA=$CHAVE_PUBLICA
BACKUP_CHAVE_PRIVADA=
BACKUP_SENHA=

# Cópia fora do servidor: crie um remoto com \`rclone config\` e aponte aqui.
#   BACKUP_DESTINO_REMOTO=b2:erp-backups/producao
BACKUP_DESTINO_REMOTO=
EOF
chmod 600 .env

# ------------------------------------------------------ .env da aplicação
# Partimos do exemplo para não perder chave nova que ele venha a ganhar; só os
# valores de produção são reescritos.
cp backend/.env.example backend/.env
trocar() { sed -i "s|^$1=.*|$1=$2|" backend/.env; }

trocar SECRET_KEY "$SECRET_KEY"
trocar DEBUG "False"
trocar ALLOWED_HOSTS "$API"
trocar CORS_ALLOWED_ORIGINS "https://$PAINEL"
trocar URL_API "https://$API"
trocar URL_PAINEL "https://$PAINEL"
trocar POSTGRES_HOST "db"
trocar POSTGRES_PORT "5432"
trocar POSTGRES_PASSWORD "$SENHA_BANCO"
trocar CAMPOS_CHAVE "$CAMPOS_CHAVE"
trocar ASAAS_BASE_URL "https://api.asaas.com/v3"
trocar ASAAS_WEBHOOK_TOKEN "$TOKEN_ASAAS"
chmod 600 backend/.env

echo
echo "Pronto. Criados: .env e backend/.env (só o dono lê)."
echo "  painel  https://$PAINEL"
echo "  api     https://$API"
echo
if [ -n "$CHAVE_PUBLICA" ]; then
  cat <<EOF
ATENÇÃO — chave de backup gerada em chave-backup.txt

  Sem a chave privada não existe restauração: nenhum backup deste servidor
  poderá ser aberto. Ela precisa sair daqui AGORA.

    1. copie o conteúdo para o seu gerenciador de senhas
    2. confira que colou certo
    3. rm chave-backup.txt

EOF
else
  cat <<EOF
AVISO — 'age' não está instalado, então o backup ficaria em claro e
'preparar_producao' vai reprovar a publicação. Instale e gere a chave:

    apt install -y age && age-keygen -o chave-backup.txt

  Depois copie a linha "public key" para BACKUP_CHAVE_PUBLICA no .env,
  guarde o arquivo FORA do servidor e apague-o daqui.

EOF
fi
echo "Falta preencher à mão em backend/.env, quando tiver:"
echo "  WHATSAPP_* (opcional — desligado, os avisos ficam como SIMULADA)"
echo "A API key do Asaas não vai em arquivo: é cadastrada por empresa no painel."
