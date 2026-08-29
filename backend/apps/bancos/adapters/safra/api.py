"""Banco Safra — API REST de cobrança.

ESTADO: encanamento pronto, contrato de payload pendente.

O que já funciona e é real: autenticação OAuth2 `client_credentials`, mTLS com
o certificado guardado cifrado na conta, cache do token, repetição com recuo
exponencial nos erros que valem repetir, e o registro em lote quebrado em
blocos. Nada disso depende do desenho dos campos e não muda quando ele chegar.

O que falta: o **mapeamento dos campos** de `Titulo` para o corpo JSON que o
Safra espera, e a leitura da resposta. Isso não se adivinha — depende da
versão do contrato e do produto de cobrança, e um palpite geraria requisições
que o banco recusa com 400 sem dizer o quê, ou pior, registra com valor no
campo errado. Os dois pontos estão isolados em `_montar_payload` e
`_ler_resposta`; preencher os dois com a documentação do convênio na mão
coloca o adapter inteiro em pé, e o resto do sistema não fica sabendo.

Enquanto isso, o adapter existe e é escolhível: uma conta configurada como API
levanta um erro que diz exatamente o que falta, em vez de falhar em algum
ponto obscuro. E o boleto — código de barras e linha digitável — já sai daqui,
porque essa parte é aritmética local e não depende do banco responder.
"""
from __future__ import annotations

import logging
import time
from typing import Iterable

from django.core.cache import cache

from apps.bancos.adapters import registrar
from apps.bancos.adapters.base import (
    ErroDeIntegracao,
    OperacaoNaoSuportada,
    ResultadoLote,
    ResultadoTitulo,
    Retorno,
    Titulo,
)
from apps.bancos.adapters.safra.adapter import SafraCnab400
from apps.bancos.bancos import MeioDeIntegracao

logger = logging.getLogger(__name__)

URL_BASE = {
    True: "https://api.safra.com.br",
    False: "https://api-hml.safra.com.br",
}

#: Erros que valem repetir: instabilidade e limite de taxa. 4xx de negócio
#: não entra — repetir um "título duplicado" só multiplica o problema.
STATUS_REPETIVEIS = {408, 425, 429, 500, 502, 503, 504}
TENTATIVAS = 3
#: Lote grande vai em blocos: nenhuma API aceita 20 mil títulos num POST, e um
#: erro no meio de um bloco grande obriga a refazer trabalho demais.
TAMANHO_BLOCO = 100


@registrar
class SafraApi(SafraCnab400):
    """Herda do adapter CNAB o que é aritmética local (boleto, campo livre) e
    troca o que fala com o banco. A herança é a expressão exata da relação:
    são o mesmo banco, com o mesmo cálculo de nosso número e o mesmo código de
    barras, por dois canais diferentes."""

    codigo_banco = "422"
    nome = "Banco Safra — API"
    meios = (MeioDeIntegracao.API,)

    # ───────────────────────────────────────────────────────── autenticação
    @property
    def url_base(self) -> str:
        return URL_BASE[bool(self.conta.producao)]

    def _token(self) -> str:
        """Token OAuth2, guardado em cache até pouco antes de expirar.

        A margem de 60 segundos existe porque o token que vale "agora" pode não
        valer quando a requisição chegar ao banco — e um 401 no meio de um
        lote de 500 títulos é caro de desfazer.
        """
        chave = f"safra:token:{self.conta.pk}"
        token = cache.get(chave)
        if token:
            return token

        if not (self.conta.api_client_id and self.conta.api_client_secret):
            raise ErroDeIntegracao(
                "A conta está configurada para API, mas não tem client_id e "
                "client_secret cadastrados. Cadastre-os em Contas bancárias."
            )

        resposta = self._requisitar(
            "POST", "/oauth2/token",
            dados={
                "grant_type": "client_credentials",
                "client_id": self.conta.api_client_id,
                "client_secret": self.conta.api_client_secret,
            },
            autenticado=False,
        )
        token = resposta.get("access_token")
        if not token:
            raise ErroDeIntegracao("O banco não devolveu access_token.", detalhes=resposta)
        expira = int(resposta.get("expires_in", 300))
        cache.set(chave, token, max(30, expira - 60))
        return token

    def _certificado(self):
        """Certificado mTLS gravado em arquivo temporário durante a chamada.

        O `requests` só aceita caminho de arquivo, não bytes — daí o temporário.
        Ele vive o tempo da requisição e é apagado no `finally`; o material
        cifrado continua sendo o do banco de dados, e nunca há uma cópia
        permanente em claro no disco.
        """
        import os
        import tempfile
        from contextlib import contextmanager

        @contextmanager
        def contexto():
            if not (self.conta.api_certificado and self.conta.api_chave_privada):
                yield None
                return
            arquivos = []
            try:
                for conteudo in (self.conta.api_certificado, self.conta.api_chave_privada):
                    fd, caminho = tempfile.mkstemp(suffix=".pem")
                    with os.fdopen(fd, "w") as saida:
                        saida.write(conteudo)
                    os.chmod(caminho, 0o600)
                    arquivos.append(caminho)
                yield tuple(arquivos)
            finally:
                for caminho in arquivos:
                    try:
                        os.remove(caminho)
                    except OSError:
                        logger.warning("Certificado temporário não removido: %s", caminho)

        return contexto()

    def _requisitar(self, metodo: str, caminho: str, *, dados=None, json=None,
                    autenticado: bool = True) -> dict:
        import requests

        url = f"{self.url_base}{caminho}"
        cabecalhos = {"Accept": "application/json"}
        if autenticado:
            cabecalhos["Authorization"] = f"Bearer {self._token()}"

        ultimo_erro = None
        with self._certificado() as cert:
            for tentativa in range(1, TENTATIVAS + 1):
                try:
                    resposta = requests.request(
                        metodo, url, data=dados, json=json,
                        headers=cabecalhos, cert=cert, timeout=(10, 60),
                    )
                except requests.RequestException as exc:
                    ultimo_erro = str(exc)
                else:
                    if resposta.status_code < 400:
                        return resposta.json() if resposta.content else {}
                    ultimo_erro = f"HTTP {resposta.status_code}: {resposta.text[:400]}"
                    if resposta.status_code not in STATUS_REPETIVEIS:
                        raise ErroDeIntegracao(
                            f"O banco recusou a requisição. {ultimo_erro}",
                            detalhes={"status": resposta.status_code, "url": caminho},
                        )
                if tentativa < TENTATIVAS:
                    # Recuo exponencial: 1s, 2s. Sem jitter porque as chamadas
                    # já saem serializadas de um worker só por conta.
                    time.sleep(2 ** (tentativa - 1))

        raise ErroDeIntegracao(
            f"O banco não respondeu depois de {TENTATIVAS} tentativas. {ultimo_erro}"
        )

    # ─────────────────────────────────────────────────────────── registro
    def registrar_cobrancas_em_lote(self, titulos: Iterable[Titulo]) -> ResultadoLote:
        titulos = list(titulos)
        resultados: list[ResultadoTitulo] = []

        for inicio in range(0, len(titulos), TAMANHO_BLOCO):
            bloco = titulos[inicio:inicio + TAMANHO_BLOCO]
            corpo = {"titulos": [self._montar_payload(t) for t in bloco]}
            resposta = self._requisitar("POST", "/cobranca/v1/boletos/lote", json=corpo)
            resultados.extend(self._ler_resposta(bloco, resposta))

        return ResultadoLote(resultados=resultados, protocolo=str(resultados and "" or ""))

    def _montar_payload(self, titulo: Titulo) -> dict:
        """PENDENTE — mapeamento dos campos, a preencher com o manual da API.

        Deliberadamente não implementado: um palpite aqui produz requisições
        que o banco aceita com o valor no campo errado, e isso não aparece em
        teste nenhum — aparece no extrato do cliente.
        """
        raise OperacaoNaoSuportada(
            "A integração por API do Safra ainda não tem o mapeamento de campos "
            "definido. Use CNAB 400 nesta conta, ou preencha `_montar_payload` "
            "e `_ler_resposta` com a documentação do convênio "
            "(apps/bancos/adapters/safra/api.py)."
        )

    def _ler_resposta(self, bloco: list[Titulo], resposta: dict) -> list[ResultadoTitulo]:
        """PENDENTE — leitura da resposta, par de `_montar_payload`."""
        raise OperacaoNaoSuportada(
            "Leitura da resposta da API do Safra ainda não definida."
        )

    # ──────────────────────────────────────────────────────────── retorno
    def processar_retorno(self, conteudo: bytes) -> Retorno:
        """Mesmo em conta de API, o retorno costuma continuar chegando em
        arquivo — o extrato de cobrança do Safra é CNAB. Reaproveitar o parser
        do adapter CNAB é o comportamento certo, não um atalho."""
        return super().processar_retorno(conteudo)

    def obter_retornos(self) -> list[tuple[str, bytes]]:
        # Sem SFTP, a conta de API busca movimento pela própria API — o que
        # depende do mesmo contrato pendente acima.
        return super().obter_retornos()

    def transmitir(self, conteudo: bytes, nome_arquivo: str) -> str:
        raise OperacaoNaoSuportada(
            "Conta de API não transmite arquivo: os títulos são registrados "
            "por requisição."
        )
