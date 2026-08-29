"""Arquivos enviados: nome opaco na gravação, URL assinada na leitura.

Aqui trafega o que não pode circular solto: o arquivo de remessa, que carrega
a carteira de cobrança inteira da empresa — nome, documento, valor e
vencimento de cada sacado —, o arquivo de retorno, que carrega os pagamentos,
e o PDF do boleto, que carrega a linha digitável.

Duas medidas, uma para cada ponta:

* na gravação, o caminho é `banco/2026/08/<32 hexadecimais>.ret` — não há o
  que adivinhar, e o nome que o banco deu ao arquivo não vaza para a URL;
* na leitura, quem serve é a aplicação (`MidiaView`), e só com um token
  assinado pela `SECRET_KEY` que caduca. O link continua colável em `<img>` e
  em `<a href>`, que não sabem mandar cabeçalho `Authorization`.

O nome de origem do arquivo bancário não se perde: fica em
`ArquivoBancario.nome_original`, que é o que o operador reconhece na tela e o
que o suporte do banco pergunta.
"""
import os
import uuid
from pathlib import Path

from django.conf import settings
from django.core import signing
from django.http import Http404

SALT = "cobrancas.midia"

#: Só estes tipos são gravados e devolvidos. Fecha a porta para um arquivo que
#: o navegador pudesse interpretar como página (HTML, SVG com script).
IMAGENS = {".jpg": "image/jpeg", ".jpeg": "image/jpeg", ".png": "image/png",
           ".webp": "image/webp", ".gif": "image/gif"}

#: Documento gerado pelo sistema — hoje, o PDF do boleto. PDF e só PDF: é o
#: formato que todo mundo consegue abrir e que o navegador não executa.
DOCUMENTOS = {".pdf": "application/pdf"}

#: Arquivo bancário CNAB — texto de posição fixa. Servido como `text/plain`
#: para que o navegador baixe em vez de tentar renderizar, e nunca como
#: `application/octet-stream`, que em alguns clientes vira download executável.
ARQUIVOS_BANCARIOS = {
    ".rem": "text/plain", ".ret": "text/plain", ".txt": "text/plain",
    ".crt": "text/plain",
}

EXTENSOES = {**IMAGENS, **DOCUMENTOS, **ARQUIVOS_BANCARIOS}


def extensao_valida(nome: str) -> str:
    ext = Path(nome or "").suffix.lower()
    return ext if ext in EXTENSOES else ""


# ------------------------------------------------------------------ gravação
def _caminho(prefixo: str, filename: str, *, datado: bool, padrao: str = ".jpg") -> str:
    """Descarta o nome de origem: ele não acrescenta nada e entrega informação."""
    ext = extensao_valida(filename) or padrao
    if datado:
        from django.utils import timezone

        hoje = timezone.localdate()
        prefixo = f"{prefixo}/{hoje.year}/{hoje.month:02d}"
    return f"{prefixo}/{uuid.uuid4().hex}{ext}"


def upload_arquivo_banco(instance, filename: str) -> str:
    """Remessa e retorno. Datado: a pasta cresce alguns arquivos por dia."""
    return _caminho("banco", filename, datado=True, padrao=".txt")


def upload_boleto(instance, filename: str) -> str:
    """PDF do boleto. Documento de apresentação — nunca fonte da verdade do
    pagamento, que é a cobrança mais o retorno do banco (regra 22)."""
    return _caminho("boletos", filename, datado=True, padrao=".pdf")


def upload_importacao(instance, filename: str) -> str:
    """Planilha de importação de clientes/cobranças, guardada para auditoria:
    quando a carga entra torta, a pergunta é sempre \"o que exatamente foi
    enviado?\"."""
    return _caminho("importacoes", filename, datado=True, padrao=".csv")


def upload_logo_empresa(instance, filename: str) -> str:
    return _caminho("empresas/logos", filename, datado=False)


def upload_avatar_usuario(instance, filename: str) -> str:
    return _caminho("usuarios/avatares", filename, datado=False)


# -------------------------------------------------------------------- leitura
def url_assinada(arquivo, request=None) -> str | None:
    """Endereço temporário do arquivo. `None` quando não há arquivo."""
    nome = getattr(arquivo, "name", "") or ""
    if not nome:
        return None
    token = signing.dumps(nome, salt=SALT, compress=True)
    caminho = f"/api/v1/midia/{token}/"
    if request is not None:
        return request.build_absolute_uri(caminho)
    # Sem request no contexto, um endereço relativo apontaria para o domínio do
    # painel, que não serve a API. `URL_API` fecha esse buraco em produção.
    base = (settings.URL_API or "").rstrip("/")
    return f"{base}{caminho}" if base else caminho


def resolver_caminho(nome: str) -> str:
    """Confere que o caminho assinado continua dentro de MEDIA_ROOT.

    A assinatura já impediria forjar `../../etc/passwd`, mas um token antigo
    emitido por uma versão anterior desta função não impediria — e o custo de
    conferir é um `realpath`.
    """
    raiz = os.path.realpath(settings.MEDIA_ROOT)
    alvo = os.path.realpath(os.path.join(raiz, nome))
    if not (alvo == raiz or alvo.startswith(raiz + os.sep)):
        raise Http404("Arquivo fora do diretório de mídia.")
    if not extensao_valida(alvo) or not os.path.isfile(alvo):
        raise Http404("Arquivo não encontrado.")
    return alvo


def abrir(token: str) -> str:
    """Valida o token e devolve o caminho absoluto do arquivo."""
    try:
        nome = signing.loads(token, salt=SALT,
                             max_age=settings.MIDIA_URL_VALIDADE_SEGUNDOS)
    except signing.SignatureExpired:
        raise Http404("Link expirado.")
    except signing.BadSignature:
        raise Http404("Link inválido.")
    return resolver_caminho(nome)
