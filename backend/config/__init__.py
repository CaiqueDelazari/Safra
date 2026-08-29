# O app Celery precisa existir no import do pacote de configuração: é assim
# que `@shared_task` encontra o broker sem cada módulo importar `app`.
from config.celery import app as celery_app

__all__ = ("celery_app",)
