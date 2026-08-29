#!/usr/bin/env bash
# Publica uma nova versão com segurança: backup, build, verificação e subida.
#
#   ./deploy/publicar.sh
set -euo pipefail

cd "$(dirname "$0")/.."
COMPOSE="docker compose -f docker-compose.prod.yml"

echo "==> 1/5 Backup preventivo"
./deploy/backup.sh

echo "==> 2/5 Atualizando o código"
git pull --ff-only

echo "==> 3/5 Construindo as imagens"
$COMPOSE build

echo "==> 4/5 Subindo (migrações rodam na inicialização do backend)"
$COMPOSE up -d

echo "    aguardando o backend responder…"
for _ in $(seq 1 30); do
  # Os mesmos dois cabeçalhos do HEALTHCHECK, pelos mesmos motivos: sem o Host
  # o Django responde 400 (ALLOWED_HOSTS não lista "localhost") e esta espera
  # nunca terminava — 60 s de silêncio a cada publicação, sem nunca confirmar
  # que o backend subiu. Sem o proto, um 301 passaria por sucesso.
  if $COMPOSE exec -T backend sh -c \
      'H="${ALLOWED_HOSTS%%,*}"; curl -fsS -H "Host: ${H:-localhost}" \
       -H "X-Forwarded-Proto: https" http://localhost:8000/api/v1/saude/' \
      > /dev/null 2>&1; then
    echo "    backend no ar"
    break
  fi
  sleep 2
done

echo "==> 5/5 Conferência de produção"
# Não derruba o deploy: só reporta o que ainda está pendente.
$COMPOSE exec -T backend python manage.py preparar_producao || true

echo
echo "Publicado. Logs:  $COMPOSE logs -f --tail=50"
