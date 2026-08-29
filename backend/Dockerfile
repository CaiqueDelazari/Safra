# Imagem única para os três processos: web, worker e beat. O que muda entre
# eles é o comando, não o conteúdo — três imagens divergiriam na primeira
# publicação apressada, e o worker rodaria com um código diferente do da API.
FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /app

# libpq para o psycopg; curl para o healthcheck. Sem compilador: todas as
# dependências têm wheel para linux/amd64, e um gcc na imagem final é
# superfície de ataque sem contrapartida.
RUN apt-get update \
    && apt-get install -y --no-install-recommends libpq5 curl \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

# Usuário sem privilégio. As pastas graváveis são criadas antes da troca —
# depois dela, o processo não tem permissão para criá-las.
RUN useradd --create-home --shell /usr/sbin/nologin app \
    && mkdir -p /app/media /app/staticfiles /app/banco/entrada /app/banco/saida \
    && chown -R app:app /app
USER app

EXPOSE 8000

# Testa pela porta de rede, com Host válido: sem o cabeçalho o Django responde
# 400 (ALLOWED_HOSTS) e o contêiner ficaria eternamente "unhealthy".
HEALTHCHECK --interval=30s --timeout=5s --start-period=40s --retries=3 \
    CMD sh -c 'H="${ALLOWED_HOSTS%%,*}"; curl -fsS -H "Host: ${H:-localhost}" \
        -H "X-Forwarded-Proto: https" http://localhost:8000/api/v1/saude/ || exit 1'

CMD ["gunicorn", "config.wsgi:application", "--bind", "0.0.0.0:8000", \
     "--workers", "3", "--threads", "2", "--timeout", "120", \
     "--access-logfile", "-", "--error-logfile", "-"]
