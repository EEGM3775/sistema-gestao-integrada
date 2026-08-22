# backend/moduloprancheta/motores/documento.py
"""Motor `pdf_nativo` — PDF e imagem, os formatos que o browser já abre.

**Este motor não converte para visualizar: converte para a lista.** O PDF é
servido como está (é isso que "render nativo do browser" quer dizer em
`formatos.py`), e a imagem também. O que falta nos dois é a **miniatura** — sem
ela o acervo de uma obra é uma lista de nomes de arquivo, e "achar a prancha
certa" volta a ser abrir uma por uma, que é exatamente o que o módulo existe
para acabar.

Por isso `tipos = (MINIATURA,)` e nada mais. Gerar um `vetor_2d` de um PDF seria
converter para pior: o PDF já é vetor, e rasterizá-lo em SVG perderia o texto
selecionável que o canteiro usa para conferir cota.
"""
from __future__ import annotations

import io

from payment.planos import PRANCHETA_LADO_MINIATURA_PX

from .base import (
    NAO_EMBRULHAR,
    Adaptador,
    ArquivoCorrompido,
    MotorIndisponivel,
    Saida,
)

# Lado maior da miniatura. 600 px cabe num card de acervo em tela retina sem
# virar download: o objetivo é reconhecer a prancha, não ler a cota — para ler,
# abre-se o arquivo, que continua lá.
LADO_MINIATURA = PRANCHETA_LADO_MINIATURA_PX


class MotorDocumento(Adaptador):
    codigo = "pdf_nativo"
    tipos = ("miniatura",)

    def _detectar_versao(self) -> str:
        """Versão do Pillow — o denominador comum dos dois caminhos.

        A miniatura de PDF precisa também do `pypdfium2`, mas a ausência dele não
        torna o motor inteiro indisponível: imagem continua funcionando. Quem
        reporta essa metade é o `converter`, no formato em que ela falta.
        """
        try:
            from PIL import __version__ as pillow_versao
        except Exception:
            return ""
        return f"pillow-{pillow_versao}"

    def converter(self, caminho: str, *, formato: str, tipo: str, economia: str = "",
                  teto_snap: int | None = 0, retomada=None, prazo=None) -> Saida:
        # `retomada`/`prazo` ignorados: `retomavel = False` (PRA.11). Este motor
        # converte numa unidade indivisível, e o pipeline nunca lhe manda outra
        # coisa que não `None` — declarar o contrário faria uma volta à fila
        # refazer exatamente o mesmo trabalho para chegar ao mesmo estouro.
        # `economia` ignorado: este motor não declara nenhuma (`economias`
        # vazio), então o pipeline nunca lhe manda outra coisa que não `""`.
        if formato == "pdf":
            imagem = self._primeira_pagina_do_pdf(caminho)
        else:
            imagem = self._abrir_imagem(caminho)
        return self._miniatura(imagem)

    # -- caminhos por formato ------------------------------------------------
    def _primeira_pagina_do_pdf(self, caminho: str):
        """Primeira página rasterizada, via PDFium.

        `pypdfium2` e não o `pdfplumber` que já está no `requirements`: aquele
        entrou para **extrair tabela** de PDF de prefeitura (ORC.5b) e o
        rasterizador dele é justamente um wrapper do PDFium. Chamar o PDFium
        direto tira uma camada do caminho quente e não acrescenta dependência
        conceitual nova.
        """
        try:
            import pypdfium2
        except Exception as exc:
            raise MotorIndisponivel(
                "O rasterizador de PDF (pypdfium2) não está instalado nesta imagem."
            ) from exc

        try:
            documento = pypdfium2.PdfDocument(caminho)
            if len(documento) == 0:
                raise ArquivoCorrompido("O PDF não tem nenhuma página.")
            pagina = documento[0]
            # `scale` em pontos→pixels. 2 dá ~144 dpi: nítido o bastante para a
            # miniatura e barato o bastante para uma prancha A0.
            return pagina.render(scale=2).to_pil()
        except NAO_EMBRULHAR:
            # O teto agindo, ou falha já classificada — ver `NAO_EMBRULHAR`. Uma
            # prancha A0 rasterizada a 144 dpi é da ordem de 100 MP em RGBA, e é
            # o cliente quem escolhe o tamanho da folha: este `render` é o ponto
            # deste motor que aloca proporcionalmente ao arquivo de entrada.
            raise
        except Exception as exc:
            raise ArquivoCorrompido(f"PDF ilegível: {exc}") from exc

    def _abrir_imagem(self, caminho: str):
        try:
            from PIL import Image
        except Exception as exc:  # pragma: no cover - Pillow é dependência dura
            raise MotorIndisponivel("Pillow não está instalado.") from exc

        try:
            imagem = Image.open(caminho)
            imagem.load()
            return imagem
        except NAO_EMBRULHAR:
            # `Image.open` só lê o cabeçalho; quem aloca é o `load()`, e ele
            # aloca pelas dimensões **declaradas** no arquivo. O `MAX_IMAGE_PIXELS`
            # do Pillow barra a bomba de descompressão clássica e o que sobra é
            # o teto do D57 — que é nosso, e não "imagem ilegível".
            raise
        except Exception as exc:
            raise ArquivoCorrompido(f"Imagem ilegível: {exc}") from exc

    # -- saída ---------------------------------------------------------------
    def _miniatura(self, imagem) -> Saida:
        return miniatura(imagem)


def miniatura(imagem, **detalhe) -> Saida:
    """Uma imagem PIL vira a miniatura padrão do acervo.

    Módulo-nível e não método porque a PRA.1b lhe deu um segundo dono: o
    `MotorDwg` extrai com o `dwgbmp` o raster que o CAD gravou dentro do DWG
    (planta §4.4) e precisa exatamente deste encolhimento — mesmo lado, mesmo
    JPEG, mesmo card. Duas implementações dariam dois tamanhos de cartão.
    """
    from PIL import Image

    # `RGB` antes do thumbnail: PNG com alfa e PDF renderizado vêm em RGBA, e
    # o JPEG não tem canal alfa — salvar direto explodiria em OSError.
    if imagem.mode not in ("RGB", "L"):
        fundo = Image.new("RGB", imagem.size, "white")
        fundo.paste(imagem, mask=imagem.split()[-1] if "A" in imagem.mode else None)
        imagem = fundo

    imagem.thumbnail((LADO_MINIATURA, LADO_MINIATURA), Image.LANCZOS)
    buffer = io.BytesIO()
    imagem.save(buffer, format="JPEG", quality=82, optimize=True)
    return Saida(
        conteudo=buffer.getvalue(),
        extensao="jpg",
        content_type="image/jpeg",
        detalhe={"largura": imagem.width, "altura": imagem.height, **detalhe},
    )
