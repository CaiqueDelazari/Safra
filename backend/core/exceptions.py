import logging

from django.core.exceptions import ValidationError as DjangoValidationError
from django.db import IntegrityError
from rest_framework import status
from rest_framework.response import Response
from rest_framework.views import exception_handler

from core.services import RegraDeNegocioError

logger = logging.getLogger(__name__)


def api_exception_handler(exc, context):
    if isinstance(exc, RegraDeNegocioError):
        corpo = {"detail": exc.mensagem, "codigo": "regra_de_negocio"}
        if exc.campo:
            corpo["campo"] = exc.campo
        return Response(corpo, status=status.HTTP_422_UNPROCESSABLE_ENTITY)

    if isinstance(exc, DjangoValidationError):
        return Response(
            {"detail": exc.messages, "codigo": "validacao"},
            status=status.HTTP_400_BAD_REQUEST,
        )

    if isinstance(exc, IntegrityError):
        logger.warning("IntegrityError: %s", exc)
        return Response(
            {"detail": "Operação viola uma restrição de integridade.", "codigo": "integridade"},
            status=status.HTTP_409_CONFLICT,
        )

    resposta = exception_handler(exc, context)
    if resposta is None:
        logger.exception("Erro não tratado", exc_info=exc)
        return Response(
            {"detail": "Erro interno.", "codigo": "erro_interno"},
            status=status.HTTP_500_INTERNAL_SERVER_ERROR,
        )
    return resposta
