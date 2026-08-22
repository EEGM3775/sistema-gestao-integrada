#!/usr/bin/env python3
"""
Remove marca d'água de PDFs sem rasterizar a página.

Instalação:
    pip install pymupdf

Uso:
    # 1) Descobrir o que existe no PDF (SEMPRE comece por aqui)
    python remove_marca_dagua.py diagnostico entrada.pdf

    # 2) Remover, conforme o que o diagnóstico apontou:
    python remove_marca_dagua.py texto     entrada.pdf saida.pdf "RASCUNHO"
    python remove_marca_dagua.py xobject   entrada.pdf saida.pdf "Fm0"
    python remove_marca_dagua.py camada    entrada.pdf saida.pdf "Watermark"
    python remove_marca_dagua.py anotacoes entrada.pdf saida.pdf
    python remove_marca_dagua.py imagem    entrada.pdf saida.pdf 42
"""

import re
import sys

import fitz  # PyMuPDF


# ---------------------------------------------------------------- diagnóstico

def diagnostico(caminho):
    """Lista tudo que pode ser a marca d'água, página por página."""
    doc = fitz.open(caminho)
    print(f"{caminho}: {len(doc)} página(s)\n")

    ocgs = doc.get_ocgs()
    if ocgs:
        print("Camadas (OCG) do documento:")
        for xref, info in ocgs.items():
            print(f"  xref {xref}: nome={info.get('name')!r}")
        print()

    for n, page in enumerate(doc, start=1):
        print(f"--- Página {n} ---")

        for a in page.annots() or []:
            print(f"  ANOTAÇÃO: tipo={a.type[1]} conteudo={a.info.get('content')!r}")

        for xo in page.get_xobjects():
            # (xref, nome, tipo_invocador, bbox...)
            print(f"  XOBJECT: nome=/{xo[1]} xref={xo[0]}")

        for img in page.get_images(full=True):
            print(f"  IMAGEM: xref={img[0]} {img[2]}x{img[3]}px nome=/{img[7]}")

        # Texto que aparece rotacionado costuma ser marca d'água diagonal
        for bloco in page.get_text("dict")["blocks"]:
            for linha in bloco.get("lines", []):
                direcao = linha["dir"]
                if abs(direcao[1]) > 0.01:  # não é horizontal
                    txt = "".join(s["text"] for s in linha["spans"])
                    print(f"  TEXTO INCLINADO: {txt!r} dir={direcao}")
        print()

    doc.close()


# ------------------------------------------------- edição do fluxo de conteúdo

def _stream_da_pagina(page):
    """Consolida o conteúdo da página em um único stream e devolve (xref, bytes)."""
    page.clean_contents()
    xref = page.get_contents()[0]
    return xref, page.parent.xref_stream(xref)


def _sem_blocos_de_texto(data, alvo):
    """Remove blocos BT...ET que contenham o texto alvo."""
    alvo = alvo.encode("latin-1", "replace")
    saida, pos = bytearray(), 0
    for m in re.finditer(rb"BT\b.*?\bET", data, re.S):
        if alvo in m.group(0):
            saida += data[pos:m.start()]
            pos = m.end()
    saida += data[pos:]
    return bytes(saida)


def _sem_chamada_xobject(data, nome):
    """Remove as invocações '/Nome Do' e o bloco q...Q que as envolve."""
    nome = nome.lstrip("/").encode()
    chamada = rb"/" + re.escape(nome) + rb"\s+Do"
    data = re.sub(rb"q\b(?:(?!\bq\b).)*?" + chamada + rb".*?\bQ", b"", data, flags=re.S)
    return re.sub(chamada, b"", data)


def _sem_camada(data, nome):
    """Remove blocos de conteúdo marcado /OC ... BDC ... EMC."""
    nome = nome.lstrip("/").encode()
    padrao = rb"/OC\s*/" + re.escape(nome) + rb"\s*BDC.*?EMC"
    return re.sub(padrao, b"", data, flags=re.S)


def _aplicar(entrada, saida, transformacao):
    doc = fitz.open(entrada)
    alteradas = 0
    for page in doc:
        xref, data = _stream_da_pagina(page)
        novo = transformacao(data)
        if novo != data:
            doc.update_stream(xref, novo)
            alteradas += 1
    doc.save(saida, garbage=4, deflate=True, clean=True)
    doc.close()
    print(f"{alteradas} página(s) alterada(s) -> {saida}")


# ---------------------------------------------------------------- operações

def remover_texto(entrada, saida, texto):
    _aplicar(entrada, saida, lambda d: _sem_blocos_de_texto(d, texto))


def remover_xobject(entrada, saida, nome):
    _aplicar(entrada, saida, lambda d: _sem_chamada_xobject(d, nome))


def remover_camada(entrada, saida, nome):
    _aplicar(entrada, saida, lambda d: _sem_camada(d, nome))


def remover_anotacoes(entrada, saida):
    """Marcas inseridas como anotação (Watermark, Stamp, FreeText)."""
    doc = fitz.open(entrada)
    n = 0
    for page in doc:
        for a in list(page.annots() or []):
            if a.type[1] in ("Watermark", "Stamp", "FreeText"):
                page.delete_annot(a)
                n += 1
    doc.save(saida, garbage=4, deflate=True, clean=True)
    doc.close()
    print(f"{n} anotação(ões) removida(s) -> {saida}")


def remover_imagem(entrada, saida, xref):
    """Marca d'água que é uma imagem sobreposta (use o xref do diagnóstico)."""
    doc = fitz.open(entrada)
    for page in doc:
        if xref in [i[0] for i in page.get_images()]:
            page.delete_image(xref)
    doc.save(saida, garbage=4, deflate=True, clean=True)
    doc.close()
    print(f"Imagem xref={xref} removida -> {saida}")


# ---------------------------------------------------------------------- CLI

if __name__ == "__main__":
    args = sys.argv[1:]
    if not args:
        print(__doc__)
        sys.exit(1)

    cmd = args[0]
    try:
        if cmd == "diagnostico":
            diagnostico(args[1])
        elif cmd == "texto":
            remover_texto(args[1], args[2], args[3])
        elif cmd == "xobject":
            remover_xobject(args[1], args[2], args[3])
        elif cmd == "camada":
            remover_camada(args[1], args[2], args[3])
        elif cmd == "anotacoes":
            remover_anotacoes(args[1], args[2])
        elif cmd == "imagem":
            remover_imagem(args[1], args[2], int(args[3]))
        else:
            print(f"Comando desconhecido: {cmd}\n")
            print(__doc__)
            sys.exit(1)
    except IndexError:
        print("Argumentos faltando.\n")
        print(__doc__)
        sys.exit(1)
