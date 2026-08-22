# backend/funcoesimpexp/entrada.py
"""PRA.5a — a admissão de UM arquivo. O espelho de `entrega.py`.

**Por que existe um caminho de arquivo único ao lado do lote** (decisão do dono,
08/08/2026, depois de olhar como as plataformas grandes fazem): o Procore para e
pede confirmação quando *ele* adivinhou algo — ao subir prancha ele roda OCR para
inferir número, título e disciplina, e por isso "as pranchas precisam ser
confirmadas e revisadas". Box, Google Drive e Dropbox não param nunca: o que eles
fatiam é arquivo **grande**, e o "commit" é técnico, não humano.

A régua que sai daí, e que este arquivo materializa:

- **o lote confere** — a pasta do projetista chega e nós adivinhamos obra e
  disciplina do caminho (`TorreA/ARQ/p.dwg`). Palpite nosso, decisão de gente: a
  R1 vale, nada entra no acervo antes do sim, e a R6 desfaz;
- **o avulso grava** — a pessoa escolheu o documento, digitou a revisão e apontou
  o arquivo. Não há palpite nosso para confirmar, e uma tela de conferência de
  um item só seria cerimônia.

**O que NÃO muda entre os dois é a porta.** Os dois passam por aqui, e aqui é o
único lugar do sistema que decide se um arquivo entra: assinatura de bytes
(allowlist da plataforma), o que o destino aceita, o que o plano vende, o teto de
tamanho e — quando entrar — o antivírus do [D74](../../docs/modulos/funcoesimpexp.md).
Era isso que estava repartido: cada módulo com o seu `uploads.py`, e a Prancheta
decidindo o formato pelo **nome** ([D75](../../docs/historico-correcoes.md)).
"""
from __future__ import annotations

import hashlib
from dataclasses import dataclass

from .limites import limites_do_plano, validar_entrada
from .registro import Recurso

#: Quanto do arquivo basta ler para decidir o formato. Igual ao do motor: a
#: assinatura mora nos primeiros bytes, e recusar cedo é o que evita trazer 300 MB
#: para a memória por um arquivo que não vai entrar.
AMOSTRA = 4096

#: Tamanho do bloco de leitura do hash. Em blocos porque o arquivo já está em
#: disco temporário quando passa de `FILE_UPLOAD_MAX_MEMORY_SIZE`, e um `.read()`
#: inteiro traria de volta para a memória exatamente o que o Django tirou dela.
BLOCO = 1024 * 1024


@dataclass(frozen=True)
class ArquivoAdmitido:
    """O que se sabe de um arquivo depois de ele passar na porta."""

    formato: str
    hash: str
    tamanho: int
    nome: str


def admitir(arquivo, *, recurso: Recurso, user) -> ArquivoAdmitido:
    """Deixa este arquivo entrar, ou levanta. É a porta, e não há outra.

    Levanta o que `limites` levanta, e quem chama traduz:
    `ArquivoGrandeDemais` e `FormatoNaoContratado` → **402** (parede comercial,
    tem o que comprar); `FormatoDesconhecido` → **400** (não é limite de plano, é
    arquivo que a plataforma não sabe o que é — chamar isso de "faça upgrade"
    mandaria o cliente pagar por algo que nenhum plano abre).

    A ordem é a do motor e é a economia: tamanho absoluto primeiro (o único que
    se sabe sem olhar um byte), formato depois (sobre a amostra), plano por
    último (negar por plano exige antes saber QUAL formato é).
    """
    posicao = arquivo.tell() if hasattr(arquivo, "tell") else 0
    arquivo.seek(0)
    amostra = arquivo.read(AMOSTRA)
    arquivo.seek(0)

    formato = validar_entrada(
        tamanho=getattr(arquivo, "size", None) or 0,
        nome=getattr(arquivo, "name", "") or "",
        conteudo=amostra,
        limites=limites_do_plano(user),
        recurso=recurso,
        user=user,
    )

    # O hash só depois de o arquivo ser aceito: ler 300 MB inteiros para calcular
    # um SHA que ninguém vai usar é o custo que a recusa precoce existe para não
    # pagar. É a mesma ordem do caminho de lote.
    digest = hashlib.sha256()
    tamanho = 0
    for bloco in iter(lambda: arquivo.read(BLOCO), b""):
        digest.update(bloco)
        tamanho += len(bloco)
    # Restaura a posição para o `save()` do FileField não gravar vazio.
    arquivo.seek(posicao)

    return ArquivoAdmitido(
        formato=formato.codigo,
        hash=digest.hexdigest(),
        tamanho=tamanho,
        nome=(getattr(arquivo, "name", "") or "")[:255],
    )
