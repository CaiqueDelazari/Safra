"""Aplicação Celery — filas, workers e agendamento.

Três filas, e a separação não é enfeite:

* `padrao`   — trabalho curto (e-mail, PDF de um boleto, recálculo pontual);
* `lotes`    — geração de lote e montagem de remessa. Demora minutos e come
               CPU; misturado com o resto, atrasaria um e-mail por meia hora;
* `retorno`  — leitura de arquivo do banco. Tem prioridade sobre lote porque é
               dinheiro que já entrou e ainda não apareceu no painel do
               cliente — e porque é a única fila cujo atraso o cliente do
               nosso cliente sente (boleto pago que continua "em aberto").

O worker de produção sobe com `-Q padrao,lotes,retorno`; separar em processos
diferentes é uma linha no compose no dia em que o volume pedir.
"""
import os

from celery import Celery
from celery.signals import setup_logging

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")

app = Celery("cobrancas")
app.config_from_object("django.conf:settings", namespace="CELERY")
app.autodiscover_tasks()

app.conf.task_default_queue = "padrao"
app.conf.task_routes = {
    "cobrancas.gerar_em_lote": {"queue": "lotes"},
    "cobrancas.marcar_vencidas": {"queue": "padrao"},
    "clientes.importar_planilha": {"queue": "lotes"},
    "bancos.montar_remessa": {"queue": "lotes"},
    "bancos.enviar_remessa": {"queue": "lotes"},
    "bancos.processar_retorno": {"queue": "retorno"},
    "bancos.varrer_retornos": {"queue": "retorno"},
    "bancos.reprocessar_presos": {"queue": "retorno"},
}


@setup_logging.connect
def _usar_logging_do_django(**_kwargs):
    """Sem isto o Celery instala o próprio logging e o LOGGING do settings
    passa a valer só para o gunicorn — os dois processos passam a escrever em
    formatos diferentes e o `docker compose logs` fica ilegível."""
    from logging.config import dictConfig

    from django.conf import settings

    dictConfig(settings.LOGGING)
