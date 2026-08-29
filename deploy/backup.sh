#!/usr/bin/env bash
# Backup do PostgreSQL: cifrado, com retenção e cópia fora do servidor.
#
#   ./deploy/backup.sh                              backup normal
#   ./deploy/backup.sh restaurar arquivo.sql.gz.age   restaura um backup
#
# O dump tem a carteira inteira do cliente: nome, endereço, telefone, CPF e
# histórico financeiro. Guardado em claro ao lado do banco, quem levasse o
# servidor levaria tudo — e a cópia externa seria só mais um lugar de onde
# vazar. Por isso o arquivo sai cifrado e a chave de leitura não fica aqui.
set -euo pipefail

cd "$(dirname "$0")/.."

COMPOSE="docker compose -f docker-compose.prod.yml"
DESTINO="./backups"
RETENCAO_DIAS=14

# shellcheck disable=SC1091
[ -f .env ] && set -a && source .env && set +a

: "${POSTGRES_USER:?defina POSTGRES_USER no .env}"
: "${POSTGRES_DB:?defina POSTGRES_DB no .env}"

mkdir -p "$DESTINO"
chmod 700 "$DESTINO"

# ---------------------------------------------------------------- cifragem
# Dois caminhos, nesta ordem de preferência:
#
#   age  — assimétrico. O servidor guarda só a chave PÚBLICA: quem invadir a
#          máquina não consegue ler backup nenhum, nem os antigos. É o certo.
#   openssl — simétrico, com a senha no .env. Protege contra o arquivo vazar
#          (bucket aberto, disco roubado), mas não contra o servidor cair.
#
# Sem nenhum dos dois configurado, o backup local ainda acontece — perder
# backup é pior que backup em claro —, mas o aviso é barulhento e o envio
# externo é recusado: mandar a carteira em claro para fora é pior ainda.
cifrar() {
  if [ -n "${BACKUP_CHAVE_PUBLICA:-}" ]; then
    age -r "$BACKUP_CHAVE_PUBLICA" -o "$2" "$1"
    rm -f "$1"
    echo "$2"
  elif [ -n "${BACKUP_SENHA:-}" ]; then
    openssl enc -aes-256-cbc -pbkdf2 -iter 200000 -salt \
      -pass env:BACKUP_SENHA -in "$1" -out "$2"
    rm -f "$1"
    echo "$2"
  else
    echo "$1"
  fi
}

extensao_cifrada() {
  if [ -n "${BACKUP_CHAVE_PUBLICA:-}" ]; then echo ".age"
  elif [ -n "${BACKUP_SENHA:-}" ]; then echo ".enc"
  else echo ""; fi
}

decifrar() {
  case "$1" in
    *.age)
      : "${BACKUP_CHAVE_PRIVADA:?defina BACKUP_CHAVE_PRIVADA para restaurar um .age}"
      age -d -i "$BACKUP_CHAVE_PRIVADA" "$1"
      ;;
    *.enc)
      : "${BACKUP_SENHA:?defina BACKUP_SENHA para restaurar um .enc}"
      openssl enc -d -aes-256-cbc -pbkdf2 -iter 200000 -pass env:BACKUP_SENHA -in "$1"
      ;;
    *)
      cat "$1"
      ;;
  esac
}

# ------------------------------------------------------------- restauração
restaurar() {
  local arquivo="$1"
  [ -f "$arquivo" ] || { echo "Arquivo não encontrado: $arquivo" >&2; exit 1; }

  echo "ATENÇÃO: isto substitui todo o conteúdo do banco '$POSTGRES_DB'."
  read -rp "Digite RESTAURAR para confirmar: " confirmacao
  [ "$confirmacao" = "RESTAURAR" ] || { echo "Cancelado."; exit 1; }

  echo "Parando a aplicação…"
  $COMPOSE stop backend frontend

  decifrar "$arquivo" | gunzip -c | $COMPOSE exec -T db \
    psql -U "$POSTGRES_USER" -d "$POSTGRES_DB"

  echo "Subindo a aplicação…"
  $COMPOSE start backend frontend
  echo "Restauração concluída a partir de $arquivo"
}

if [ "${1:-}" = "restaurar" ]; then
  restaurar "${2:?informe o arquivo de backup}"
  exit 0
fi

# ------------------------------------------------------------------ backup
BRUTO="$DESTINO/cobrancas-$(date +%Y%m%d-%H%M%S).sql.gz"

# --clean --if-exists deixa o dump pronto para restaurar sobre uma base existente.
$COMPOSE exec -T db pg_dump -U "$POSTGRES_USER" -d "$POSTGRES_DB" \
  --clean --if-exists --no-owner \
  | gzip -9 > "$BRUTO"

# Um dump minúsculo quase sempre significa que o banco não respondeu.
if [ "$(stat -c%s "$BRUTO")" -lt 2048 ]; then
  echo "FALHA: backup gerado vazio — verifique o banco." >&2
  rm -f "$BRUTO"
  exit 1
fi

ARQUIVO=$(cifrar "$BRUTO" "$BRUTO$(extensao_cifrada)")
chmod 600 "$ARQUIVO"
TAMANHO=$(du -h "$ARQUIVO" | cut -f1)

# ----------------------------------------------------------- cópia externa
# Backup que só existe no servidor não é backup: o mesmo incêndio leva os dois.
if [ -n "${BACKUP_DESTINO_REMOTO:-}" ]; then
  if [ "$ARQUIVO" = "$BRUTO" ]; then
    echo "RECUSADO: envio externo sem cifragem. Configure BACKUP_CHAVE_PUBLICA" >&2
    echo "          ou BACKUP_SENHA antes de mandar a base para fora." >&2
    exit 1
  fi
  if ! command -v rclone > /dev/null; then
    echo "FALHA: BACKUP_DESTINO_REMOTO configurado, mas rclone não está instalado." >&2
    exit 1
  fi
  rclone copy "$ARQUIVO" "$BACKUP_DESTINO_REMOTO" --no-traverse
  echo "  cópia externa enviada para $BACKUP_DESTINO_REMOTO"
  # A retenção lá fora é do provedor (versionamento/ciclo de vida do bucket):
  # apagar remoto daqui daria ao servidor invadido o poder de apagar o backup.
fi

find "$DESTINO" -name 'cobrancas-*.sql.gz*' -mtime "+$RETENCAO_DIAS" -delete

if [ "$ARQUIVO" = "$BRUTO" ]; then
  echo "AVISO: backup EM CLARO. A carteira inteira do cliente está legível em" >&2
  echo "       $ARQUIVO — configure BACKUP_CHAVE_PUBLICA (age) ou BACKUP_SENHA." >&2
fi

echo "[$(date '+%d/%m/%Y %H:%M')] backup OK: $ARQUIVO ($TAMANHO)"
echo "  backups guardados: $(find "$DESTINO" -name 'cobrancas-*.sql.gz*' | wc -l)"
