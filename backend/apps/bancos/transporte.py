"""Transporte de arquivo: SFTP e diretório local.

Separado do adapter de propósito. "Como se monta o CNAB do Safra" e "como o
arquivo chega ao Safra" mudam por motivos diferentes e em ritmos diferentes: o
layout muda quando o banco publica um manual novo, o transporte muda quando o
cliente troca de convênio ou o time de TI dele abre um SFTP. Juntos, uma
mudança de credencial exigiria mexer no código que monta boleto.

Dois caminhos, e o segundo é o comum:

* **SFTP** — o banco fornece host, usuário e diretórios. Automático de ponta a
  ponta: o worker envia a remessa e varre o diretório de retorno sozinho.
* **Diretório local** — um volume que alguém alimenta (script do cliente,
  rclone, montagem de rede). Serve para quem ainda baixa o retorno à mão do
  internet banking e só quer que o sistema o processe sem upload manual.

Quem não tem nenhum dos dois continua funcionando: gera a remessa, baixa pelo
painel, e sobe o retorno pela tela. É o fluxo da maioria das empresas, e não é
um fluxo degradado.
"""
from __future__ import annotations

import logging
from pathlib import Path

from django.conf import settings

from apps.bancos.adapters.base import ErroDeIntegracao

logger = logging.getLogger(__name__)

#: Extensões que valem como retorno num diretório. Evita processar o `.tmp`
#: que o cliente SFTP do banco ainda está escrevendo — arquivo pela metade
#: viraria "500 títulos, 300 processados" e um reprocessamento desnecessário.
EXTENSOES_RETORNO = {".ret", ".txt", ".crt", ".rem"}


def _paramiko():
    try:
        import paramiko  # noqa: PLC0415
    except ImportError as exc:  # pragma: no cover - depende do ambiente
        raise ErroDeIntegracao(
            "Transmissão por SFTP pedida, mas o pacote `paramiko` não está "
            "instalado nesta imagem. Instale-o ou desative o SFTP na conta."
        ) from exc
    return paramiko


def _conectar(conta):
    paramiko = _paramiko()
    cliente = paramiko.SSHClient()
    # A chave do host é confiada na primeira conexão. Num ambiente de
    # produção com o banco, o correto é fixar a chave conhecida — deixado
    # explícito aqui porque a alternativa silenciosa (`AutoAddPolicy` sem
    # comentário) esconde uma decisão de segurança real.
    cliente.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    try:
        cliente.connect(
            hostname=conta.sftp_host,
            port=conta.sftp_porta or 22,
            username=conta.sftp_usuario,
            password=conta.sftp_senha or None,
            timeout=30,
            allow_agent=False,
            look_for_keys=False,
        )
    except Exception as exc:  # noqa: BLE001
        raise ErroDeIntegracao(
            f"Não foi possível conectar ao SFTP do banco ({conta.sftp_host}): {exc}"
        ) from exc
    return cliente


def enviar_sftp(conta, conteudo: bytes, nome_arquivo: str) -> str:
    """Envia a remessa. Devolve o caminho remoto, que serve de protocolo.

    Escreve com nome temporário e só então renomeia: se o banco varrer o
    diretório no meio da transferência, ele encontraria um arquivo truncado e
    o rejeitaria — com o agravante de que o NSA já foi consumido e o reenvio
    precisa de um número novo.
    """
    cliente = _conectar(conta)
    try:
        sftp = cliente.open_sftp()
        destino = f"{(conta.sftp_dir_remessa or '.').rstrip('/')}/{nome_arquivo}"
        temporario = f"{destino}.parcial"
        with sftp.open(temporario, "wb") as remoto:
            remoto.write(conteudo)
        sftp.rename(temporario, destino)
        logger.info("Remessa enviada por SFTP: %s", destino)
        return destino
    except ErroDeIntegracao:
        raise
    except Exception as exc:  # noqa: BLE001
        raise ErroDeIntegracao(f"Falha ao enviar a remessa por SFTP: {exc}") from exc
    finally:
        cliente.close()


def baixar_sftp(conta) -> list[tuple[str, bytes]]:
    """Baixa os retornos disponíveis. Não apaga nada do servidor do banco.

    Apagar seria a forma óbvia de não reprocessar, e é a errada: se o
    processamento falhar aqui, o arquivo já não existiria mais lá e o
    movimento do dia estaria perdido. Quem evita reprocessar é o hash
    (`ArquivoBancario.hash_arquivo`), que decide pelo conteúdo.
    """
    cliente = _conectar(conta)
    try:
        sftp = cliente.open_sftp()
        diretorio = (conta.sftp_dir_retorno or ".").rstrip("/")
        arquivos = []
        for nome in sftp.listdir(diretorio):
            if Path(nome).suffix.lower() not in EXTENSOES_RETORNO:
                continue
            with sftp.open(f"{diretorio}/{nome}", "rb") as remoto:
                arquivos.append((nome, remoto.read()))
        logger.info("SFTP %s: %d arquivo(s) de retorno", conta.sftp_host, len(arquivos))
        return arquivos
    except ErroDeIntegracao:
        raise
    except Exception as exc:  # noqa: BLE001
        raise ErroDeIntegracao(f"Falha ao ler o diretório de retorno: {exc}") from exc
    finally:
        cliente.close()


# ------------------------------------------------------------ diretório local
def ler_diretorio_entrada() -> list[tuple[str, bytes]]:
    """Retornos deixados no volume de entrada por qualquer meio.

    Move o que leu para `processados/`, e é aqui que mover é seguro: o arquivo
    continua no disco, só sai do caminho da varredura. O hash ainda protege
    contra reprocessar se alguém devolvê-lo.
    """
    entrada: Path = settings.BANCO_DIR_ENTRADA
    if not entrada.exists():
        return []
    processados = entrada / "processados"
    processados.mkdir(parents=True, exist_ok=True)

    arquivos = []
    for caminho in sorted(entrada.iterdir()):
        if not caminho.is_file() or caminho.suffix.lower() not in EXTENSOES_RETORNO:
            continue
        try:
            arquivos.append((caminho.name, caminho.read_bytes()))
            caminho.rename(processados / caminho.name)
        except OSError as exc:
            logger.warning("Retorno %s não pôde ser lido: %s", caminho, exc)
    return arquivos


def gravar_diretorio_saida(nome_arquivo: str, conteudo: bytes) -> str:
    """Deixa a remessa num volume, para quem transmite por fora."""
    saida: Path = settings.BANCO_DIR_SAIDA
    saida.mkdir(parents=True, exist_ok=True)
    destino = saida / nome_arquivo
    destino.write_bytes(conteudo)
    return str(destino)
