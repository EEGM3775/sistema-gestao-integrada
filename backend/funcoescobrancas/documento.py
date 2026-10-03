"""O PDF do boleto dentro da tela — buscado pela nossa máquina (item 56 do dono).

Depois de gerar a cobrança, a tela lateral não mostrava o boleto: só um link
para o Asaas numa aba nova. Mostrar o PDF dentro do SGI (miniatura e leitor)
esbarra em duas coisas do navegador: o Asaas é outra origem, e o
`frame-src` da nossa CSP não o admite. Por isso o PDF passa pelo backend.

**Buscar URL de terceiro pelo servidor é SSRF, se deixar.** A URL vem do
retorno do Asaas gravado no boleto, não do usuário, mas mesmo assim só sai daqui
para `https://` num host do Asaas, com teto de tamanho cortado **durante** o
download e relógio — os dois números moram em `payment/planos.py` (§5.5s).
"""
from __future__ import annotations

import hashlib
import io
import logging
from urllib.parse import urlparse

import requests
from django.core.cache import cache

from payment.planos import ERP_BOLETO_PDF_SEGUNDOS, ERP_BOLETO_PDF_TETO_MB

logger = logging.getLogger(__name__)

HOSTS_DO_ASAAS = ("asaas.com",)
MB = 1024 * 1024
# A miniatura é derivada de um PDF imutável (mudou o boleto, muda a URL) — o
# cache é desempenho, não limite de uso (§5.6 do planos.py).
CACHE_MINIATURA_S = 24 * 3600


class DocumentoIndisponivel(Exception):
    """O PDF não pôde ser trazido. `mensagem` é para quem está na tela."""

    def __init__(self, mensagem: str):
        super().__init__(mensagem)
        self.mensagem = mensagem


def url_permitida(url: str) -> bool:
    try:
        partes = urlparse(url or "")
    except ValueError:
        return False
    host = (partes.hostname or "").lower()
    return partes.scheme == "https" and any(
        host == h or host.endswith(f".{h}") for h in HOSTS_DO_ASAAS
    )


def baixar_pdf(url: str) -> bytes:
    if not url_permitida(url):
        raise DocumentoIndisponivel("O boleto não tem um PDF do Asaas para mostrar aqui. Abra pelo link.")
    teto = ERP_BOLETO_PDF_TETO_MB * MB
    try:
        with requests.get(url, stream=True, timeout=ERP_BOLETO_PDF_SEGUNDOS, allow_redirects=False) as resp:
            if resp.status_code != 200:
                raise DocumentoIndisponivel("O Asaas não entregou o PDF agora. Tente de novo em instantes.")
            partes, total = [], 0
            for bloco in resp.iter_content(64 * 1024):
                total += len(bloco)
                if total > teto:
                    raise DocumentoIndisponivel("O PDF do boleto é maior do que o esperado. Abra pelo link do Asaas.")
                partes.append(bloco)
    except requests.RequestException as exc:
        logger.warning("Falha ao buscar o PDF do boleto no Asaas: %s", exc)
        raise DocumentoIndisponivel("O Asaas não respondeu. Tente de novo em instantes.") from exc
    conteudo = b"".join(partes)
    if not conteudo.startswith(b"%PDF"):
        # O `invoiceUrl` é a página da fatura, não o PDF — acontece com PIX/cartão.
        raise DocumentoIndisponivel("Esta cobrança não tem boleto em PDF. Abra a fatura pelo link do Asaas.")
    return conteudo


def miniatura_de_pdf(conteudo: bytes, largura: int = 480) -> bytes:
    """A primeira página de um PDF como PNG."""
    try:
        import pypdfium2
    except ImportError as exc:  # imagem sem o rasterizador: o leitor segue funcionando
        raise DocumentoIndisponivel("A miniatura não está disponível neste servidor.") from exc
    documento = pypdfium2.PdfDocument(conteudo)
    try:
        pagina = documento[0]
        escala = largura / pagina.get_width()
        imagem = pagina.render(scale=escala).to_pil()
        saida = io.BytesIO()
        imagem.save(saida, format="PNG", optimize=True)
    finally:
        documento.close()
    return saida.getvalue()


def miniatura_png(url: str, largura: int = 480) -> bytes:
    """A miniatura do boleto do Asaas — a tela lateral a pede a cada abertura."""
    chave = f"boleto:miniatura:{hashlib.sha256(url.encode()).hexdigest()[:32]}:{largura}"
    guardada = cache.get(chave)
    if guardada:
        return guardada
    png = miniatura_de_pdf(baixar_pdf(url), largura)
    cache.set(chave, png, CACHE_MINIATURA_S)
    return png
