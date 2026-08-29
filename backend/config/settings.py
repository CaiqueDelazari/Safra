"""
Configuração central da plataforma de cobranças.

Camadas: apps de domínio -> services -> repositories -> models.
Trabalho pesado nunca na requisição: API -> fila -> worker (ver config/celery.py).
"""
import sys
from datetime import timedelta
from pathlib import Path

from django.core.exceptions import ImproperlyConfigured

from decouple import Csv, config

BASE_DIR = Path(__file__).resolve().parent.parent

#: `manage.py test` roda com DEBUG=False; as travas de produção abaixo não
#: podem derrubar a suíte por causa disso.
RODANDO_TESTES = "test" in sys.argv

SECRET_KEY = config("SECRET_KEY", default="dev-insecure-change-me")
DEBUG = config("DEBUG", default=True, cast=bool)
ALLOWED_HOSTS = config("ALLOWED_HOSTS", default="*", cast=Csv())

# Trava de partida: com DEBUG desligado o sistema está na internet, e nenhuma
# das configurações abaixo pode continuar no valor de desenvolvimento.
# Falhar aqui é melhor que subir aberto e descobrir depois.
if not DEBUG and not RODANDO_TESTES:
    if SECRET_KEY == "dev-insecure-change-me" or len(SECRET_KEY) < 40:
        raise ImproperlyConfigured(
            "SECRET_KEY de desenvolvimento com DEBUG=False. Gere uma chave "
            "nova: python -c \"from django.utils.crypto import get_random_string; "
            "print(get_random_string(64))\""
        )
    if "*" in ALLOWED_HOSTS:
        raise ImproperlyConfigured(
            "ALLOWED_HOSTS=* com DEBUG=False. Liste os domínios reais."
        )

INSTALLED_APPS = [
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
    # terceiros
    "rest_framework",
    "rest_framework_simplejwt.token_blacklist",
    "corsheaders",
    "django_filters",
    "drf_spectacular",
    # domínio
    "core",
    "apps.empresas",
    "apps.accounts",
    "apps.clientes",
    "apps.bancos",
    "apps.cobrancas",
    "apps.pagamentos",
    "apps.conciliacao",
    "apps.relatorios",
    "apps.auditoria",
]

MIDDLEWARE = [
    "corsheaders.middleware.CorsMiddleware",
    "django.middleware.security.SecurityMiddleware",
    "whitenoise.middleware.WhiteNoiseMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
    # contexto de requisição (usuário, empresa ativa, IP) usado por auditoria e tenancy
    "core.middleware.RequestContextMiddleware",
]

ROOT_URLCONF = "config.urls"

TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS": [BASE_DIR / "templates"],
        "APP_DIRS": True,
        "OPTIONS": {
            "context_processors": [
                "django.template.context_processors.request",
                "django.contrib.auth.context_processors.auth",
                "django.contrib.messages.context_processors.messages",
            ],
        },
    },
]

WSGI_APPLICATION = "config.wsgi.application"


def _opcoes_do_banco() -> dict:
    """Ajustes exigidos por Postgres hospedado (Supabase, Neon, RDS).

    Nada disso é necessário com o banco em contêiner na mesma máquina, então
    tudo é opcional e o padrão preserva o comportamento local.
    """
    opcoes: dict = {}

    sslmode = config("POSTGRES_SSLMODE", default="")
    if sslmode:
        opcoes["sslmode"] = sslmode

    schema = config("POSTGRES_SCHEMA", default="")
    if schema:
        opcoes["options"] = f"-c search_path={schema},public"

    # Pooler em modo transação (PgBouncer) não sobrevive a prepared statement:
    # o psycopg reaproveita um plano numa conexão que já é outra.
    if config("POSTGRES_POOLER", default=False, cast=bool):
        opcoes["prepare_threshold"] = None

    return opcoes


DATABASES = {
    "default": {
        "ENGINE": "django.db.backends.postgresql",
        "NAME": config("POSTGRES_DB", default="cobrancas"),
        "USER": config("POSTGRES_USER", default="cobrancas"),
        "PASSWORD": config("POSTGRES_PASSWORD", default="cobrancas"),
        "HOST": config("POSTGRES_HOST", default="localhost"),
        "PORT": config("POSTGRES_PORT", default="5432"),
        "CONN_MAX_AGE": config("POSTGRES_CONN_MAX_AGE", default=60, cast=int),
        "OPTIONS": _opcoes_do_banco(),
    }
}

if RODANDO_TESTES:
    # Conexão persistente atravessa a fronteira entre classes de teste e chega
    # fechada na seguinte ("the connection is closed").
    DATABASES["default"]["CONN_MAX_AGE"] = 0

AUTH_USER_MODEL = "accounts.User"

AUTH_PASSWORD_VALIDATORS = [
    {"NAME": "django.contrib.auth.password_validation.UserAttributeSimilarityValidator"},
    {"NAME": "django.contrib.auth.password_validation.MinimumLengthValidator",
     "OPTIONS": {"min_length": 10}},
    {"NAME": "django.contrib.auth.password_validation.CommonPasswordValidator"},
    {"NAME": "django.contrib.auth.password_validation.NumericPasswordValidator"},
]

LANGUAGE_CODE = "pt-br"
TIME_ZONE = "America/Sao_Paulo"
USE_I18N = True
USE_TZ = True

# ------------------------------------------------------ tamanho de requisição
UPLOAD_IMAGEM_MAX_MB = config("UPLOAD_IMAGEM_MAX_MB", default=5, cast=int)
# Retorno de 50 mil títulos em CNAB 240 passa de 20 MB. O teto é alto porque o
# caso legítimo é grande — mas existe, senão um envio errado enche o disco.
UPLOAD_ARQUIVO_BANCO_MAX_MB = config("UPLOAD_ARQUIVO_BANCO_MAX_MB", default=64, cast=int)
UPLOAD_PLANILHA_MAX_MB = config("UPLOAD_PLANILHA_MAX_MB", default=32, cast=int)
DATA_UPLOAD_MAX_MEMORY_SIZE = (
    max(UPLOAD_ARQUIVO_BANCO_MAX_MB, UPLOAD_PLANILHA_MAX_MB) + 4
) * 1024 * 1024
FILE_UPLOAD_MAX_MEMORY_SIZE = 2 * 1024 * 1024
DATA_UPLOAD_MAX_NUMBER_FIELDS = 2000
FILE_UPLOAD_PERMISSIONS = 0o640

# Validade do link assinado de um arquivo (ver core/midia.py). Curto o
# bastante para um link vazado não valer amanhã, longo o bastante para o
# operador baixar a remessa e mandar ao gerente.
MIDIA_URL_VALIDADE_SEGUNDOS = config("MIDIA_URL_VALIDADE_HORAS", default=12,
                                     cast=int) * 3600

STATIC_URL = "static/"
STATIC_ROOT = BASE_DIR / "staticfiles"
MEDIA_URL = "media/"
MEDIA_ROOT = BASE_DIR / "media"
DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"

# ---------------------------------------------------------------- DRF / API v1
REST_FRAMEWORK = {
    "DEFAULT_AUTHENTICATION_CLASSES": (
        "rest_framework_simplejwt.authentication.JWTAuthentication",
    ),
    "DEFAULT_PERMISSION_CLASSES": ("rest_framework.permissions.IsAuthenticated",),
    "DEFAULT_FILTER_BACKENDS": (
        "django_filters.rest_framework.DjangoFilterBackend",
        "rest_framework.filters.SearchFilter",
        "rest_framework.filters.OrderingFilter",
    ),
    "DEFAULT_PAGINATION_CLASS": "core.pagination.DefaultPagination",
    "PAGE_SIZE": 25,
    "EXCEPTION_HANDLER": "core.exceptions.api_exception_handler",
    "DEFAULT_SCHEMA_CLASS": "drf_spectacular.openapi.AutoSchema",
    "DEFAULT_VERSIONING_CLASS": "rest_framework.versioning.URLPathVersioning",
    "DEFAULT_VERSION": "v1",
    # v2 entra nesta lista no dia em que existir; o roteador já está montado
    # por versão em config/urls.py, então acrescentar não mexe na v1.
    "ALLOWED_VERSIONS": ["v1"],
    "DEFAULT_THROTTLE_CLASSES": (
        "core.throttling.AnonimoThrottle",
        "core.throttling.UsuarioThrottle",
        "rest_framework.throttling.ScopedRateThrottle",
    ),
    "DEFAULT_THROTTLE_RATES": {
        "anon": config("THROTTLE_ANON", default="60/min"),
        "user": config("THROTTLE_USER", default="600/min"),
        "login": config("THROTTLE_LOGIN", default="10/min"),
        "login_conta": config("THROTTLE_LOGIN_CONTA", default="20/hour"),
        "refresh": config("THROTTLE_REFRESH", default="60/hour"),
        "midia": config("THROTTLE_MIDIA", default="600/min"),
        "segundo_fator": config("THROTTLE_SEGUNDO_FATOR", default="20/hour"),
        # Operações que custam dinheiro ou tarifa no banco. Teto baixo de
        # propósito: ninguém gera cem lotes por minuto de forma legítima, e um
        # laço acidental no painel viraria cem remessas.
        "operacao_bancaria": config("THROTTLE_BANCO", default="30/min"),
        "upload_retorno": config("THROTTLE_UPLOAD_RETORNO", default="60/hour"),
    },
}

SPECTACULAR_SETTINGS = {
    "TITLE": "Plataforma de Cobranças — API",
    "DESCRIPTION": (
        "API multiempresa para gestão de clientes, cobranças, boletos e "
        "retornos bancários."
    ),
    "VERSION": "1.0.0",
    "SERVE_INCLUDE_SCHEMA": False,
    # A documentação desenha o mapa inteiro da API. Aberta, é um presente para
    # quem procura por onde entrar; em produção fica atrás de login de staff.
    "SERVE_PERMISSIONS": ["rest_framework.permissions.AllowAny"] if DEBUG
    else ["rest_framework.permissions.IsAdminUser"],
}

# O painel faz tudo que a operação precisa; o admin do Django existe para
# manutenção pontual. Em produção fica desligado por padrão e, quando ligado,
# nunca no caminho óbvio.
ADMIN_ATIVO = config("ADMIN_ATIVO", default=DEBUG, cast=bool)
ADMIN_URL = config("ADMIN_URL", default="admin/").strip("/") + "/"

SIMPLE_JWT = {
    "ACCESS_TOKEN_LIFETIME": timedelta(minutes=config("JWT_ACCESS_MIN", default=30, cast=int)),
    "REFRESH_TOKEN_LIFETIME": timedelta(days=config("JWT_REFRESH_DAYS", default=7, cast=int)),
    "ROTATE_REFRESH_TOKENS": True,
    "BLACKLIST_AFTER_ROTATION": True,
    "UPDATE_LAST_LOGIN": True,
    "AUTH_HEADER_TYPES": ("Bearer",),
}

CORS_ALLOWED_ORIGINS = config(
    "CORS_ALLOWED_ORIGINS",
    default="http://localhost:3000,http://127.0.0.1:3000",
    cast=Csv(),
)
CORS_ALLOW_HEADERS = (
    "accept", "authorization", "content-type", "user-agent",
    "x-csrftoken", "x-requested-with", "x-empresa-id",
)

# ------------------------------------------------------------------- Cache
# Redis, o mesmo que serve de broker para as filas. Diferente do sistema
# anterior, aqui ele não é opcional: os tetos de requisição precisam ser
# contados uma vez só entre os workers do gunicorn, e o lock de idempotência
# do processamento de retorno (apps/bancos/tasks.py) depende de um `add`
# atômico compartilhado — em cache por processo, dois workers processariam o
# mesmo arquivo em paralelo e o "não duplica pagamento" viraria promessa vazia.
REDIS_URL = config("REDIS_URL", default="redis://localhost:6379/0")

CACHES = {
    "default": {
        "BACKEND": "django.core.cache.backends.redis.RedisCache",
        "LOCATION": REDIS_URL,
        "KEY_PREFIX": "cobrancas",
    }
}

if RODANDO_TESTES:
    # A suíte não sobe Redis. LocMem serve: cada teste roda num processo só,
    # então o `add` continua atômico o suficiente para exercitar a regra.
    CACHES = {
        "default": {
            "BACKEND": "django.core.cache.backends.locmem.LocMemCache",
            "LOCATION": "testes",
        }
    }

# ------------------------------------------------------------------- Celery
CELERY_BROKER_URL = config("CELERY_BROKER_URL", default=REDIS_URL)
CELERY_RESULT_BACKEND = config("CELERY_RESULT_BACKEND", default=REDIS_URL)
CELERY_TASK_SERIALIZER = "json"
CELERY_RESULT_SERIALIZER = "json"
CELERY_ACCEPT_CONTENT = ["json"]
CELERY_TIMEZONE = TIME_ZONE
CELERY_ENABLE_UTC = True
# Confirma a tarefa só depois de executada: worker morto no meio de um lote
# devolve o trabalho para a fila em vez de perdê-lo. Exige que as tarefas
# sejam idempotentes — e elas são, por construção (ver apps/bancos/tasks.py).
CELERY_TASK_ACKS_LATE = True
CELERY_TASK_REJECT_ON_WORKER_LOST = True
# Uma tarefa por vez por processo: as nossas são pesadas e longas: buscar mais
# só faria uma delas esperar na memória de um worker ocupado.
CELERY_WORKER_PREFETCH_MULTIPLIER = 1
CELERY_WORKER_MAX_TASKS_PER_CHILD = 200
CELERY_TASK_TIME_LIMIT = config("CELERY_TASK_TIME_LIMIT", default=1800, cast=int)
CELERY_TASK_SOFT_TIME_LIMIT = config("CELERY_TASK_SOFT_TIME_LIMIT", default=1500, cast=int)
CELERY_RESULT_EXPIRES = 60 * 60 * 24 * 3
CELERY_BROKER_CONNECTION_RETRY_ON_STARTUP = True
#: Na suíte, `delay()` executa na hora e no mesmo processo. Sem isto, todo
#: teste de lote precisaria de um worker no ar.
CELERY_TASK_ALWAYS_EAGER = config("CELERY_EAGER", default=RODANDO_TESTES, cast=bool)
CELERY_TASK_EAGER_PROPAGATES = True

# Rotinas periódicas. O intervalo da varredura de retorno é o que define quão
# fresco fica o dashboard — o banco publica o retorno uma vez por dia útil,
# mas varrer de hora em hora custa quase nada e cobre republicação.
CELERY_BEAT_SCHEDULE = {
    "varrer-retornos": {
        "task": "bancos.varrer_retornos",
        "schedule": config("INTERVALO_VARRER_RETORNOS_MIN", default=60, cast=int) * 60,
    },
    "marcar-vencidas": {
        "task": "cobrancas.marcar_vencidas",
        # Uma vez por dia, de madrugada: "vencida" é conceito de data, não de
        # instante, e recalcular a cada hora só geraria log repetido.
        "schedule": 24 * 60 * 60,
    },
    "reprocessar-arquivos-presos": {
        "task": "bancos.reprocessar_presos",
        "schedule": 30 * 60,
    },
}

# ------------------------------------------------- Segredos guardados no banco
# Chave da cifra dos campos sensíveis — aqui, as credenciais bancárias de cada
# empresa. Vazia, o sistema deriva uma da SECRET_KEY e sobe do mesmo jeito, mas
# aí trocar a SECRET_KEY torna as credenciais gravadas ilegíveis.
# Gerar com:
#   python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"
CAMPOS_CHAVE = config("CAMPOS_CHAVE", default="")

# ------------------------------------------------------------ integração banco
# Diretório onde os arquivos de remessa gerados e de retorno recebidos ficam
# antes de virarem `ArquivoBancario`. Em produção é um volume; o SFTP do banco,
# quando configurado, escreve aqui.
BANCO_DIR_ENTRADA = Path(config("BANCO_DIR_ENTRADA", default=str(BASE_DIR / "banco" / "entrada")))
BANCO_DIR_SAIDA = Path(config("BANCO_DIR_SAIDA", default=str(BASE_DIR / "banco" / "saida")))

# Tamanho do bloco ao processar arquivo grande: 500 registros por transação.
# Menor, o overhead de commit domina; maior, um erro no fim desfaz trabalho
# demais e a memória do worker cresce sem necessidade.
LOTE_TAMANHO_BLOCO = config("LOTE_TAMANHO_BLOCO", default=500, cast=int)
#: Teto de cobranças num único lote de remessa. Acima disto o sistema divide em
#: vários lotes: banco nenhum gosta de arquivo com 200 mil títulos, e um erro
#: no meio invalidaria o arquivo inteiro.
LOTE_MAX_TITULOS = config("LOTE_MAX_TITULOS", default=20000, cast=int)

# URL pública do painel, usada nos links enviados ao sacado.
URL_PAINEL = config("URL_PAINEL", default="http://localhost:3000")
# URL pública desta API. Usada para montar link de arquivo quando o serializer
# roda fora de uma requisição (tarefa, comando, e-mail).
URL_API = config("URL_API", default="")

#: Nome que aparece no aplicativo autenticador do segundo fator e no rodapé
#: dos e-mails.
NOME_DO_SISTEMA = config("NOME_DO_SISTEMA", default="Plataforma de Cobranças")

# --------------------------------------------------------------------- e-mail
# Envio do boleto ao sacado. Sem host configurado, o Django escreve no console
# — o fluxo continua exercitável sem SMTP contratado.
EMAIL_BACKEND = config(
    "EMAIL_BACKEND",
    default="django.core.mail.backends.console.EmailBackend"
    if DEBUG else "django.core.mail.backends.smtp.EmailBackend",
)
EMAIL_HOST = config("EMAIL_HOST", default="")
EMAIL_PORT = config("EMAIL_PORT", default=587, cast=int)
EMAIL_HOST_USER = config("EMAIL_HOST_USER", default="")
EMAIL_HOST_PASSWORD = config("EMAIL_HOST_PASSWORD", default="")
EMAIL_USE_TLS = config("EMAIL_USE_TLS", default=True, cast=bool)
DEFAULT_FROM_EMAIL = config("DEFAULT_FROM_EMAIL", default="nao-responda@localhost")

LOGGING = {
    "version": 1,
    "disable_existing_loggers": False,
    "formatters": {
        "verbose": {"format": "[{asctime}] {levelname} {name} {message}", "style": "{"},
    },
    "handlers": {
        "console": {"class": "logging.StreamHandler", "formatter": "verbose"},
    },
    "root": {"handlers": ["console"], "level": config("LOG_LEVEL", default="INFO")},
}

# ------------------------------------------------------------- endurecimento
SESSION_COOKIE_HTTPONLY = True
SESSION_COOKIE_SAMESITE = "Lax"
CSRF_COOKIE_SAMESITE = "Lax"
SECURE_REFERRER_POLICY = "strict-origin-when-cross-origin"
SECURE_CONTENT_TYPE_NOSNIFF = True
X_FRAME_OPTIONS = "DENY"
SESSION_COOKIE_AGE = config("SESSION_COOKIE_AGE", default=8 * 3600, cast=int)
SESSION_EXPIRE_AT_BROWSER_CLOSE = True

if not DEBUG:
    # Exceto sob `manage.py test`: o cliente de teste fala HTTP, então o
    # redirecionamento responde 301 antes de qualquer view.
    SECURE_SSL_REDIRECT = not RODANDO_TESTES
    SESSION_COOKIE_SECURE = True
    CSRF_COOKIE_SECURE = True
    SECURE_HSTS_SECONDS = 31536000
    SECURE_HSTS_INCLUDE_SUBDOMAINS = True
    SECURE_HSTS_PRELOAD = True
    SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https")
    # O painel manda o token no cabeçalho, nunca em cookie: o navegador não
    # tem por que enviar credencial para outra origem.
    CORS_ALLOW_CREDENTIALS = False
    CSRF_TRUSTED_ORIGINS = CORS_ALLOWED_ORIGINS
