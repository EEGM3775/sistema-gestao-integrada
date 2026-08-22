"""Amostras de arquivo de projeto para o E2E da Prancheta (PRA.8).

**Por que elas moram aqui, e não em `backend/media/amostras_prancheta/`:** aquele
diretório está sob `media/`, que o `.gitignore` exclui inteiro (linha 115) — as
amostras que provaram os quatro motores em 31/07 existem só na máquina que as
gerou e dentro da imagem do backend. Um E2E que dependesse delas passaria aqui e
falharia em clone limpo, no CI e na máquina do próximo. Então o teste carrega as
próprias.

Três das quatro são **escritas à mão**, em texto, e isso é de propósito: uma
amostra legível é documentação do que o motor precisa receber, e quem for
depurar uma conversão consegue olhar o arquivo em vez de decodificar um blob.

O **DWG é a exceção** e não tem como não ser: é binário, e o único caminho de
escrita (`dxf2dwg`, do LibreDWG) vive no *build stage* do Dockerfile — a imagem
de runtime carrega só o `dwg2dxf`, o decodificador. Então ele viaja comprimido em
base64, gerado a partir da amostra `AC1015` (R2000) que a PRA.1 usou para provar
o motor. Vale o incômodo: é o formato dominante da construtora brasileira e o
único cujo motor exigiu compilar código de terceiro na imagem (o **D33**), o que
o torna o mais frágil a uma mudança de build — e portanto o que mais precisa de
um teste que rode sozinho.
"""
from __future__ import annotations

import base64
import zlib

# ---------------------------------------------------------------------------
# A planta: um cômodo de 8 × 5 m com um vão de porta de 0,9 m e uma divisória.
# É a MESMA geometria nos três formatos 2D — o que permite comparar as derivadas
# entre motores sem que a diferença de desenho polua a comparação.
# ---------------------------------------------------------------------------
PAREDES = [
    ((0.0, 0.0), (8.0, 0.0)),
    ((8.0, 0.0), (8.0, 5.0)),
    ((8.0, 5.0), (0.0, 5.0)),
    ((0.0, 5.0), (0.0, 3.5)),   # vão da porta entre y=2,6 e y=3,5
    ((0.0, 2.6), (0.0, 0.0)),
    ((5.0, 0.0), (5.0, 3.2)),   # divisória interna
]


# ---------------------------------------------------------------------------
# PDF — o formato mais comum do canteiro. O motor não o converte para ler: ele
# abre nativo no browser, e a derivada é só a miniatura do card do acervo.
# ---------------------------------------------------------------------------
def _pdf() -> bytes:
    """PDF 1.4 de uma página, com a planta em traço vetorial.

    Montado com os offsets da tabela `xref` **calculados**, e não escritos à mão:
    um byte a mais em qualquer objeto invalidaria a tabela, e o PDFium recusaria
    o arquivo com um erro que pareceria defeito do motor.
    """
    escala, base_x, base_y = 40, 60, 60  # 1 m = 40 pt, folha A4 paisagem
    traços = ["1 w", "0 0 0 RG"]
    for (x1, y1), (x2, y2) in PAREDES:
        traços.append(
            f"{base_x + x1 * escala:.1f} {base_y + y1 * escala:.1f} m "
            f"{base_x + x2 * escala:.1f} {base_y + y2 * escala:.1f} l S"
        )
    traços.append("BT /F1 10 Tf 60 300 Td (AMOSTRA PRANCHETA - PRA.8) Tj ET")
    fluxo = "\n".join(traços).encode("latin-1")

    objetos = [
        b"<< /Type /Catalog /Pages 2 0 R >>",
        b"<< /Type /Pages /Kids [3 0 R] /Count 1 >>",
        b"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 595 421] "
        b"/Resources << /Font << /F1 5 0 R >> >> /Contents 4 0 R >>",
        b"<< /Length " + str(len(fluxo)).encode() + b" >>\nstream\n" + fluxo + b"\nendstream",
        b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>",
    ]

    saida = bytearray(b"%PDF-1.4\n")
    offsets = []
    for numero, corpo in enumerate(objetos, start=1):
        offsets.append(len(saida))
        saida += f"{numero} 0 obj\n".encode() + corpo + b"\nendobj\n"

    inicio_xref = len(saida)
    saida += f"xref\n0 {len(objetos) + 1}\n".encode()
    saida += b"0000000000 65535 f \n"
    for offset in offsets:
        saida += f"{offset:010d} 00000 n \n".encode()
    saida += (
        f"trailer\n<< /Size {len(objetos) + 1} /Root 1 0 R >>\n"
        f"startxref\n{inicio_xref}\n%%EOF\n"
    ).encode()
    return bytes(saida)


# ---------------------------------------------------------------------------
# DXF — o motor livre sem asterisco (`ezdxf`, MIT, Python puro). R12 ASCII: o
# dialeto mais antigo e mais tolerante, e o que qualquer exportador escreve.
# ---------------------------------------------------------------------------
def _dxf() -> bytes:
    linhas = [
        "0", "SECTION", "2", "HEADER",
        "9", "$ACADVER", "1", "AC1009",
        "9", "$INSBASE", "10", "0.0", "20", "0.0", "30", "0.0",
        "9", "$EXTMIN", "10", "0.0", "20", "0.0", "30", "0.0",
        "9", "$EXTMAX", "10", "8.0", "20", "5.0", "30", "0.0",
        "0", "ENDSEC",
        "0", "SECTION", "2", "ENTITIES",
    ]
    for (x1, y1), (x2, y2) in PAREDES:
        linhas += [
            "0", "LINE", "8", "PAREDE",
            "10", f"{x1}", "20", f"{y1}", "30", "0.0",
            "11", f"{x2}", "21", f"{y2}", "31", "0.0",
        ]
    # Eixo, para a derivada ter mais de uma camada a desenhar.
    linhas += [
        "0", "LINE", "8", "EIXO",
        "10", "-0.5", "20", "2.5", "30", "0.0",
        "11", "8.5", "21", "2.5", "31", "0.0",
    ]
    linhas += ["0", "ENDSEC", "0", "EOF"]
    return ("\r\n".join(linhas) + "\r\n").encode("ascii")


# ---------------------------------------------------------------------------
# IFC — o 3D livre (IfcOpenShell, LGPL). Duas paredes extrudadas: geometria
# suficiente para o iterador tesselar e o glTF sair com mais de uma malha.
# ---------------------------------------------------------------------------
_IFC = """ISO-10303-21;
HEADER;
FILE_DESCRIPTION(('ViewDefinition [CoordinationView]'),'2;1');
FILE_NAME('','2026-08-01T00:00:00',(''),(''),'SGI PRA.8','SGI PRA.8','');
FILE_SCHEMA(('IFC4'));
ENDSEC;
DATA;
#1=IFCSIUNIT(*,.LENGTHUNIT.,$,.METRE.);
#2=IFCUNITASSIGNMENT((#1));
#3=IFCCARTESIANPOINT((0.,0.,0.));
#4=IFCAXIS2PLACEMENT3D(#3,$,$);
#5=IFCGEOMETRICREPRESENTATIONCONTEXT($,'Model',3,1.0000000000000001E-05,#4,$);
#6=IFCPROJECT('0Vni_c9DPEle3LrnD1LJdM',$,'Amostra Prancheta',$,$,$,$,(#5),#2);
#7=IFCRECTANGLEPROFILEDEF(.AREA.,$,$,8.,0.20000000000000001);
#8=IFCCARTESIANPOINT((4.,0.,0.));
#9=IFCAXIS2PLACEMENT3D(#8,$,$);
#10=IFCDIRECTION((0.,0.,1.));
#11=IFCEXTRUDEDAREASOLID(#7,#9,#10,2.7999999999999998);
#12=IFCSHAPEREPRESENTATION(#5,'Body','SweptSolid',(#11));
#13=IFCLOCALPLACEMENT($,#4);
#14=IFCPRODUCTDEFINITIONSHAPE($,$,(#12));
#15=IFCWALL('1cnGyWWsv4FujpK2gJ3Zjc',$,'Parede frontal',$,$,#13,#14,$,$);
#16=IFCRECTANGLEPROFILEDEF(.AREA.,$,$,8.,0.20000000000000001);
#17=IFCCARTESIANPOINT((4.,5.,0.));
#18=IFCAXIS2PLACEMENT3D(#17,$,$);
#19=IFCDIRECTION((0.,0.,1.));
#20=IFCEXTRUDEDAREASOLID(#16,#18,#19,2.7999999999999998);
#21=IFCSHAPEREPRESENTATION(#5,'Body','SweptSolid',(#20));
#22=IFCLOCALPLACEMENT($,#4);
#23=IFCPRODUCTDEFINITIONSHAPE($,$,(#21));
#24=IFCWALL('2XzAjtY89BIu_uiQ7O80j9',$,'Parede dos fundos',$,$,#22,#23,$,$);
ENDSEC;
END-ISO-10303-21;
"""


# ---------------------------------------------------------------------------
# DWG — AC1015 (R2000), 19.988 bytes, zlib + base64. O único que não dá para
# escrever à mão (ver o topo do arquivo).
# ---------------------------------------------------------------------------
_DWG_B64 = (
    "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"
    "2vNJ9H7bQ/yS7H8BVDI4PA=="
)

# `bytes` prontos, resolvidos uma vez na importação.
PDF = _pdf()
DXF = _dxf()
IFC = _IFC.encode("ascii")
DWG = zlib.decompress(base64.b64decode(_DWG_B64))

#: `(código do formato, nome do arquivo, bytes, tipo de derivada esperado)`.
#: O 4º item é o contrato que o E2E cobra do pipeline — e é diferente por
#: família: PDF só ganha miniatura (o browser abre o original), DXF e DWG viram
#: o mesmo `vetor_2d` por caírem no mesmo motor de renderização, e o IFC vira
#: `modelo_3d`.
AMOSTRAS = [
    ("pdf", "prancha-amostra.pdf", PDF, "miniatura"),
    ("dxf", "planta-amostra.dxf", DXF, "vetor_2d"),
    ("dwg", "planta-amostra.dwg", DWG, "vetor_2d"),
    ("ifc", "modelo-amostra.ifc", IFC, "modelo_3d"),
]

#: RVT **reconhecível**, e só isso — de propósito fora das `AMOSTRAS`.
#:
#: As quatro acima existem para converter; esta existe para ser **recusada pelo
#: plano** (402). Não é um Revit de verdade e não precisa ser: nenhum motor a
#: abre, porque a parede comercial responde antes — o `aps` só chega na PRA.4.
#:
#: O que ela precisa ter, depois da PRA.5a que fechou o
#: [D75](../../docs/historico-correcoes.md), é **o cabeçalho OLE2 verdadeiro**. Antes o
#: nome decidia o formato, e `b"nao importa o conteudo"` chegava ao 402; agora a
#: porta lê os bytes, aquilo seria texto, e a resposta certa passou a ser 400
#: (formato desconhecido). Um arquivo que se diz RVT e não é não merece parede
#: comercial — merece recusa, e é essa a diferença que o E2E precisa provar.
RVT_RECONHECIVEL = b"\xd0\xcf\x11\xe0\xa1\xb1\x1a\xe1" + b"0" * 1024


if __name__ == "__main__":  # bancada: escrever as quatro em disco para inspeção
    import sys

    destino = sys.argv[1] if len(sys.argv) > 1 else "."
    for codigo, nome, dados, _tipo in AMOSTRAS:
        with open(f"{destino}/{nome}", "wb") as saida:
            saida.write(dados)
        print(f"{codigo:5} {nome:24} {len(dados):>8} bytes")
